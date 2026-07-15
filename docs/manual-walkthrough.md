# Manual walkthrough — see the system work end to end

A by-hand run of the whole flow, so you can validate behavior with your own eyes
instead of trusting `scripts/smoke.py`. Start the stack, ingest the fictional
Meridian corpus, attach the MCP server to an agent, run queries that each target
a specific tool, and check the result against known ground truth.

Companion to the README (which has the architecture and rationale). This doc is
the click-by-click.

---

## 0. Prerequisites

- Docker running.
- `.env` filled: `OPENAI_API_KEY`, `MCP_API_KEY`, `UI_PASSWORD` (copy `.env.example`).
- An MCP client for step 5 (Claude Code CLI or Claude Desktop).

```bash
cp .env.example .env      # then edit in your keys
```

## 1. Start the stack

```bash
docker compose up --build
```

Wait for the app to report healthy, then confirm the two stores are reachable:

```bash
curl -s http://localhost:8000/healthz          # -> {"status":"ok"}
```

- UI: http://localhost:8000 (HTTP Basic — any username, `UI_PASSWORD`)
- Qdrant dashboard (inspect raw chunks): http://localhost:6333/dashboard

## 2. The corpus

The test corpus is `test_corpus/meridian/` — eleven documents (4 generated PDFs,
5 markdown, 2 plain text) of one fictional client, **Meridian Financial**.
Every fact is invented, so a correct answer *proves retrieval*: the model has
nothing to remember. The PDFs carry realistic chaff (headers, footers, page
numbers, tables, a cover TOC) to exercise wheat-from-chaff extraction.

- [test_corpus/meridian/COMPANY.md](../test_corpus/meridian/COMPANY.md) — the
  canon (fact ledger + negative controls). **Never ingest this file.**
- [test_corpus/meridian/TAGS.md](../test_corpus/meridian/TAGS.md) — tags per
  document, rationale, and ready-to-run ingest commands.
- PDFs are committed; to regenerate them:
  `cd test_corpus/meridian/generators && for g in gen_*.py; do uv run python $g; done`

## 3. Ingest documents

**Fast first pass** — via the UI: open http://localhost:8000, upload
`test_corpus/meridian/docs/meridian-aml-policy.md`, tags `compliance`. The
response shows `outcome` (`created`) and a chunk count.

**Full corpus, via API** — run the eleven `curl` commands from
[TAGS.md](../test_corpus/meridian/TAGS.md#ingest-commands).

**Validate ingestion:**
- Each POST returns `{"document": {...}, "outcome": "created"}` with `chunk_count > 0`.
- The UI list now shows every document with its tags and chunk count.
- In the Qdrant dashboard, collection `chunks` shows payloads with `text`,
  `heading_path`, and (for PDFs) `page_start`/`page_end`.

## 4. Attach the MCP server to an agent

**Claude Code:**

```bash
claude mcp add --transport http docintel http://localhost:8000/mcp \
  --header "Authorization: Bearer <MCP_API_KEY>"
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "docintel": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {"Authorization": "Bearer <MCP_API_KEY>"}
    }
  }
}
```

Confirm the agent lists seven tools: `search`, `search_by_tag`,
`search_by_document`, `list_documents`, `list_tags`, `get_document_outline`,
`expand_chunk`.

## 5. Query playbook

Run the fifteen queries in
[test_corpus/meridian/QUERY-PLAYBOOK.md](../test_corpus/meridian/QUERY-PLAYBOOK.md).
Each query targets one tool-selection behavior and states the expected tool
trajectory (primary + acceptable), the rationale, and the invented ground truth
to validate against — including two negative controls that catch hallucination
outright. Start every agent session with the playbook's preamble ("use the
docintel tools, don't rely on prior knowledge, cite sources"): a
general-purpose host like Claude Code has a coding persona and won't treat bare
questions as knowledge-base lookups on its own.

For every search-type query, confirm three things:
1. **Grounded** — the claim matches the cited chunk's text (cross-check in the
   Qdrant dashboard or the raw file).
2. **Cited** — the answer names the filename plus pages or heading path from the
   result's `location`.
3. **Scoped** — tag/document-scoped queries returned *only* in-scope documents.

## 6. Dedup / versioning demo (proves the three SHA-256 rules)

Watch the `outcome` field change without touching search:

The API changelog is the natural versioning fixture — changelogs get new
versions in real life:

```bash
D=test_corpus/meridian/docs

# Rule 1 — identical bytes re-uploaded: no re-embed, tags merge.
curl -u admin:$UI_PASSWORD -F "file=@$D/kestrel-api-changelog.md" -F "tags=engineering" \
  -X POST http://localhost:8000/api/documents
#   -> outcome: "unchanged"  (and the doc now carries product + settlement + engineering)

# Rule 2 — same filename, edited content: new version, delete-first re-ingest.
cp $D/kestrel-api-changelog.md kestrel-api-changelog.md   # copy so we can edit
# edit the copy: add a new "## v2027.3" entry at the top, save
curl -u admin:$UI_PASSWORD -F "file=@kestrel-api-changelog.md" -F "tags=product" \
  -X POST http://localhost:8000/api/documents
#   -> outcome: "updated"  (same document id, old vectors gone)
```

**Validate:** after Rule 2, ask the agent "what changed in the latest Kestrel
API release?" — the answer reflects your invented v2027.3 entry, and searching
old v2027.2 phrasing shows the re-ingested (not duplicated) document. That is
the delete-first replacement working. (Clean up: `rm kestrel-api-changelog.md`,
then re-upload the original to restore the corpus state.)

## 7. Auth check (least privilege)

```bash
# No token -> 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
#   -> 401
```

Also confirm the agent has **no write tool** — ingestion/deletion live only in the
UI/API. Read-only surface by design.

---

### One-command sanity check

If you just want the automated happy path (start checks, one ingest, one MCP search, the auth 401 — no agent attach):

```bash
uv run python scripts/smoke.py
```

It ingests one sample doc, runs a `search` over MCP, and asserts the auth 401 —
the same spine as this walkthrough, minus the human judgment.
