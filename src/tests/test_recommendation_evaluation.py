import pandas as pd
import pytest

from ml.datasets import load_amazon, prepare_catalog, temporal_split
from ml.metrics import ranking_metrics
from ml.run_eval import evaluate
from recsys.domain import Book, Rating
from recsys.engine import HybridRecommender


def test_ranking_metrics_account_for_missing_predictions():
    metrics = ranking_metrics([1], {1, 2})
    assert metrics["recall@10"] == 0.5
    assert metrics["ndcg@10"] == pytest.approx(1 / (1 + 1 / 1.584962500721156))


def test_future_rerating_does_not_remove_training_history():
    data = pd.DataFrame({"User_id": ["u"] * 20, "Id": ["same"] * 20,
                         "review/time": list(range(1, 21)), "score": list(range(1, 21))})
    train, val, test = temporal_split(data)
    assert train.iloc[0].score == 16
    assert val.iloc[0].score == 18
    assert test.iloc[0].score == 20
    assert train["review/time"].max() < val["review/time"].min()


def test_local_amazon_loader_preserves_utf8_and_book_identity(tmp_path):
    root = tmp_path / "AmazonBooks"
    root.mkdir()
    pd.DataFrame({"Id": ["edition-1", "edition-2"], "Title": ["Космос", "Космос"],
                  "User_id": ["u", "v"], "review/score": [5, 4], "review/time": [100, 200]}).to_csv(
                      root / "Books_rating.csv", index=False, encoding="utf-8")
    pd.DataFrame({"Title": ["Космос"], "description": ["Путешествие к звёздам"],
                  "categories": ["['Фантастика']"]}).to_csv(root / "books_data.csv", index=False, encoding="utf-8")
    data = load_amazon(tmp_path)
    books, identities, train = prepare_catalog(tmp_path, data)
    assert len(books) == 2  # одинаковое название не склеивает разные издания
    assert set(identities) == {"edition-1", "edition-2"}
    assert all(b.title == "Космос" and b.description == "Путешествие к звёздам" for b in books)
    assert all(b.genres == ("фантастика",) for b in books)
    assert data.score.tolist() == [10, 8]


def test_amazon_evaluation_accepts_explicit_catalog_and_keeps_cohorts():
    import numpy as np

    class Encoder:
        def encode(self, texts):
            return np.ones((len(texts), 2), dtype=np.float32)

    model = HybridRecommender(Encoder())
    catalog = model.prepare([Book(1, "Seen"), Book(2, "Target")], [Rating(1, 1, 10)])
    holdout = pd.DataFrame({"User_id": ["warm", "cold"], "Id": ["target", "target"], "score": [8, 10]})
    for cohort, users, cold in [("all", 2, 1), ("warm", 1, 0), ("cold", 1, 1)]:
        result = evaluate(model, catalog, holdout, {"target": 2}, {"warm": 1, "cold": 2}, cohort=cohort)
        assert result["users"] == users
        assert result["cold_users"] == cold
        assert result["recall@10"] == 1
