import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backend.services.ingestion_model_runtime import (
    ModelExtractionError,
    ModelExtractionResult,
    extract_load_order_with_model,
)


@pytest.mark.asyncio
async def test_extract_load_order_returns_structured_payload() -> None:
    raw_text = "Customer: Acme Logistics\nOrigin: Madrid, ES\nCargo: Ceramic tiles"
    model_json = json.dumps(
        {
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "cargo_description": "Ceramic tiles",
        }
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": model_json}}],
    }

    with patch("httpx.AsyncClient", autospec=True) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="test-model",
        )

        result = await extract_load_order_with_model(raw_text, settings)

    assert result.extracted_payload["customer_name"] == "Acme Logistics"
    assert result.extracted_payload["origin_text"] == "Madrid, ES"
    assert result.provider == "lm_studio"
    assert result.model_name == "test-model"
    assert result.raw_model_response == model_json


@pytest.mark.asyncio
async def test_extract_load_order_raises_on_non_200_response() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("httpx.AsyncClient", autospec=True) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="test-model",
        )

        with pytest.raises(ModelExtractionError, match="status 500"):
            await extract_load_order_with_model("Customer: test", settings)


@pytest.mark.asyncio
async def test_extract_load_order_raises_on_invalid_json_content() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json"}}],
    }

    with patch("httpx.AsyncClient", autospec=True) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="test-model",
        )

        with pytest.raises(ModelExtractionError, match="Invalid JSON"):
            await extract_load_order_with_model("Customer: test", settings)


@pytest.mark.asyncio
async def test_extract_load_order_accepts_fenced_json_content() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "```json\n{\"customer_name\": \"SurQuimica Global S.L.\", \"truck_type_id\": 1}\n```"}}],
    }

    with patch("httpx.AsyncClient", autospec=True) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            INGESTION_MODEL_NAME="test-model",
        )

        result = await extract_load_order_with_model("Customer: test", settings)

    assert result.extracted_payload["customer_name"] == "SurQuimica Global S.L."
    assert result.extracted_payload["truck_type_id"] == 1


@pytest.mark.asyncio
async def test_model_extraction_result_is_immutable() -> None:
    result = ModelExtractionResult(
        extracted_payload={"customer_name": "Acme"},
        raw_model_response="{}",
        confidence_summary=None,
        normalization_warnings=[],
        provider="lm_studio",
        model_name="test",
    )

    with pytest.raises(Exception):
        result.extracted_payload = {}  # type: ignore[misc]
