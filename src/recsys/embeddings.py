"""Применение предобученной текстовой модели без кэширования векторов."""

from typing import Sequence

import numpy as np

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class FastEmbedEncoder:
    def __init__(self, cache_dir: str = ".cache/models", model_name: str = DEFAULT_MODEL, threads: int = 2):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        return np.asarray(list(self.model.embed(list(texts), batch_size=32)), dtype=np.float32)
