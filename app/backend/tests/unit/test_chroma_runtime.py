from pathlib import Path

import pytest

from app.backend.services.chroma_runtime import _reset_client


@pytest.fixture(autouse=True)
def _isolate_chroma(tmp_path: Path) -> None:
    _reset_client()
    yield
    _reset_client()


def test_collection_bootstrap_works():
    from app.backend.services.chroma_runtime import smart_comms_collection

    col = smart_comms_collection()
    assert col is not None
    assert col.name == "smart_comms_memory"


def test_upsert_and_query_roundtrip():
    from app.backend.services.chroma_runtime import similarity_query, upsert_document

    upsert_document(
        collection_name="smart_comms_memory",
        document_id="test_001",
        document="Customer: Acme Corp. Route: Madrid to Paris.",
        metadata={"order_id": "order-1"},
    )

    results = similarity_query(
        collection_name="smart_comms_memory",
        query="Madrid to Paris route",
        top_k=3,
    )
    assert len(results) >= 1
    assert results[0]["id"] == "test_001"
    assert "Acme Corp" in results[0]["document"]


def test_query_returns_empty_when_no_match():
    from app.backend.services.chroma_runtime import similarity_query

    results = similarity_query(
        collection_name="carrier_search_memory",
        query="no matching documents here",
        top_k=3,
    )
    assert results == []


def test_health_check_returns_true():
    from app.backend.services.chroma_runtime import check_health

    assert check_health() is True


def test_health_check_cached_reflects_current_state():
    from unittest.mock import patch

    from app.backend.services.chroma_runtime import check_health_cached

    with patch("app.backend.services.chroma_runtime.check_health", side_effect=[True, False]):
        assert check_health_cached() is True
        assert check_health_cached() is False


def test_rag_memory_smart_comms_roundtrip():
    from app.backend.services.rag_memory import (
        index_smart_comms_memory,
        retrieve_smart_comms_context,
    )

    index_smart_comms_memory(
        order_id="order-1",
        customer_name="Atlas Logistics",
        route_label="Barcelona -> Berlin",
        operator_question="What is the best carrier for this?",
        assistant_response="Carrier X is recommended based on price.",
    )

    results = retrieve_smart_comms_context(
        query="Barcelona Berlin carrier",
        top_k=3,
    )
    assert len(results) >= 1
    assert "Atlas Logistics" in results[0]["document"]


def test_rag_memory_carrier_search_roundtrip():
    from app.backend.services.rag_memory import (
        index_carrier_decision_memory,
        retrieve_carrier_search_context,
    )

    index_carrier_decision_memory(
        order_id="order-2",
        origin="Valencia",
        destination="Lyon",
        adr_required=False,
        truck_type="Curtainsider",
        customer_price="1200",
        selected_carrier="FastTruck SL",
        carrier_price="950",
        margin="250",
    )

    results = retrieve_carrier_search_context(
        query="Valencia Lyon curtainsider",
        top_k=3,
    )
    assert len(results) >= 1
    assert "FastTruck SL" in results[0]["document"]


def test_get_collection_creates_new():
    from app.backend.services.chroma_runtime import get_collection

    col = get_collection("test_temp_collection")
    assert col.name == "test_temp_collection"
