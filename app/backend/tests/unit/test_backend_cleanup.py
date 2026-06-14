from pathlib import Path


def test_spanish_service_and_test_leftovers_are_removed() -> None:
    assert not Path("app/backend/services/ordenes.py").exists()
    assert not Path("app/backend/tests/unit/test_ordenes_service.py").exists()
    assert not Path("app/backend/tests/unit/test_order_states.py").exists()
