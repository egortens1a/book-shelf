"""Асинхронный gRPC-клиент API. ML-библиотеки здесь не импортируются."""

import logging

import grpc

from app.core.errors import RecommendationsUnavailable
from recsys.proto import recommendations_pb2 as pb
from recsys.proto import recommendations_pb2_grpc as rpc
from recsys.transport import GRPC_OPTIONS, MAX_MESSAGE_BYTES

logger = logging.getLogger(__name__)


class RecommendationClient:
    def __init__(self, target: str, timeout: float = 30.0):
        self.target = target
        self.timeout = timeout

    async def recommend(self, request: pb.RecommendationRequest) -> pb.RecommendationResponse:
        if request.ByteSize() > MAX_MESSAGE_BYTES:
            raise RecommendationsUnavailable("Recommendation catalog exceeds the RPC message limit")
        try:
            async with grpc.aio.insecure_channel(self.target, options=GRPC_OPTIONS) as channel:
                logger.info("HTTP -> gRPC Recommend target=%s user_id=%s", self.target, request.user_id)
                response = await rpc.RecommendationServiceStub(channel).Recommend(request, timeout=self.timeout)
                logger.info("gRPC -> HTTP returned=%s user_id=%s", len(response.items), request.user_id)
                return response
        except grpc.aio.AioRpcError as exc:
            logger.warning("Recommendation RPC failed: %s", exc.code().name)
            raise RecommendationsUnavailable("Recommendation service is temporarily unavailable") from exc
