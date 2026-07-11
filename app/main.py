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
    mcp_asgi = BearerAuthMiddleware(mcp.streamable_http_app(), settings.mcp_api_key)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # A mounted sub-app's lifespan never runs: the host must run the
        # MCP session manager itself or the first /mcp request fails.
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Document Intelligence Server", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        repo.count_documents()  # SQLite reachable
        qclient.get_collections()  # Qdrant reachable
        return {"status": "ok"}

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.include_router(build_router(pipeline, repo, templates))
    # MCP app serves /mcp itself; root-mount (registered last, so it only sees
    # requests no route matched) avoids the /mcp -> /mcp/ slash redirect.
    app.mount("/", mcp_asgi)
    app.add_middleware(
        BasicAuthMiddleware, password=settings.ui_password,
        exempt_prefixes=("/mcp", "/healthz"),
    )
    return app


# Run with factory mode so importing this module stays side-effect free:
#   uvicorn app.main:create_app --factory
