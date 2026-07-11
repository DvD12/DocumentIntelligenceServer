# Document Intelligence Server — Design

**Date:** 2026-07-11
**Status:** Approved (pending final user review)
**Context:** Indigo.Ai "AI Solutions Engineer" hiring assignment. RAG ingestion pipeline + management UI + MCP server (Python, Streamable HTTP). ~12h estimated budget, scope extended by choice to include both bonuses (hybrid search, chunk provenance) and live deployment.

## 1. Goals & Scope

Build backend infrastructure that turns an uploaded document corpus into an agent-queryable knowledge base:

1. **Document management UI** — upload (PDF, txt, md), tag at upload, list, delete.
2. **Ingestion pipeline** — parse → chunk → embed → store; idempotent, deduplicated.
3. **MCP server (core deliverable)** — knowledge base exposed as agent-ready tools over Streamable HTTP with Bearer auth.

In scope (bonus): hybrid search (dense + BM25 + RRF fusion), chunk-level provenance (page numbers / heading paths), live deployment.

Out of scope: answer generation (the consuming agent composes answers), UI polish, OAuth, auto-tagging, contextual retrieval (LLM-written chunk context), parent-document retrieval. Last two documented as future work.

## 2. Stack

| Concern | Choice | Rationale |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Assignment requires Python; FastAPI = async, typed, standard |
| MCP | Official `mcp` SDK (FastMCP API), Streamable HTTP transport | Official SDK, required transport, mounts as ASGI sub-app |
| Vector store | Qdrant (container local / Qdrant Cloud free tier prod) | Native dense+sparse hybrid with server-side RRF; payload filtering powers tag/document-scoped search |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, cosine) | Strong/cheap default; key provided |
| Sparse vectors | FastEmbed BM25 model, IDF via Qdrant collection modifier | Local, free, no API dependency |
| Metadata store | SQLite (WAL mode) | Right-sized; write volume trivial; documented Postgres swap-path |
| Frontend | Jinja templates + htmx/vanilla JS, served by FastAPI | One service; review attention stays on RAG/MCP |
| Packaging | Docker + docker-compose (app + qdrant) | Single-command local run (deliverable) |

## 3. Architecture

One FastAPI app (single container) + Qdrant:

```
┌─────────────────────────────────────────────┐
│  app (FastAPI)                              │
│  /            Jinja UI (upload/list/delete) │
│  /api/*       REST for the UI               │
│  /mcp         MCP server (Streamable HTTP,  │
│               Bearer auth)                  │
│  /healthz     store connectivity check      │
│                                             │
│  ingestion    parse → chunk → embed → store │
│  retrieval    hybrid search service         │
│  stores       qdrant client + sqlite repo   │
└──────────────┬──────────────────────────────┘
        ┌──────▼──────┐     SQLite = file on
        │   Qdrant    │     volume in app
        └─────────────┘     container
```

**Boundary rule:** MCP tools and web API are thin adapters over shared `ingestion`/`retrieval` services. Neither adapter owns logic.

Repo layout:

```
/app
  /web          # routers + Jinja templates (UI + /api)
  /mcp_server   # tool definitions, auth middleware ("mcp_server" avoids shadowing SDK pkg)
  /ingestion    # parsers, chunker, embedder, pipeline
  /retrieval    # hybrid search service
  /stores       # qdrant_store.py, metadata_repo.py
  /core         # config (pydantic-settings), models, errors
  main.py
/tests
/docs           # Part 1 answers, this spec
docker-compose.yml
Dockerfile
.env.example
README.md
```

## 4. Ingestion Pipeline

Upload → dedup check → parse → chunk → embed → upsert Qdrant → write SQLite (order is the transaction strategy, see §8).

- **Parsing:** PDF via text-extraction lib with per-page text + heuristic heading detection (font-size/weight signals; imperfect, documented); txt/md via encoding-tolerant read, md headings parsed exactly.
- **Chunking:** structure-aware recursive splitter — split at headings → paragraphs → sentences; target ~450 tokens (config `CHUNK_TOKENS`), ~15% overlap (`CHUNK_OVERLAP`). Empirical defaults, exposed as config, rationale in README.
- **Contextual prefix:** embedded text = `"{filename} > {heading path} — {chunk text}"`. Mitigates chunk-island context loss. Raw chunk text stored separately for display/quoting.
- **Embedding:** batched OpenAI calls, SDK retry/backoff. `Embedder` is an interface (test seam: deterministic fake).
- **Dedup rules** (`content_hash` = SHA-256 of file bytes, UNIQUE):
  1. hash exists → no re-ingest; merge tags, update filename if changed
  2. same filename, new hash → version replacement: delete points by `document_id` filter, re-ingest
  3. otherwise → new document
- **Idempotency net:** point IDs = `uuid5(document_id, chunk_index)` — crash-retry overwrites partial upserts instead of duplicating. All re-ingest paths are delete-first, so ID stability across chunker-config changes is never load-bearing.

## 5. Data Model

**SQLite:**

```
documents:      id (uuid pk), filename, content_hash (UNIQUE), media_type,
                size_bytes, chunk_count, uploaded_at, updated_at
tags:           id, name (UNIQUE, lowercased)
document_tags:  document_id, tag_id
```

**Qdrant** — collection `chunks`, named vectors per point:

- `dense`: 1536, cosine (OpenAI, prefixed text)
- `sparse`: BM25 weights (FastEmbed), collection `modifier: idf`

Payload: `document_id, chunk_index, text` (raw), `heading_path` (list|null), `page_start, page_end` (null for txt/md), `token_count`.

**Consistency rule:** payload holds only immutable-per-version fields. Mutable metadata (filename, tags — dedup rule 1 updates both without re-ingesting) lives solely in SQLite and is joined into results at response-assembly time. Tag-scoped search resolves tags → `document_id`s in SQLite, then filters Qdrant by `document_id`. Avoids stale-payload class of bugs entirely.

## 6. Retrieval (hybrid)

Single Qdrant query: two `prefetch` branches (dense k≈20, sparse k≈20) → `fusion: rrf` server-side → top-k. Tag/document scoping = `document_id` payload filter on the same query (tag/filename resolution happens in SQLite first, per §5 consistency rule). One code path for all three search tools; the filter is the only variable. Result envelope enriched with filename/tags from SQLite.

## 7. MCP Tool Interface (evaluation centerpiece)

Design principles (also README rationale):

1. Descriptions state **when** to use the tool (trigger conditions, pointers to sibling tools), not only what it does.
2. **One result envelope** across all search tools.
3. Bare-minimum call works: only `query` required; sane defaults elsewhere.
4. **Errors are guidance:** unknown tag/document errors list valid values + fuzzy suggestions (stdlib difflib) so the agent self-corrects in one turn.
5. **Read-only surface:** no ingest/delete tools; least privilege (writes = management UI only).

Tools (5 required names fixed by assignment + 2 additions):

| Tool | Params | Returns |
|---|---|---|
| `list_documents` | — | id, filename, tags, uploaded_at, chunk_count per doc |
| `list_tags` | — | tag name + document count |
| `search` | `query` (req), `top_k` (default 8, max 25) | result envelope |
| `search_by_tag` | `query`, `tags` (req, ≥1), `tag_match` ("any"/"all", default "any"), `top_k` | result envelope |
| `search_by_document` | `query`, `documents` (req, ≥1, IDs or filenames), `top_k` | result envelope |
| `get_document_outline` | `document` (ID or filename) | heading tree + page ranges + chunk counts |
| `expand_chunk` | `document_id`, `chunk_index`, `before`/`after` (default 1) | neighboring chunks (bounded context growth around a confirmed hit) |

Result envelope:

```json
{
  "query": "...",
  "results": [{
    "rank": 1,
    "text": "raw chunk text",
    "document": {"id": "…", "filename": "aml-policy.pdf", "tags": ["compliance"]},
    "location": {"pages": [4,5], "heading_path": ["3 Client Tiers","3.2 Limits"], "chunk_index": 12}
  }],
  "documents_searched": 12
}
```

`location` = provenance bonus, structured for citation.

Server `initialize` metadata declares name + instructions describing the knowledge base domain (disambiguates from other servers' generic `search` tools; hosts additionally namespace tool names per server).

Considered and rejected: `get_document_chunks(document, pages)` bulk fetch — token-economy risk (section dumps flood agent context); `expand_chunk` + `search_by_document` cover the need bounded. Documented in README.

## 8. Auth, Config, Error Handling

**Auth:**
- `/mcp`: static Bearer token (`MCP_API_KEY`), middleware, constant-time compare, 401 + `WWW-Authenticate` on failure. Production path (OAuth 2.1 resource server per MCP spec) documented, not built.
- UI + `/api`: HTTP Basic, single password (`UI_PASSWORD`) — required because deployment is public.

**Config:** pydantic-settings, env-only. `.env` gitignored, `.env.example` committed. Keys: `OPENAI_API_KEY`, `MCP_API_KEY`, `UI_PASSWORD`, `QDRANT_URL`, `QDRANT_API_KEY`, `DB_PATH`, `EMBED_MODEL`, `CHUNK_TOKENS`, `CHUNK_OVERLAP`.

**Errors:**
- Ingestion ordering as transaction: pure computation → Qdrant upsert → SQLite last. Failure before SQLite commit → delete points for `document_id`, error to UI. Invariant: metadata never references missing chunks. (Honest substitute for cross-store transactions; README-documented.)
- Upload validation: pdf/txt/md only, ~20MB cap, corrupt/empty-text files rejected with specific messages, nothing persisted.
- MCP: no raw exceptions to agents — catch-all → structured guidance errors; Qdrant outage → "knowledge base temporarily unavailable".
- SQLite: WAL + busy_timeout (concurrent ingestion writes are ms-scale at pipeline end; embedding API is the real bottleneck).

## 9. Testing

- **Unit:** chunker (boundaries, overlap, prefix, token targets), dedup decision table (three rules), tag normalization, filename fuzzy matching.
- **Integration:** ingestion + retrieval against real Qdrant container (test fixture); MCP tools via in-process Streamable HTTP client incl. auth cases (valid/wrong/missing token). Fake deterministic embedder throughout (no API cost/flakiness).
- **Smoke:** compose up → upload sample doc → MCP `search` finds it. Doubles as demo-video script.

Coverage targets decision-bearing logic; SDK plumbing trusted.

## 10. Deployment

- Local/reviewer: `docker-compose up` (app + qdrant), deliverable requirement.
- Live: app container → Railway / Fly.io / Render (final pick at deploy time; all consume Dockerfile + env vars). Vectors → Qdrant Cloud free tier (1GB). SQLite on persistent volume. Secrets in platform env vars.

## 11. Known Limitations / Future Work (README material)

- PDF heading detection heuristic; structureless PDFs degrade to page-only provenance.
- Chunk params are folklore defaults; production tuning needs an eval set.
- Context-loss ladder: overlap + contextual prefixing implemented; contextual retrieval (Anthropic-style LLM chunk blurbs) and parent-document retrieval are the next rungs.
- SQLite → Postgres when multi-instance.
- Static bearer → OAuth 2.1 per MCP spec for real multi-client auth.
- Auto-tagging via LLM at ingestion.

## 12. Non-Goals Restated

No answer generation server-side; no re-ranking cross-encoder (RRF only); no UI framework; no multi-tenancy.
