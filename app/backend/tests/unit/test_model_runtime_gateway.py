"""Unit tests for the provider-aware model runtime gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backend.services.model_runtime_gateway import (
    RuntimeProvenance,
    structured_completion,
    stream_completion,
    CompletionResult,
    resolve_profile_config,
)


def _make_response_mock(json_body: object) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = json_body
    response.raise_for_status.return_value = None
    return response


def _make_post_error_mock(exc: Exception) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = exc
    return mock_client


class TestResolveProfileConfig:
    def test_ingestion_profile_resolves_local_provider(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="qwen-2.5-3b",
        )

        config = resolve_profile_config(settings, "ingestion")
        assert config["provider"] == "lm_studio"
        assert config["model_name"] == "qwen-2.5-3b"
        assert config["base_url"] == "http://127.0.0.1:1234/v1"
        assert config["timeout_seconds"] == 30

    def test_local_agent_profile_resolves_local_provider(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            LOCAL_AGENT_MODEL_NAME="phi-3.5-mini",
        )

        config = resolve_profile_config(settings, "local_agent")
        assert config["provider"] == "lm_studio"
        assert config["model_name"] == "phi-3.5-mini"
        assert config["base_url"] == "http://127.0.0.1:1234/v1"
        assert config["timeout_seconds"] == 60
        assert config["temperature"] == 0.7
        assert config["max_tokens"] == 500

    def test_reasoning_profile_resolves_cloud_provider(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test-key",
            REASONING_MODEL_BASE_URL="https://openrouter.ai/api/v1",
        )

        config = resolve_profile_config(settings, "reasoning")
        assert config["provider"] == "openrouter"
        assert config["model_name"] == "deepseek/deepseek-flash-v1"
        assert config["base_url"] == "https://openrouter.ai/api/v1"
        assert config["api_key"] == "sk-test-key"
        assert config["timeout_seconds"] == 60
        assert config["temperature"] == 0.3
        assert config["max_tokens"] == 1024


class TestStructuredCompletion:
    @pytest.mark.asyncio
    async def test_local_lm_studio_structured_success(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="qwen-2.5-3b",
        )

        response_mock = _make_response_mock({
            "choices": [
                {
                    "message": {
                        "content": '{"key": "value", "status": "ok"}'
                    }
                }
            ]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await structured_completion(
                settings=settings,
                messages=[{"role": "user", "content": "test"}],
                profile="ingestion",
            )

        assert isinstance(result, CompletionResult)
        assert result.content == {"key": "value", "status": "ok"}
        assert result.provenance.provider == "lm_studio"
        assert result.provenance.model_name == "qwen-2.5-3b"
        assert result.provenance.runtime_profile == "ingestion"

    @pytest.mark.asyncio
    async def test_local_lm_studio_structured_missing_model(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="",
        )

        with pytest.raises(ValueError, match="not configured"):
            await structured_completion(
                settings=settings,
                messages=[{"role": "user", "content": "test"}],
                profile="ingestion",
            )

    @pytest.mark.asyncio
    async def test_cloud_openrouter_structured_success(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test-key",
            REASONING_MODEL_BASE_URL="https://openrouter.ai/api/v1",
        )

        response_mock = _make_response_mock({
            "choices": [
                {
                    "message": {
                        "content": '{"decision": "proceed", "next_action": "review"}'
                    }
                }
            ]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await structured_completion(
                settings=settings,
                messages=[{"role": "user", "content": "test"}],
                profile="reasoning",
            )

        assert isinstance(result, CompletionResult)
        assert result.provenance.provider == "openrouter"
        assert result.provenance.model_name == "deepseek/deepseek-flash-v1"
        assert result.provenance.runtime_profile == "reasoning"

    @pytest.mark.asyncio
    async def test_cloud_provider_http_error_normalization(self) -> None:
        from app.backend.core.settings import Settings
        import httpx

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test-key",
        )

        error_response = MagicMock()
        error_response.status_code = 502

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=error_response,
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Model runtime error"):
                await structured_completion(
                    settings=settings,
                    messages=[{"role": "user", "content": "test"}],
                    profile="reasoning",
                )

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        from app.backend.core.settings import Settings
        import httpx

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="qwen-2.5-3b",
            INGESTION_MODEL_TIMEOUT_SECONDS=2,
        )

        mock_client = _make_post_error_mock(httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Model runtime request timed out"):
                await structured_completion(
                    settings=settings,
                    messages=[{"role": "user", "content": "test"}],
                    profile="ingestion",
                )

    @pytest.mark.asyncio
    async def test_malformed_json_response_raises_error(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="qwen-2.5-3b",
        )

        response_mock = _make_response_mock({
            "choices": [
                {
                    "message": {
                        "content": "not valid json {"
                    }
                }
            ]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Failed to parse model response"):
                await structured_completion(
                    settings=settings,
                    messages=[{"role": "user", "content": "test"}],
                    profile="ingestion",
                )

    @pytest.mark.asyncio
    async def test_structured_completion_accepts_fenced_json_response(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test-key",
        )

        response_mock = _make_response_mock({
            "choices": [
                {
                    "message": {
                        "content": "```json\n{\"decision\": \"proceed\", \"next_action\": \"review\"}\n```"
                    }
                }
            ]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await structured_completion(
                settings=settings,
                messages=[{"role": "user", "content": "test"}],
                profile="reasoning",
            )

        assert result.content == {"decision": "proceed", "next_action": "review"}

    @pytest.mark.asyncio
    async def test_structured_completion_accepts_tool_call_arguments_json(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test-key",
        )

        response_mock = _make_response_mock({
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "emit_json",
                                    "arguments": '{"decision": "proceed", "next_action": "review"}',
                                }
                            }
                        ],
                    }
                }
            ]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await structured_completion(
                settings=settings,
                messages=[{"role": "user", "content": "test"}],
                profile="reasoning",
            )

        assert result.content == {"decision": "proceed", "next_action": "review"}


class TestStreamCompletion:
    @pytest.mark.asyncio
    async def test_local_lm_studio_streaming_success(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            LOCAL_AGENT_MODEL_NAME="qwen-2.5-3b",
        )

        stream_chunks = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            'data: {"choices":[{"delta":{"content":" world"}}]}\n',
            "data: [DONE]\n",
        ]

        async def _async_iter_lines():
            for line in stream_chunks:
                yield line

        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 200
        mock_stream_response.raise_for_status.return_value = None
        mock_stream_response.aiter_lines = _async_iter_lines

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream = MagicMock()
        mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_client.stream.return_value.__aexit__ = AsyncMock(return_value=None)

        chunks: list[str] = []

        with patch("httpx.AsyncClient", return_value=mock_client):
            async for chunk in stream_completion(
                settings=settings,
                messages=[{"role": "user", "content": "Hi"}],
                profile="local_agent",
            ):
                chunks.append(chunk)

        assert "".join(chunks) == "Hello world"

    @pytest.mark.asyncio
    async def test_streaming_missing_model_returns_error_message(self) -> None:
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            LOCAL_AGENT_MODEL_NAME="",
        )

        chunks = []
        async for chunk in stream_completion(
            settings=settings,
            messages=[{"role": "user", "content": "Hi"}],
            profile="local_agent",
        ):
            chunks.append(chunk)

        joined = "".join(chunks)
        assert "not configured" in joined.lower()

    @pytest.mark.asyncio
    async def test_streaming_http_error_yields_error_message(self) -> None:
        from app.backend.core.settings import Settings
        import httpx

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            LOCAL_AGENT_MODEL_NAME="qwen-2.5-3b",
        )

        error_response = MagicMock()
        error_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=error_response,
            )
        )

        chunks = []
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for chunk in stream_completion(
                settings=settings,
                messages=[{"role": "user", "content": "Hi"}],
                profile="local_agent",
            ):
                chunks.append(chunk)

        joined = "".join(chunks)
        assert "Model runtime error" in joined


class TestRuntimeProvenance:
    def test_provenance_dataclass_fields(self) -> None:
        prov = RuntimeProvenance(
            provider="lm_studio",
            model_name="qwen-2.5-3b",
            runtime_profile="local_agent",
        )
        assert prov.provider == "lm_studio"
        assert prov.model_name == "qwen-2.5-3b"
        assert prov.runtime_profile == "local_agent"


class TestCompletionResult:
    def test_completion_result_dataclass_fields(self) -> None:
        prov = RuntimeProvenance(
            provider="openrouter",
            model_name="deepseek/flash",
            runtime_profile="reasoning",
        )
        result = CompletionResult(
            content={"ok": True},
            provenance=prov,
            raw_text='{"ok": true}',
        )
        assert result.content == {"ok": True}
        assert result.provenance.provider == "openrouter"
        assert result.raw_text == '{"ok": true}'
