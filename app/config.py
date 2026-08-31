"""DemumuMind Panel — infrastructure configuration.

SSOT for infrastructure only (database/redis/bind/cors/panel key).
All domain data (providers, models, keys, budgets, guardrails, roles)
lives in the database / Redis — never as constants here.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./demumumind.db"
    REDIS_URL: str = ""
    BIND_ADDR: str = "0.0.0.0:8000"
    CORS_ORIGINS: str = "http://localhost:5173"
    PANEL_API_KEY: str = "dev-insecure-panel-key-change-me"
    AUTO_MIGRATE: int = 1

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def bind_host(self) -> str:
        host, _, _ = self.BIND_ADDR.rpartition(":")
        return host or "0.0.0.0"

    @property
    def bind_port(self) -> int:
        _, _, port = self.BIND_ADDR.rpartition(":")
        return int(port or "8000")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
