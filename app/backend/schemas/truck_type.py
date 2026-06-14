from pydantic import BaseModel, ConfigDict


class TruckTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
