from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.core.errors import DocIntelError
from app.core.models import DocumentMeta
from app.ingestion.pipeline import IngestionPipeline
from app.stores.metadata_repo import MetadataRepo


def _doc_json(meta: DocumentMeta) -> dict:
    return {
        "id": meta.id, "filename": meta.filename, "tags": meta.tags,
        "media_type": meta.media_type, "size_bytes": meta.size_bytes,
        "chunk_count": meta.chunk_count,
        "uploaded_at": meta.uploaded_at.isoformat(),
        "updated_at": meta.updated_at.isoformat(),
    }


def build_router(
    pipeline: IngestionPipeline, repo: MetadataRepo, templates: Jinja2Templates
) -> APIRouter:
    router = APIRouter()

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

    @router.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: str):
        if not pipeline.delete(doc_id):
            return JSONResponse(
                {"error": "not_found", "message": f"No document with id '{doc_id}'."},
                status_code=404,
            )
        return Response(status_code=204)

    @router.get("/api/tags")
    def list_tags():
        return {"tags": [{"name": n, "document_count": c} for n, c in repo.list_tags()]}

    return router
