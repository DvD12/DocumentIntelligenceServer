from app.core.config import Settings, get_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.embed_model == "text-embedding-3-small"
    assert s.embed_dim == 1536
    assert s.chunk_tokens == 450
    assert s.chunk_overlap == 0.15
    assert s.qdrant_url == "http://localhost:6333"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHUNK_TOKENS", "300")
    monkeypatch.setenv("MCP_API_KEY", "sekrit")
    get_settings.cache_clear()
    s = get_settings()
    assert s.chunk_tokens == 300
    assert s.mcp_api_key == "sekrit"
    get_settings.cache_clear()
