"""Configured recommender with explicit catalog and user inputs for each call."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np
from scipy.sparse import csr_matrix

from recsys.domain import Book, Rating, Recommendation, UserProfile


class Encoder(Protocol):
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


def normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12)


def percentile_scores(values: np.ndarray, candidates: list[int]) -> np.ndarray:
    """Put two different score scales on candidate percentile ranks; zeros stay zero."""
    selected = np.asarray(values)[candidates]
    _, inverse, counts = np.unique(selected, return_inverse=True, return_counts=True)
    ranked = np.cumsum(counts)[inverse] / len(selected)
    ranked[selected <= 0] = 0
    result = np.zeros(len(values), dtype=np.float64)
    result[candidates] = ranked
    return result


@dataclass
class PreparedCatalog:
    """Explicit input data for offline ranking; not retained by the recommender."""

    books: list[Book]
    index: dict[int, int]
    vectors: np.ndarray
    user_ratings: dict[int, dict[int, float]]
    centered: csr_matrix
    observed: csr_matrix
    squared: csr_matrix
    counts: np.ndarray
    bayesian_rating: np.ndarray
    popularity: np.ndarray
    min_common: int
    min_ratings: int
    shrinkage: float
    _similarity_matrix: np.ndarray | None = None

    def _similarity_block(self, start: int, stop: int) -> np.ndarray:
        """The same adjusted cosine for one seed or a bounded offline batch."""
        dot = (self.centered[start:stop] @ self.centered.T).toarray()
        left = (self.squared[start:stop] @ self.observed.T).toarray()
        right = (self.observed[start:stop] @ self.squared.T).toarray()
        common = (self.observed[start:stop] @ self.observed.T).toarray()
        denom = np.sqrt(left * right)
        valid = (common >= self.min_common) & (self.counts[None, :] >= self.min_ratings) & (denom > 1e-12)
        sim = np.zeros_like(dot, dtype=np.float32)
        sim[valid] = dot[valid] / denom[valid] * common[valid] / (common[valid] + self.shrinkage)
        sim[np.arange(stop - start), np.arange(start, stop)] = 0
        return np.clip(sim, -1, 1)

    def precompute_similarities(self, cache_dir: str, block_size: int = 64) -> None:
        """Offline acceleration; identical similarities, stored on disk in blocks."""
        from recsys.similarity_cache import precompute

        precompute(self, cache_dir, block_size)

    def item_similarities(self, book_id: int) -> np.ndarray:
        """Знаменатель adjusted cosine вычисляется только по общим читателям."""
        if self._similarity_matrix is not None:
            return self._similarity_matrix[self.index[book_id]]
        i = self.index[book_id]
        return self._similarity_block(i, i + 1)[0]


class HybridRecommender:
    """Store the encoder and settings; accept recommendation data per call."""

    def __init__(
        self, encoder: Encoder, *, cf_weight: float = 0.25, min_common: int = 2,
        min_ratings: int = 3, shrinkage: float = 10.0, positive_threshold: float = 8.0,
    ):
        if not 0 <= cf_weight <= 1:
            raise ValueError("cf_weight must be between 0 and 1")
        if min_common < 1 or min_ratings < 1 or shrinkage < 0:
            raise ValueError("Invalid CF support parameters")
        self.encoder = encoder
        self.cf_weight = cf_weight
        self.min_common = min_common
        self.min_ratings = min_ratings
        self.shrinkage = shrinkage
        self.positive_threshold = positive_threshold

    def recommend(
        self, books: Sequence[Book], user: UserProfile, ratings: Iterable[Rating],
        *, limit: int = 10, mode: str = "hybrid",
    ) -> list[Recommendation]:
        """Rank the supplied books for a user without retaining request data."""
        catalog = self.prepare(books, ratings)
        return self.rank(catalog, user, limit=limit, mode=mode)

    def prepare(self, books: Sequence[Book], ratings: Iterable[Rating]) -> PreparedCatalog:
        """Build explicit vectors/statistics, reusable across offline comparisons."""
        books = list(books)
        index = {b.book_id: i for i, b in enumerate(books)}
        if len(index) != len(books):
            raise ValueError("Duplicate book_id")
        vectors = normalize(self.encoder.encode([b.text for b in books])) if books else np.empty((0, 0))
        user_ratings: dict[int, dict[int, float]] = {}
        for r in ratings:
            if not np.isfinite(r.score) or not 1 <= r.score <= 10:
                raise ValueError("Rating must be finite and between 1 and 10")
            if r.book_id in index:
                user = user_ratings.setdefault(r.user_id, {})
                if r.book_id in user:
                    raise ValueError("Duplicate user-book rating")
                # Reuse catalog integer objects across millions of user profiles.
                book_id = books[index[r.book_id]].book_id
                user[book_id] = r.score
        size = sum(len(user) for user in user_ratings.values())
        rows = np.empty(size, dtype=np.int32)
        cols = np.empty(size, dtype=np.int32)
        raw = np.empty(size, dtype=np.float32)
        centered = np.empty(size, dtype=np.float32)
        k = 0
        for col, user in enumerate(user_ratings.values()):
            mean = sum(user.values()) / len(user)
            for book_id, score in user.items():
                rows[k] = index[book_id]
                cols[k] = col
                raw[k] = score
                centered[k] = score - mean
                k += 1
        shape = (len(books), len(user_ratings))
        centered = csr_matrix((centered, (rows, cols)), shape=shape, dtype=np.float32)
        # Маска независима от centered: оценка, равная среднему, тоже наблюдалась.
        observed = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=shape, dtype=np.float32)
        squared = centered.multiply(centered).tocsr()
        counts = np.asarray(observed.sum(axis=1)).ravel()
        totals = np.bincount(rows, weights=raw, minlength=len(books))
        prior = float(np.mean(raw, dtype=np.float64)) if size else 5.5
        bayesian_rating = (totals + 10 * prior) / (counts + 10) / 10
        popularity = counts / max(float(counts.max(initial=0)), 1)
        return PreparedCatalog(
            books=books, index=index, vectors=vectors, user_ratings=user_ratings,
            centered=centered, observed=observed, squared=squared, counts=counts,
            bayesian_rating=bayesian_rating, popularity=popularity,
            min_common=self.min_common, min_ratings=self.min_ratings, shrinkage=self.shrinkage,
        )

    def _components(self, catalog: PreparedCatalog, user: UserProfile, need_cf: bool):
        user_id, interests = user.user_id, user.interests
        history = catalog.user_ratings.get(user_id, {})
        profile = np.zeros(catalog.vectors.shape[1], dtype=np.float32)
        for book_id, score in history.items():
            if score >= self.positive_threshold:
                profile += catalog.vectors[catalog.index[book_id]] * (score - 5) / 5
        if interests:
            profile += normalize(self.encoder.encode(["Genres: " + ", ".join(sorted(set(interests)))]))[0]
        has_profile = np.linalg.norm(profile) > 1e-12
        content = np.clip(catalog.vectors @ normalize(profile), 0, 1) if has_profile else np.zeros(len(catalog.books))
        numerator = np.zeros(len(catalog.books))
        denominator = np.zeros(len(catalog.books))
        preference_mass = 0.0
        if need_cf:
            for book_id, score in history.items():
                # Положительное сходство + низкая оценка понижает рекомендацию.
                sim = np.maximum(catalog.item_similarities(book_id), 0)
                preference = (score - 5.5) / 4.5
                numerator += sim * preference
                denominator += sim
                preference_mass += abs(preference)
        # Normalize by the profile, not by similarity: a weak neighbor must stay weak.
        cf = np.clip(numerator / max(1.0, preference_mass), 0, 1)
        return has_profile, content, cf, denominator

    def rank(
        self, catalog: PreparedCatalog, user: UserProfile, *, limit: int = 10, mode: str = "hybrid",
    ) -> list[Recommendation]:
        """Rank explicit prepared data; used for full-catalog offline evaluation."""
        user_id, excluded = user.user_id, user.excluded_book_ids
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if mode not in {"hybrid", "hybrid_raw", "content", "cf", "popularity", "bayesian"}:
            raise ValueError("Unknown recommendation mode")
        if not catalog.books:
            return []
        history = catalog.user_ratings.get(user_id, {})
        excluded_ids = set(excluded) | set(history)
        candidates = [i for i, b in enumerate(catalog.books) if b.published and b.book_id not in excluded_ids]
        if not candidates:
            return []
        if mode in {"popularity", "bayesian"}:
            scores = catalog.popularity if mode == "popularity" else catalog.bayesian_rating
            ordered = sorted(candidates, key=lambda i: (-float(scores[i]), catalog.books[i].book_id))
            return [Recommendation(catalog.books[i].book_id, catalog.books[i].title, float(scores[i])) for i in ordered[:limit]]
        has_profile, content, cf, denominator = self._components(catalog, user, mode in {"cf", "hybrid", "hybrid_raw"})
        weight = self.cf_weight * catalog.counts / (catalog.counts + 10)
        weight[denominator == 0] = 0
        if not has_profile and not np.any(denominator):
            scores = catalog.popularity
        elif mode == "content":
            scores = content if has_profile else catalog.popularity
        elif mode == "cf":
            scores = cf
        else:
            if mode == "hybrid":
                content = percentile_scores(content, candidates)
                cf = percentile_scores(cf, candidates)
            scores = (1 - weight) * content + weight * cf
        ordered = sorted(candidates, key=lambda i: (-float(scores[i]), -float(catalog.popularity[i]), catalog.books[i].book_id))
        return [Recommendation(catalog.books[i].book_id, catalog.books[i].title, float(scores[i])) for i in ordered[:limit]]

