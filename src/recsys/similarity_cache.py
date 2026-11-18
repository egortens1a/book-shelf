"""Exact block-wise adjusted cosine for offline experiments with many users.

The gRPC service can keep calculating individual rows lazily. No model changes
or approximate neighbors are introduced by this acceleration.
"""

import hashlib
import logging
import os
from pathlib import Path
import tempfile

import numpy as np

logger = logging.getLogger(__name__)


def precompute(catalog, cache_dir: str, block_size: int) -> None:
    if block_size < 1:
        raise ValueError("block_size must be positive")
    n = len(catalog.books)
    if not n:
        return
    digest = hashlib.sha256()
    digest.update(b"adjusted-cosine-v1\0")
    digest.update(repr(([b.book_id for b in catalog.books], catalog.min_common, catalog.min_ratings, catalog.shrinkage)).encode())
    for matrix in (catalog.centered, catalog.observed):
        for values in (matrix.data, matrix.indices, matrix.indptr):
            digest.update(memoryview(values))
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest.hexdigest() + ".npy")
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".npy", delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            matrix = np.lib.format.open_memmap(temp_path, mode="w+", dtype=np.float32, shape=(n, n))
            for start in range(0, n, block_size):
                stop = min(start + block_size, n)
                matrix[start:stop] = catalog._similarity_block(start, stop)
                if start == 0 or stop == n or start // block_size % 16 == 0:
                    logger.info("CF similarity cache: %s/%s books", stop, n)
            matrix.flush()
            del matrix
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)
    cached = np.load(target, mmap_mode="r", allow_pickle=False)
    if cached.shape != (n, n) or cached.dtype != np.float32:
        raise ValueError("Invalid similarity cache")
    catalog._similarity_matrix = cached
