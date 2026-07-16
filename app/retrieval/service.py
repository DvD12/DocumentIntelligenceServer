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

    # -- public API ----------------------------------------------------------

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
        results = []
        for p in points:
            meta = metas.get(p.payload["document_id"])
            if meta is None:
                continue  # orphaned point (hard-crash residue): never surface it
            results.append(self._result(len(results) + 1, p.payload, meta))
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
                if point.payload.get("page_end") is not None and entries[-1]["pages"]:
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

    # -- internals -------------------------------------------------------------

    def _resolve_tags(self, tags: list[str], match: str) -> list[str]:
        ids, unknown = self._repo.ids_for_tags(tags, match)
        if unknown:
            all_tags = self._repo.list_tags()
            available = ", ".join(f"{n} ({c} docs)" for n, c in all_tags)
            names = [n for n, _ in all_tags]
            hints = [s for t in unknown for s in closest_matches(normalize_tag(t), names)]
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
