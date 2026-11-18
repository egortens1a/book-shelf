"""Отдельный процесс gRPC: python -m recsys.server."""

from concurrent.futures import ThreadPoolExecutor
import logging
import signal
import time

import grpc

from recsys.embeddings import FastEmbedEncoder
from recsys.config import ServerSettings
from recsys.domain import Book, Rating, UserProfile
from recsys.engine import Encoder, HybridRecommender
from recsys.proto import recommendations_pb2 as pb
from recsys.proto import recommendations_pb2_grpc as rpc
from recsys.transport import GRPC_OPTIONS

logger = logging.getLogger(__name__)


class RecommendationServicer(rpc.RecommendationServiceServicer):
    def __init__(self, encoder: Encoder, cf_weight: float = 0.25):
        self.recommender = HybridRecommender(encoder, cf_weight=cf_weight)

    def Check(self, request, context):
        return pb.HealthResponse(ready=True)

    def Recommend(self, request, context):
        started = time.monotonic()
        try:
            if request.user_id <= 0 or not 1 <= request.limit <= 100:
                raise ValueError("user_id must be positive; limit must be between 1 and 100")
            ids = {b.book_id for b in request.books}
            if any(b.book_id <= 0 or not b.title.strip() for b in request.books):
                raise ValueError("Books must have positive ids and nonempty titles")
            if any(r.user_id <= 0 or r.book_id not in ids for r in request.ratings):
                raise ValueError("Ratings must reference books in the snapshot and positive user ids")
            if not context.is_active():
                return pb.RecommendationResponse()
            items = self.recommender.recommend(
                books=[Book(b.book_id, b.title, b.description, tuple(b.genres), b.published) for b in request.books],
                user=UserProfile(request.user_id, tuple(request.interests), tuple(request.excluded_book_ids)),
                ratings=(Rating(r.user_id, r.book_id, r.score) for r in request.ratings),
                limit=request.limit,
            )
            logger.info("gRPC Recommend user_id=%s books=%s ratings=%s returned=%s elapsed=%.3fs",
                        request.user_id, len(request.books), len(request.ratings), len(items), time.monotonic() - started)
            return pb.RecommendationResponse(items=[pb.Recommendation(book_id=r.book_id, score=r.score) for r in items])
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception:
            logger.exception("Recommendation computation failed")
            context.abort(grpc.StatusCode.INTERNAL, "Recommendation computation failed")


def create_server(encoder: Encoder, address: str, cf_weight: float = 0.25):
    server = grpc.server(ThreadPoolExecutor(max_workers=1), options=GRPC_OPTIONS)
    rpc.add_RecommendationServiceServicer_to_server(RecommendationServicer(encoder, cf_weight), server)
    port = server.add_insecure_port(address)
    if not port:
        raise RuntimeError(f"Cannot bind gRPC server to {address}")
    return server, port


def main():
    settings = ServerSettings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [pid=%(process)d] %(name)s: %(message)s")
    encoder = FastEmbedEncoder(settings.cache_dir, model_name=settings.model)
    server, _ = create_server(encoder, f"{settings.host}:{settings.port}", settings.cf_weight)

    def stop(signum, frame):
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, stop)
    server.start()
    logger.info("Recommendation gRPC service listening on %s:%s", settings.host, settings.port)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop(grace=5).wait()


if __name__ == "__main__":
    main()
