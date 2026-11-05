FROM python:3.12-slim

WORKDIR /app

# Runtime deps only — wheels cover our stack; skip build-essential for faster builds.
COPY pyproject.toml alembic.ini README.md ./
COPY app ./app
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

# Bake the local embedding + reranker models into the image so the first upload/query does
# not stall on model downloads (~220 MB total).
ENV MODEL_CACHE_DIR=/app/.cache/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/.cache/models')" \
 && python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2', cache_dir='/app/.cache/models')"

RUN mkdir -p /app/storage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
