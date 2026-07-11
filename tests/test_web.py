import io

import httpx
import pytest
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.ingestion.embedder import FakeEmbedder
from app.main import create_app

AUTH = ("admin", "pw")


@pytest.fixture()
async def client(tmp_path):
    settings = Settings(
        _env_file=None, ui_password="pw", mcp_api_key="tok",
        db_path=str(tmp_path / "meta.db"), embed_dim=64,
    )
    app = create_app(
        settings=settings,
        embedder=FakeEmbedder(dim=64),
        qdrant_client=QdrantClient(":memory:"),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _upload(name: str = "a.md", content: bytes = b"# T\nBody text.", tags: str = "hr"):
    return {"file": (name, io.BytesIO(content), "text/markdown")}, {"tags": tags}


async def test_api_requires_basic_auth(client):
    r = await client.get("/api/documents")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")


async def test_healthz_is_public(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_upload_list_delete_roundtrip(client):
    files, data = _upload()
    r = await client.post("/api/documents", files=files, data=data, auth=AUTH)
    assert r.status_code == 201
    doc = r.json()["document"]
    assert doc["tags"] == ["hr"] and doc["chunk_count"] >= 1

    r = await client.get("/api/documents", auth=AUTH)
    assert [d["filename"] for d in r.json()["documents"]] == ["a.md"]

    r = await client.get("/api/tags", auth=AUTH)
    assert r.json()["tags"] == [{"name": "hr", "document_count": 1}]

    r = await client.delete(f"/api/documents/{doc['id']}", auth=AUTH)
    assert r.status_code == 204
    r = await client.get("/api/documents", auth=AUTH)
    assert r.json()["documents"] == []


async def test_duplicate_upload_reports_unchanged(client):
    files, data = _upload()
    await client.post("/api/documents", files=files, data=data, auth=AUTH)
    files, data = _upload()
    r = await client.post("/api/documents", files=files, data=data, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["outcome"] == "unchanged"


async def test_invalid_file_is_400_with_message(client):
    files = {"file": ("x.xlsx", io.BytesIO(b"nope"), "application/octet-stream")}
    r = await client.post("/api/documents", files=files, data={"tags": ""}, auth=AUTH)
    assert r.status_code == 400
    assert "Unsupported" in r.json()["message"]


async def test_delete_unknown_is_404(client):
    r = await client.delete("/api/documents/ghost", auth=AUTH)
    assert r.status_code == 404


async def test_index_page_renders(client):
    r = await client.get("/", auth=AUTH)
    assert r.status_code == 200
    assert "Upload" in r.text
