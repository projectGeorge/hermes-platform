from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    clerk_secret_key: str | None = Field(default=None, alias="CLERK_SECRET_KEY")
    clerk_jwt_key_raw: str | None = Field(default=None, alias="CLERK_JWT_KEY")
    clerk_authorized_parties_raw: str = Field(
        default="http://localhost:5173",
        alias="CLERK_AUTHORIZED_PARTIES",
    )
    ingestion_model_provider: str = Field(
        default="lm_studio",
        alias="INGESTION_MODEL_PROVIDER",
    )
    lm_studio_base_url: str = Field(
        default="http://127.0.0.1:1234/v1",
        alias="LM_STUDIO_BASE_URL",
    )
    ingestion_model_name: str = Field(
        default="",
        alias="INGESTION_MODEL_NAME",
    )
    ingestion_model_timeout_seconds: float = Field(
        default=30,
        alias="INGESTION_MODEL_TIMEOUT_SECONDS",
    )
    local_agent_model_provider: str = Field(
        default="lm_studio",
        alias="LOCAL_AGENT_MODEL_PROVIDER",
    )
    local_agent_model_name: str = Field(
        default="",
        alias="LOCAL_AGENT_MODEL_NAME",
    )
    local_agent_model_timeout_seconds: float = Field(
        default=60,
        alias="LOCAL_AGENT_MODEL_TIMEOUT_SECONDS",
    )
    local_agent_model_temperature: float = Field(
        default=0.7,
        alias="LOCAL_AGENT_MODEL_TEMPERATURE",
    )
    local_agent_model_max_tokens: int = Field(
        default=500,
        alias="LOCAL_AGENT_MODEL_MAX_TOKENS",
    )
    reasoning_model_provider: str = Field(
        default="openrouter",
        alias="REASONING_MODEL_PROVIDER",
    )
    reasoning_model_name: str = Field(
        default="",
        alias="REASONING_MODEL_NAME",
    )
    reasoning_model_api_key: str | None = Field(
        default=None,
        alias="REASONING_MODEL_API_KEY",
    )
    reasoning_model_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="REASONING_MODEL_BASE_URL",
    )
    monitoring_geocoding_provider: str = Field(
        default="opencage",
        alias="MONITORING_GEOCODING_PROVIDER",
    )
    monitoring_geocoding_api_key: str | None = Field(
        default=None,
        alias="MONITORING_GEOCODING_API_KEY",
    )
    monitoring_routing_provider: str = Field(
        default="openrouteservice",
        alias="MONITORING_ROUTING_PROVIDER",
    )
    monitoring_routing_api_key: str | None = Field(
        default=None,
        alias="MONITORING_ROUTING_API_KEY",
    )
    monitoring_routing_base_url: str = Field(
        default="https://api.openrouteservice.org",
        alias="MONITORING_ROUTING_BASE_URL",
    )
    monitoring_route_profile: str = Field(
        default="driving-hgv",
        alias="MONITORING_ROUTE_PROFILE",
    )
    reasoning_model_timeout_seconds: float = Field(
        default=60,
        alias="REASONING_MODEL_TIMEOUT_SECONDS",
    )
    reasoning_model_temperature: float = Field(
        default=0.3,
        alias="REASONING_MODEL_TEMPERATURE",
    )
    reasoning_model_max_tokens: int = Field(
        default=1024,
        alias="REASONING_MODEL_MAX_TOKENS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "reasoning_model_api_key",
        "monitoring_geocoding_api_key",
        "monitoring_routing_api_key",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def async_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def clerk_jwt_key(self) -> str | None:
        if self.clerk_jwt_key_raw is None:
            return None

        return self.clerk_jwt_key_raw.replace("\\n", "\n")

    @property
    def clerk_authorized_parties(self) -> list[str]:
        return [
            value.strip()
            for value in self.clerk_authorized_parties_raw.split(",")
            if value.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
