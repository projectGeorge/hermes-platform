from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.truck_type import TruckType

PROTOTYPE_TRUCK_TYPES: tuple[tuple[int, str], ...] = (
    (1, "tautliner"),
    (2, "reefer"),
    (3, "mega"),
)

_PROTOTYPE_TRUCK_TYPE_IDS = {truck_type_id for truck_type_id, _ in PROTOTYPE_TRUCK_TYPES}


def is_canonical_prototype_truck_type_id(truck_type_id: int | None) -> bool:
    return truck_type_id in _PROTOTYPE_TRUCK_TYPE_IDS


async def ensure_canonical_prototype_truck_types(session: AsyncSession) -> None:
    result = await session.execute(
        select(TruckType).where(TruckType.id.in_(_PROTOTYPE_TRUCK_TYPE_IDS))
    )
    existing_truck_types = {truck_type.id: truck_type for truck_type in result.scalars().all()}

    for truck_type_id, name in PROTOTYPE_TRUCK_TYPES:
        existing_truck_type = existing_truck_types.get(truck_type_id)
        if existing_truck_type is None:
            session.add(TruckType(id=truck_type_id, name=name))
            continue

        existing_truck_type.name = name

    await session.flush()
