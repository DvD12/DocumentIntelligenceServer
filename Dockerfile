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
CMD ["uv", "run", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
