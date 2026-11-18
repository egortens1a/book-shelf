"""Paired ranking evaluation on a fixed sample, with bootstrap uncertainty."""

import logging

import numpy as np
import pandas as pd

from ml.metrics import ranking_metrics
from recsys.domain import UserProfile

logger = logging.getLogger(__name__)


def evaluate_suite(model, catalog, holdout: pd.DataFrame, configurations: dict, *, max_users=1000, seed=42):
    """All configurations see the same users, relevant items and full catalog.

    configurations maps a label to (mode, cf_weight). The CF weight is changed
    only for this offline calculation and restored afterwards.
    """
    catalog_ids = {b.book_id for b in catalog.books if b.published}
    relevant = {}
    for row in holdout.itertuples(index=False):
        if row.score >= 8 and row.book_id in catalog_ids and row.book_id not in catalog.user_ratings.get(row.user_id, {}):
            relevant.setdefault(int(row.user_id), set()).add(int(row.book_id))
    users = np.array(sorted(relevant), dtype=np.int32)
    eligible = len(users)
    if not eligible:
        raise ValueError("No users with relevant holdout books")
    if max_users and len(users) > max_users:
        users = np.sort(np.random.default_rng(seed).choice(users, size=max_users, replace=False))
    rows, recommended = [], {name: set() for name in configurations}
    initial_weight = model.cf_weight
    try:
        for i, user_id in enumerate(users):
            for name, (mode, weight) in configurations.items():
                if weight is not None:
                    model.cf_weight = weight
                if mode == "random":
                    seen = catalog.user_ratings.get(user_id, {})
                    candidates = sorted(catalog_ids - set(seen))
                    rng = np.random.default_rng(np.random.SeedSequence([seed, int(user_id)]))
                    predicted = rng.choice(candidates, size=min(10, len(candidates)), replace=False).tolist()
                else:
                    result = model.rank(catalog, UserProfile(int(user_id)), mode=mode)
                    predicted = [item.book_id for item in result]
                metrics = ranking_metrics(predicted, relevant[user_id])
                rows.append({"model": name, "user_id": int(user_id), **metrics,
                             "hit_rate@10": float(bool(set(predicted) & relevant[user_id])),
                             "history": len(catalog.user_ratings.get(user_id, {})), "relevant": len(relevant[user_id])})
                recommended[name].update(predicted)
            if (i + 1) % 100 == 0:
                logger.info("Evaluation: %s/%s users", i + 1, len(users))
    finally:
        model.cf_weight = initial_weight
    details = pd.DataFrame(rows)
    summary = []
    bootstrap = np.random.default_rng(seed).integers(0, len(users), size=(500, len(users)))
    for name in configurations:
        data = details[details.model.eq(name)].sort_values("user_id")
        result = {"model": name, "users": len(users), "eligible_users": eligible,
                  "cold_users": int(data.history.eq(0).sum()), "coverage@10": len(recommended[name]) / len(catalog_ids)}
        for metric in ("recall@10", "ndcg@10", "hit_rate@10"):
            values = data[metric].to_numpy()
            samples = values[bootstrap].mean(axis=1)
            result[metric] = float(values.mean())
            result[metric + "_low"] = float(np.quantile(samples, 0.025))
            result[metric + "_high"] = float(np.quantile(samples, 0.975))
        summary.append(result)
    return pd.DataFrame(summary), details


def paired_difference(details: pd.DataFrame, left: str, right: str, metric="ndcg@10", seed=42):
    table = details.pivot(index="user_id", columns="model", values=metric)
    differences = (table[left] - table[right]).to_numpy()
    indices = np.random.default_rng(seed).integers(0, len(differences), size=(500, len(differences)))
    estimates = differences[indices].mean(axis=1)
    return {"comparison": f"{left} - {right}", "metric": metric, "delta": float(differences.mean()),
            "low": float(np.quantile(estimates, 0.025)), "high": float(np.quantile(estimates, 0.975))}
