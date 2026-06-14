from pydantic import BaseModel, Field


class RuntimeSettingsResponse(BaseModel):
    enable_auto_carrier_search: bool = False
    enable_ingestion_smart_comms_handoff: bool = False
    enable_smart_comms_retrieval: bool = False
    enable_carrier_search_retrieval: bool = False
    ingestion_provider: str = ""
    ingestion_model_name: str = ""
    reasoning_provider: str = ""
    reasoning_model_name: str = ""
    chroma_reachable: bool = False


class RuntimeSettingsUpdate(BaseModel):
    enable_auto_carrier_search: bool | None = Field(default=None)
    enable_ingestion_smart_comms_handoff: bool | None = Field(default=None)
    enable_smart_comms_retrieval: bool | None = Field(default=None)
    enable_carrier_search_retrieval: bool | None = Field(default=None)
