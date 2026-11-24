"""Amazon Books из data/: подготовка после EDA, без скачивания датасетов."""

import ast
from pathlib import Path

import pandas as pd

from recsys.engine import Book, Rating


def load_amazon(root: Path, max_rows: int | None = None) -> pd.DataFrame:
    columns = ["Id", "Title", "User_id", "review/score", "review/time"]
    chunks = pd.read_csv(
        root / "AmazonBooks/Books_rating.csv", usecols=columns, encoding="utf-8",
        dtype={"Id": "string", "Title": "string", "User_id": "string", "review/score": "float32"},
        chunksize=100_000, nrows=max_rows,
    )
    cleaned = []
    for frame in chunks:
        frame = frame.dropna(subset=columns).copy()
        frame = frame[frame["review/score"].between(1, 5) & frame["review/time"].gt(0)].copy()
        frame["score"] = frame["review/score"] * 2
        cleaned.append(frame)
    data = pd.concat(cleaned, ignore_index=True)
    if data.empty:
        raise ValueError("No valid Amazon ratings")
    for column in ("Id", "Title", "User_id"):
        data[column] = data[column].astype("category")
    return data.sort_values("review/time", kind="stable").reset_index(drop=True)


def temporal_split(data: pd.DataFrame):
    boundaries = data["review/time"].quantile([0.8, 0.9]).tolist()
    train = data[data["review/time"] <= boundaries[0]].copy()
    val = data[data["review/time"].between(boundaries[0], boundaries[1], inclusive="right")].copy()
    test = data[data["review/time"] > boundaries[1]].copy()
    # Повторную оценку заменяем только внутри периода: будущая не удаляет прошлую.
    return tuple(part.drop_duplicates(["User_id", "Id"], keep="last") for part in (train, val, test))


def _list(value) -> tuple[str, ...]:
    if pd.isna(value):
        return ()
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        parsed = [value]
    if not isinstance(parsed, list):
        parsed = [str(parsed)]
    return tuple(str(v).strip().lower() for v in parsed if str(v).strip())


def prepare_catalog(root: Path, train: pd.DataFrame, max_books: int = 1500):
    counts = train["Id"].value_counts()
    selected = counts.head(max_books).index
    train = train[train["Id"].isin(selected)].copy()
    identities = train.drop_duplicates("Id", keep="first")[["Id", "Title"]].copy()
    identities["key"] = identities["Title"].str.lower().str.strip()
    metadata = pd.read_csv(root / "AmazonBooks/books_data.csv", encoding="utf-8", usecols=["Title", "description", "categories"])
    metadata["key"] = metadata["Title"].str.lower().str.strip()
    # Название - только ключ присоединения метаданных; разные Id не объединяем.
    metadata = metadata.dropna(subset=["key"]).drop_duplicates("key", keep="first")
    joined = identities.merge(metadata.drop(columns="Title"), on="key", how="left", validate="many_to_one")
    book_ids = {external: i + 1 for i, external in enumerate(sorted(joined["Id"]))}
    books = [Book(book_ids[r.Id], r.Title, "" if pd.isna(r.description) else r.description, _list(r.categories)) for r in joined.itertuples()]
    return books, book_ids, train


def encode_ratings(data: pd.DataFrame, book_ids: dict, user_ids: dict) -> list[Rating]:
    return [Rating(user_ids[r.User_id], book_ids[r.Id], r.score) for r in data.itertuples() if r.Id in book_ids]
