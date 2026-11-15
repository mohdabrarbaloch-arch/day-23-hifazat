"""Application configuration — everything comes from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets live in .env only — never in code."""

    app_name: str = "Hifazat"
    version: str = "1.0.0"

    database_url: str = "sqlite:///./hifazat.db"
    # sqlite pooling is broken under concurrency; connect once per worker
    sqlite_connect_once: bool = False

    jwt_secret: str = "CHANGE_ME_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 h

    frontend_origin: str = "http://127.0.0.1:8000"
    rate_limit_per_minute: int = 120

    risk_threshold: int = 40

    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_production(self) -> None:
        """Refuse to boot in deplooyed mode with a weak secret."""
        if not self.debug and (not self.jwt_secret or self.jwt_secret == "CHANGE_ME_in_production"):
            raise RuntimeError(
                "JWT_SECRET is not set to a real value. Generate one with "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"` '
                "and export it."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
