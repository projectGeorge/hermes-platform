import pytest

from app.backend.core.domain_enums import (
    LOAD_ORDER_TRANSITIONS,
    LoadOrderStatus,
    validate_load_order_transition,
)


def test_validate_load_order_transition_allows_formalization() -> None:
    validate_load_order_transition(
        LoadOrderStatus.READY_FOR_FORMALIZATION,
        LoadOrderStatus.FORMALIZED,
    )


def test_validate_load_order_transition_rejects_cancelled_reactivation() -> None:
    with pytest.raises(ValueError):
        validate_load_order_transition(
            LoadOrderStatus.CANCELLED,
            LoadOrderStatus.VIABILITY_CONFIRMED,
        )


def test_validate_load_order_transition_uses_english_source_of_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        LOAD_ORDER_TRANSITIONS,
        LoadOrderStatus.VIABILITY_CONFIRMED,
        {LoadOrderStatus.CANCELLED},
    )

    with pytest.raises(ValueError):
        validate_load_order_transition(
            LoadOrderStatus.VIABILITY_CONFIRMED,
            LoadOrderStatus.FORMALIZED,
        )


def test_load_order_transitions_exposes_real_mapping_snapshot() -> None:
    assert LoadOrderStatus.VIABILITY_CONFIRMED in LOAD_ORDER_TRANSITIONS
    assert LOAD_ORDER_TRANSITIONS.get(LoadOrderStatus.CANCELLED) == set()

    transitions = dict(LOAD_ORDER_TRANSITIONS.items())

    assert transitions == {
        LoadOrderStatus.PENDING_INGESTION: {
            LoadOrderStatus.VIABILITY_PENDING,
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.VIABILITY_PENDING: {
            LoadOrderStatus.VIABILITY_CONFIRMED,
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.VIABILITY_CONFIRMED: {
            LoadOrderStatus.SEARCHING_CARRIER,
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.SEARCHING_CARRIER: {
            LoadOrderStatus.READY_FOR_FORMALIZATION,
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.READY_FOR_FORMALIZATION: {
            LoadOrderStatus.FORMALIZED,
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.FORMALIZED: {
            LoadOrderStatus.CANCELLED,
        },
        LoadOrderStatus.CANCELLED: set(),
    }
