"""Offline-оценка с исключением уже известных книг из ground truth."""

import numpy as np

from ml.metrics import ranking_metrics
from recsys.domain import UserProfile


def evaluate(model, catalog, holdout, book_ids, user_ids, *, known=None, max_users=150, mode="hybrid", cohort="all"):
    if cohort not in {"all", "warm", "cold"}:
        raise ValueError("Unknown user cohort")
    relevant = {}
    for row in holdout.itertuples():
        if row.Id not in book_ids or row.score < 8:
            continue
        uid, bid = user_ids[row.User_id], book_ids[row.Id]
        seen = set(catalog.user_ratings.get(uid, {})) | set((known or {}).get(uid, ()))
        if bid not in seen:
            relevant.setdefault(uid, set()).add(bid)
    # Детерминированная выборка, не первые пользователи с самым длинным профилем.
    users = sorted(uid for uid in relevant if cohort == "all" or
                   (uid in catalog.user_ratings) == (cohort == "warm"))
    eligible = len(users)
    rng = np.random.default_rng(42)
    if max_users and len(users) > max_users:
        users = sorted(rng.choice(users, size=max_users, replace=False).tolist())
    if not users:
        return {"recall@10": float("nan"), "ndcg@10": float("nan"),
                "coverage@10": 0.0, "users": 0, "eligible_users": 0, "cold_users": 0,
                "holdout_catalog_fraction": float(holdout["Id"].isin(book_ids).mean())}
    metrics, recommended = [], set()
    for uid in users:
        predictions = model.rank(catalog, UserProfile(uid, excluded_book_ids=tuple((known or {}).get(uid, ()))), mode=mode)
        ids = [p.book_id for p in predictions]
        recommended.update(ids)
        metrics.append(ranking_metrics(ids, relevant[uid]))
    return {
        **{key: float(np.mean([m[key] for m in metrics])) for key in metrics[0]},
        "coverage@10": len(recommended) / len(catalog.books),
        "users": len(users),
        "eligible_users": eligible,
        "cold_users": sum(uid not in catalog.user_ratings for uid in users),
        "holdout_catalog_fraction": float(holdout["Id"].isin(book_ids).mean()),
    }
