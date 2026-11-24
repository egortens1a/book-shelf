"""Full Goodbooks + enriched metadata, with explicit identity and split rules."""

import ast
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from recsys.engine import Book, Rating


def load_goodbooks(directory: Path) -> tuple[list[Book], pd.DataFrame, dict]:
    ratings = pd.read_csv(directory / "ratings.csv", dtype={"user_id": "int32", "book_id": "int32", "rating": "int8"})
    base = pd.read_csv(directory / "books.csv", usecols=["book_id", "goodreads_book_id", "title"])
    enriched = pd.read_csv(directory / "books_enriched.csv", usecols=["goodreads_book_id", "description", "genres"])
    if base.book_id.duplicated().any() or base.goodreads_book_id.duplicated().any() or enriched.goodreads_book_id.duplicated().any():
        raise ValueError("Book metadata identifiers must be unique")
    if ratings.isna().any().any() or not ratings.rating.between(1, 5).all():
        raise ValueError("Invalid ratings")
    if not ratings.user_id.gt(0).all() or not ratings.book_id.isin(base.book_id).all():
        raise ValueError("Ratings reference unknown book ids or invalid user ids")
    if ratings.duplicated(["user_id", "book_id"]).any():
        raise ValueError("Duplicate user-book ratings: do not choose a last rating without timestamps")
    # The canonical file's book_id is an internal id; join enrichment via Goodreads id.
    metadata = base.merge(enriched, on="goodreads_book_id", how="left", validate="one_to_one").sort_values("book_id")
    books = []
    for row in metadata.itertuples():
        parsed = [] if pd.isna(row.genres) else ast.literal_eval(row.genres)
        if not isinstance(parsed, list):
            raise ValueError("Genres must be a list")
        books.append(Book(int(row.book_id), row.title, "" if pd.isna(row.description) else row.description,
                          tuple(sorted({str(g).strip().lower() for g in parsed if str(g).strip()}))))
    ratings["score"] = (ratings.rating * 2).astype("int8")
    ratings = ratings.drop(columns="rating")
    histories = ratings.groupby("user_id", sort=False).size()
    summary = {"ratings": len(ratings), "users": len(histories), "books": len(books),
               "history_min": int(histories.min()), "history_median": float(histories.median()),
               "history_mean": float(histories.mean()), "empty_descriptions": sum(not b.description.strip() for b in books),
               "empty_genres": sum(not b.genres for b in books)}
    return books, ratings, summary


def split_by_user(ratings: pd.DataFrame, seed: int = 42):
    """Random 80/10/10 within each user. This is NOT a timestamp split."""
    if ratings.groupby("user_id", sort=False).size().min() < 3:
        raise ValueError("Each user needs at least three ratings")
    rng = np.random.default_rng(seed)
    keys = rng.random(len(ratings), dtype=np.float32)
    order = np.lexsort((keys, ratings.user_id.to_numpy()))
    shuffled = ratings.iloc[order]
    groups = shuffled.groupby("user_id", sort=False)
    position = groups.cumcount().to_numpy()
    counts = groups.user_id.transform("size").to_numpy()
    train_count = np.maximum(1, np.floor(counts * 0.8).astype(np.int32))
    val_count = np.maximum(1, np.floor(counts * 0.1).astype(np.int32))
    train_count = np.minimum(train_count, counts - val_count - 1)
    return tuple(shuffled.loc[mask].reset_index(drop=True) for mask in (
        position < train_count,
        (position >= train_count) & (position < train_count + val_count),
        position >= train_count + val_count,
    ))


def iter_ratings(frame: pd.DataFrame) -> Iterator[Rating]:
    """Avoid materializing six million dataclass instances at once."""
    for row in frame.itertuples(index=False):
        yield Rating(int(row.user_id), int(row.book_id), int(row.score))
