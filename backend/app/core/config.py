"""Veritas application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-in-production-veritas-secret-key-32chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Veritas"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default=DEFAULT_SECRET_KEY)
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    # Database
    database_url: str = "postgresql+asyncpg://veritas:veritas@localhost:5432/veritas"
    database_url_sync: str = "postgresql://veritas:veritas@localhost:5432/veritas"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Object storage (local fallback for development)
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = "./storage"
    s3_bucket: str = "veritas-documents"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # LLM / embeddings
    llm_provider_model: str = Field(
        default="openai/gpt-4o-mini",
        validation_alias="LLM_MODEL",
    )
    openai_api_key: str = ""
    gemini_api_key: str = ""
    github_api_key: str = ""
    anthropic_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    # Embeddings: "local" (fastembed/ONNX, no key), "openai", or "mock" (tests only).
    # embedding_dimensions must match the vector(N) column created by migration 011.
    embedding_provider: Literal["local", "openai", "mock"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    model_cache_dir: str = ""  # fastembed model cache; empty = library default
    chat_model: str = "gpt-4o-mini"
    chat_fallback_model: str = "gpt-3.5-turbo"
    use_mock_llm: bool = True  # deterministic local mode without API keys

    # Retrieval
    hybrid_vector_weight: float = 0.6
    hybrid_bm25_weight: float = 0.4
    retrieval_top_k: int = 20
    # Candidates pulled from each index (vector, keyword) before fusion.
    retrieval_candidates: int = 50
    # HNSW search breadth; higher = better recall, slower.
    hnsw_ef_search: int = 80
    rerank_top_k: int = 8
    enable_hyde: bool = True
    enable_query_expansion: bool = True
    enable_reranker: bool = True

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""
    stripe_price_team: str = ""
    frontend_url: str = "http://localhost:3000"

    # Rate limits / free tier
    free_tier_queries_per_day: int = 20
    free_tier_documents: int = 5
    free_tier_workspaces: int = 1

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Better Auth (Next.js) — JWT JWKS verification
    better_auth_url: str = "http://localhost:3000"
    # Docker: use http://frontend:3000 so the API can reach JWKS internally
    better_auth_internal_url: str = ""
    internal_auth_bootstrap_secret: str = ""

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@veritas.local"
    smtp_use_tls: bool = True

    # Reranking
    reranker_backend: Literal["lexical", "cross_encoder"] = "cross_encoder"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> "Settings":
        """Fail fast instead of booting production with dev secrets."""
        if self.app_env != "production":
            return self
        problems: list[str] = []
        if self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 chars")
        if len(self.internal_auth_bootstrap_secret) < 16:
            problems.append("INTERNAL_AUTH_BOOTSTRAP_SECRET must be at least 16 chars")
        if self.debug:
            problems.append("DEBUG must be false")
        if self.use_mock_llm:
            problems.append("USE_MOCK_LLM must be false")
        if problems:
            raise ValueError("Insecure production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
