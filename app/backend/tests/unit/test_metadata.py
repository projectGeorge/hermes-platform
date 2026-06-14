import importlib.util
from pathlib import Path
import uuid

import app.backend.models  # noqa: F401
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import CircularDependencyError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.backend.core import domain_enums
from app.backend.core.domain_enums import (
    AgentActivityState,
    AgentKind,
    CarrierPricingModel,
    ExecutionMonitoringStatus,
    IngestionRunStatus,
    LoadOrderHumanReviewStatus,
    LoadOrderStatus,
    MonitoringAlertSeverity,
    MonitoringAlertStatus,
    MonitoringAlertType,
    SmartCommsContextType,
    SmartCommsMessageRole,
)
from app.backend.db.base import Base
from app.backend.models.carrier import Carrier
from app.backend.models.load_order import LoadOrder
from app.backend.models.trip import Trip
from app.backend.models.user import User
from app.backend.schemas.carrier_search import CarrierCandidateResponse, CarrierSelectionRequest
from app.backend.schemas.load_order import LoadOrderResponse
from app.backend.schemas.agents import AgentActivityResponse, AgentStatusResponse
from app.backend.schemas.monitoring import ExecutionMonitoringReadModelResponse
from app.backend.schemas.smart_comms import SmartCommsConversationResponse, SmartCommsMessageResponse


def test_spanish_compatibility_model_files_are_removed() -> None:
    assert not Path("app/backend/models/usuario.py").exists()
    assert not Path("app/backend/models/cliente.py").exists()
    assert not Path("app/backend/models/direccion.py").exists()
    assert not Path("app/backend/models/tipo_camion.py").exists()
    assert not Path("app/backend/models/transportista.py").exists()
    assert not Path("app/backend/models/orden_carga.py").exists()
    assert not Path("app/backend/models/viaje.py").exists()
    assert not Path("app/backend/schemas/usuario.py").exists()
    assert not Path("app/backend/schemas/orden_carga.py").exists()


def _load_foundation_orders_migration():
    migration_path = Path("alembic/versions/20260411_01_foundation_orders.py")
    spec = importlib.util.spec_from_file_location("foundation_orders_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_ingestion_runs_migration():
    migration_path = Path("alembic/versions/20260414_02_phase51_ingestion_runs.py")
    spec = importlib.util.spec_from_file_location("ingestion_runs_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_human_reviews_migration():
    migration_path = Path("alembic/versions/20260418_01_phase52_human_reviews.py")
    spec = importlib.util.spec_from_file_location("human_reviews_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_pending_ingestion_completion_migration():
    migration_path = Path("alembic/versions/20260419_01_phase52_pending_ingestion_completion.py")
    spec = importlib.util.spec_from_file_location(
        "pending_ingestion_completion_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_carrier_search_snapshot_migration():
    migration_path = Path("alembic/versions/20260422_01_phase61_carrier_search_snapshot.py")
    spec = importlib.util.spec_from_file_location(
        "carrier_search_snapshot_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_carrier_selection_migration():
    migration_path = Path("alembic/versions/20260426_01_phase62_carrier_selection.py")
    spec = importlib.util.spec_from_file_location(
        "carrier_selection_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_load_order_timestamps_migration():
    migration_path = Path("alembic/versions/20260427_01_phase71_load_order_timestamps.py")
    spec = importlib.util.spec_from_file_location(
        "load_order_timestamps_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_ingestion_trace_runtime_migration():
    migration_path = Path("alembic/versions/20260502_01_phase72_ingestion_trace_runtime.py")
    spec = importlib.util.spec_from_file_location(
        "ingestion_trace_runtime_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_execution_monitoring_snapshots_migration():
    migration_path = Path("alembic/versions/20260517_01_phase8b_execution_monitoring_snapshots.py")
    spec = importlib.util.spec_from_file_location(
        "execution_monitoring_snapshots_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_load_order_formalized_status_migration():
    migration_path = Path("alembic/versions/20260530_01_load_order_formalized_status.py")
    spec = importlib.util.spec_from_file_location(
        "load_order_formalized_status_migration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_metadata_contains_english_foundation_tables() -> None:
    assert {
        "users",
        "customers",
        "addresses",
        "truck_types",
        "load_orders",
        "ingestion_runs",
        "load_order_human_reviews",
        "carriers",
        "trips",
    }.issubset(set(Base.metadata.tables))
    assert Base.metadata.tables["load_orders"].c.status.type.enums == [
        member.value for member in LoadOrderStatus
    ]
    assert Base.metadata.tables["ingestion_runs"].c.status.type.enums == [
        member.value for member in IngestionRunStatus
    ]
    assert Base.metadata.tables["load_order_human_reviews"].c.review_status.type.enums == [
        member.value for member in LoadOrderHumanReviewStatus
    ]


def test_metadata_contains_ingestion_runs_columns() -> None:
    assert {
        "id",
        "user_id",
        "route",
        "status",
        "raw_text",
        "extracted_payload",
        "missing_fields",
        "load_order_id",
        "error_detail",
        "provider",
        "model_name",
        "execution_path",
        "trace_steps",
        "raw_model_response",
        "confidence_summary",
        "normalization_warnings",
        "created_at",
        "updated_at",
    }.issubset(Base.metadata.tables["ingestion_runs"].columns.keys())
    ingestion_runs = Base.metadata.tables["ingestion_runs"]
    assert not ingestion_runs.c.raw_text.nullable
    assert ingestion_runs.c.status.type.create_constraint is True
    assert ingestion_runs.c.created_at.server_default is not None
    assert ingestion_runs.c.updated_at.server_default is not None


def test_metadata_contains_load_order_human_reviews_columns() -> None:
    assert {
        "id",
        "load_order_id",
        "ingestion_run_id",
        "reviewed_by_user_id",
        "review_status",
        "submitted_fields",
        "remaining_missing_fields",
        "review_notes",
        "created_at",
    }.issubset(Base.metadata.tables["load_order_human_reviews"].columns.keys())
    load_order_human_reviews = Base.metadata.tables["load_order_human_reviews"]
    assert not load_order_human_reviews.c.review_status.nullable
    assert not load_order_human_reviews.c.submitted_fields.nullable
    assert load_order_human_reviews.c.review_status.type.create_constraint is True
    assert load_order_human_reviews.c.created_at.server_default is not None


def test_metadata_contains_carrier_search_columns() -> None:
    carriers = Base.metadata.tables["carriers"]
    trips = Base.metadata.tables["trips"]

    assert "adr_capable" in carriers.columns.keys()
    assert not carriers.c.adr_capable.nullable
    assert carriers.c.adr_capable.default is not None
    assert carriers.c.adr_capable.default.arg is False

    assert trips.c.proposal_status.default is not None
    assert trips.c.proposal_status.default.arg == "candidate"


def test_metadata_contains_carrier_selection_column() -> None:
    load_orders = Base.metadata.tables["load_orders"]

    assert "selected_trip_id" in load_orders.columns.keys()
    assert load_orders.c.selected_trip_id.nullable


def test_metadata_contains_execution_monitoring_snapshot_columns() -> None:
    snapshots = Base.metadata.tables["execution_monitoring_snapshots"]

    assert {
        "id",
        "load_order_id",
        "status",
        "progress_percent",
        "current_checkpoint",
        "route_points",
        "events",
        "alerts",
        "metadata",
        "created_at",
        "last_refreshed_at",
    }.issubset(snapshots.columns.keys())
    assert not snapshots.c.load_order_id.nullable
    assert not snapshots.c.status.nullable
    assert not snapshots.c.progress_percent.nullable


def test_metadata_contains_load_order_timestamps() -> None:
    load_orders = Base.metadata.tables["load_orders"]

    assert {"created_at", "updated_at"}.issubset(load_orders.columns.keys())
    assert load_orders.c.created_at.server_default is not None
    assert load_orders.c.updated_at.server_default is not None


def test_carrier_selection_schemas_expose_selection_fields() -> None:
    assert LoadOrderResponse.model_fields["selected_trip_id"].annotation == uuid.UUID | None
    assert CarrierCandidateResponse.model_fields["is_selected"].default is False
    assert CarrierSelectionRequest.model_fields["trip_id"].annotation == uuid.UUID | None


def test_domain_enums_include_carrier_search_values() -> None:
    assert [member.value for member in domain_enums.TripProposalStatus] == [
        "candidate",
        "rejected",
    ]
    assert [member.value for member in domain_enums.CarrierRejectionReason] == [
        "invalid_documentation",
        "adr_not_supported",
        "truck_type_mismatch",
        "non_profitable",
    ]


def test_alembic_baseline_enum_matches_domain_values() -> None:
    migration = _load_foundation_orders_migration()

    assert migration.load_order_status_enum.enums == [
        "pending_ingestion",
        "viability_pending",
        "viability_confirmed",
        "searching_carrier",
        "ready_for_formalization",
        "cancelled",
    ]


def test_alembic_ingestion_run_enum_matches_domain_values() -> None:
    migration = _load_ingestion_runs_migration()

    assert migration.ingestion_run_status_enum.enums == [
        member.value for member in IngestionRunStatus
    ]


def test_alembic_human_review_enum_matches_domain_values() -> None:
    migration = _load_human_reviews_migration()

    assert migration.load_order_human_review_status_enum.enums == [
        member.value for member in LoadOrderHumanReviewStatus
    ]


def test_pending_ingestion_completion_migration_uses_postgresql_json_operator() -> None:
    migration = _load_pending_ingestion_completion_migration()

    assert "extracted_payload ->> 'customer_name'" in migration.POSTGRESQL_BACKFILL_SQL
    assert "extracted_payload ->> 'origin_text'" in migration.POSTGRESQL_BACKFILL_SQL
    assert "extracted_payload ->> 'destination_text'" in migration.POSTGRESQL_BACKFILL_SQL
    assert "json_extract" not in migration.POSTGRESQL_BACKFILL_SQL


def test_pending_ingestion_completion_migration_keeps_sqlite_backfill_separate() -> None:
    migration = _load_pending_ingestion_completion_migration()

    assert "json_extract(ingestion_runs.extracted_payload, '$.customer_name')" in (
        migration.SQLITE_BACKFILL_SQL
    )
    assert "json_extract" not in migration.POSTGRESQL_BACKFILL_SQL


def test_carrier_search_snapshot_migration_revises_pending_ingestion_completion() -> None:
    migration = _load_carrier_search_snapshot_migration()

    assert migration.revision == "20260422_01"
    assert migration.down_revision == "20260419_01"


def test_carrier_selection_migration_revises_carrier_search_snapshot() -> None:
    migration = _load_carrier_selection_migration()

    assert migration.revision == "20260426_01"
    assert migration.down_revision == "20260422_01"


def test_load_order_timestamps_migration_revises_carrier_selection() -> None:
    migration = _load_load_order_timestamps_migration()

    assert migration.revision == "20260427_01"
    assert migration.down_revision == "20260426_01"


def test_carrier_search_snapshot_migration_normalizes_legacy_trip_statuses() -> None:
    migration = _load_carrier_search_snapshot_migration()

    assert "UPDATE trips" in migration.TRIP_PROPOSAL_STATUS_BACKFILL_SQL
    assert "proposal_status = 'candidate'" in migration.TRIP_PROPOSAL_STATUS_BACKFILL_SQL
    assert "proposal_status = 'Evaluando'" in migration.TRIP_PROPOSAL_STATUS_BACKFILL_SQL


def test_alembic_baseline_creates_english_foundation_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        load_orders_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='load_orders'"
            )
            if row[0] is not None
        )

    assert {
        "users",
        "customers",
        "addresses",
        "truck_types",
        "load_orders",
        "carriers",
        "trips",
    }.issubset(set(inspector.get_table_names()))
    assert {
        "user_id",
        "customer_id",
        "customer_name",
        "status",
        "origin_text",
        "origin_load_date",
        "destination_text",
        "destination_unload_date",
        "cargo_description",
        "customer_price",
    }.issubset({column["name"] for column in inspector.get_columns("load_orders")})
    assert "fk_load_orders_user_id__users" in load_orders_sql
    assert "fk_load_orders_customer_id__customers" in load_orders_sql
    assert "fk_load_orders_origin_id__addresses" in load_orders_sql
    assert "fk_load_orders_destination_id__addresses" in load_orders_sql
    assert "fk_load_orders_truck_type_id__truck_types" in load_orders_sql


def test_alembic_head_creates_ingestion_runs_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        ingestion_runs_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestion_runs'"
            )
            if row[0] is not None
        )

    assert "ingestion_runs" in inspector.get_table_names()
    assert {
        "id",
        "user_id",
        "route",
        "status",
        "raw_text",
        "extracted_payload",
        "missing_fields",
        "load_order_id",
        "error_detail",
        "created_at",
        "updated_at",
    }.issubset({column["name"] for column in inspector.get_columns("ingestion_runs")})
    assert "fk_ingestion_runs_user_id__users" in ingestion_runs_sql
    assert "fk_ingestion_runs_load_order_id__load_orders" in ingestion_runs_sql
    assert 'status VARCHAR(50) NOT NULL' in ingestion_runs_sql
    assert "CHECK (status IN ('processing', 'completed', 'failed'))" in ingestion_runs_sql
    assert "raw_text TEXT NOT NULL" in ingestion_runs_sql
    assert "created_at" in ingestion_runs_sql
    assert "updated_at" in ingestion_runs_sql


def test_alembic_head_creates_load_order_human_reviews_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        human_reviews_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='load_order_human_reviews'"
            )
            if row[0] is not None
        )

    assert "load_order_human_reviews" in inspector.get_table_names()
    assert {
        "id",
        "load_order_id",
        "ingestion_run_id",
        "reviewed_by_user_id",
        "review_status",
        "submitted_fields",
        "remaining_missing_fields",
        "review_notes",
        "created_at",
    }.issubset(
        {column["name"] for column in inspector.get_columns("load_order_human_reviews")}
    )
    assert "fk_load_order_human_reviews_load_order_id__load_orders" in human_reviews_sql
    assert "fk_load_order_human_reviews_ingestion_run_id__ingestion_runs" in human_reviews_sql
    assert "fk_load_order_human_reviews_reviewed_by_user_id__users" in human_reviews_sql
    assert 'review_status VARCHAR(50) NOT NULL' in human_reviews_sql
    assert (
        "CHECK (review_status IN ('fields_updated', 'viability_confirmed'))"
        in human_reviews_sql
    )
    assert "submitted_fields JSON NOT NULL" in human_reviews_sql
    assert "remaining_missing_fields JSON NOT NULL" in human_reviews_sql
    assert "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL" in human_reviews_sql


def test_alembic_head_creates_pending_ingestion_text_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)

    assert {
        "customer_name",
        "origin_text",
        "destination_text",
    }.issubset({column["name"] for column in inspector.get_columns("load_orders")})


def test_alembic_head_creates_carrier_search_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        carriers_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='carriers'"
            )
            if row[0] is not None
        )

    assert "adr_capable" in {column["name"] for column in inspector.get_columns("carriers")}
    assert "adr_capable BOOLEAN NOT NULL" in carriers_sql
    assert "DEFAULT 0" not in carriers_sql


def test_alembic_head_creates_carrier_selection_column(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        load_orders_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='load_orders'"
            )
            if row[0] is not None
        )

    assert "selected_trip_id" in {
        column["name"] for column in inspector.get_columns("load_orders")
    }
    assert "fk_load_orders_selected_trip_id__trips" in load_orders_sql


def test_alembic_head_creates_load_order_timestamps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        load_orders_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='load_orders'"
            )
            if row[0] is not None
        )

    assert {"created_at", "updated_at"}.issubset(
        {column["name"] for column in inspector.get_columns("load_orders")}
    )
    assert "created_at DATETIME" in load_orders_sql
    assert "updated_at DATETIME" in load_orders_sql
    assert "CURRENT_TIMESTAMP" in load_orders_sql


def test_execution_monitoring_snapshots_migration_revises_carrier_intelligence() -> None:
    migration = _load_execution_monitoring_snapshots_migration()

    assert migration.revision == "20260517_01"
    assert migration.down_revision == "20260508_02"


def test_load_order_formalized_status_migration_revises_execution_monitoring_snapshots() -> None:
    migration = _load_load_order_formalized_status_migration()

    assert migration.revision == "20260530_01"
    assert migration.down_revision == "20260517_01"


def test_alembic_head_creates_execution_monitoring_snapshots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        snapshots_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_monitoring_snapshots'"
            )
            if row[0] is not None
        )

    assert {
        "load_order_id",
        "status",
        "progress_percent",
        "current_checkpoint",
        "route_points",
        "events",
        "alerts",
        "metadata",
        "created_at",
        "last_refreshed_at",
    }.issubset({column["name"] for column in inspector.get_columns("execution_monitoring_snapshots")})
    assert "progress_percent INTEGER DEFAULT '0' NOT NULL" in snapshots_sql


def test_same_flush_allows_persisting_selected_trip_relationship() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email=f"operator-{uuid.uuid4()}@example.com",
            operator_name="Operator Demo",
            auth_id=f"auth_{uuid.uuid4()}",
        )
        carrier = Carrier(company_name="Carrier Demo", documentation_valid=True, adr_capable=False)
        load_order = LoadOrder(user=user, status=LoadOrderStatus.PENDING_INGESTION, currency="EUR")
        trip = Trip(load_order=load_order, carrier=carrier)
        load_order.selected_trip = trip

        session.add_all([user, carrier, load_order, trip])

        try:
            session.commit()
        except CircularDependencyError as exc:  # pragma: no cover - red step expectation
            raise AssertionError("same-flush selected trip persistence should not cycle") from exc

        assert load_order.selected_trip_id == trip.id


def test_ingestion_trace_runtime_migration_revises_load_order_timestamps() -> None:
    migration = _load_ingestion_trace_runtime_migration()

    assert migration.revision == "20260502_01"
    assert migration.down_revision == "20260427_01"


def test_alembic_head_creates_ingestion_trace_runtime_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "alembic.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        ingestion_runs_sql = next(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestion_runs'"
            )
            if row[0] is not None
        )

    assert {
        "provider",
        "model_name",
        "execution_path",
        "trace_steps",
        "raw_model_response",
        "confidence_summary",
        "normalization_warnings",
    }.issubset({column["name"] for column in inspector.get_columns("ingestion_runs")})
    assert "provider VARCHAR(50)" in ingestion_runs_sql
    assert "model_name VARCHAR(255)" in ingestion_runs_sql
    assert "execution_path VARCHAR(50)" in ingestion_runs_sql
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email=f"operator-{uuid.uuid4()}@example.com",
            operator_name="Operator Demo",
            auth_id=f"auth_{uuid.uuid4()}",
        )
        carrier = Carrier(company_name="Carrier Demo", documentation_valid=True, adr_capable=False)
        load_order = LoadOrder(user=user, status=LoadOrderStatus.PENDING_INGESTION, currency="EUR")
        trip = Trip(load_order=load_order, carrier=carrier)
        load_order.selected_trip = trip

        session.add_all([user, carrier, load_order, trip])

        try:
            session.commit()
        except CircularDependencyError as exc:  # pragma: no cover - red step expectation
            raise AssertionError("same-flush selected trip persistence should not cycle") from exc

        assert load_order.selected_trip_id == trip.id


def _load_agent_runtime_foundation_migration():
    migration_path = Path("alembic/versions/20260508_01_phase8a_agent_runtime_foundation.py")
    spec = importlib.util.spec_from_file_location(
        "agent_runtime_foundation_migration", migration_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_domain_enums_include_agent_kind_values() -> None:
    assert [member.value for member in AgentKind] == [
        "orchestrator",
        "ingestion",
        "carrier_search",
        "smart_comms",
        "monitoring",
    ]


def test_domain_enums_include_agent_activity_state_values() -> None:
    assert [member.value for member in AgentActivityState] == [
        "running",
        "completed",
        "awaiting_operator",
        "warning",
        "error",
    ]


def test_domain_enums_include_monitoring_alert_severity_values() -> None:
    assert [member.value for member in MonitoringAlertSeverity] == [
        "info",
        "warning",
        "critical",
    ]


def test_domain_enums_include_monitoring_alert_type_values() -> None:
    assert [member.value for member in MonitoringAlertType] == [
        "status_changed",
        "deadline_approaching",
        "missing_route_data",
        "stalled_workflow",
        "margin_risk",
    ]


def test_domain_enums_include_monitoring_alert_status_values() -> None:
    assert [member.value for member in MonitoringAlertStatus] == [
        "open",
        "resolved",
    ]


def test_domain_enums_include_smart_comms_context_type_values() -> None:
    assert [member.value for member in SmartCommsContextType] == [
        "dashboard",
        "orders_list",
        "load_order",
        "carrier_match",
        "intake_review",
        "settings",
    ]


def test_domain_enums_include_smart_comms_message_role_values() -> None:
    assert [member.value for member in SmartCommsMessageRole] == [
        "user",
        "assistant",
        "system",
    ]


def test_domain_enums_include_carrier_pricing_model_values() -> None:
    assert [member.value for member in CarrierPricingModel] == [
        "per_km",
        "flat_rate",
        "market_adjusted",
    ]


def test_metadata_contains_agent_activities_table() -> None:
    assert "agent_activities" in Base.metadata.tables


def test_metadata_contains_smart_comms_conversations_table() -> None:
    assert "smart_comms_conversations" in Base.metadata.tables


def test_metadata_contains_smart_comms_messages_table() -> None:
    assert "smart_comms_messages" in Base.metadata.tables


def test_metadata_contains_monitoring_alerts_table() -> None:
    assert "monitoring_alerts" in Base.metadata.tables


def test_metadata_contains_agent_activities_columns() -> None:
    agent_activities = Base.metadata.tables["agent_activities"]
    assert {
        "id",
        "agent_kind",
        "activity_state",
        "load_order_id",
        "title",
        "detail",
        "activity_key",
        "next_action",
        "metadata",
        "created_at",
    }.issubset(agent_activities.columns.keys())
    assert not agent_activities.c.agent_kind.nullable
    assert not agent_activities.c.activity_state.nullable
    assert not agent_activities.c.title.nullable
    assert not agent_activities.c.activity_key.nullable
    assert agent_activities.c.load_order_id.nullable
    assert agent_activities.c.detail.nullable
    assert agent_activities.c.next_action.nullable
    assert agent_activities.c.metadata.nullable
    assert agent_activities.c.created_at.server_default is not None


def test_metadata_contains_smart_comms_conversations_columns() -> None:
    conversations = Base.metadata.tables["smart_comms_conversations"]
    assert {
        "id",
        "user_id",
        "context_type",
        "context_id",
        "route_path",
        "title",
        "created_at",
        "updated_at",
    }.issubset(conversations.columns.keys())
    assert not conversations.c.user_id.nullable
    assert not conversations.c.context_type.nullable
    assert not conversations.c.route_path.nullable
    assert conversations.c.context_id.nullable
    assert conversations.c.title.nullable
    assert conversations.c.created_at.server_default is not None
    assert conversations.c.updated_at.server_default is not None


def test_metadata_contains_smart_comms_messages_columns() -> None:
    messages = Base.metadata.tables["smart_comms_messages"]
    assert {
        "id",
        "conversation_id",
        "role",
        "content",
        "metadata",
        "created_at",
    }.issubset(messages.columns.keys())
    assert not messages.c.conversation_id.nullable
    assert not messages.c.role.nullable
    assert not messages.c.content.nullable
    assert messages.c.metadata.nullable
    assert messages.c.created_at.server_default is not None


def test_metadata_contains_monitoring_alerts_columns() -> None:
    alerts = Base.metadata.tables["monitoring_alerts"]
    assert {
        "id",
        "load_order_id",
        "alert_type",
        "severity",
        "status",
        "title",
        "detail",
        "dedupe_key",
        "metadata",
        "created_at",
        "resolved_at",
    }.issubset(alerts.columns.keys())
    assert not alerts.c.alert_type.nullable
    assert not alerts.c.severity.nullable
    assert not alerts.c.status.nullable
    assert not alerts.c.title.nullable
    assert not alerts.c.dedupe_key.nullable
    assert alerts.c.load_order_id.nullable
    assert alerts.c.detail.nullable
    assert alerts.c.metadata.nullable
    assert alerts.c.resolved_at.nullable
    assert alerts.c.created_at.server_default is not None


def test_agent_runtime_foundation_migration_revises_ingestion_trace_runtime() -> None:
    migration = _load_agent_runtime_foundation_migration()

    assert migration.revision == "20260508_01"
    assert migration.down_revision == "20260502_01"


def test_agent_runtime_foundation_migration_enum_values_match_domain() -> None:
    migration = _load_agent_runtime_foundation_migration()

    assert migration.agent_kind_enum.enums == [member.value for member in AgentKind]
    assert migration.agent_activity_state_enum.enums == [
        member.value for member in AgentActivityState
    ]
    assert migration.monitoring_alert_severity_enum.enums == [
        member.value for member in MonitoringAlertSeverity
    ]
    assert migration.monitoring_alert_type_enum.enums == [
        member.value for member in MonitoringAlertType
    ]
    assert migration.monitoring_alert_status_enum.enums == [
        member.value for member in MonitoringAlertStatus
    ]
    assert set(migration.smart_comms_context_type_enum.enums).issubset(
        set(member.value for member in SmartCommsContextType)
    )
    assert migration.smart_comms_message_role_enum.enums == [
        member.value for member in SmartCommsMessageRole
    ]


def test_agent_activity_schema_exposes_expected_fields() -> None:
    assert set(AgentActivityResponse.model_fields.keys()) == {
        "id",
        "agent_kind",
        "activity_state",
        "load_order_id",
        "title",
        "detail",
        "activity_key",
        "next_action",
        "metadata",
        "created_at",
    }


def test_agent_status_schema_exposes_expected_fields() -> None:
    assert set(AgentStatusResponse.model_fields.keys()) == {
        "agent_kind",
        "display_name",
        "state",
        "headline",
        "last_activity_at",
        "active_item_count",
    }


def test_execution_monitoring_schema_exposes_expected_fields() -> None:
    assert set(ExecutionMonitoringReadModelResponse.model_fields.keys()) == {
        "snapshot",
        "alerts",
        "shipment",
        "agent_update",
    }


def test_smart_comms_conversation_schema_exposes_expected_fields() -> None:
    assert set(SmartCommsConversationResponse.model_fields.keys()) == {
        "id",
        "user_id",
        "context_type",
        "context_id",
        "route_path",
        "title",
        "created_at",
        "updated_at",
    }


def _load_carrier_intelligence_migration():
    migration_path = Path("alembic/versions/20260508_02_phase8a_carrier_intelligence.py")
    spec = importlib.util.spec_from_file_location(
        "carrier_intelligence_migration", migration_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_carrier_intelligence_migration_revises_agent_runtime_foundation() -> None:
    migration = _load_carrier_intelligence_migration()

    assert migration.revision == "20260508_02"
    assert migration.down_revision == "20260508_01"


def test_metadata_contains_carrier_intelligence_columns() -> None:
    carriers = Base.metadata.tables["carriers"]
    trips = Base.metadata.tables["trips"]

    assert "home_base_text" in carriers.columns.keys()
    assert "service_countries" in carriers.columns.keys()
    assert "preferred_lanes" in carriers.columns.keys()
    assert "pricing_model" in carriers.columns.keys()
    assert "flat_rate_amount" in carriers.columns.keys()
    assert "fuel_surcharge_pct" in carriers.columns.keys()

    assert "ranking_score" in trips.columns.keys()
    assert "score_breakdown" in trips.columns.keys()
    assert "agent_reasoning" in trips.columns.keys()


def test_smart_comms_message_schema_exposes_expected_fields() -> None:
    assert set(SmartCommsMessageResponse.model_fields.keys()) == {
        "id",
        "conversation_id",
        "role",
        "content",
        "metadata",
        "created_at",
    }
