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
