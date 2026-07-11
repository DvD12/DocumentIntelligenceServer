import hashlib
import math
from typing import Protocol

from openai import OpenAI


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Batched OpenAI embeddings. Retries/backoff handled by the SDK itself."""

    def __init__(
        self, api_key: str, model: str, dim: int, batch_size: int = 128, client=None
    ) -> None:
        self._client = client or OpenAI(api_key=api_key)
        self.model = model
        self.dim = dim
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in resp.data)
        return vectors


class FakeEmbedder:
    """Deterministic word-hash embeddings for tests: shared words => similar vectors."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            h = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
