# Document Intelligence Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RAG knowledge base with management UI and an MCP server (Streamable HTTP, Bearer auth) exposing 7 agent-ready tools, per the approved spec at `docs/superpowers/specs/2026-07-11-document-intelligence-design.md`.

**Architecture:** Single FastAPI app (Jinja UI + REST + mounted MCP ASGI sub-app) over Qdrant (hybrid dense+BM25 search, server-side RRF) and SQLite (metadata, WAL). MCP tools and web API are thin adapters over shared `ingestion`/`retrieval` services.

**Tech Stack:** Python 3.12, uv, FastAPI, `mcp>=2` (MCPServer), `qdrant-client[fastembed]`, OpenAI `text-embedding-3-small`, tiktoken, pdfplumber, SQLite (stdlib `sqlite3`), pytest.

## Global Constraints

- Python `>=3.12`; dependency manager: `uv` (commit `uv.lock`).
- MCP SDK **v2**: `from mcp.server import MCPServer` (v1 `FastMCP` renamed; transport config lives on `run()`/app builders, NOT the constructor).
- Transport: **Streamable HTTP** mounted at `/mcp`, `stateless_http=True`.
- Embeddings: OpenAI `text-embedding-3-small`, 1536 dims, cosine. Same model for ingestion and queries — never mix.
- Chunking defaults: `CHUNK_TOKENS=450`, `CHUNK_OVERLAP=0.15`, min chunk 50 tokens (merge smaller into previous).
- Qdrant collection `chunks`: named dense vector `dense` (1536, cosine) + named sparse vector `sparse` (`modifier=IDF`), BM25 sparse embeddings via fastembed model `Qdrant/bm25`.
- Qdrant payload holds ONLY immutable-per-version fields (`document_id`, `chunk_index`, `text`, `heading_path`, `page_start`, `page_end`, `token_count`). Filename/tags live in SQLite only, joined at response time.
- Point IDs: `uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk_index}")`.
- All agent-facing errors: structured guidance (`{"error": code, "message": actionable text with valid values + fuzzy suggestions}`), never stack traces.
- Secrets/config via env only (pydantic-settings); `.env` gitignored; `.env.example` current at all times.
- Tests use `FakeEmbedder` (deterministic, word-hash) and `QdrantClient(":memory:")` — no API keys, no containers needed. First fastembed use downloads the tiny BM25 model artifacts (network needed once).
- **One commit per task** (user rule, overrides commit-per-step). Run `uv run pytest` green + `uv run ruff check .` clean before every commit.
- Windows dev machine: prefer `uv run` prefixes; paths in code POSIX-style (pathlib).

---

### Task 1: Project scaffold + configuration

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `app.core.config.Settings` (fields below), `get_settings() -> Settings` (lru_cached).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "document-intelligence-server"
version = "0.1.0"
description = "RAG knowledge base with MCP server (Streamable HTTP)"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "mcp>=2.0",
    "qdrant-client[fastembed]>=1.12",
    "openai>=1.40",
    "pydantic-settings>=2.4",
    "tiktoken>=0.7",
    "pdfplumber>=0.11",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.6",
    "reportlab>=4",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.env
data/
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
dist/
```

- [ ] **Step 3: Write `.env.example`**

```bash
# OpenAI — embeddings (text-embedding-3-small)
OPENAI_API_KEY=sk-proj-...

# MCP endpoint Bearer token: clients send "Authorization: Bearer <value>"
MCP_API_KEY=generate-a-long-random-string

# HTTP Basic password for the management UI/API (any username)
UI_PASSWORD=choose-a-password

# Qdrant. Local compose: http://qdrant:6333 (in-container) / http://localhost:6333 (host)
QDRANT_URL=http://localhost:6333
# Only for Qdrant Cloud:
# QDRANT_API_KEY=

# SQLite metadata database location
DB_PATH=data/metadata.db

# Tunables (defaults shown)
# EMBED_MODEL=text-embedding-3-small
# CHUNK_TOKENS=450
# CHUNK_OVERLAP=0.15
```

- [ ] **Step 4: Write the failing test `tests/test_config.py`**

```python
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
```

- [ ] **Step 5: Run `uv sync`, then run the test to verify it fails**

Run: `uv sync && uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'` (empty `__init__.py` files created in Step 6). Commit `uv.lock` with this task.

- [ ] **Step 6: Implement `app/core/config.py` (+ empty `app/__init__.py`, `app/core/__init__.py`, `tests/__init__.py`)**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from env vars / .env only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    mcp_api_key: str = "change-me"
    ui_password: str = "change-me"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    db_path: str = "data/metadata.db"
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    chunk_tokens: int = 450
    chunk_overlap: float = 0.15


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Run tests to verify pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 2 PASS

- [ ] **Step 8: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "chore: scaffold project, config via pydantic-settings"
```

---

### Task 2: Domain models, errors, text helpers

**Files:**
- Create: `app/core/models.py`, `app/core/errors.py`, `app/core/text.py`, `tests/test_text.py`

**Interfaces:**
- Produces:
  - `models.ParsedSection(heading_path: list[str], text: str, page_start: int | None, page_end: int | None)`
  - `models.ParsedDocument(sections: list[ParsedSection])`
  - `models.Chunk(document_id: str, chunk_index: int, text: str, prefixed_text: str, heading_path: list[str], page_start: int | None, page_end: int | None, token_count: int)`
  - `models.DocumentMeta(id: str, filename: str, content_hash: str, media_type: str, size_bytes: int, chunk_count: int, tags: list[str], uploaded_at: datetime, updated_at: datetime)`
  - `errors.DocIntelError(message)` with class attr `code`; subclasses `ParseError("parse_error")`, `UnknownTagsError("unknown_tags")`, `UnknownDocumentsError("unknown_documents")`, `StoreUnavailableError("store_unavailable")`
  - `text.normalize_tag(tag: str) -> str`; `text.closest_matches(value: str, candidates: list[str], n: int = 3) -> list[str]`

- [ ] **Step 1: Write failing tests `tests/test_text.py`**

```python
from app.core.text import closest_matches, normalize_tag


def test_normalize_tag():
    assert normalize_tag("  Compliance ") == "compliance"
    assert normalize_tag("HR") == "hr"


def test_closest_matches_finds_typo():
    assert closest_matches("complaince", ["compliance", "hr", "product"]) == ["compliance"]


def test_closest_matches_empty_when_nothing_close():
    assert closest_matches("zzzzzz", ["compliance", "hr"]) == []
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_text.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the three modules**

`app/core/text.py`:

```python
import difflib


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def closest_matches(value: str, candidates: list[str], n: int = 3) -> list[str]:
    return difflib.get_close_matches(value, candidates, n=n, cutoff=0.6)
```

`app/core/errors.py`:

```python
class DocIntelError(Exception):
    """Errors safe to surface to agents/UI as actionable guidance."""

    code = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ParseError(DocIntelError):
    code = "parse_error"


class UnknownTagsError(DocIntelError):
    code = "unknown_tags"


class UnknownDocumentsError(DocIntelError):
    code = "unknown_documents"


class StoreUnavailableError(DocIntelError):
    code = "store_unavailable"
```

`app/core/models.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class ParsedSection(BaseModel):
    heading_path: list[str] = Field(default_factory=list)
    text: str
    page_start: int | None = None
    page_end: int | None = None


class ParsedDocument(BaseModel):
    sections: list[ParsedSection]


class Chunk(BaseModel):
    document_id: str
    chunk_index: int
    text: str
    prefixed_text: str
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    token_count: int


class DocumentMeta(BaseModel):
    id: str
    filename: str
    content_hash: str
    media_type: str
    size_bytes: int
    chunk_count: int
    tags: list[str] = Field(default_factory=list)
    uploaded_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_text.py -v`
Expected: 3 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: domain models, guidance-error hierarchy, tag/fuzzy helpers"
```

---

### Task 3: SQLite metadata repository

**Files:**
- Create: `app/stores/__init__.py`, `app/stores/metadata_repo.py`, `tests/test_metadata_repo.py`

**Interfaces:**
- Consumes: `DocumentMeta`, `normalize_tag` (Task 2).
- Produces: `MetadataRepo(db_path: str)` with methods (all thread-safe via one internal `threading.Lock`):
  - `create_document(*, id: str, filename: str, content_hash: str, media_type: str, size_bytes: int, chunk_count: int, tags: list[str]) -> DocumentMeta`
  - `get(document_id: str) -> DocumentMeta | None`; `get_many(ids: set[str]) -> list[DocumentMeta]`
  - `get_by_hash(content_hash: str) -> DocumentMeta | None`; `get_by_filename(filename: str) -> DocumentMeta | None`
  - `merge_tags(document_id: str, tags: list[str]) -> None`; `update_filename(document_id: str, filename: str) -> None`
  - `replace_content(document_id: str, *, filename: str, content_hash: str, size_bytes: int, chunk_count: int, tags: list[str]) -> None` (new version: overwrites hash/size/count, merges tags, bumps `updated_at`)
  - `delete(document_id: str) -> bool`
  - `list_documents() -> list[DocumentMeta]`; `count_documents() -> int`
  - `list_tags() -> list[tuple[str, int]]` (name, document count; sorted by name)
  - `ids_for_tags(tags: list[str], match: str) -> tuple[list[str], list[str]]` → (document_ids, unknown_tags); `match` is `"any"` or `"all"`
  - `resolve_documents(refs: list[str]) -> tuple[list[DocumentMeta], list[str]]` — each ref matched against id first, then case-insensitive filename; second element = unresolved refs

- [ ] **Step 1: Write failing tests `tests/test_metadata_repo.py`**

```python
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
    assert repo.list_tags() == []  # cascade removed junction rows; empty tags pruned
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_metadata_repo.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/stores/metadata_repo.py`**

```python
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.core.models import DocumentMeta
from app.core.text import normalize_tag

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS document_tags (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MetadataRepo:
    """SQLite-backed document metadata. Single connection, lock-serialized.

    Right-sized for one app instance; swap target is Postgres when scaling out.
    """

    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)

    # -- internal helpers -------------------------------------------------

    def _row_to_meta(self, row: sqlite3.Row) -> DocumentMeta:
        tags = [
            r["name"]
            for r in self._conn.execute(
                "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id = t.id "
                "WHERE dt.document_id = ? ORDER BY t.name",
                (row["id"],),
            )
        ]
        return DocumentMeta(**{**dict(row), "tags": tags})

    def _attach_tags(self, document_id: str, tags: list[str]) -> None:
        for tag in {normalize_tag(t) for t in tags if normalize_tag(t)}:
            self._conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            self._conn.execute(
                "INSERT OR IGNORE INTO document_tags (document_id, tag_id) "
                "SELECT ?, id FROM tags WHERE name = ?",
                (document_id, tag),
            )

    def _prune_orphan_tags(self) -> None:
        self._conn.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM document_tags)"
        )

    def _get_unlocked(self, document_id: str) -> DocumentMeta | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        return self._row_to_meta(row) if row else None

    # -- public API --------------------------------------------------------

    def create_document(
        self, *, id: str, filename: str, content_hash: str, media_type: str,
        size_bytes: int, chunk_count: int, tags: list[str],
    ) -> DocumentMeta:
        with self._lock, self._conn:
            now = _now()
            self._conn.execute(
                "INSERT INTO documents (id, filename, content_hash, media_type, size_bytes,"
                " chunk_count, uploaded_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (id, filename, content_hash, media_type, size_bytes, chunk_count, now, now),
            )
            self._attach_tags(id, tags)
            return self._get_unlocked(id)  # type: ignore[return-value]

    def get(self, document_id: str) -> DocumentMeta | None:
        with self._lock:
            return self._get_unlocked(document_id)

    def get_many(self, ids: set[str]) -> list[DocumentMeta]:
        with self._lock:
            metas = (self._get_unlocked(i) for i in ids)
            return [m for m in metas if m]

    def get_by_hash(self, content_hash: str) -> DocumentMeta | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return self._row_to_meta(row) if row else None

    def get_by_filename(self, filename: str) -> DocumentMeta | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE filename = ? COLLATE NOCASE", (filename,)
            ).fetchone()
            return self._row_to_meta(row) if row else None

    def merge_tags(self, document_id: str, tags: list[str]) -> None:
        with self._lock, self._conn:
            self._attach_tags(document_id, tags)
            self._conn.execute(
                "UPDATE documents SET updated_at = ? WHERE id = ?", (_now(), document_id)
            )

    def update_filename(self, document_id: str, filename: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET filename = ?, updated_at = ? WHERE id = ?",
                (filename, _now(), document_id),
            )

    def replace_content(
        self, document_id: str, *, filename: str, content_hash: str,
        size_bytes: int, chunk_count: int, tags: list[str],
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET filename=?, content_hash=?, size_bytes=?,"
                " chunk_count=?, updated_at=? WHERE id=?",
                (filename, content_hash, size_bytes, chunk_count, _now(), document_id),
            )
            self._attach_tags(document_id, tags)

    def delete(self, document_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            self._prune_orphan_tags()
            return cur.rowcount > 0

    def list_documents(self) -> list[DocumentMeta]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM documents ORDER BY uploaded_at DESC"
            ).fetchall()
            return [self._row_to_meta(r) for r in rows]

    def count_documents(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def list_tags(self) -> list[tuple[str, int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT t.name, COUNT(dt.document_id) AS n FROM tags t "
                "JOIN document_tags dt ON dt.tag_id = t.id "
                "GROUP BY t.name ORDER BY t.name"
            ).fetchall()
            return [(r["name"], r["n"]) for r in rows]

    def ids_for_tags(self, tags: list[str], match: str) -> tuple[list[str], list[str]]:
        wanted = [normalize_tag(t) for t in tags]
        with self._lock:
            known = {
                r["name"] for r in self._conn.execute("SELECT name FROM tags").fetchall()
            }
            unknown = [t for t in wanted if t not in known]
            if unknown:
                return [], unknown
            placeholders = ",".join("?" * len(wanted))
            having = "HAVING COUNT(DISTINCT t.name) = ?" if match == "all" else ""
            params: list = [*wanted, len(wanted)] if match == "all" else [*wanted]
            rows = self._conn.execute(
                f"SELECT dt.document_id FROM document_tags dt "
                f"JOIN tags t ON t.id = dt.tag_id WHERE t.name IN ({placeholders}) "
                f"GROUP BY dt.document_id {having}",
                params,
            ).fetchall()
            return [r["document_id"] for r in rows], []

    def resolve_documents(self, refs: list[str]) -> tuple[list[DocumentMeta], list[str]]:
        metas: list[DocumentMeta] = []
        unknown: list[str] = []
        for ref in refs:
            meta = self.get(ref) or self.get_by_filename(ref)
            (metas if meta else unknown).append(meta if meta else ref)  # type: ignore[arg-type]
        return metas, unknown
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_metadata_repo.py -v`
Expected: 6 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: SQLite metadata repository with normalized tags and dedup lookups"
```

---

### Task 4: Chunker (structure-aware recursive splitter)

**Files:**
- Create: `app/ingestion/__init__.py`, `app/ingestion/chunker.py`, `tests/test_chunker.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `ParsedSection`, `Chunk` (Task 2).
- Produces:
  - `chunker.count_tokens(text: str) -> int`
  - `chunker.chunk_document(parsed: ParsedDocument, filename: str, document_id: str, target_tokens: int, overlap: float) -> list[Chunk]`
  - Constant `chunker.MIN_CHUNK_TOKENS = 50`

Behavior contract: split each section paragraphs → sentences → hard token cut; pack pieces up to `target_tokens`; carry ~`overlap * target_tokens` tokens of trailing pieces into the next chunk; merge a trailing chunk smaller than `MIN_CHUNK_TOKENS` into its predecessor (same section). `prefixed_text = "{filename} > {' > '.join(heading_path)} — {text}"` (heading part omitted when path empty). `chunk_index` global across sections, 0-based. Chunks inherit section `heading_path`/`page_start`/`page_end`.

- [ ] **Step 1: Write failing tests `tests/test_chunker.py`**

```python
from app.core.models import ParsedDocument, ParsedSection
from app.ingestion.chunker import MIN_CHUNK_TOKENS, chunk_document, count_tokens


def _doc(text: str, heading: list[str] | None = None) -> ParsedDocument:
    return ParsedDocument(
        sections=[ParsedSection(heading_path=heading or [], text=text, page_start=1, page_end=2)]
    )


def _long_text(sentences: int = 200) -> str:
    return " ".join(
        f"Sentence number {i} talks about the compliance policy in some detail."
        for i in range(sentences)
    )


def test_short_section_is_single_chunk():
    chunks = chunk_document(_doc("Hello world."), "a.txt", "d1", 450, 0.15)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "Hello world."


def test_long_section_splits_within_budget():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    assert len(chunks) > 1
    assert all(count_tokens(c.text) <= int(450 * 1.2) for c in chunks)


def test_overlap_repeats_trailing_sentence():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    last_sentence = chunks[0].text.split(". ")[-2]
    assert last_sentence in chunks[1].text


def test_no_tiny_trailing_chunk():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    assert count_tokens(chunks[-1].text) >= MIN_CHUNK_TOKENS


def test_prefix_contains_filename_and_headings():
    doc = ParsedDocument(sections=[
        ParsedSection(heading_path=["3 Client Tiers", "3.2 Limits"], text="Tier-2 caps apply.")
    ])
    chunks = chunk_document(doc, "aml-policy.pdf", "d1", 450, 0.15)
    assert chunks[0].prefixed_text == (
        "aml-policy.pdf > 3 Client Tiers > 3.2 Limits — Tier-2 caps apply."
    )
    assert chunks[0].text == "Tier-2 caps apply."


def test_chunk_index_global_across_sections():
    doc = ParsedDocument(sections=[
        ParsedSection(heading_path=["A"], text="First section."),
        ParsedSection(heading_path=["B"], text="Second section."),
    ])
    chunks = chunk_document(doc, "a.md", "d1", 450, 0.15)
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[1].heading_path == ["B"]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/ingestion/chunker.py` (+ empty `app/ingestion/__init__.py`)**

```python
import re

import tiktoken

from app.core.models import Chunk, ParsedDocument, ParsedSection

_ENC = tiktoken.get_encoding("cl100k_base")  # tokenizer family of text-embedding-3-*
MIN_CHUNK_TOKENS = 50
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_recursive(text: str, max_tokens: int) -> list[str]:
    """Split into pieces each <= max_tokens, preferring natural boundaries."""
    if count_tokens(text) <= max_tokens:
        return [text]
    for pattern in (_PARAGRAPH_RE, _SENTENCE_RE):
        parts = [p for p in pattern.split(text) if p.strip()]
        if len(parts) > 1:
            pieces: list[str] = []
            for part in parts:
                pieces.extend(_split_recursive(part, max_tokens))
            return pieces
    tokens = _ENC.encode(text)  # no separators left: hard cut
    return [_ENC.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]


def _pack(pieces: list[str], target: int, overlap_tokens: int) -> list[str]:
    """Greedily pack pieces into chunks near `target` tokens, piece-level overlap."""
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for piece in pieces:
        piece_tokens = count_tokens(piece)
        if buffer and size + piece_tokens > target:
            chunks.append(" ".join(buffer))
            carried: list[str] = []
            carried_size = 0
            for prev in reversed(buffer):
                prev_tokens = count_tokens(prev)
                if carried_size + prev_tokens > overlap_tokens:
                    break
                carried.insert(0, prev)
                carried_size += prev_tokens
            buffer, size = carried, carried_size
        buffer.append(piece)
        size += piece_tokens
    if buffer:
        last = " ".join(buffer)
        if chunks and count_tokens(last) < MIN_CHUNK_TOKENS:
            chunks[-1] = chunks[-1] + " " + last
        else:
            chunks.append(last)
    return chunks


def _prefix(filename: str, heading_path: list[str]) -> str:
    if heading_path:
        return f"{filename} > {' > '.join(heading_path)} — "
    return f"{filename} — "


def chunk_document(
    parsed: ParsedDocument, filename: str, document_id: str,
    target_tokens: int, overlap: float,
) -> list[Chunk]:
    overlap_tokens = int(target_tokens * overlap)
    chunks: list[Chunk] = []
    index = 0
    for section in parsed.sections:
        text = section.text.strip()
        if not text:
            continue
        pieces = _split_recursive(text, target_tokens)
        for body in _pack(pieces, target_tokens, overlap_tokens):
            chunks.append(_make_chunk(section, filename, document_id, index, body))
            index += 1
    return chunks


def _make_chunk(
    section: ParsedSection, filename: str, document_id: str, index: int, body: str
) -> Chunk:
    return Chunk(
        document_id=document_id,
        chunk_index=index,
        text=body,
        prefixed_text=_prefix(filename, section.heading_path) + body,
        heading_path=section.heading_path,
        page_start=section.page_start,
        page_end=section.page_end,
        token_count=count_tokens(body),
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: 6 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: structure-aware recursive chunker with overlap and contextual prefix"
```

---

### Task 5: Parsers (txt, markdown, PDF)

**Files:**
- Create: `app/ingestion/parsers.py`, `tests/test_parsers.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `ParsedSection`, `ParseError` (Task 2).
- Produces: `parsers.parse_document(filename: str, data: bytes) -> ParsedDocument`. Raises `ParseError` for unsupported extensions, corrupt files, or no extractable text.
  - txt → one section, no headings/pages.
  - md → sections at `#`-headings; `heading_path` = heading stack; no pages.
  - pdf → heading heuristic: line is heading when median char size > 1.15 × document body median AND < 80 chars AND doesn't end with '.'. Single-level `heading_path`. `page_start`/`page_end` per section.

- [ ] **Step 1: Write `tests/conftest.py` with a generated PDF fixture (reportlab, dev-dep)**

```python
import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Two-page PDF: 18pt headings, 10pt body — exercises the heading heuristic."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 780, "1 Purpose")
    c.setFont("Helvetica", 10)
    for i in range(3):
        c.drawString(72, 750 - 14 * i, f"This policy explains the purpose, line {i}")
    c.showPage()
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 780, "2 Client Tiers")
    c.setFont("Helvetica", 10)
    for i in range(3):
        c.drawString(72, 750 - 14 * i, f"Tier rules and transfer caps, line {i}")
    c.showPage()
    c.save()
    return buf.getvalue()
```

- [ ] **Step 2: Write failing tests `tests/test_parsers.py`**

```python
import pytest

from app.core.errors import ParseError
from app.ingestion.parsers import parse_document


def test_txt_single_section():
    doc = parse_document("notes.txt", b"Plain text body.")
    assert len(doc.sections) == 1
    assert doc.sections[0].heading_path == []
    assert doc.sections[0].page_start is None


def test_markdown_heading_stack():
    md = b"# Policy\nIntro text.\n\n## Limits\nCap is 10k.\n\n# Appendix\nEnd."
    doc = parse_document("p.md", md)
    paths = [s.heading_path for s in doc.sections]
    assert ["Policy"] in paths
    assert ["Policy", "Limits"] in paths
    assert ["Appendix"] in paths
    limits = next(s for s in doc.sections if s.heading_path == ["Policy", "Limits"])
    assert "Cap is 10k." in limits.text


def test_pdf_headings_and_pages(sample_pdf_bytes):
    doc = parse_document("policy.pdf", sample_pdf_bytes)
    headed = [s for s in doc.sections if s.heading_path]
    assert any(s.heading_path == ["1 Purpose"] and s.page_start == 1 for s in headed)
    assert any(s.heading_path == ["2 Client Tiers"] and s.page_start == 2 for s in headed)


def test_unsupported_extension():
    with pytest.raises(ParseError, match="Unsupported"):
        parse_document("sheet.xlsx", b"whatever")


def test_empty_content_rejected():
    with pytest.raises(ParseError, match="No extractable text"):
        parse_document("empty.txt", b"   ")
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest tests/test_parsers.py -v`
Expected: FAIL — `ModuleNotFoundError: app.ingestion.parsers`

- [ ] **Step 4: Implement `app/ingestion/parsers.py`**

```python
import io
import re
from statistics import median

import pdfplumber

from app.core.errors import ParseError
from app.core.models import ParsedDocument, ParsedSection

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PDF_HEADING_SIZE_RATIO = 1.15
_PDF_HEADING_MAX_CHARS = 80


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        doc = _parse_pdf(data)
    elif lower.endswith((".md", ".markdown")):
        doc = _parse_markdown(_decode(data))
    elif lower.endswith(".txt"):
        doc = ParsedDocument(sections=[ParsedSection(text=_decode(data))])
    else:
        raise ParseError(f"Unsupported file type: '{filename}'. Supported: .pdf, .txt, .md")
    if not any(s.text.strip() for s in doc.sections):
        raise ParseError(f"No extractable text in '{filename}'.")
    return doc


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _parse_markdown(text: str) -> ParsedDocument:
    sections: list[ParsedSection] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(ParsedSection(heading_path=[t for _, t in stack], text=body))
        buffer.clear()

    for line in text.splitlines():
        m = _MD_HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
        else:
            buffer.append(line)
    flush()
    return ParsedDocument(sections=sections)


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfplumber raises various types on corrupt input
        raise ParseError(f"Could not open PDF: {exc}") from exc

    with pdf:
        page_lines: list[tuple[int, str, float]] = []  # (page_no, text, median char size)
        for page_no, page in enumerate(pdf.pages, start=1):
            for line in page.extract_text_lines():
                sizes = [c["size"] for c in line["chars"]]
                if line["text"].strip() and sizes:
                    page_lines.append((page_no, line["text"].strip(), median(sizes)))

    if not page_lines:
        return ParsedDocument(sections=[])
    body_size = median(size for _, _, size in page_lines)

    sections: list[ParsedSection] = []
    heading: list[str] = []
    buffer: list[str] = []
    start_page = end_page = page_lines[0][0]

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(ParsedSection(
                heading_path=list(heading), text=body,
                page_start=start_page, page_end=end_page,
            ))
        buffer.clear()

    for page_no, text, size in page_lines:
        is_heading = (
            size > body_size * _PDF_HEADING_SIZE_RATIO
            and len(text) < _PDF_HEADING_MAX_CHARS
            and not text.endswith(".")
        )
        if is_heading:
            flush()
            heading = [text]
            start_page = page_no
        else:
            if not buffer:
                start_page = page_no
            buffer.append(text)
        end_page = page_no
    flush()
    return ParsedDocument(sections=sections)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_parsers.py -v`
Expected: 5 PASS. `extract_text_lines` exists from pdfplumber 0.11 — if missing, `uv sync` didn't resolve `>=0.11`.

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: txt/markdown/pdf parsers with heading detection and page provenance"
```

---

### Task 6: Embedders (OpenAI + deterministic fake)

**Files:**
- Create: `app/ingestion/embedder.py`, `tests/test_embedder.py`

**Interfaces:**
- Produces:
  - `embedder.Embedder` (Protocol): attr `dim: int`, method `embed(texts: list[str]) -> list[list[float]]`
  - `embedder.OpenAIEmbedder(api_key: str, model: str, dim: int, batch_size: int = 128, client=None)` — `client` injectable for tests
  - `embedder.FakeEmbedder(dim: int = 64)` — deterministic word-hash vectors; texts sharing words are cosine-closer than disjoint texts

- [ ] **Step 1: Write failing tests `tests/test_embedder.py`**

```python
import math

from app.ingestion.embedder import FakeEmbedder, OpenAIEmbedder


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def test_fake_is_deterministic():
    e = FakeEmbedder()
    assert e.embed(["hello world"]) == e.embed(["hello world"])


def test_fake_similarity_orders_by_shared_words():
    e = FakeEmbedder()
    q, close, far = e.embed([
        "transfer caps for tier-2 clients",
        "tier-2 clients have transfer caps of 10k",
        "vacation policy accrual rules",
    ])
    assert _cos(q, close) > _cos(q, far)


class _StubClient:
    class _Item:
        def __init__(self, vec):
            self.embedding = vec

    class _Resp:
        def __init__(self, n):
            self.data = [_StubClient._Item([0.0]) for _ in range(n)]

    def __init__(self):
        self.calls: list[int] = []
        self.embeddings = self

    def create(self, model: str, input: list[str]):
        self.calls.append(len(input))
        return _StubClient._Resp(len(input))


def test_openai_embedder_batches():
    stub = _StubClient()
    e = OpenAIEmbedder(api_key="x", model="m", dim=1, batch_size=2, client=stub)
    out = e.embed(["a", "b", "c", "d", "e"])
    assert stub.calls == [2, 2, 1]
    assert len(out) == 5
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/ingestion/embedder.py`**

```python
import hashlib
import math
from typing import Protocol

from openai import OpenAI


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Batched OpenAI embeddings. Retries/backoff handled by the SDK itself."""

    def __init__(
        self, api_key: str, model: str, dim: int, batch_size: int = 128, client=None
    ) -> None:
        self._client = client or OpenAI(api_key=api_key)
        self.model = model
        self.dim = dim
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in resp.data)
        return vectors


class FakeEmbedder:
    """Deterministic word-hash embeddings for tests: shared words => similar vectors."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            h = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_embedder.py -v`
Expected: 3 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: embedder protocol with batched OpenAI impl and deterministic fake"
```

---

### Task 7: Qdrant store (hybrid dense+BM25)

**Files:**
- Create: `app/stores/qdrant_store.py`, `tests/test_qdrant_store.py`

**Interfaces:**
- Consumes: `Chunk` (Task 2).
- Produces:
  - `qdrant_store.COLLECTION = "chunks"`, `qdrant_store.SPARSE_MODEL = "Qdrant/bm25"`
  - `qdrant_store.point_id(document_id: str, chunk_index: int) -> str` (uuid5)
  - `QdrantStore(client: QdrantClient, dense_dim: int)` with:
    - `ensure_collection() -> None` (idempotent)
    - `upsert_chunks(chunks: list[Chunk], dense_vectors: list[list[float]]) -> None`
    - `delete_document(document_id: str) -> None`
    - `hybrid_search(query_text: str, dense_query: list[float], limit: int, document_ids: list[str] | None = None) -> list` (Qdrant `ScoredPoint`s, payload included, RRF-fused)
    - `get_chunks(document_id: str, indices: list[int]) -> list` (records sorted by `chunk_index`)
    - `all_chunks(document_id: str) -> list` (records sorted by `chunk_index`)

First use of `Qdrant/bm25` downloads small model artifacts via fastembed (network needed once; Docker build pre-warms it in Task 12).

- [ ] **Step 1: Write failing tests `tests/test_qdrant_store.py`**

```python
import pytest
from qdrant_client import QdrantClient

from app.core.models import Chunk
from app.ingestion.embedder import FakeEmbedder
from app.stores.qdrant_store import QdrantStore, point_id


@pytest.fixture()
def store() -> QdrantStore:
    s = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    s.ensure_collection()
    return s


EMB = FakeEmbedder(dim=64)


def _chunk(doc_id: str, idx: int, text: str) -> Chunk:
    return Chunk(
        document_id=doc_id, chunk_index=idx, text=text,
        prefixed_text=f"doc.md — {text}", heading_path=[], token_count=5,
    )


def _ingest(store: QdrantStore, doc_id: str, texts: list[str]) -> None:
    chunks = [_chunk(doc_id, i, t) for i, t in enumerate(texts)]
    store.upsert_chunks(chunks, EMB.embed([c.prefixed_text for c in chunks]))


def test_point_id_deterministic():
    assert point_id("d1", 0) == point_id("d1", 0)
    assert point_id("d1", 0) != point_id("d1", 1)


def test_search_finds_relevant_chunk(store):
    _ingest(store, "d1", ["transfer caps for tier-2 clients are 10k"])
    _ingest(store, "d2", ["vacation accrual is 2 days per month"])
    query = "what are the transfer caps for tier-2 clients"
    hits = store.hybrid_search(query, EMB.embed([query])[0], limit=1)
    assert hits[0].payload["document_id"] == "d1"


def test_document_filter_scopes_search(store):
    _ingest(store, "d1", ["transfer caps for tier-2 clients"])
    _ingest(store, "d2", ["transfer caps for tier-3 partners"])
    query = "transfer caps"
    hits = store.hybrid_search(query, EMB.embed([query])[0], limit=5, document_ids=["d2"])
    assert {h.payload["document_id"] for h in hits} == {"d2"}


def test_upsert_is_idempotent(store):
    _ingest(store, "d1", ["alpha text", "beta text"])
    _ingest(store, "d1", ["alpha text", "beta text"])
    assert len(store.all_chunks("d1")) == 2


def test_delete_document_removes_all_points(store):
    _ingest(store, "d1", ["alpha", "beta"])
    store.delete_document("d1")
    assert store.all_chunks("d1") == []


def test_get_chunks_by_indices_sorted(store):
    _ingest(store, "d1", ["zero", "one", "two"])
    recs = store.get_chunks("d1", [2, 0])
    assert [r.payload["chunk_index"] for r in recs] == [0, 2]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_qdrant_store.py -v`
Expected: FAIL — `ModuleNotFoundError: app.stores.qdrant_store`

- [ ] **Step 3: Implement `app/stores/qdrant_store.py`**

```python
import uuid

from qdrant_client import QdrantClient, models

from app.core.models import Chunk

COLLECTION = "chunks"
SPARSE_MODEL = "Qdrant/bm25"


def point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk_index}"))


def _doc_filter(document_ids: list[str]) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))]
    )


class QdrantStore:
    """Vector store adapter. Payload holds only immutable-per-version chunk fields."""

    def __init__(self, client: QdrantClient, dense_dim: int) -> None:
        self._client = client
        self._dense_dim = dense_dim

    def ensure_collection(self) -> None:
        if self._client.collection_exists(COLLECTION):
            return
        self._client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=self._dense_dim, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )

    def upsert_chunks(self, chunks: list[Chunk], dense_vectors: list[list[float]]) -> None:
        points = [
            models.PointStruct(
                id=point_id(c.document_id, c.chunk_index),
                vector={
                    "dense": v,
                    "sparse": models.Document(text=c.prefixed_text, model=SPARSE_MODEL),
                },
                payload={
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "heading_path": c.heading_path,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "token_count": c.token_count,
                },
            )
            for c, v in zip(chunks, dense_vectors, strict=True)
        ]
        self._client.upsert(collection_name=COLLECTION, points=points)

    def delete_document(self, document_id: str) -> None:
        self._client.delete(
            collection_name=COLLECTION,
            points_selector=models.FilterSelector(filter=_doc_filter([document_id])),
        )

    def hybrid_search(
        self, query_text: str, dense_query: list[float], limit: int,
        document_ids: list[str] | None = None,
    ) -> list:
        qfilter = _doc_filter(document_ids) if document_ids else None
        result = self._client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                models.Prefetch(query=dense_query, using="dense", limit=20, filter=qfilter),
                models.Prefetch(
                    query=models.Document(text=query_text, model=SPARSE_MODEL),
                    using="sparse", limit=20, filter=qfilter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return result.points

    def get_chunks(self, document_id: str, indices: list[int]) -> list:
        ids = [point_id(document_id, i) for i in indices]
        recs = self._client.retrieve(collection_name=COLLECTION, ids=ids, with_payload=True)
        return sorted(recs, key=lambda r: r.payload["chunk_index"])

    def all_chunks(self, document_id: str) -> list:
        points, _ = self._client.scroll(
            collection_name=COLLECTION,
            scroll_filter=_doc_filter([document_id]),
            limit=10_000,
            with_payload=True,
        )
        return sorted(points, key=lambda p: p.payload["chunk_index"])
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_qdrant_store.py -v`
Expected: 6 PASS (first run downloads BM25 artifacts — allow ~30s once). If `models.Document` upsert fails in local mode, replace sparse entries with explicit vectors: `from fastembed import SparseTextEmbedding; se = SparseTextEmbedding(SPARSE_MODEL)` then `models.SparseVector(indices=emb.indices.tolist(), values=emb.values.tolist())` for `emb in se.embed(texts)` — same for the query path via `se.query_embed(query_text)`.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: qdrant store with named dense+sparse vectors and RRF hybrid search"
```

---

### Task 8: Ingestion pipeline (dedup + transactional ordering)

**Files:**
- Create: `app/ingestion/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `MetadataRepo` (Task 3), `QdrantStore` (Task 7), `Embedder` (Task 6), `parse_document` (Task 5), `chunk_document` (Task 4), `ParseError`.
- Produces:
  - `pipeline.MAX_UPLOAD_BYTES = 20 * 1024 * 1024`
  - `pipeline.IngestResult` (dataclass: `document: DocumentMeta`, `outcome: str` — `"created" | "updated" | "unchanged"`)
  - `IngestionPipeline(repo, store, embedder, chunk_tokens: int, chunk_overlap: float)` with:
    - `ingest(filename: str, data: bytes, tags: list[str]) -> IngestResult`
    - `delete(document_id: str) -> bool` (points first, then metadata row; returns repo result)

- [ ] **Step 1: Write failing tests `tests/test_pipeline.py`**

```python
import pytest
from qdrant_client import QdrantClient

from app.core.errors import ParseError
from app.ingestion.embedder import FakeEmbedder
from app.ingestion.pipeline import IngestionPipeline
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore


@pytest.fixture()
def env(tmp_path):
    repo = MetadataRepo(str(tmp_path / "meta.db"))
    store = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    pipeline = IngestionPipeline(repo, store, FakeEmbedder(dim=64), 450, 0.15)
    return repo, store, pipeline


DOC_V1 = b"# Policy\nTier-2 transfer caps are 10k per day."
DOC_V2 = b"# Policy\nTier-2 transfer caps are 20k per day, effective July."


def test_new_document_created(env):
    repo, store, pipeline = env
    result = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    assert result.outcome == "created"
    assert result.document.chunk_count == len(store.all_chunks(result.document.id))
    assert result.document.tags == ["compliance"]


def test_rule1_same_hash_is_noop_with_tag_merge(env):
    repo, store, pipeline = env
    first = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    again = pipeline.ingest("policy-renamed.md", DOC_V1, ["hr"])
    assert again.outcome == "unchanged"
    assert again.document.id == first.document.id
    assert again.document.filename == "policy-renamed.md"
    assert sorted(again.document.tags) == ["compliance", "hr"]
    assert len(store.all_chunks(first.document.id)) == first.document.chunk_count


def test_rule2_same_name_new_hash_replaces(env):
    repo, store, pipeline = env
    first = pipeline.ingest("policy.md", DOC_V1, ["compliance"])
    second = pipeline.ingest("policy.md", DOC_V2, [])
    assert second.outcome == "updated"
    assert second.document.id == first.document.id
    assert second.document.content_hash != first.document.content_hash
    texts = " ".join(p.payload["text"] for p in store.all_chunks(first.document.id))
    assert "20k" in texts and "10k" not in texts


def test_rule3_distinct_files_coexist(env):
    repo, store, pipeline = env
    a = pipeline.ingest("a.md", DOC_V1, [])
    b = pipeline.ingest("b.md", DOC_V2, [])
    assert a.document.id != b.document.id
    assert repo.count_documents() == 2


def test_oversized_upload_rejected(env):
    _, _, pipeline = env
    with pytest.raises(ParseError, match="20MB"):
        pipeline.ingest("big.txt", b"x" * (20 * 1024 * 1024 + 1), [])


def test_failed_upsert_leaves_no_metadata(env, monkeypatch):
    repo, store, pipeline = env
    monkeypatch.setattr(store, "upsert_chunks", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        pipeline.ingest("policy.md", DOC_V1, [])
    assert repo.count_documents() == 0


def test_delete_removes_points_and_row(env):
    repo, store, pipeline = env
    result = pipeline.ingest("policy.md", DOC_V1, [])
    assert pipeline.delete(result.document.id) is True
    assert repo.get(result.document.id) is None
    assert store.all_chunks(result.document.id) == []
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/ingestion/pipeline.py`**

```python
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ParseError
from app.core.models import DocumentMeta
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import Embedder
from app.ingestion.parsers import parse_document
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@dataclass
class IngestResult:
    document: DocumentMeta
    outcome: str  # "created" | "updated" | "unchanged"


class IngestionPipeline:
    """Parse -> chunk -> embed -> upsert vectors -> write metadata (in that order).

    Metadata is written LAST so it never references chunks that don't exist;
    on failure after vector writes begin, this document's points are deleted.
    """

    def __init__(
        self, repo: MetadataRepo, store: QdrantStore, embedder: Embedder,
        chunk_tokens: int, chunk_overlap: float,
    ) -> None:
        self._repo = repo
        self._store = store
        self._embedder = embedder
        self._chunk_tokens = chunk_tokens
        self._chunk_overlap = chunk_overlap

    def ingest(self, filename: str, data: bytes, tags: list[str]) -> IngestResult:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ParseError("File exceeds the 20MB upload limit.")
        content_hash = hashlib.sha256(data).hexdigest()

        existing = self._repo.get_by_hash(content_hash)
        if existing is not None:  # dedup rule 1: identical content
            self._repo.merge_tags(existing.id, tags)
            if existing.filename != filename:
                self._repo.update_filename(existing.id, filename)
            return IngestResult(self._repo.get(existing.id), "unchanged")

        # All pure computation happens before any write.
        parsed = parse_document(filename, data)
        same_name = self._repo.get_by_filename(filename)
        if same_name is not None:  # dedup rule 2: new version of a known file
            document_id, outcome = same_name.id, "updated"
        else:  # dedup rule 3: brand-new document
            document_id, outcome = str(uuid.uuid4()), "created"

        chunks = chunk_document(
            parsed, filename, document_id, self._chunk_tokens, self._chunk_overlap
        )
        vectors = self._embedder.embed([c.prefixed_text for c in chunks])

        self._store.ensure_collection()
        if same_name is not None:
            # Delete-first: v2 may produce fewer chunks than v1 (stale-point risk).
            self._store.delete_document(document_id)
        try:
            self._store.upsert_chunks(chunks, vectors)
            if same_name is not None:
                self._repo.replace_content(
                    document_id, filename=filename, content_hash=content_hash,
                    size_bytes=len(data), chunk_count=len(chunks), tags=tags,
                )
            else:
                self._repo.create_document(
                    id=document_id, filename=filename, content_hash=content_hash,
                    media_type=_media_type(filename), size_bytes=len(data),
                    chunk_count=len(chunks), tags=tags,
                )
        except Exception:
            self._store.delete_document(document_id)
            raise
        return IngestResult(self._repo.get(document_id), outcome)

    def delete(self, document_id: str) -> bool:
        self._store.delete_document(document_id)
        return self._repo.delete(document_id)


def _media_type(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower() or "unknown"
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: 7 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: ingestion pipeline with three-rule dedup and write-ordering cleanup"
```

---

### Task 9: Retrieval service (search, outline, expand)

**Files:**
- Create: `app/retrieval/__init__.py`, `app/retrieval/service.py`, `tests/test_search_service.py`

**Interfaces:**
- Consumes: `MetadataRepo`, `QdrantStore`, `Embedder`, errors, `closest_matches`.
- Produces: `SearchService(repo, store, embedder)` with:
  - `search(query: str, top_k: int = 8, tags: list[str] | None = None, tag_match: str = "any", documents: list[str] | None = None) -> dict` — the result envelope
  - `outline(document_ref: str) -> dict`
  - `expand(document_id: str, chunk_index: int, before: int = 1, after: int = 1) -> dict`
  - Raises `UnknownTagsError` / `UnknownDocumentsError` with guidance messages (available values + fuzzy suggestions).

Envelope (exact shape):

```json
{
  "query": "...",
  "results": [{
    "rank": 1,
    "text": "raw chunk text",
    "document": {"id": "...", "filename": "aml-policy.pdf", "tags": ["compliance"]},
    "location": {"pages": [4, 5], "heading_path": ["3 Client Tiers"], "chunk_index": 12}
  }],
  "documents_searched": 12
}
```

`pages` is `null` for txt/md; `heading_path` is `null` when empty.

- [ ] **Step 1: Write failing tests `tests/test_search_service.py`**

```python
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
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_search_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/retrieval/service.py` (+ empty `app/retrieval/__init__.py`)**

```python
from app.core.errors import UnknownDocumentsError, UnknownTagsError
from app.core.models import DocumentMeta
from app.core.text import closest_matches, normalize_tag
from app.ingestion.embedder import Embedder
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore


class SearchService:
    """Hybrid retrieval over the knowledge base. Single code path for all scopes."""

    def __init__(self, repo: MetadataRepo, store: QdrantStore, embedder: Embedder) -> None:
        self._repo = repo
        self._store = store
        self._embedder = embedder

    # -- public API --------------------------------------------------------

    def search(
        self, query: str, top_k: int = 8, tags: list[str] | None = None,
        tag_match: str = "any", documents: list[str] | None = None,
    ) -> dict:
        doc_ids: list[str] | None = None
        if tags:
            doc_ids = self._resolve_tags(tags, tag_match)
        if documents:
            doc_ids = [m.id for m in self._resolve_documents(documents)]

        if doc_ids == []:  # valid scope, zero matching docs (e.g. tag_match="all")
            return {"query": query, "results": [], "documents_searched": 0}

        dense = self._embedder.embed([query])[0]
        points = self._store.hybrid_search(query, dense, limit=top_k, document_ids=doc_ids)
        metas = {
            m.id: m
            for m in self._repo.get_many({p.payload["document_id"] for p in points})
        }
        results = [
            self._result(rank, p.payload, metas[p.payload["document_id"]])
            for rank, p in enumerate(points, start=1)
        ]
        searched = len(doc_ids) if doc_ids is not None else self._repo.count_documents()
        return {"query": query, "results": results, "documents_searched": searched}

    def outline(self, document_ref: str) -> dict:
        meta = self._resolve_documents([document_ref])[0]
        entries: list[dict] = []
        for point in self._store.all_chunks(meta.id):
            path = point.payload.get("heading_path") or []
            heading = " > ".join(path) if path else "(no heading)"
            if entries and entries[-1]["heading"] == heading:
                entries[-1]["chunk_count"] += 1
                if point.payload.get("page_end") is not None:
                    entries[-1]["pages"][1] = point.payload["page_end"]
            else:
                pages = None
                if point.payload.get("page_start") is not None:
                    pages = [point.payload["page_start"], point.payload["page_end"]]
                entries.append({"heading": heading, "pages": pages, "chunk_count": 1})
        return {
            "document": {"id": meta.id, "filename": meta.filename, "tags": meta.tags},
            "outline": entries,
        }

    def expand(
        self, document_id: str, chunk_index: int, before: int = 1, after: int = 1
    ) -> dict:
        meta = self._repo.get(document_id)
        if meta is None:
            raise UnknownDocumentsError(
                f"No document with id '{document_id}'. "
                "Use list_documents to see valid ids, or search results' document.id."
            )
        before, after = min(before, 3), min(after, 3)
        lo = max(0, chunk_index - before)
        hi = min(meta.chunk_count - 1, chunk_index + after)
        recs = self._store.get_chunks(document_id, list(range(lo, hi + 1)))
        return {
            "document": {"id": meta.id, "filename": meta.filename, "tags": meta.tags},
            "chunks": [
                {
                    "chunk_index": r.payload["chunk_index"],
                    "text": r.payload["text"],
                    "location": self._location(r.payload),
                }
                for r in recs
            ],
        }

    # -- internals -----------------------------------------------------------

    def _resolve_tags(self, tags: list[str], match: str) -> list[str]:
        ids, unknown = self._repo.ids_for_tags(tags, match)
        if unknown:
            available = ", ".join(f"{n} ({c} docs)" for n, c in self._repo.list_tags())
            names = [n for n, _ in self._repo.list_tags()]
            hints = [
                s for t in unknown for s in closest_matches(normalize_tag(t), names)
            ]
            hint = f" Did you mean: {', '.join(dict.fromkeys(hints))}?" if hints else ""
            raise UnknownTagsError(
                f"No documents carry tag(s): {', '.join(unknown)}. "
                f"Available tags: {available or '(none yet)'}.{hint}"
            )
        return ids

    def _resolve_documents(self, refs: list[str]) -> list[DocumentMeta]:
        metas, unknown = self._repo.resolve_documents(refs)
        if unknown:
            names = [d.filename for d in self._repo.list_documents()]
            hints = [s for r in unknown for s in closest_matches(r, names)]
            hint = (
                f" Closest existing filenames: {', '.join(dict.fromkeys(hints))}."
                if hints else ""
            )
            raise UnknownDocumentsError(
                f"No document matches: {', '.join(unknown)}.{hint} "
                "Call list_documents for the full inventory."
            )
        return metas

    @staticmethod
    def _location(payload: dict) -> dict:
        pages = None
        if payload.get("page_start") is not None:
            pages = [payload["page_start"], payload["page_end"]]
        return {
            "pages": pages,
            "heading_path": payload.get("heading_path") or None,
            "chunk_index": payload["chunk_index"],
        }

    def _result(self, rank: int, payload: dict, meta: DocumentMeta) -> dict:
        return {
            "rank": rank,
            "text": payload["text"],
            "document": {"id": meta.id, "filename": meta.filename, "tags": meta.tags},
            "location": self._location(payload),
        }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_search_service.py -v`
Expected: 8 PASS

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: retrieval service with scoped hybrid search, outline, expand, guidance errors"
```

---

### Task 10: MCP server (7 tools) + Bearer auth

**Files:**
- Create: `app/mcp_server/__init__.py`, `app/mcp_server/auth.py`, `app/mcp_server/server.py`, `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `SearchService` (Task 9), `MetadataRepo` (Task 3), `DocIntelError`.
- Produces:
  - `auth.BearerAuthMiddleware(app: ASGIApp, token: str)` — pure ASGI wrapper, 401 + `WWW-Authenticate: Bearer` unless `Authorization: Bearer <token>` matches (constant-time).
  - `server.build_mcp(service: SearchService, repo: MetadataRepo) -> MCPServer`
  - Tool names (fixed): `list_documents`, `list_tags`, `search`, `search_by_tag`, `search_by_document`, `get_document_outline`, `expand_chunk`.

The tool descriptions below ARE the deliverable being evaluated — copy them verbatim; do not paraphrase or shorten.

- [ ] **Step 1: Write failing tests `tests/test_mcp_server.py`**

Tests exercise the real Streamable HTTP transport in-process (stateless + JSON responses) via raw JSON-RPC POSTs — covering transport, auth, and tool wiring end-to-end.

```python
import contextlib

import httpx
import pytest
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


@pytest.fixture()
async def client(tmp_path):
    repo = MetadataRepo(str(tmp_path / "meta.db"))
    store = QdrantStore(QdrantClient(":memory:"), dense_dim=64)
    emb = FakeEmbedder(dim=64)
    pipeline = IngestionPipeline(repo, store, emb, 450, 0.15)
    pipeline.ingest(
        "aml-policy.md",
        b"# AML Policy\nTier-2 transfer caps are 10k per day.",
        ["compliance"],
    )
    mcp = build_mcp(SearchService(repo, store, emb), repo)
    inner = mcp.streamable_http_app(stateless_http=True, json_response=True)
    app = Starlette(routes=[Mount("/mcp", app=BearerAuthMiddleware(inner, TOKEN))])
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        transport = httpx.ASGITransport(app=app)
        yield httpx.AsyncClient(transport=transport, base_url="http://test")


def _rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


async def test_missing_token_is_401(client):
    r = await client.post("/mcp", json=_rpc("tools/list"),
                          headers={k: v for k, v in HEADERS.items() if k != "Authorization"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_wrong_token_is_401(client):
    r = await client.post("/mcp", json=_rpc("tools/list"),
                          headers={**HEADERS, "Authorization": "Bearer wrong"})
    assert r.status_code == 401


async def test_tools_list_names(client):
    r = await client.post("/mcp", json=_rpc("tools/list"), headers=HEADERS)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {
        "list_documents", "list_tags", "search", "search_by_tag",
        "search_by_document", "get_document_outline", "expand_chunk",
    }


async def test_search_tool_call(client):
    r = await client.post("/mcp", json=_rpc(
        "tools/call",
        {"name": "search", "arguments": {"query": "tier-2 transfer caps"}},
    ), headers=HEADERS)
    assert r.status_code == 200
    payload = r.json()["result"]
    assert payload.get("isError") is not True
    structured = payload["structuredContent"]
    assert structured["results"][0]["document"]["filename"] == "aml-policy.md"


async def test_unknown_tag_returns_guidance_not_exception(client):
    r = await client.post("/mcp", json=_rpc(
        "tools/call",
        {"name": "search_by_tag", "arguments": {"query": "x", "tags": ["complaince"]}},
    ), headers=HEADERS)
    assert r.status_code == 200
    structured = r.json()["result"]["structuredContent"]
    assert structured["error"] == "unknown_tags"
    assert "compliance" in structured["message"]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/mcp_server/auth.py`**

```python
import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Static Bearer-token gate for the MCP mount. Constant-time comparison."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        provided = headers.get(b"authorization", b"").decode("latin-1")
        if not secrets.compare_digest(provided, self._expected):
            response = JSONResponse(
                {"error": "unauthorized", "message": "Send 'Authorization: Bearer <MCP_API_KEY>'."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
```

- [ ] **Step 4: Implement `app/mcp_server/server.py`**

```python
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from app.core.errors import DocIntelError
from app.retrieval.service import SearchService
from app.stores.metadata_repo import MetadataRepo

INSTRUCTIONS = (
    "This server exposes a company knowledge base of internal documents "
    "(compliance policies, product manuals, onboarding guides, FAQs). Ground your "
    "answers in retrieved chunks and cite each source as filename plus the pages or "
    "heading found in the result's `location`. Start broad with `search`; narrow with "
    "`search_by_tag` or `search_by_document` when the question clearly targets a topic "
    "or a specific document. Tools never modify the knowledge base."
)

TopK = Annotated[int, Field(ge=1, le=25, description="Number of chunks to return.")]


def build_mcp(service: SearchService, repo: MetadataRepo) -> MCPServer:
    mcp = MCPServer("document-intelligence", instructions=INSTRUCTIONS)

    def guarded(fn, /, *args, **kwargs) -> dict:
        """Convert domain errors into structured guidance the agent can act on."""
        try:
            return fn(*args, **kwargs)
        except DocIntelError as exc:
            return {"error": exc.code, "message": exc.message}

    @mcp.tool()
    def list_documents() -> dict:
        """List every document in the knowledge base with its metadata.

        Use this to discover what documents exist (e.g. before choosing a scoped
        search, or to answer "which documents cover X" by name). Returns id,
        filename, tags, chunk_count and timestamps per document. This is NOT a
        content search — for questions about what documents SAY, use `search`.
        """
        docs = repo.list_documents()
        return {
            "documents": [
                {
                    "id": d.id, "filename": d.filename, "tags": d.tags,
                    "chunk_count": d.chunk_count,
                    "uploaded_at": d.uploaded_at.isoformat(),
                    "updated_at": d.updated_at.isoformat(),
                }
                for d in docs
            ],
            "total": len(docs),
        }

    @mcp.tool()
    def list_tags() -> dict:
        """List all tags in use, with the number of documents carrying each.

        Use this before `search_by_tag` when you are unsure which topic tags
        exist, or to answer "what topic areas does the knowledge base cover".
        Tags are lowercase labels assigned by humans at upload time (e.g.
        'compliance', 'hr', 'onboarding', 'product').
        """
        return {"tags": [{"name": n, "document_count": c} for n, c in repo.list_tags()]}

    @mcp.tool()
    def search(query: str, top_k: TopK = 8) -> dict:
        """Semantic + keyword (hybrid) search across the ENTIRE knowledge base.

        The default search tool: use it when the question does not clearly
        belong to one topic area or one known document. Matches by meaning AND
        by exact terms, so include distinctive identifiers from the user's
        question (codes, acronyms, product names) verbatim in `query`. Returns
        the top_k most relevant chunks with their source document and a
        `location` (pages / heading_path) to cite. If results look off-topic,
        try `list_tags` + `search_by_tag` to narrow the scope.
        """
        return guarded(service.search, query, top_k=top_k)

    @mcp.tool()
    def search_by_tag(
        query: str,
        tags: Annotated[list[str], Field(min_length=1, description="Tags to restrict to.")],
        tag_match: Annotated[
            str,
            Field(pattern="^(any|all)$",
                  description="'any' = documents with at least one tag; 'all' = every tag."),
        ] = "any",
        top_k: TopK = 8,
    ) -> dict:
        """Hybrid search restricted to documents carrying the given tags.

        Use when the question clearly belongs to a topic area (e.g. compliance
        rules, HR policy, product behavior) — scoping by tag removes noise from
        unrelated departments. Call `list_tags` first if unsure which tags
        exist; unknown tags return an error listing valid ones. For questions
        with no obvious topic, prefer `search`.
        """
        return guarded(service.search, query, top_k=top_k, tags=tags, tag_match=tag_match)

    @mcp.tool()
    def search_by_document(
        query: str,
        documents: Annotated[
            list[str],
            Field(min_length=1, description="Document ids or exact filenames."),
        ],
        top_k: TopK = 8,
    ) -> dict:
        """Hybrid search restricted to specific documents (by id or filename).

        Use when the user names a document ("what does the AML policy say
        about...") or when a previous result identified the right document and
        you want to dig deeper into it. Accepts document ids (preferred, from
        earlier results) or exact filenames; unknown references return an error
        with the closest existing filenames.
        """
        return guarded(service.search, query, top_k=top_k, documents=documents)

    @mcp.tool()
    def get_document_outline(
        document: Annotated[str, Field(description="Document id or exact filename.")],
    ) -> dict:
        """Return one document's structure: headings, page ranges, chunk counts.

        Use to answer "what does document X cover" without a content search, or
        to decide whether `search_by_document` is worthwhile and how to phrase
        it (echoing a heading's wording into the query improves matching).
        Returns no chunk text — only structure.
        """
        return guarded(service.outline, document)

    @mcp.tool()
    def expand_chunk(
        document_id: Annotated[str, Field(description="`document.id` from a search result.")],
        chunk_index: Annotated[int, Field(ge=0, description="`location.chunk_index` from a search result.")],
        before: Annotated[int, Field(ge=0, le=3, description="Chunks before (max 3).")] = 1,
        after: Annotated[int, Field(ge=0, le=3, description="Chunks after (max 3).")] = 1,
    ) -> dict:
        """Fetch the chunks surrounding a search hit, in document order.

        Use when a search result clearly contains the answer but is cut off or
        references nearby context ("the limits above", a continuing table or
        list). Take `document_id` and `chunk_index` directly from that result.
        Bounded on purpose — for broader digging, use `search_by_document`.
        """
        return guarded(service.expand, document_id, chunk_index, before=before, after=after)

    return mcp
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: 5 PASS.
API drift checks if anything errors (SDK v2 moved serving config out of the constructor):
- `uv run python -c "from mcp.server import MCPServer; import inspect; print(inspect.signature(MCPServer.streamable_http_app))"` — adjust `stateless_http`/`json_response` kwarg placement to whatever this prints.
- If the mounted endpoint 404s, the inner app may already serve at `/mcp` internally: check for a `streamable_http_path` kwarg in the same signature and set it to `"/"`, or change the test/mount path accordingly. The externally visible endpoint MUST be `POST /mcp`.
- If `structuredContent` is absent in responses, tool return-type is not being inferred as structured; print the raw response and check `result.content[0].text` — then consult the SDK docs for structured output (`Do not guess`).

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: MCP server with 7 agent-ready tools over Streamable HTTP + bearer auth"
```

---

### Task 11: Web UI, REST API, Basic auth, healthz, app assembly

**Files:**
- Create: `app/web/__init__.py`, `app/web/auth.py`, `app/web/routes.py`, `app/web/templates/index.html`, `app/main.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `IngestionPipeline`, `MetadataRepo`, `SearchService`, `build_mcp`, `BearerAuthMiddleware`, `get_settings`.
- Produces:
  - `web.auth.BasicAuthMiddleware(app, password: str, exempt_prefixes: tuple[str, ...])` — HTTP Basic (any username), skips exempt path prefixes.
  - `web.routes.build_router(pipeline, repo, templates) -> APIRouter` with: `GET /` (HTML), `POST /api/documents` (multipart: `file`, `tags` comma-separated form field) → 201 `{document, outcome}` (200 when `outcome == "unchanged"`), `GET /api/documents`, `DELETE /api/documents/{doc_id}` → 204 or 404, `GET /api/tags`.
  - `main.create_app(settings=None, embedder=None, qdrant_client=None) -> FastAPI` (overrides for tests) and module-level `app = create_app()` for uvicorn. `GET /healthz` unauthenticated.

- [ ] **Step 1: Write failing tests `tests/test_web.py`**

```python
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
        settings=settings, embedder=FakeEmbedder(dim=64), qdrant_client=QdrantClient(":memory:"),
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
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_web.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/web/auth.py`**

```python
import base64
import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BasicAuthMiddleware:
    """HTTP Basic gate for the management UI/API. Any username; shared password."""

    def __init__(self, app: ASGIApp, password: str, exempt_prefixes: tuple[str, ...]) -> None:
        self._app = app
        self._password = password
        self._exempt = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(self._exempt):
            await self._app(scope, receive, send)
            return
        provided = self._extract_password(scope)
        if provided is None or not secrets.compare_digest(provided, self._password):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="document-intelligence"'},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    def _extract_password(scope: Scope) -> str | None:
        header = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        if not header.startswith("Basic "):
            return None
        try:
            decoded = base64.b64decode(header[6:]).decode()
        except Exception:
            return None
        return decoded.split(":", 1)[1] if ":" in decoded else None
```

- [ ] **Step 4: Implement `app/web/routes.py`**

```python
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.errors import DocIntelError
from app.ingestion.pipeline import IngestionPipeline
from app.stores.metadata_repo import MetadataRepo


def build_router(
    pipeline: IngestionPipeline, repo: MetadataRepo, templates: Jinja2Templates
) -> APIRouter:
    router = APIRouter()

    def _doc_json(meta) -> dict:
        return {
            "id": meta.id, "filename": meta.filename, "tags": meta.tags,
            "media_type": meta.media_type, "size_bytes": meta.size_bytes,
            "chunk_count": meta.chunk_count,
            "uploaded_at": meta.uploaded_at.isoformat(),
            "updated_at": meta.updated_at.isoformat(),
        }

    @router.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {
            "documents": repo.list_documents(),
            "tags": [name for name, _ in repo.list_tags()],
        })

    @router.post("/api/documents")
    def upload(file: UploadFile, tags: str = Form("")):
        tag_list = [t for t in (s.strip() for s in tags.split(",")) if t]
        try:
            result = pipeline.ingest(file.filename or "unnamed", file.file.read(), tag_list)
        except DocIntelError as exc:
            return JSONResponse({"error": exc.code, "message": exc.message}, status_code=400)
        status = 200 if result.outcome == "unchanged" else 201
        return JSONResponse(
            {"document": _doc_json(result.document), "outcome": result.outcome},
            status_code=status,
        )

    @router.get("/api/documents")
    def list_documents():
        return {"documents": [_doc_json(d) for d in repo.list_documents()]}

    @router.delete("/api/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str):
        if not pipeline.delete(doc_id):
            return JSONResponse(
                {"error": "not_found", "message": f"No document with id '{doc_id}'."},
                status_code=404,
            )

    @router.get("/api/tags")
    def list_tags():
        return {"tags": [{"name": n, "document_count": c} for n, c in repo.list_tags()]}

    return router
```

- [ ] **Step 5: Implement `app/web/templates/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Document Intelligence — Knowledge Base</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 60rem; margin: 2rem auto; padding: 0 1rem; }
    table { border-collapse: collapse; width: 100%; margin-top: 1.5rem; }
    th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #ddd; }
    .tag { background: #eef; border-radius: 3px; padding: .1rem .4rem; margin-right: .25rem; font-size: .85em; }
    form { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
    #status { margin-left: .5rem; }
    button { cursor: pointer; }
  </style>
</head>
<body>
  <h1>Knowledge Base</h1>
  <form id="upload-form">
    <input type="file" name="file" accept=".pdf,.txt,.md" required>
    <input type="text" name="tags" placeholder="tags, comma-separated" list="known-tags">
    <datalist id="known-tags">
      {% for tag in tags %}<option value="{{ tag }}">{% endfor %}
    </datalist>
    <button type="submit">Upload</button>
    <span id="status"></span>
  </form>

  <table>
    <thead>
      <tr><th>Filename</th><th>Tags</th><th>Chunks</th><th>Uploaded</th><th></th></tr>
    </thead>
    <tbody>
      {% for doc in documents %}
      <tr>
        <td>{{ doc.filename }}</td>
        <td>{% for tag in doc.tags %}<span class="tag">{{ tag }}</span>{% endfor %}</td>
        <td>{{ doc.chunk_count }}</td>
        <td>{{ doc.uploaded_at.strftime("%Y-%m-%d %H:%M") }}</td>
        <td><button data-id="{{ doc.id }}" class="delete">Delete</button></td>
      </tr>
      {% else %}
      <tr><td colspan="5">No documents yet — upload one above.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <script>
    const status = document.getElementById("status");
    document.getElementById("upload-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      status.textContent = "Uploading…";
      const resp = await fetch("/api/documents", { method: "POST", body: new FormData(e.target) });
      const body = await resp.json();
      if (!resp.ok) { status.textContent = body.message || "Upload failed"; return; }
      location.reload();
    });
    document.querySelectorAll("button.delete").forEach((btn) =>
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this document and all its chunks?")) return;
        await fetch(`/api/documents/${btn.dataset.id}`, { method: "DELETE" });
        location.reload();
      })
    );
  </script>
</body>
</html>
```

- [ ] **Step 6: Implement `app/main.py`**

```python
import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.ingestion.embedder import Embedder, OpenAIEmbedder
from app.ingestion.pipeline import IngestionPipeline
from app.mcp_server.auth import BearerAuthMiddleware
from app.mcp_server.server import build_mcp
from app.retrieval.service import SearchService
from app.stores.metadata_repo import MetadataRepo
from app.stores.qdrant_store import QdrantStore
from app.web.auth import BasicAuthMiddleware
from app.web.routes import build_router

TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"


def create_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    qdrant_client: QdrantClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    repo = MetadataRepo(settings.db_path)
    qclient = qdrant_client or QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key
    )
    store = QdrantStore(qclient, settings.embed_dim)
    embedder = embedder or OpenAIEmbedder(
        api_key=settings.openai_api_key, model=settings.embed_model, dim=settings.embed_dim
    )
    pipeline = IngestionPipeline(
        repo, store, embedder, settings.chunk_tokens, settings.chunk_overlap
    )
    service = SearchService(repo, store, embedder)

    mcp = build_mcp(service, repo)
    mcp_asgi = BearerAuthMiddleware(
        mcp.streamable_http_app(stateless_http=True), settings.mcp_api_key
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Mounted sub-apps' lifespans never run: the host must run the session manager.
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Document Intelligence Server", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        repo.count_documents()          # SQLite reachable
        qclient.get_collections()       # Qdrant reachable
        return {"status": "ok"}

    app.mount("/mcp", mcp_asgi)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.include_router(build_router(pipeline, repo, templates))
    app.add_middleware(
        BasicAuthMiddleware, password=settings.ui_password,
        exempt_prefixes=("/mcp", "/healthz"),
    )
    return app


app = create_app()
```

Note: `app = create_app()` at import time requires env vars only in production; tests always call `create_app(...)` with overrides. If module-level instantiation bothers test collection (it builds a real `QdrantClient` toward `settings.qdrant_url` — construction does not connect, so it should not), guard it: `if os.getenv("APP_AUTOCREATE", "1") == "1":`.

- [ ] **Step 7: Run full suite to verify pass**

Run: `uv run pytest -v`
Expected: all tests PASS (Tasks 1–11). Endpoint check for the mounted path: `uv run python -c "from app.main import create_app"` succeeds.

- [ ] **Step 8: Ruff + commit**

```bash
uv run ruff check .
git add -A
git commit -m "feat: management UI, REST API, basic auth, healthz, app assembly with MCP mount"
```

---

### Task 12: Docker, compose, sample documents, smoke script

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `sample_docs/aml-policy.md`, `sample_docs/hr-handbook.md`, `scripts/smoke.py`

**Interfaces:**
- Consumes: the running stack (`app` on :8000, `qdrant` on :6333).
- Produces: `docker compose up --build` = whole stack, one command (assignment deliverable). `uv run python scripts/smoke.py` = end-to-end verification, doubles as demo-video script.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

# Pre-warm the fastembed BM25 model so the first upload isn't slow/offline-fragile
RUN uv run python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git
.venv
.env
data/
docs/
tests/
__pycache__
*.pyc
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.13.4
    volumes:
      - qdrant_storage:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "bash -c ':> /dev/tcp/127.0.0.1/6333' || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10

  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      QDRANT_URL: http://qdrant:6333
      DB_PATH: /srv/data/metadata.db
    volumes:
      - app_data:/srv/data
    depends_on:
      qdrant:
        condition: service_healthy

volumes:
  qdrant_storage:
  app_data:
```

If the qdrant healthcheck fails because the image lacks bash, swap the test for `["CMD", "/qdrant/qdrant", "--help"]`-style no-op and rely on `interval` + app-side retries, or use `wget`-based check if present — verify with `docker compose ps`.

- [ ] **Step 4: Write sample documents**

`sample_docs/aml-policy.md`:

```markdown
# AML Policy 2024

## 1 Purpose
This policy defines anti-money-laundering controls for all client-facing teams.

## 2 Client Tiers

### 2.1 Classification
Clients are classified as tier-1 (institutional), tier-2 (SME), or tier-3 (retail)
based on annual volume and risk profile (see policy code AML-2024-B).

### 2.2 Transfer Limits
Tier-2 clients have a transfer cap of 10,000 EUR per day. Exceptions require
written approval from the compliance desk within two business days.

## 3 Reporting
Suspicious activity must be reported through the SAR workflow within 24 hours.
```

`sample_docs/hr-handbook.md`:

```markdown
# HR Handbook

## Vacation
Employees accrue 2 days of paid vacation per month, capped at 30 days.

## Onboarding
New hires complete security training within the first week. Badge access is
provisioned by IT on day one; payroll enrollment closes on the 15th.
```

- [ ] **Step 5: Write `scripts/smoke.py`**

```python
"""End-to-end smoke test against a running stack (docker compose up).

Usage: uv run python scripts/smoke.py [BASE_URL]
Reads UI_PASSWORD and MCP_API_KEY from the environment (.env values).
"""

import os
import pathlib
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
UI_AUTH = ("admin", os.environ["UI_PASSWORD"])
MCP_HEADERS = {
    "Authorization": f"Bearer {os.environ['MCP_API_KEY']}",
    "Accept": "application/json, text/event-stream",
}


def rpc(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as c:
        assert c.get("/healthz").json()["status"] == "ok", "healthz failed"
        print("healthz ok")

        doc = pathlib.Path("sample_docs/aml-policy.md")
        r = c.post(
            "/api/documents", auth=UI_AUTH,
            files={"file": (doc.name, doc.read_bytes(), "text/markdown")},
            data={"tags": "compliance"},
        )
        r.raise_for_status()
        print(f"upload ok: {r.json()['outcome']}")

        r = c.post("/mcp", headers=MCP_HEADERS, json=rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "tier-2 transfer cap"}},
        ))
        r.raise_for_status()
        body = r.text
        assert "aml-policy.md" in body, f"expected aml-policy.md in results: {body[:500]}"
        print("mcp search ok — found aml-policy.md")

        r = c.post("/mcp", json=rpc("tools/list"))  # no auth header
        assert r.status_code == 401, "MCP endpoint must reject unauthenticated calls"
        print("mcp auth ok — 401 without token")

    print("SMOKE PASSED")


if __name__ == "__main__":
    main()
```

Note: with default SSE responses the `/mcp` reply body is an `event-stream` text — the `in body` assertion works for both JSON and SSE framing.

- [ ] **Step 6: Run the smoke test**

```bash
docker compose up --build -d
# wait for "Application startup complete" in: docker compose logs -f app
uv run python scripts/smoke.py
docker compose down
```

Expected output ends with `SMOKE PASSED`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: dockerized stack with compose, sample docs, e2e smoke script"
```

---

### Task 13: README + Part 1 answers document

**Files:**
- Create: `README.md`, `docs/part1-ai-assisted-coding.md`
- Modify: `.env.example` (verify still matches `Settings` fields exactly)

This task is writing, not coding — source material is the spec (`docs/superpowers/specs/2026-07-11-document-intelligence-design.md`, sections referenced below) and the conversation log. **Part 1 answers and the "where/how AI was used" README section MUST be reviewed and reworded by the user — they are the user's voice, will be probed in a live interview, and must not read as generated boilerplate.**

- [ ] **Step 1: Write `README.md` with this exact section structure**

1. **What this is** — 3-sentence pitch (assignment scenario, spec §1).
2. **Architecture** — ASCII diagram from spec §3 + the boundary rule (thin adapters, shared services).
3. **Stack choices & rationale** — table from spec §2, one "why" line each; expand on: Qdrant (native hybrid + RRF server-side), text-embedding-3-small (cost/quality, Matryoshka footnote), SQLite (right-sizing + Postgres swap-path), Jinja over SPA (review attention on RAG/MCP).
4. **RAG design** — chunking strategy + parameters and why (~450/15%, folklore-defaults caveat, spec §4); contextual prefixing and the context-loss mitigation ladder (overlap → prefix → contextual retrieval → parent-document, first two implemented); dedup rules (three-rule table); hybrid search explanation (dense vs BM25 vs RRF, why financial docs need keyword rescue).
5. **MCP tool design rationale** — the 5 principles from spec §7 verbatim; per-tool "when the agent should reach for it" table; errors-as-guidance with a concrete example; considered-and-rejected: `get_document_chunks` bulk fetch (token economy), write tools over MCP (least privilege).
6. **Authentication** — MCP: Bearer header, exact curl example; UI: Basic; production path = OAuth 2.1 resource server (named, not built).
7. **Running locally** — `cp .env.example .env`, fill keys, `docker compose up --build`; or `uv sync && uv run uvicorn app.main:app` + local qdrant. Test suite: `uv run pytest`.
8. **Connecting an MCP client** — Claude Desktop / Claude Code (`claude mcp add --transport http docintel https://<host>/mcp --header "Authorization: Bearer <key>"`) + generic JSON config block; note tools are namespaced per server by hosts.
9. **Deployment** — compose = reference; live = app container + Qdrant Cloud (spec §10); secrets via platform env vars.
10. **Known limitations & future work** — spec §11 list, verbatim honesty.
11. **AI-assisted development** — link to `docs/part1-ai-assisted-coding.md`; 5-bullet summary of where AI was used in THIS repo (design dialogue, plan generation, code generation per plan, what was human-decided: scope, stack arbitration, dedup semantics, tool UX).

- [ ] **Step 2: Draft `docs/part1-ai-assisted-coding.md` (max 1 page)**

Three sections mirroring the assignment's three questions. Draft from the conversation-established sketch: (1) spec-first workflow, CLAUDE.md/rules files, skills/hooks, plan→implement→verify; tutor-mode for unfamiliar domains vs accelerant-mode for familiar .NET; (2) value = boilerplate elimination, cross-stack mobility (this repo as evidence), compressed learning; risks = plausible-but-wrong code, stale API knowledge (mitigated here via live docs lookup — cite the FastMCP→MCPServer v2 rename caught during planning), tool descriptions as contracts with probabilistic consumers, injection surface in retrieved content; (3) role → specify/verify/orchestrate; durable skills = decomposition, evals, trust boundaries, client communication. **Mark file as DRAFT — user must rewrite in own voice before submission.**

- [ ] **Step 3: Verify docs against reality**

Every command in the README must be executed once as written: compose up, uv run pytest, the curl example (against local stack), the `claude mcp add` line. Fix drift.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: client-grade README and Part 1 draft answers"
```

---

### Task 14: Live deployment (interactive — requires user accounts)

**Files:**
- Modify: `README.md` (fill live URLs), possibly platform config file (e.g. `fly.toml` or `railway.json`) depending on chosen platform.

**This task cannot run unattended.** It needs the user to: pick the platform (Railway / Fly.io / Render), create the account, create a Qdrant Cloud cluster, and paste secrets into the platform dashboard. Execute as a pairing session:

- [ ] **Step 1: Qdrant Cloud** — user creates free 1GB cluster at cloud.qdrant.io → obtain `QDRANT_URL` (https URL) + `QDRANT_API_KEY`.
- [ ] **Step 2: Platform setup** — user creates app from the GitHub repo with the existing `Dockerfile`; attach a persistent volume mounted where `DB_PATH` points (e.g. `/srv/data`); set env vars: `OPENAI_API_KEY`, `MCP_API_KEY` (fresh long random), `UI_PASSWORD`, `QDRANT_URL`, `QDRANT_API_KEY`, `DB_PATH=/srv/data/metadata.db`.
- [ ] **Step 3: Verify** — `https://<host>/healthz` returns `{"status":"ok"}`; run `uv run python scripts/smoke.py https://<host>` with prod env vars locally exported.
- [ ] **Step 4: Connect a real MCP client** — add the server to Claude Desktop/Claude Code with the prod URL + Bearer header; run a real query end-to-end ("what are the tier-2 transfer caps?"); confirm citation includes filename + heading.
- [ ] **Step 5: Update README** with live URLs (app, MCP endpoint) and commit:

```bash
git add README.md
git commit -m "docs: live deployment URLs"
```

Push to GitHub (user creates the repo; `git remote add origin ... && git push -u origin main`).

---

## Verification checklist (after all tasks)

- [ ] `uv run pytest` — all green
- [ ] `uv run ruff check .` — clean
- [ ] `docker compose up --build` + `scripts/smoke.py` — SMOKE PASSED
- [ ] MCP endpoint answers over the network with Bearer auth; 401 without
- [ ] Re-upload same file → no duplicate chunks (check chunk counts in UI)
- [ ] Live URL healthy; real MCP client (Claude Desktop/Code) lists 7 tools and answers a grounded query with citation
- [ ] README instructions executed verbatim on a clean machine/checkout
- [ ] `.env.example` matches `Settings` fields exactly
- [ ] Part 1 document rewritten in the user's own voice (not AI boilerplate)
- [ ] Demo video recorded (user; smoke script = storyboard: upload → manage → MCP query → cite architecture)
