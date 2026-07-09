"""Veritas application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Veritas"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default="change-me-in-production-veritas-secret-key-32chars")
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
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o-mini"
    chat_fallback_model: str = "gpt-3.5-turbo"
    use_mock_llm: bool = True  # deterministic local mode without API keys

    # Retrieval
    hybrid_vector_weight: float = 0.6
    hybrid_bm25_weight: float = 0.4
    retrieval_top_k: int = 20
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

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@veritas.local"
    smtp_use_tls: bool = True

    # Retrieval productionization
    use_pgvector: bool = False
    reranker_backend: Literal["lexical", "cross_encoder"] = "lexical"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # SSO / OIDC / SAML
    use_mock_sso: bool = True  # local IdP simulation without real OIDC provider
    sso_callback_base_url: str = ""  # defaults to frontend_url when empty
    sso_state_ttl_seconds: int = 600
    sso_jit_default_role: Literal["viewer", "editor"] = "viewer"
    webhook_max_attempts: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
