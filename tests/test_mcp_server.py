import contextlib
import json

import httpx
from qdrant_client import QdrantClient
from starlette.applications import Starlette
from starlette.routing import Mount

from app.ingestion.embedder import FakeEmbedder
from app.ingestion.pipeline import IngestionPipeline
from app.mcp_server.auth import BearerAuthMiddleware
from app.mcp_server.server import build_mcp
from app.retrieval.service import SearchService
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore

TOKEN = "test-token"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@contextlib.asynccontextmanager
async def make_client(tmp_path):
    """Whole stack in one task: pytest-asyncio finalizes fixtures in a different
    task, which violates anyio cancel-scope rules for session_manager.run()."""
    repo = MetadataRepo(str(tmp_path / "meta.db"))
    store = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    emb = FakeEmbedder(dim=64)
    pipeline = IngestionPipeline(repo, store, emb, 450, 0.15)
    pipeline.ingest(
        "aml-policy.md",
        b"# AML Policy\nTier-2 transfer caps are 10k per day.",
        ["compliance"],
    )
    mcp = build_mcp(SearchService(repo, store, emb), repo, json_response=True)
    # Inner app serves /mcp itself; mount at root to avoid slash-redirects.
    app = Starlette(
        routes=[Mount("/", app=BearerAuthMiddleware(mcp.streamable_http_app(), TOKEN))]
    )
    async with mcp.session_manager.run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


def _tool_payload(response: httpx.Response) -> dict:
    """FastMCP returns dict tool results as JSON text in content[0]."""
    result = response.json()["result"]
    assert result.get("isError") is not True, result
    return json.loads(result["content"][0]["text"])


async def test_missing_token_is_401(tmp_path):
    async with make_client(tmp_path) as client:
        r = await client.post(
            "/mcp", json=_rpc("tools/list"),
            headers={k: v for k, v in HEADERS.items() if k != "Authorization"},
        )
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"


async def test_wrong_token_is_401(tmp_path):
    async with make_client(tmp_path) as client:
        r = await client.post(
            "/mcp", json=_rpc("tools/list"),
            headers={**HEADERS, "Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401


async def test_tools_list_names(tmp_path):
    async with make_client(tmp_path) as client:
        r = await client.post("/mcp", json=_rpc("tools/list"), headers=HEADERS)
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert names == {
            "list_documents", "list_tags", "search", "search_by_tag",
            "search_by_document", "get_document_outline", "expand_chunk",
        }


async def test_search_tool_call(tmp_path):
    async with make_client(tmp_path) as client:
        r = await client.post("/mcp", json=_rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "tier-2 transfer caps"}},
        ), headers=HEADERS)
        assert r.status_code == 200
        payload = _tool_payload(r)
        assert payload["results"][0]["document"]["filename"] == "aml-policy.md"
        assert payload["results"][0]["location"]["heading_path"] == ["AML Policy"]


async def test_unknown_tag_returns_guidance_not_exception(tmp_path):
    async with make_client(tmp_path) as client:
        r = await client.post("/mcp", json=_rpc(
            "tools/call",
            {"name": "search_by_tag", "arguments": {"query": "x", "tags": ["complaince"]}},
        ), headers=HEADERS)
        assert r.status_code == 200
        payload = _tool_payload(r)
        assert payload["error"] == "unknown_tags"
        assert "compliance" in payload["message"]
