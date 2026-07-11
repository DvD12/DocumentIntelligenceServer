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

    # -- internal helpers (callers hold the lock) ---------------------------

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

    # -- public API ----------------------------------------------------------

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
            if meta:
                metas.append(meta)
            else:
                unknown.append(ref)
        return metas, unknown
