import numpy as np
import pytest

from recsys.domain import UserProfile
from recsys.engine import Book, HybridRecommender, Rating, percentile_scores


class ToyEncoder:
    """Фиксированная геометрия для проверки ранжирования, без модели и сети."""

    def encode(self, texts):
        return np.array([[1, 0] if "space" in t.lower() else [0, 1] for t in texts], dtype=np.float32)


def test_content_excludes_rated_finished_and_unpublished_and_returns_ten():
    books = [Book(i, f"space {i}", published=i != 3) for i in range(1, 16)]
    ratings = [Rating(1, 1, 10)]
    model = HybridRecommender(ToyEncoder())
    result = model.recommend(books, UserProfile(1, excluded_book_ids=(2,)), ratings)
    assert len(result) == 10
    assert not {1, 2, 3} & {r.book_id for r in result}
    assert all(r.score == pytest.approx(1) for r in result)


def test_genre_interests_and_new_book_without_ratings():
    books = [Book(1, "cooking"), Book(2, "space")]
    ratings = []
    model = HybridRecommender(ToyEncoder())
    result = model.recommend(books, UserProfile(99, interests=("space",)), ratings)
    assert result[0].book_id == 2
    assert result[0].score == pytest.approx(1)


def test_adjusted_cosine_uses_only_common_readers_in_denominator():
    # u1/u2: среднее = 6. Книги 1/2 имеют одинаковые остатки 2,-2.
    # u3 оценивает только книгу 1 и контрольную книгу; не должен менять cosine(1,2).
    ratings = [Rating(1, 1, 8), Rating(1, 2, 8), Rating(1, 3, 2),
               Rating(2, 1, 4), Rating(2, 2, 4), Rating(2, 3, 10),
               Rating(3, 1, 10), Rating(3, 3, 2)]
    books = [Book(i, str(i)) for i in range(1, 4)]
    model = HybridRecommender(ToyEncoder(), min_ratings=2, shrinkage=0)
    catalog = model.prepare(books, ratings)
    assert catalog.item_similarities(1)[1] == pytest.approx(1)
    assert catalog.item_similarities(2)[0] == pytest.approx(1)
    assert catalog.item_similarities(1)[2] == pytest.approx(-32 / np.sqrt(24 * 48))


def test_no_coraters_means_pure_content_even_with_many_candidate_ratings():
    books = [Book(1, "space seed"), Book(2, "space candidate"), Book(3, "cooking")]
    ratings = [Rating(1, 1, 10)] + [Rating(u, 2, 10) for u in range(2, 30)]
    model = HybridRecommender(ToyEncoder(), cf_weight=1)
    assert model.recommend(books, UserProfile(1), ratings)[0].score == pytest.approx(1)


def test_zero_variance_is_finite_and_empty_catalog_is_allowed():
    books = [Book(1, "a"), Book(2, "b")]
    ratings = [Rating(1, 1, 8), Rating(1, 2, 8)]
    model = HybridRecommender(ToyEncoder())
    catalog = model.prepare(books, ratings)
    assert np.isfinite(catalog.item_similarities(1)).all()
    assert model.rank(catalog, UserProfile(1)) == []
    assert HybridRecommender(ToyEncoder()).recommend([], UserProfile(1), []) == []


def test_cold_start_popularity_and_ties_are_deterministic():
    books = [Book(3, "a"), Book(2, "b"), Book(1, "c")]
    ratings = []
    model = HybridRecommender(ToyEncoder())
    assert [r.book_id for r in model.recommend(books, UserProfile(99), ratings)] == [1, 2, 3]


def test_negative_rating_lowers_cf_score_for_similar_candidate():
    books = [Book(i, str(i)) for i in range(1, 5)]
    ratings = [Rating(1, 1, 1), Rating(1, 4, 10)]
    for u in range(2, 6):
        ratings += [Rating(u, 1, 9), Rating(u, 2, 9), Rating(u, 3, 1)]
    model = HybridRecommender(ToyEncoder())
    result = model.recommend(books, UserProfile(1), ratings, mode="cf")
    assert next(r.score for r in result if r.book_id == 2) == 0


def test_cf_weight_depends_on_candidate_support():
    books = [Book(1, "space"), Book(2, "cooking"), Book(3, "other")]
    ratings = [Rating(1, 1, 10)]
    for uid in (2, 3, 4):
        ratings += [Rating(uid, 1, 9), Rating(uid, 2, 9), Rating(uid, 3, 1)]
    model = HybridRecommender(ToyEncoder(), cf_weight=0.25)
    candidate = next(r for r in model.recommend(books, UserProfile(1), ratings) if r.book_id == 2)
    assert candidate.score == pytest.approx(0.25 * 3 / 13)
    raw = next(r for r in model.recommend(books, UserProfile(1), ratings, mode="hybrid_raw") if r.book_id == 2)
    assert raw.score == pytest.approx(0.25 * (3 / 13) ** 2)


def test_single_seed_preserves_similarity_strength(monkeypatch):
    books = [Book(i, str(i)) for i in (1, 2, 3)]
    ratings = [Rating(1, 1, 10)]
    model = HybridRecommender(ToyEncoder())
    catalog = model.prepare(books, ratings)
    monkeypatch.setattr(catalog, "item_similarities", lambda _: np.array([0, 0.1, 0.8], dtype=np.float32))
    scores = {r.book_id: r.score for r in model.rank(catalog, UserProfile(1), mode="cf")}
    assert scores[2] == pytest.approx(0.1)
    assert scores[3] == pytest.approx(0.8)


def test_popularity_counts_interactions_and_quality_is_a_separate_baseline():
    books = [Book(1, "a"), Book(2, "b")]
    ratings = [Rating(1, 1, 10), Rating(2, 2, 8), Rating(3, 2, 8), Rating(4, 2, 8)]
    model = HybridRecommender(ToyEncoder())
    assert model.recommend(books, UserProfile(99), ratings, mode="popularity")[0].book_id == 2
    assert model.recommend(books, UserProfile(99), ratings, mode="bayesian")[0].book_id == 1


def test_disk_similarity_cache_preserves_lazy_ranking(tmp_path):
    books = [Book(i, str(i)) for i in (1, 2, 3)]
    ratings = [Rating(1, 1, 10), Rating(2, 1, 9), Rating(2, 2, 9), Rating(2, 3, 1),
               Rating(3, 1, 8), Rating(3, 2, 8), Rating(3, 3, 2)]
    model = HybridRecommender(ToyEncoder(), min_ratings=2)
    catalog = model.prepare(books, ratings)
    expected = [catalog.item_similarities(i).copy() for i in (1, 2, 3)]
    before = model.rank(catalog, UserProfile(1))
    catalog.precompute_similarities(str(tmp_path), block_size=2)
    for bid, row in zip((1, 2, 3), expected):
        np.testing.assert_allclose(catalog.item_similarities(bid), row)
    assert model.rank(catalog, UserProfile(1)) == before
    assert len(list(tmp_path.glob("*.npy"))) == 1


def test_percentile_calibration_uses_candidates_preserves_ties_and_zero_signal():
    scores = percentile_scores(np.array([100, 0, 0.1, 0.8, 0.8]), [1, 2, 3, 4])
    np.testing.assert_allclose(scores, [0, 0, 0.5, 1, 1])
    np.testing.assert_allclose(percentile_scores(np.zeros(3), [0, 1, 2]), np.zeros(3))


def test_fusion_is_invariant_to_positive_rescaling_of_one_signal(monkeypatch):
    books = [Book(i, str(i)) for i in (1, 2, 3)]
    ratings = [Rating(1, 1, 10), Rating(2, 2, 9), Rating(3, 3, 9)]
    model = HybridRecommender(ToyEncoder())
    monkeypatch.setattr(model, "_components", lambda *args: (True, np.array([0, .8, .6]),
                                                            np.array([0, .01, .02]), np.ones(3)))
    first = model.recommend(books, UserProfile(1), ratings)
    monkeypatch.setattr(model, "_components", lambda *args: (True, np.array([0, .8, .6]),
                                                            np.array([0, .1, .2]), np.ones(3)))
    assert model.recommend(books, UserProfile(1), ratings) == first


def test_configured_recommender_does_not_encode_until_called_and_accepts_new_inputs():
    class CountingEncoder(ToyEncoder):
        def __init__(self):
            self.calls = 0

        def encode(self, texts):
            self.calls += 1
            return super().encode(texts)

    encoder = CountingEncoder()
    model = HybridRecommender(encoder)
    assert encoder.calls == 0
    books = [Book(1, "space"), Book(2, "cooking")]
    first = model.recommend(books, UserProfile(1), [Rating(1, 1, 10)])
    second = model.recommend(books, UserProfile(1), [Rating(1, 2, 10)])
    third = model.recommend([Book(10, "cooking"), Book(11, "space")], UserProfile(1), [])
    assert [item.book_id for item in first] == [2]
    assert [item.book_id for item in second] == [1]
    assert [item.book_id for item in third] == [10, 11]
    assert encoder.calls == 3


def test_prepared_ranking_matches_direct_recommendation():
    books = [Book(i, f"space {i}") for i in range(1, 6)]
    ratings = [Rating(1, 1, 10), Rating(2, 2, 8)]
    user = UserProfile(1, interests=("space",), excluded_book_ids=(3,))
    model = HybridRecommender(ToyEncoder())
    catalog = model.prepare(books, ratings)
    assert model.rank(catalog, user) == model.recommend(books, user, iter(ratings))
