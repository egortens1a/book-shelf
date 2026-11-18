"""Ranking-метрики по полному каталогу кандидатов, без sampled negatives."""

import math


def ranking_metrics(predicted: list[int], relevant: set[int], k: int = 10) -> dict[str, float]:
    if not relevant:
        raise ValueError("Relevant set must be nonempty")
    hits = [int(book_id in relevant) for book_id in predicted[:k]]
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {"recall@10": sum(hits) / len(relevant), "ndcg@10": dcg / ideal}
