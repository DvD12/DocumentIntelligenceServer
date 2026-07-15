import uuid

from fastembed import SparseTextEmbedding
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
        # BM25 vectors are computed client-side: passing models.Document to a
        # real Qdrant server requests *server-side* inference (cloud-only) and
        # fails with "InferenceService is not initialized".
        self._sparse = SparseTextEmbedding(SPARSE_MODEL)

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(COLLECTION):
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
        # Qdrant Cloud rejects a filtered delete/update on an unindexed payload
        # field with 400 "Index required but not found for document_id"; local
        # Qdrant allows it, so the gap only surfaces in the cloud. Filtered reads
        # (search) work without it, filtered deletes do not. Idempotent — runs on
        # every ingest and at startup, so existing collections gain the index too.
        self._client.create_payload_index(
            collection_name=COLLECTION,
            field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    def upsert_chunks(self, chunks: list[Chunk], dense_vectors: list[list[float]]) -> None:
        sparse_vectors = [
            models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in self._sparse.embed([c.prefixed_text for c in chunks])
        ]
        points = [
            models.PointStruct(
                id=point_id(c.document_id, c.chunk_index),
                vector={"dense": v, "sparse": s},
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
            for c, v, s in zip(chunks, dense_vectors, sparse_vectors, strict=True)
        ]
        self._client.upsert(collection_name=COLLECTION, points=points)

    def delete_document(self, document_id: str) -> None:
        if not self._client.collection_exists(COLLECTION):
            return  # nothing ingested yet: nothing to delete
        self._client.delete(
            collection_name=COLLECTION,
            points_selector=models.FilterSelector(filter=_doc_filter([document_id])),
        )

    def hybrid_search(
        self, query_text: str, dense_query: list[float], limit: int,
        document_ids: list[str] | None = None,
    ) -> list:
        qfilter = _doc_filter(document_ids) if document_ids else None
        sparse_query = next(iter(self._sparse.query_embed(query_text)))
        result = self._client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                models.Prefetch(query=dense_query, using="dense", limit=20, filter=qfilter),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_query.indices.tolist(),
                        values=sparse_query.values.tolist(),
                    ),
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
