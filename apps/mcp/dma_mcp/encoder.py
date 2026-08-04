"""The bundled 384-dim encoder (V4's only model use — local,
deterministic, at submit; the serving path never touches it).

Mirrors apps/worker/dma_worker/embed.py::minilm_encoder — the two
services build from separate contexts, and the wrapper is small enough
that a shared package would cost more than this mirror note. The model
NAME must stay identical on both sides: a mixed-model index returns
plausible nonsense (TRD §18).
"""
from __future__ import annotations

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def minilm_encoder(model_dir: str | None = None):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_dir or MODEL_NAME, device="cpu")

    class _Encoder:
        name = MODEL_NAME

        def encode(self, texts):
            return model.encode(texts, normalize_embeddings=True,
                                show_progress_bar=False).tolist()

    return _Encoder()
