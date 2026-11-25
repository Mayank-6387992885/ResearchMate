import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "ResearchMate API"
    api_v1_prefix: str = "/api/v1"
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
