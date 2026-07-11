import pytest
from qdrant_client import QdrantClient

from app.core.errors import ParseError
from app.ingestion.embedder import FakeEmbedder
from app.ingestion.pipeline import IngestionPipeline
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore


@pytest.fixture()
def env(tmp_path):
    repo = MetadataRepo(str(tmp_path / "meta.db"))
    store = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    pipeline = IngestionPipeline(repo, store, FakeEmbedder(dim=64), 450, 0.15)
    return repo, store, pipeline


DOC_V1 = b"# Policy\nTier-2 transfer caps are 10k per day."
DOC_V2 = b"# Policy\nTier-2 transfer caps are 20k per day, effective July."


def test_new_document_created(env):
    repo, store, pipeline = env
    result = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    assert result.outcome == "created"
    assert result.document.chunk_count == len(store.all_chunks(result.document.id))
    assert result.document.tags == ["compliance"]


def test_rule1_same_hash_is_noop_with_tag_merge(env):
    repo, store, pipeline = env
    first = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    again = pipeline.ingest("policy-renamed.md", DOC_V1, ["hr"])
    assert again.outcome == "unchanged"
    assert again.document.id == first.document.id
    assert again.document.filename == "policy-renamed.md"
    assert sorted(again.document.tags) == ["compliance", "hr"]
    assert len(store.all_chunks(first.document.id)) == first.document.chunk_count


def test_rule2_same_name_new_hash_replaces(env):
    repo, store, pipeline = env
    first = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    second = pipeline.ingest("policy.md", DOC_V2, [])
    assert second.outcome == "updated"
    assert second.document.id == first.document.id
    assert second.document.content_hash != first.document.content_hash
    texts = " ".join(p.payload["text"] for p in store.all_chunks(first.document.id))
    assert "20k" in texts and "10k" not in texts


def test_rule3_distinct_files_coexist(env):
    repo, store, pipeline = env
    a = pipeline.ingest("a.md", DOC_V1, [])
    b = pipeline.ingest("b.md", DOC_V2, [])
    assert a.document.id != b.document.id
    assert repo.count_documents() == 2


def test_oversized_upload_rejected(env):
    _, _, pipeline = env
    with pytest.raises(ParseError, match="20MB"):
        pipeline.ingest("big.txt", b"x" * (20 * 1024 * 1024 + 1), [])


def test_failed_upsert_leaves_no_metadata(env, monkeypatch):
    repo, store, pipeline = env
    monkeypatch.setattr(store, "upsert_chunks", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        pipeline.ingest("policy.md", DOC_V1, [])
    assert repo.count_documents() == 0


def test_delete_removes_points_and_row(env):
    repo, store, pipeline = env
    result = pipeline.ingest("policy.md", DOC_V1, [])
    assert pipeline.delete(result.document.id) is True
    assert repo.get(result.document.id) is None
    assert store.all_chunks(result.document.id) == []
