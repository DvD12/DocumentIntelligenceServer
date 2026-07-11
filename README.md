# Document Intelligence Server

Backend infrastructure that turns a folder of internal documents (policies, manuals, guides, FAQs) into an **agent-queryable knowledge base**. Documents are uploaded and tagged through a small management UI, run through a RAG ingestion pipeline (parse → chunk → embed → store), and exposed to any MCP-compatible AI agent through an **MCP server over Streamable HTTP** with seven purpose-designed tools.

Built as the practical assignment for indigo.ai's *AI Solutions Engineer* role. The scenario: a financial-services client wants employees to ask questions in natural language and get precise, grounded, **citable** answers from their document base.

## Architecture

```
┌─────────────────────────────────────────────┐
│  app (FastAPI, one container)               │
│                                             │
│  /            Jinja UI (upload/list/delete) │
│  /api/*       REST used by the UI           │
│  /mcp         MCP server (Streamable HTTP,  │
│               Bearer auth)                  │
│  /healthz     store connectivity check      │
│                                             │
│  ingestion    parse → chunk → embed → store │
│  retrieval    hybrid search service         │
│  stores       qdrant client + sqlite repo   │
└──────────────┬──────────────────────────────┘
               │
        ┌──────▼──────┐        SQLite = file on a
        │   Qdrant    │        volume inside the
        │ (container) │        app container
        └─────────────┘
```

**Boundary rule:** the MCP tools and the web API are thin adapters over the same `ingestion`/`retrieval` service layer. Neither owns logic; both call it. Search behavior is tested once, and the MCP layer stays pure interface design — which is what an agent actually consumes.

## Stack choices and rationale

| Concern | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Required language; async, typed, boring in the good way |
| MCP | Official `mcp` SDK (FastMCP), Streamable HTTP | Required transport. Pinned to stable 1.x — 2.0 is beta-only on PyPI |
| Vector store | Qdrant | Native hybrid search: dense + sparse vectors on the same point, RRF fusion server-side, payload filtering for scoped search |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, cosine) | Strong default at ~$0.02/M tokens. Same model embeds documents and queries — a hard invariant |
| Sparse vectors | FastEmbed BM25 (`Qdrant/bm25`), computed client-side | Free, local, no API dependency. IDF weighting applied by Qdrant (`modifier: idf`) |
| Metadata | SQLite (WAL) | Right-sized for one instance; documented Postgres swap-path for scale-out |
| Frontend | Jinja + vanilla JS served by FastAPI | One less service; the assignment's focus (and this repo's) is RAG + MCP |
| Packaging | Docker + docker-compose, `uv` with committed lockfile | One-command reproduction |

## RAG design

**Chunking** — structure-aware recursive splitter: split at headings → paragraphs → sentences, only hard-cutting token runs as a last resort. Targets ~450 tokens per chunk with 15% overlap; trailing fragments under 50 tokens merge into their predecessor. The 450/15% values are industry folk-defaults, exposed as config (`CHUNK_TOKENS`, `CHUNK_OVERLAP`); a production deployment would tune them against a retrieval eval set.

**Contextual prefixing** — the text that gets *embedded* is `filename > heading path — chunk text`, while the raw chunk is what agents *read*. This mitigates the "chunk island" problem (a chunk saying "the aforementioned limits apply…" embeds poorly without knowing where it lives). The full mitigation ladder, in increasing cost: overlap → contextual prefixing (both implemented) → LLM contextual retrieval → parent-document retrieval (both documented future work).

**Hybrid search** — every query runs twice: dense cosine search (meaning: "how long do we keep records" finds retention policy) and BM25 keyword search (exact terms: "policy AML-2024-B" finds the literal code). The two rankings merge via Reciprocal Rank Fusion server-side in a single Qdrant request. Financial documents are full of codes and acronyms — the keyword branch regularly rescues queries the semantic branch fumbles.

**Provenance** — each chunk carries its origin: page range for PDFs (heading detection in PDFs is heuristic, via font-size analysis), heading path for markdown. Search results return a structured `location` so agents cite *"aml-policy.pdf, p. 4, §2.2"*.

**Deduplication** — three rules keyed on SHA-256 of file bytes:

| Situation | Action |
|---|---|
| Same content hash exists | No re-parse, no re-embed. Merge tags, update filename |
| Same filename, new hash | New version: delete old vectors (delete-first — v2 may have fewer chunks), re-ingest under the same document id |
| Neither | New document |

Write ordering doubles as the transaction strategy: all pure computation first, then vector upsert, then the SQLite row *last* — metadata never references chunks that don't exist. On failure mid-write, the document's points are deleted. Point IDs are deterministic (`uuid5(document_id:chunk_index)`) so a crashed ingestion retried overwrites its partial work instead of duplicating it.

**Consistency rule** — Qdrant payloads hold only immutable-per-version fields. Mutable metadata (filename, tags) lives solely in SQLite and is joined into results at response time; tag-scoped search resolves tags → document ids in SQLite, then filters Qdrant by id. One source of truth per fact; no stale-payload bug class.

## MCP tool design

Five principles drove the interface (this is the part an LLM actually "sees"):

1. **Descriptions say *when*, not just what.** Each search variant names its trigger condition and points to its siblings, so an agent can choose between three search tools without trial and error.
2. **One result envelope for all search tools** — the agent learns the shape once.
3. **A bare-minimum call must work**: only `query` is required anywhere; everything else has defaults.
4. **Errors are guidance.** An unknown tag returns the valid tags with counts and a fuzzy "did you mean" — the agent self-corrects in one turn instead of guessing.
5. **Read-only surface.** Writes belong to the management UI; agents get least privilege.

| Tool | Agent reaches for it when… |
|---|---|
| `search` | Default: question has no obvious topic or document |
| `search_by_tag` | Question clearly belongs to a topic area (compliance, hr, …) |
| `search_by_document` | User named a document, or a previous hit identified it |
| `list_documents` | "What documents do we have?" / before choosing a scope |
| `list_tags` | Before `search_by_tag` when tags are unknown |
| `get_document_outline` | "What does document X cover?" — structure without content search |
| `expand_chunk` | A hit is cut off or references nearby context — bounded neighborhood fetch |

Example error (agent typos a tag):

```json
{
  "error": "unknown_tags",
  "message": "No documents carry tag(s): complaince. Available tags: compliance (12 docs), hr (5). Did you mean: compliance?"
}
```

**Considered and rejected:** a `get_document_chunks(document, pages)` bulk fetch — token economics are wrong (a section dump can flood an agent's context where search returns the two relevant chunks); `expand_chunk` + `search_by_document` cover the need bounded. Also rejected: write tools over MCP (least privilege).

Result envelope (all search tools):

```json
{
  "query": "...",
  "results": [{
    "rank": 1,
    "text": "raw chunk text, quotable",
    "document": {"id": "…", "filename": "aml-policy.md", "tags": ["compliance"]},
    "location": {"pages": null, "heading_path": ["2 Client Tiers", "2.2 Transfer Limits"], "chunk_index": 3}
  }],
  "documents_searched": 12
}
```

## Authentication

**MCP endpoint** — static Bearer token, checked constant-time, over TLS in production:

```bash
curl -X POST https://<host>/mcp \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Missing/wrong token → `401` with `WWW-Authenticate: Bearer`. The production upgrade path is the MCP spec's OAuth 2.1 resource-server flow (per-client identity, scopes, expiry, revocation) — named deliberately, not built: one shared demo endpoint doesn't justify an authorization server.

**Management UI/API** — HTTP Basic (any username + `UI_PASSWORD`); required because the app is deployed publicly. `/healthz` is open.

Note: the transport's DNS-rebinding protection is disabled — it's a browser-attack defense for localhost servers that would reject arbitrary deploy hostnames; this endpoint is Bearer-authenticated and server-to-server.

## Running locally

```bash
cp .env.example .env      # fill OPENAI_API_KEY, MCP_API_KEY, UI_PASSWORD
docker compose up --build
```

UI at http://localhost:8000 (HTTP Basic, any username). MCP endpoint at `http://localhost:8000/mcp`.

Verify end-to-end (uploads a sample doc, queries via MCP, checks auth):

```bash
uv run python scripts/smoke.py
```

Development without Docker: `uv sync`, start a local Qdrant (`docker run -p 6333:6333 qdrant/qdrant:v1.18.1`), then `uv run uvicorn app.main:create_app --factory`. Tests need no services and no API keys: `uv run pytest` (58 tests: deterministic fake embedder + Qdrant in-memory mode).

### Trying the full flow by hand

1. **Ingest** — upload through the UI (file + comma-separated tags), or via API:

   ```bash
   curl -u admin:$UI_PASSWORD -X POST http://localhost:8000/api/documents \
     -F "file=@sample_docs/aml-policy.md" -F "tags=compliance"
   ```

   The response reports the dedup `outcome` (`created` / `updated` / `unchanged`) and the chunk count. Chunks themselves can be inspected in Qdrant's own dashboard at http://localhost:6333/dashboard (collection `chunks` — payload shows text, heading path, pages).

2. **Query over MCP** — call the `search` tool exactly as an agent would:

   ```bash
   curl -X POST http://localhost:8000/mcp \
     -H "Authorization: Bearer $MCP_API_KEY" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"tier-2 transfer cap"}}}'
   ```

   The result contains ranked chunks with `document` and `location` (pages / heading path) for citation.

3. **Or let an agent drive** — register the server in an MCP client (next section) and ask a question ("what are the tier-2 transfer caps?"); the agent picks a search tool, retrieves chunks, and answers with citations.

`scripts/smoke.py` automates steps 1–2 plus an auth check.

## Connecting an MCP client

Claude Code:

```bash
claude mcp add --transport http docintel https://<host>/mcp \
  --header "Authorization: Bearer <MCP_API_KEY>"
```

Claude Desktop / generic JSON config:

```json
{
  "mcpServers": {
    "docintel": {
      "type": "http",
      "url": "https://<host>/mcp",
      "headers": {"Authorization": "Bearer <MCP_API_KEY>"}
    }
  }
}
```

Hosts namespace tools per server, so our generic names (`search`, …) can't collide with other connected servers.

## Deployment

`docker-compose.yml` is the reference environment. Live deployment: the app container on any Dockerfile-consuming platform (Railway/Fly.io/Render) + Qdrant Cloud free tier for vectors + a persistent volume for the SQLite file. All secrets via platform env vars; nothing in the image or repo.

**Live deployment** (Railway + Qdrant Cloud free tier):

- Management UI: https://documentintelligenceserver-production.up.railway.app (HTTP Basic)
- MCP endpoint: `https://documentintelligenceserver-production.up.railway.app/mcp` (Bearer token)
- Health: https://documentintelligenceserver-production.up.railway.app/healthz

Credentials are provided separately to reviewers, not in this repository.

## Known limitations & future work

- PDF heading detection is heuristic (font-size based); structureless PDFs degrade to page-only provenance.
- Chunk parameters are folk defaults; production tuning needs a retrieval eval set.
- Context-loss ladder: LLM contextual retrieval (Anthropic-style chunk situating) and parent-document retrieval are the next rungs.
- Tool results are JSON in text content; MCP `structuredContent` (typed output schemas) would let strict clients validate.
- SQLite → Postgres when running multiple app instances.
- Static Bearer → OAuth 2.1 resource server for real multi-client auth.
- Re-ranking with a cross-encoder after RRF; LLM auto-tagging at ingestion.

## AI-assisted development

This project was built with Claude Code in a spec-first workflow: design dialogue → written spec → task-by-task implementation plan → TDD execution. Full written answers (Part 1): [docs/part1-ai-assisted-coding.md](docs/part1-ai-assisted-coding.md).

Where AI was used, in one paragraph: architecture and trade-off exploration (vector store, chunking, tool design) happened in a reviewed dialogue; every decision above was human-arbitrated. Code was AI-generated against a pre-approved plan with tests written first, then human-reviewed. Notable steering moments: pinning `mcp` to stable 1.x after discovering v2 is beta-only (stale-training-data risk, mitigated by live docs lookup); catching that `models.Document` upserts request cloud-only server-side inference — the in-memory test mode masked it, the real-container smoke test exposed it; the delete-before-first-upload crash caught by tests.
