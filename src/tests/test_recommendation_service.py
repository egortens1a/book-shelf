from unittest.mock import AsyncMock

import pytest

from app.core.errors import RecommendationsUnavailable
from app.services.recommendation_service import RecommendationService
from recsys.proto import recommendations_pb2 as pb


@pytest.mark.parametrize("items", [
    [(999, 0.5)], [(1, 0.5)], [(2, 0.5)], [(3, 0.5)], [(4, float("nan"))],
    [(4, 1.1)], [(4, 0.5), (4, 0.5)],
])
async def test_invalid_rpc_results_are_rejected(snapshot, items):
    service = RecommendationService(None, AsyncMock())
    service.repo.load = AsyncMock(return_value=snapshot)
    service.client.recommend.return_value = pb.RecommendationResponse(
        items=[pb.Recommendation(book_id=bid, score=score) for bid, score in items])
    with pytest.raises(RecommendationsUnavailable):
        await service.recommend(1)
