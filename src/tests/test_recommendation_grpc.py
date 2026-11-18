import asyncio
from unittest.mock import patch

import grpc
import pytest

from app.core.errors import RecommendationsUnavailable
from app.services.recommendation_client import RecommendationClient
from recsys.engine import HybridRecommender
from recsys.proto import recommendations_pb2 as pb
from recsys.proto import recommendations_pb2_grpc as rpc


def request():
    return pb.RecommendationRequest(
        user_id=1, limit=10, excluded_book_ids=[2],
        books=[pb.Book(book_id=i, title=f"space {i}", published=i != 3) for i in range(1, 16)],
        ratings=[pb.Rating(user_id=1, book_id=1, score=10)],
    )


async def test_real_rpc_returns_ten_and_checks_health(grpc_target):
    response = await RecommendationClient(grpc_target).recommend(request())
    assert len(response.items) == 10
    assert all({field.name for field, _ in item.ListFields()} == {"book_id", "score"}
               for item in response.items)
    assert not {1, 2, 3} & {r.book_id for r in response.items}
    async with grpc.aio.insecure_channel(grpc_target) as channel:
        health = await rpc.RecommendationServiceStub(channel).Check(pb.HealthRequest(), timeout=2)
        assert health.ready


@pytest.mark.parametrize("case", ["limit", "nan", "duplicate_book", "duplicate_rating", "unknown_book"])
async def test_invalid_snapshot_has_explicit_grpc_status(grpc_target, case):
    data = request()
    if case == "limit": data.limit = 0
    if case == "nan": data.ratings[0].score = float("nan")
    if case == "duplicate_book": data.books.add().CopyFrom(data.books[0])
    if case == "duplicate_rating": data.ratings.add().CopyFrom(data.ratings[0])
    if case == "unknown_book": data.ratings[0].book_id = 999
    async with grpc.aio.insecure_channel(grpc_target) as channel:
        with pytest.raises(grpc.aio.AioRpcError) as error:
            await rpc.RecommendationServiceStub(channel).Recommend(data, timeout=2)
        assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_each_rpc_recalculates_from_its_input(grpc_target):
    client = RecommendationClient(grpc_target)
    data = request()
    with patch.object(HybridRecommender, "prepare", autospec=True, side_effect=HybridRecommender.prepare) as prepare:
        first = await client.recommend(data)
        second = await client.recommend(data)
    assert first == second
    assert prepare.call_count == 2
    assert prepare.call_args_list[0].args[0] is prepare.call_args_list[1].args[0]


async def test_catalog_and_ratings_changes_affect_next_request(grpc_target):
    client = RecommendationClient(grpc_target)
    data = request()
    first = await client.recommend(data)
    bid = first.items[0].book_id
    data.books[bid - 1].published = False
    data.ratings.add(user_id=1, book_id=first.items[1].book_id, score=8)
    result = await client.recommend(data)
    assert bid not in {r.book_id for r in result.items}
    assert first.items[1].book_id not in {r.book_id for r in result.items}


async def test_unavailable_server_maps_to_service_error():
    # Свободный порт без сервера: никаких внешних адресов или пользовательских сервисов.
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(RecommendationsUnavailable):
        await RecommendationClient(f"127.0.0.1:{port}", timeout=0.1).recommend(request())


async def test_deadline_is_enforced():
    class SlowService(rpc.RecommendationServiceServicer):
        async def Recommend(self, request, context):
            await asyncio.sleep(2)
            return pb.RecommendationResponse()

    server = grpc.aio.server()
    rpc.add_RecommendationServiceServicer_to_server(SlowService(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        with pytest.raises(RecommendationsUnavailable):
            await RecommendationClient(f"127.0.0.1:{port}", timeout=0.02).recommend(request())
    finally:
        await server.stop(0)
