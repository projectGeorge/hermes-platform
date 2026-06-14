from fastapi import APIRouter

from app.backend.schemas.truck_type import TruckTypeResponse
from app.backend.services.prototype_catalog import PROTOTYPE_TRUCK_TYPES

router = APIRouter(prefix="/truck-types", tags=["Truck Types"])


@router.get("", response_model=list[TruckTypeResponse])
async def list_truck_types() -> list[TruckTypeResponse]:
    return [
        TruckTypeResponse(id=truck_type_id, name=name)
        for truck_type_id, name in PROTOTYPE_TRUCK_TYPES
    ]
