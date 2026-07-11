import pytest
from qdrant_client import QdrantClient

from app.core.errors import UnknownDocumentsError, UnknownTagsError
from app.ingestion.embedder import FakeEmbedder
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.service import SearchService
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore

AML = b"# AML Policy\nTier-2 transfer caps are 10k per day.\n\n# Appendix\nContact compliance desk."
HR = b"# HR Handbook\nVacation accrual is 2 days per month."


@pytest.fixture()
def env(tmp_path):
    repo = MetadataRepo(str(tmp_path / "meta.db"))
    store = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    emb = FakeEmbedder(dim=64)
    pipeline = IngestionPipeline(repo, store, emb, 450, 0.15)
    pipeline.ingest("aml-policy.md", AML, ["compliance"])
    pipeline.ingest("hr-handbook.md", HR, ["hr"])
    return SearchService(repo, store, emb)


def test_search_envelope_shape(env):
    out = env.search("what are the tier-2 transfer caps")
    assert out["documents_searched"] == 2
    top = out["results"][0]
    assert top["rank"] == 1
    assert top["document"]["filename"] == "aml-policy.md"
    assert top["document"]["tags"] == ["compliance"]
    assert top["location"]["heading_path"] == ["AML Policy"]
    assert top["location"]["pages"] is None


def test_search_by_tag_scopes(env):
    out = env.search("transfer caps accrual", tags=["hr"])
    assert out["documents_searched"] == 1
    assert all(r["document"]["filename"] == "hr-handbook.md" for r in out["results"])


def test_unknown_tag_error_has_guidance(env):
    with pytest.raises(UnknownTagsError) as exc:
        env.search("anything", tags=["complaince"])
    msg = exc.value.message
    assert "complaince" in msg and "compliance" in msg and "hr" in msg


def test_search_by_document_accepts_filename(env):
    out = env.search("transfer caps", documents=["aml-policy.md"])
    assert all(r["document"]["filename"] == "aml-policy.md" for r in out["results"])


def test_unknown_document_error_has_guidance(env):
    with pytest.raises(UnknownDocumentsError) as exc:
        env.search("x", documents=["aml_policy.md"])
    assert "aml-policy.md" in exc.value.message


def test_outline_groups_by_heading(env):
    out = env.outline("aml-policy.md")
    assert out["document"]["filename"] == "aml-policy.md"
    headings = [o["heading"] for o in out["outline"]]
    assert headings == ["AML Policy", "Appendix"]
    assert all(o["chunk_count"] >= 1 for o in out["outline"])


def test_expand_returns_neighbors(env):
    doc_id = env.outline("aml-policy.md")["document"]["id"]
    out = env.expand(doc_id, 1, before=1, after=1)
    indices = [c["chunk_index"] for c in out["chunks"]]
    assert indices == [0, 1]  # doc has 2 chunks; index 2 doesn't exist


def test_expand_unknown_document(env):
    with pytest.raises(UnknownDocumentsError):
        env.expand("no-such-id", 0)
