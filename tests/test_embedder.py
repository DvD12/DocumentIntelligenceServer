import math

from app.ingestion.embedder import FakeEmbedder, OpenAIEmbedder


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def test_fake_is_deterministic():
    e = FakeEmbedder()
    assert e.embed(["hello world"]) == e.embed(["hello world"])


def test_fake_similarity_orders_by_shared_words():
    e = FakeEmbedder()
    q, close, far = e.embed([
        "transfer caps for tier-2 clients",
        "tier-2 clients have transfer caps of 10k",
        "vacation policy accrual rules",
    ])
    assert _cos(q, close) > _cos(q, far)


class _StubClient:
    class _Item:
        def __init__(self, vec):
            self.embedding = vec

    class _Resp:
        def __init__(self, n):
            self.data = [_StubClient._Item([0.0]) for _ in range(n)]

    def __init__(self):
        self.calls: list[int] = []
        self.embeddings = self

    def create(self, model: str, input: list[str]):
        self.calls.append(len(input))
        return _StubClient._Resp(len(input))


def test_openai_embedder_batches():
    stub = _StubClient()
    e = OpenAIEmbedder(api_key="x", model="m", dim=1, batch_size=2, client=stub)
    out = e.embed(["a", "b", "c", "d", "e"])
    assert stub.calls == [2, 2, 1]
    assert len(out) == 5
