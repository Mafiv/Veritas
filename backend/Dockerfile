FROM python:3.12-slim

WORKDIR /app

# Runtime deps only — wheels cover our stack; skip build-essential for faster builds.
COPY pyproject.toml alembic.ini README.md ./
COPY app ./app
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

RUN mkdir -p /app/storage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
