from app.backend.core.settings import Settings, normalize_database_url


def _settings_with_isolated_env(**overrides: str):
    values = {
        "DATABASE_URL": "sqlite+aiosqlite:///./tests.db",
        "CLERK_SECRET_KEY": None,
        "CLERK_JWT_KEY": None,
        "INGESTION_MODEL_NAME": "",
        "LOCAL_AGENT_MODEL_NAME": "",
        "REASONING_MODEL_NAME": "",
        "REASONING_MODEL_API_KEY": None,
        "MONITORING_GEOCODING_PROVIDER": "opencage",
        "MONITORING_GEOCODING_API_KEY": None,
        "MONITORING_ROUTING_PROVIDER": "openrouteservice",
        "MONITORING_ROUTING_API_KEY": None,
    }
    values.update(overrides)
    return Settings(
        **values,
    )


def test_normalize_database_url_adds_asyncpg_driver() -> None:
    assert normalize_database_url(
        "postgresql://user:pass@localhost:5432/hermes_db"
    ) == "postgresql+asyncpg://user:pass@localhost:5432/hermes_db"


def test_normalize_database_url_keeps_sqlite_async_url() -> None:
    assert normalize_database_url(
        "sqlite+aiosqlite:///./tests.db"
    ) == "sqlite+aiosqlite:///./tests.db"


def test_settings_split_clerk_authorized_parties() -> None:
    settings = _settings_with_isolated_env(
        CLERK_AUTHORIZED_PARTIES="http://localhost:5173,https://hermes.local",
    )

    assert settings.clerk_authorized_parties == [
        "http://localhost:5173",
        "https://hermes.local",
    ]


def test_settings_normalize_clerk_jwt_key_newlines() -> None:
    settings = _settings_with_isolated_env(
        CLERK_JWT_KEY="-----BEGIN PUBLIC KEY-----\\nline-1\\n-----END PUBLIC KEY-----",
    )

    assert settings.clerk_jwt_key == "-----BEGIN PUBLIC KEY-----\nline-1\n-----END PUBLIC KEY-----"


def test_settings_expose_ingestion_model_runtime_defaults() -> None:
    settings = _settings_with_isolated_env()

    assert settings.ingestion_model_provider == "lm_studio"
    assert settings.lm_studio_base_url == "http://127.0.0.1:1234/v1"
    assert settings.ingestion_model_name == ""
    assert settings.ingestion_model_timeout_seconds == 30


def test_settings_expose_local_agent_model_runtime_defaults() -> None:
    settings = _settings_with_isolated_env()

    assert settings.local_agent_model_provider == "lm_studio"
    assert settings.local_agent_model_name == ""
    assert settings.local_agent_model_timeout_seconds == 60
    assert settings.local_agent_model_temperature == 0.7
    assert settings.local_agent_model_max_tokens == 500


def test_settings_expose_reasoning_model_runtime_defaults() -> None:
    settings = _settings_with_isolated_env()

    assert settings.reasoning_model_provider == "openrouter"
    assert settings.reasoning_model_name == ""
    assert settings.reasoning_model_api_key is None
    assert settings.reasoning_model_base_url == "https://openrouter.ai/api/v1"
    assert settings.reasoning_model_timeout_seconds == 60
    assert settings.reasoning_model_temperature == 0.3
    assert settings.reasoning_model_max_tokens == 1024


def test_settings_ingestion_and_local_agent_can_share_same_model() -> None:
    settings = _settings_with_isolated_env(
        INGESTION_MODEL_NAME="qwen-2.5-3b-instruct",
        LOCAL_AGENT_MODEL_NAME="qwen-2.5-3b-instruct",
    )

    assert settings.ingestion_model_name == "qwen-2.5-3b-instruct"
    assert settings.local_agent_model_name == "qwen-2.5-3b-instruct"
    assert settings.ingestion_model_name == settings.local_agent_model_name


def test_settings_ingestion_and_local_agent_can_have_different_models() -> None:
    settings = _settings_with_isolated_env(
        INGESTION_MODEL_NAME="qwen-2.5-3b-instruct",
        LOCAL_AGENT_MODEL_NAME="phi-3.5-mini-instruct",
    )

    assert settings.ingestion_model_name == "qwen-2.5-3b-instruct"
    assert settings.local_agent_model_name == "phi-3.5-mini-instruct"
    assert settings.ingestion_model_name != settings.local_agent_model_name


def test_settings_reasoning_openrouter_configuration() -> None:
    settings = _settings_with_isolated_env(
        REASONING_MODEL_PROVIDER="openrouter",
        REASONING_MODEL_BASE_URL="https://openrouter.ai/api/v1",
        REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
        REASONING_MODEL_API_KEY="sk-or-v1-test",
    )

    assert settings.reasoning_model_provider == "openrouter"
    assert settings.reasoning_model_base_url == "https://openrouter.ai/api/v1"
    assert settings.reasoning_model_name == "deepseek/deepseek-flash-v1"
    assert settings.reasoning_model_api_key == "sk-or-v1-test"


def test_settings_expose_monitoring_route_provider_defaults() -> None:
    settings = _settings_with_isolated_env()

    assert settings.monitoring_geocoding_provider == "opencage"
    assert settings.monitoring_geocoding_api_key is None
    assert settings.monitoring_routing_provider == "openrouteservice"
    assert settings.monitoring_routing_api_key is None
    assert settings.monitoring_routing_base_url == "https://api.openrouteservice.org"
    assert settings.monitoring_route_profile == "driving-hgv"
