FROM python:3.12-slim

WORKDIR /app

# Runtime deps only — wheels cover our stack; skip build-essential for faster builds.
COPY pyproject.toml alembic.ini README.md ./
COPY app ./app
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

# Bake the local embedding model + tokenizer into the image so the first upload/query does
# not stall on downloads (~130 MB).
ENV MODEL_CACHE_DIR=/app/.cache/models \
    TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken
# The optional cross-encoder (RERANKER_BACKEND=cross_encoder) downloads on first use.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/.cache/models')" \
 && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

RUN mkdir -p /app/storage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
