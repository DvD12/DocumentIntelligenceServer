# Manual walkthrough — see the system work end to end

A by-hand run of the whole flow, so you can validate behavior with your own eyes
instead of trusting `scripts/smoke.py`. Start the stack, ingest real documents,
attach the MCP server to an agent, run prompts that each target a specific tool,
and check the result against what should happen.

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
curl -s http://localhost:8000/healthz          # -> {"status":"ok",...}
```

- UI: http://localhost:8000 (HTTP Basic — any username, `UI_PASSWORD`)
- Qdrant dashboard (inspect raw chunks): http://localhost:6333/dashboard

## 2. Fetch a real corpus

```bash
uv run python scripts/fetch_corpus.py
```

Downloads five license-clean PDFs into `corpus/` and prints a tag cheat-sheet.
Four are public-domain financial documents (acronym-dense, deeply sectioned —
they stress the keyword branch and give tags real meaning); one arXiv paper is an
out-of-domain control. (EUR-Lex and SEC EDGAR were the obvious first picks but
bot-block or serve HTML, which the parser doesn't take — hence BIS/IRS/NIST.)

| File | Suggested tag | Why it's in the set |
|---|---|---|
| `basel3.pdf` (BIS) | `capital` | Cleanly structured (~130 headings) + code-dense (CET1, RWA, LCR) → best outline + keyword demos |
| `irs-employer-tax-guide.pdf` (Pub 15) | `payroll` | Long, tabular; headings extract but noisily → realistic messy PDF |
| `irs-investment-income.pdf` (Pub 550) | `investments` | Distinct topic, shares finance vocab with Basel → proves tag isolation |
| `nist-cybersecurity-framework.pdf` | `security` | Uniform-font layout → **no headings detected**, degrades to page-only provenance (README limitation, live) |
| `attention-is-all-you-need.pdf` | `research` | Out-of-domain control: retrieval shouldn't collapse or bleed into finance |

Also on disk already: `sample_docs/aml-policy.md`, `sample_docs/hr-handbook.md`
(small, structured — good for a first, fast ingest).

## 3. Ingest documents

**Fast first pass** — the markdown sample, via the UI: open http://localhost:8000,
upload `sample_docs/aml-policy.md`, tags `compliance`. The response shows
`outcome` (`created`) and a chunk count.

**Bulk, via API** — ingest the corpus with the tags above:

```bash
# one file
curl -u admin:$UI_PASSWORD -X POST http://localhost:8000/api/documents \
  -F "file=@corpus/basel3.pdf" -F "tags=capital"

# the rest
curl -u admin:$UI_PASSWORD -F "file=@corpus/irs-employer-tax-guide.pdf"        -F "tags=payroll"     -X POST http://localhost:8000/api/documents
curl -u admin:$UI_PASSWORD -F "file=@corpus/irs-investment-income.pdf"         -F "tags=investments" -X POST http://localhost:8000/api/documents
curl -u admin:$UI_PASSWORD -F "file=@corpus/nist-cybersecurity-framework.pdf"  -F "tags=security"    -X POST http://localhost:8000/api/documents
curl -u admin:$UI_PASSWORD -F "file=@corpus/attention-is-all-you-need.pdf"     -F "tags=research"    -X POST http://localhost:8000/api/documents
curl -u admin:$UI_PASSWORD -F "file=@sample_docs/aml-policy.md"                -F "tags=compliance"  -X POST http://localhost:8000/api/documents
```

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

## 5. Prompt playbook

Each row is a prompt to type at the agent, the tool it should pick, and what to
check. The point is to watch the agent *choose the right tool from the
descriptions* and cite grounded results — that tool-selection behavior is the
deliverable.

| # | Prompt to the agent | Expected tool | What validates it |
|---|---|---|---|
| 1 | "What documents do we have?" | `list_documents` | Lists all ingested files with tags + chunk counts. No content search. |
| 2 | "What topic areas does the knowledge base cover?" | `list_tags` | Returns `capital`, `payroll`, `investments`, `security`, `research`, `compliance` with doc counts. |
| 3 | "What is the tier-2 transfer cap?" | `search` | Finds `aml-policy.md`; answer cites **10,000 EUR/day**, §2.2. |
| 4 | "Find policy AML-2024-B." | `search` (keyword branch) | Literal code match → the classification chunk. This is the BM25 half of hybrid earning its keep; a pure-semantic store fumbles bare codes. Also try "CET1" against the Basel doc. |
| 5 | "What do our **capital** documents say about the minimum common equity ratio?" | `search_by_tag` (tags=`capital`) | Results only from `basel3.pdf` — never the IRS or arXiv docs, even though investments/tax share finance vocabulary. Proves tag isolation. |
| 6 | "In the Basel III document, how is a G-SIB defined?" | `search_by_document` (documents=`basel3.pdf`) | Hits confined to `basel3.pdf`, cited with page numbers. |
| 7 | "What does the Basel III document cover?" | `get_document_outline` | Returns heading/page structure, **no chunk text**. `basel3.pdf` has a rich outline; contrast with `nist-cybersecurity-framework.pdf`, which returns page-only entries — the heuristic's documented degradation. |
| 8 | "Show me more context around that transfer-limit chunk." (after prompt 3) | `expand_chunk` | Returns the neighboring chunks in document order (the §2.2 surroundings). |
| 9 | "Search the **capitol** documents for the leverage ratio." (deliberate typo) | `search_by_tag` → error | Structured error lists valid tags + "Did you mean: capital?" and the agent self-corrects in one turn. |
| 10 | "How does self-attention work?" | `search` | Answer grounded in `attention-is-all-you-need.pdf` — the out-of-domain control still retrieves cleanly and doesn't bleed into finance docs. |

### Validating each answer

For search prompts (3–6, 10), confirm three things:
1. **Grounded** — the claim matches the cited chunk's text (cross-check in the
   Qdrant dashboard or the raw file).
2. **Cited** — the answer names the filename plus pages or heading path from the
   result's `location`.
3. **Scoped** — tag/document-scoped prompts returned *only* in-scope documents.

## 6. Dedup / versioning demo (proves the three SHA-256 rules)

Watch the `outcome` field change without touching search:

```bash
# Rule 1 — identical bytes re-uploaded: no re-embed, tags merge.
curl -u admin:$UI_PASSWORD -F "file=@sample_docs/aml-policy.md" -F "tags=finance" \
  -X POST http://localhost:8000/api/documents
#   -> outcome: "unchanged"  (and the doc now carries both compliance + finance tags)

# Rule 2 — same filename, edited content: new version, delete-first re-ingest.
cp sample_docs/aml-policy.md aml-policy.md            # copy so we can edit in place
# edit aml-policy.md: change "10,000 EUR" to "15,000 EUR", save
curl -u admin:$UI_PASSWORD -F "file=@aml-policy.md" -F "tags=compliance" \
  -X POST http://localhost:8000/api/documents
#   -> outcome: "updated"  (same document id, old vectors gone)
```

**Validate:** after Rule 2, re-run prompt 3 ("tier-2 transfer cap"). The answer
now says **15,000 EUR** — the old vectors are gone, not merely shadowed. That is
the delete-first replacement working. (Clean up: `rm aml-policy.md`.)

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

If you just want the automated version of steps 1–4's happy path:

```bash
uv run python scripts/smoke.py
```

It ingests one sample doc, runs a `search` over MCP, and asserts the auth 401 —
the same spine as this walkthrough, minus the human judgment.
