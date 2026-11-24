import numpy as np

from recsys.embeddings import FastEmbedEncoder


def test_encoder_recalculates_vectors_without_saving_them(tmp_path, monkeypatch):
    calls = []

    class Model:
        def __init__(self, **kwargs):
            pass

        def embed(self, texts, batch_size):
            calls.extend(texts)
            return iter(np.array([len(t), 1], dtype=np.float32) for t in texts)

    monkeypatch.setattr("fastembed.TextEmbedding", Model)
    encoder = FastEmbedEncoder(str(tmp_path))
    first = encoder.encode(["space", "space"])
    second = encoder.encode(["space", "space"])
    np.testing.assert_array_equal(first, [[5, 1], [5, 1]])
    np.testing.assert_array_equal(first, second)
    assert calls == ["space", "space", "space", "space"]
    assert encoder.encode([]).shape == (0, 384)
    assert list(tmp_path.iterdir()) == []
