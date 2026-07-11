import pytest
from qdrant_client import QdrantClient

from app.core.models import Chunk
from app.ingestion.embedder import FakeEmbedder
from app.stores.qdrant_store import QdrantStore, point_id


@pytest.fixture()
def store() -> QdrantStore:
    s = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    s.ensure_collection()
    return s


EMB = FakeEmbedder(dim=64)


def _chunk(doc_id: str, idx: int, text: str) -> Chunk:
    return Chunk(
        document_id=doc_id, chunk_index=idx, text=text,
        prefixed_text=f"doc.md — {text}", heading_path=[], token_count=5,
    )


def _ingest(store: QdrantStore, doc_id: str, texts: list[str]) -> None:
    chunks = [_chunk(doc_id, i, t) for i, t in enumerate(texts)]
    store.upsert_chunks(chunks, EMB.embed([c.prefixed_text for c in chunks]))


def test_point_id_deterministic():
    assert point_id("d1", 0) == point_id("d1", 0)
    assert point_id("d1", 0) != point_id("d1", 1)


def test_search_finds_relevant_chunk(store):
    _ingest(store, "d1", ["transfer caps for tier-2 clients are 10k"])
    _ingest(store, "d2", ["vacation accrual is 2 days per month"])
    query = "what are the transfer caps for tier-2 clients"
    hits = store.hybrid_search(query, EMB.embed([query])[0], limit=1)
    assert hits[0].payload["document_id"] == "d1"


def test_document_filter_scopes_search(store):
    _ingest(store, "d1", ["transfer caps for tier-2 clients"])
    _ingest(store, "d2", ["transfer caps for tier-3 partners"])
    query = "transfer caps"
    hits = store.hybrid_search(query, EMB.embed([query])[0], limit=5, document_ids=["d2"])
    assert {h.payload["document_id"] for h in hits} == {"d2"}


def test_upsert_is_idempotent(store):
    _ingest(store, "d1", ["alpha text", "beta text"])
    _ingest(store, "d1", ["alpha text", "beta text"])
    assert len(store.all_chunks("d1")) == 2


def test_delete_document_removes_all_points(store):
    _ingest(store, "d1", ["alpha", "beta"])
    store.delete_document("d1")
    assert store.all_chunks("d1") == []


def test_get_chunks_by_indices_sorted(store):
    _ingest(store, "d1", ["zero", "one", "two"])
    recs = store.get_chunks("d1", [2, 0])
    assert [r.payload["chunk_index"] for r in recs] == [0, 2]
