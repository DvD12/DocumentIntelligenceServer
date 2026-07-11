import pytest

from app.stores.metadata_repo import MetadataRepo


@pytest.fixture()
def repo(tmp_path):
    return MetadataRepo(str(tmp_path / "meta.db"))


def make(repo, filename="a.pdf", content_hash="h1", tags=("compliance",)):
    return repo.create_document(
        id=f"id-{content_hash}", filename=filename, content_hash=content_hash,
        media_type="pdf", size_bytes=10, chunk_count=3, tags=list(tags),
    )


def test_create_and_lookups(repo):
    doc = make(repo)
    assert repo.get(doc.id).filename == "a.pdf"
    assert repo.get_by_hash("h1").id == doc.id
    assert repo.get_by_filename("a.pdf").id == doc.id
    assert repo.get_by_hash("nope") is None
    assert repo.count_documents() == 1


def test_tags_normalized_and_counted(repo):
    make(repo, "a.pdf", "h1", ["Compliance", " HR "])
    make(repo, "b.pdf", "h2", ["compliance"])
    assert repo.list_tags() == [("compliance", 2), ("hr", 1)]


def test_merge_tags_is_additive_and_idempotent(repo):
    doc = make(repo, tags=["compliance"])
    repo.merge_tags(doc.id, ["hr", "compliance"])
    assert sorted(repo.get(doc.id).tags) == ["compliance", "hr"]


def test_ids_for_tags_any_all_unknown(repo):
    d1 = make(repo, "a.pdf", "h1", ["compliance", "hr"])
    d2 = make(repo, "b.pdf", "h2", ["compliance"])
    ids, unknown = repo.ids_for_tags(["compliance"], "any")
    assert set(ids) == {d1.id, d2.id} and unknown == []
    ids, _ = repo.ids_for_tags(["compliance", "hr"], "all")
    assert ids == [d1.id]
    _, unknown = repo.ids_for_tags(["complaince"], "any")
    assert unknown == ["complaince"]


def test_resolve_documents_by_id_and_name(repo):
    doc = make(repo)
    metas, unknown = repo.resolve_documents([doc.id, "A.PDF", "ghost.pdf"])
    assert [m.id for m in metas] == [doc.id, doc.id]
    assert unknown == ["ghost.pdf"]


def test_replace_content_and_delete(repo):
    doc = make(repo)
    repo.replace_content(doc.id, filename="a.pdf", content_hash="h9",
                         size_bytes=20, chunk_count=5, tags=["product"])
    updated = repo.get(doc.id)
    assert updated.content_hash == "h9" and updated.chunk_count == 5
    assert "product" in updated.tags and "compliance" in updated.tags
    assert repo.delete(doc.id) is True
    assert repo.get(doc.id) is None
    assert repo.list_tags() == []  # cascade removed junction rows; orphan tags pruned
