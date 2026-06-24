from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

CLASSIFICATIONS = ["Public", "Internal", "Confidential", "Restricted"]
FREQUENCIES = ["Realtime", "Hourly", "Daily", "Weekly", "Monthly", "Ad-hoc"]
FORMATS = ["Table", "View", "API", "File", "Stream", "Dashboard"]


class DataProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    domain: str = ""
    owner_name: str = ""
    owner_email: str = ""
    classification: str = "Internal"
    source_systems: str = ""
    update_frequency: str = "Daily"
    output_format: str = "Table"
    sla: str = ""
    contains_pii: bool = False
    tags: str = ""


class DataProductCreate(DataProductBase):
    pass


class DataProductUpdate(DataProductBase):
    pass


class DataProductOut(DataProductBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssistRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class AssistResponse(BaseModel):
    fields: dict
    source: str  # "claude" or "fallback"
    note: str = ""
