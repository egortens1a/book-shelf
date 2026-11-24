import numpy as np
import pandas as pd
import pytest

from ml.goodbooks import load_goodbooks, split_by_user
from ml.goodbooks_eval import evaluate_suite, paired_difference
from recsys.engine import Book, HybridRecommender, Rating


def test_enrichment_joins_by_goodreads_id_without_title_matching(tmp_path):
    pd.DataFrame({"user_id": [1, 2], "book_id": [1, 2], "rating": [5, 4]}).to_csv(tmp_path / "ratings.csv", index=False)
    pd.DataFrame({"book_id": [1, 2], "goodreads_book_id": [900, 700], "title": ["Same", "Same"]}).to_csv(
        tmp_path / "books.csv", index=False)
    pd.DataFrame({"goodreads_book_id": [700, 900], "description": ["Second", "First"],
                  "genres": ["['History']", "['Science']"]}).to_csv(tmp_path / "books_enriched.csv", index=False)
    books, ratings, summary = load_goodbooks(tmp_path)
    assert [(b.book_id, b.description, b.genres) for b in books] == [(1, "First", ("science",)), (2, "Second", ("history",))]
    assert ratings.score.tolist() == [10, 8]
    assert summary["ratings"] == 2


def test_per_user_split_preserves_every_rating_and_has_no_overlap():
    data = pd.DataFrame({"user_id": np.repeat([1, 2, 3], 20), "book_id": np.arange(60) + 1, "score": 8})
    parts = split_by_user(data)
    assert [len(p) for p in parts] == [48, 6, 6]
    assert all(set(p.user_id) == {1, 2, 3} for p in parts)
    identities = [set(zip(p.user_id, p.book_id)) for p in parts]
    assert not identities[0] & identities[1] and not identities[0] & identities[2] and not identities[1] & identities[2]
    assert set.union(*identities) == set(zip(data.user_id, data.book_id))
    for first, second in zip(parts, split_by_user(data)):
        pd.testing.assert_frame_equal(first, second)


def test_split_rejects_history_too_short_for_validation_and_test():
    with pytest.raises(ValueError):
        split_by_user(pd.DataFrame({"user_id": [1, 1], "book_id": [1, 2], "score": [8, 10]}))


def test_evaluation_pairs_users_reports_intervals_and_restores_weight():
    class Encoder:
        def encode(self, texts):
            return np.ones((len(texts), 2), dtype=np.float32)

    model = HybridRecommender(Encoder(), cf_weight=0.25)
    catalog = model.prepare([Book(i, str(i)) for i in range(1, 14)],
                            [Rating(1, 1, 10), Rating(2, 2, 8)])
    holdout = pd.DataFrame({"user_id": [1, 1, 2], "book_id": [1, 3, 4], "score": [10, 8, 10]})
    configs = {"content": ("content", None), "hybrid": ("hybrid", 0.9), "random": ("random", None)}
    results, details = evaluate_suite(model, catalog, holdout, configs, max_users=2)
    assert model.cf_weight == 0.25
    assert results.users.eq(2).all()
    assert results.cold_users.eq(0).all()
    assert details.groupby("model").user_id.apply(set).tolist() == [{1, 2}] * 3
    assert details.relevant.eq(1).all()  # the already-rated item is not ground truth
    assert results["recall@10_low"].le(results["recall@10_high"]).all()
    difference = paired_difference(details, "content", "hybrid")
    assert difference["delta"] == 0
    assert difference["low"] == 0 and difference["high"] == 0


def test_enrichment_rejects_unknown_book_in_ratings(tmp_path):
    pd.DataFrame({"user_id": [1], "book_id": [99], "rating": [5]}).to_csv(tmp_path / "ratings.csv", index=False)
    pd.DataFrame({"book_id": [1], "goodreads_book_id": [900], "title": ["a"]}).to_csv(tmp_path / "books.csv", index=False)
    pd.DataFrame({"goodreads_book_id": [900], "description": ["text"], "genres": ["[]"]}).to_csv(
        tmp_path / "books_enriched.csv", index=False)
    with pytest.raises(ValueError, match="unknown book"):
        load_goodbooks(tmp_path)
