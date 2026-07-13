# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

RAG knowledge base + MCP server (Streamable HTTP) — the practical assignment for indigo.ai's AI Solutions Engineer role. [README.md](README.md) is the authoritative product documentation (architecture, stack rationale, tool design, run instructions). Design spec and task-by-task implementation plan live in `docs/superpowers/`. Read the README before changing anything user-facing.

## Commands

```bash
uv sync                                     # install deps (Python pinned 3.12 via .python-version)
uv run pytest                               # full suite — no API keys, no containers needed
uv run pytest tests/test_chunker.py -v      # one file
uv run pytest tests/test_pipeline.py::test_rule1_same_hash_is_noop_with_tag_merge -v
uv run ruff check .                         # lint (run before every commit)
docker compose up --build                   # full local stack (needs .env, see .env.example)
uv run python scripts/smoke.py [BASE_URL]   # e2e against a running stack (needs UI_PASSWORD, MCP_API_KEY env)
uv run uvicorn app.main:create_app --factory  # dev server without Docker (needs local Qdrant on :6333)
```

App has NO module-level instance — always `create_app()` via `--factory` (module-level construction builds a real OpenAI client and breaks test imports).

## Architecture — the rules that span files

**Adapter boundary:** MCP tools (`app/mcp_server/server.py`) and the web API (`app/web/routes.py`) are thin adapters over shared services (`app/retrieval/service.py`, `app/ingestion/pipeline.py`). Logic never lives in an adapter. Search behavior is tested once, at the service layer.

**Two stores, one truth per fact:** Qdrant payloads hold only immutable-per-version chunk fields (document_id, chunk_index, text, provenance). Mutable metadata (filename, tags) lives only in SQLite (`app/stores/metadata_repo.py`) and is joined into responses at assembly time. Tag-scoped search resolves tags → document_ids in SQLite first, then filters Qdrant by id. Never copy filename/tags into a Qdrant payload.

**Ingestion write ordering is the transaction strategy:** pure computation → Qdrant upsert → SQLite row LAST. On failure after vector writes, the document's points are deleted. Metadata must never reference chunks that don't exist. Dedup follows three rules keyed on SHA-256 (see `pipeline.ingest`); version replacement is delete-first because v2 may produce fewer chunks; deterministic point ids (`uuid5(doc_id:chunk_index)`) are a crash-retry net only.

**Embedded text ≠ displayed text:** vectors are computed from `chunk.prefixed_text` (filename + heading path + body — contextual prefixing); agents read `chunk.text` (raw body). Query and document embeddings must use the same model (`EMBED_MODEL`); changing it requires full re-ingestion.

**MCP mount pattern (non-obvious):** the FastMCP app serves `/mcp` itself and is mounted at root, registered after all FastAPI routes — mounting it under `/mcp` causes 307 slash-redirects. `BearerAuthMiddleware` wraps the mount but only guards paths starting `/mcp`. The host lifespan must run `mcp.session_manager.run()` or the first MCP request fails.

**Tool descriptions are the deliverable** (evaluation priority #1). The docstrings in `app/mcp_server/server.py` and the `INSTRUCTIONS` string are agent-facing contract, deliberately worded (when-to-use, sibling pointers). Don't rephrase casually. Domain errors surface as `{"error": code, "message": guidance}` via `guarded()` — never raw exceptions to agents.

## Pinned/trap dependencies

- `mcp>=1.16,<2` — v2 (`MCPServer`) is beta-only on PyPI; this code uses the v1 `FastMCP` API. Don't bump without migrating.
- BM25 sparse vectors are computed client-side with fastembed (`QdrantStore._sparse`). Passing `models.Document` to a real Qdrant server requests cloud-only server-side inference and fails — but WORKS in `:memory:` local mode, so tests won't catch a regression; the smoke test will.
- Qdrant server image (compose) must stay within one minor of `qdrant-client`.
- Transport DNS-rebinding protection is intentionally disabled (Bearer-authed server-to-server endpoint; Host allowlists break on deploy hostnames).

## Testing strategy

`FakeEmbedder` (deterministic word-hash vectors — shared words = cosine-similar) + `QdrantClient(":memory:")` make the whole suite key-less and container-less. MCP tests speak raw JSON-RPC over the real Streamable HTTP transport (stateless + json_response) and build their stack per-test via a context manager — pytest-asyncio finalizes fixtures in a different task, which violates anyio cancel-scope rules for `session_manager.run()`. FastMCP 1.x returns dict tool results as JSON text in `content[0]`, not `structuredContent`.

## Conventions

- Atomic commits: one per smallest coherent unit of work. `uv run pytest` green + `ruff check` clean before every commit.
- Config only via env / pydantic-settings (`app/core/config.py`); keep `.env.example` in sync with `Settings` fields.
- Deployment: Railway (app container + volume at `/srv/data` for SQLite) + Qdrant Cloud. Push to `main` redeploys.
