from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

CLASSIFICATIONS = ["Public", "Internal", "Confidential", "Restricted"]
FREQUENCIES = ["Realtime", "Hourly", "Daily", "Weekly", "Monthly", "Ad-hoc"]
FORMATS = ["Table", "View", "API", "File", "Stream", "Dashboard"]

FIELD_TYPES = [
    "string", "integer", "number", "decimal", "boolean",
    "date", "timestamp", "object", "array",
]
RULE_TYPES = [
    "not_null", "unique", "accepted_values", "range",
    "regex", "freshness", "row_count", "custom",
]
CONTRACT_STATUSES = ["draft", "active", "deprecated"]


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
    has_contract: bool = False
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


# --- Data contracts ----------------------------------------------------------
class SchemaField(BaseModel):
    name: str = ""
    type: str = "string"
    required: bool = False
    pii: bool = False
    description: str = ""


class QualityRule(BaseModel):
    field: str = ""  # empty = dataset-level rule
    rule: str = "not_null"
    description: str = ""


class DataContractBase(BaseModel):
    version: str = "1.0.0"
    status: str = "draft"
    schema_fields: List[SchemaField] = Field(default_factory=list)
    quality_rules: List[QualityRule] = Field(default_factory=list)
    slo_availability: str = ""
    slo_freshness: str = ""
    slo_max_latency: str = ""


class DataContractUpsert(DataContractBase):
    pass


class DataContractOut(DataContractBase):
    id: int
    product_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssistContractResponse(BaseModel):
    contract: dict  # {schema_fields, quality_rules, slo_*}
    source: str
    note: str = ""


# ── New AI assist schemas ─────────────────────────────────────────────────────

class ImproveDescriptionRequest(BaseModel):
    description: str = Field(..., min_length=1)
    name: str = ""
    domain: str = ""

class ImproveDescriptionResponse(BaseModel):
    improved: str
    note: str = ""


class SuggestRequest(BaseModel):
    name: str = ""
    domain: str = ""
    description: str = ""
    source_systems: str = ""

class SuggestResponse(BaseModel):
    suggestions: List[str]
    note: str = ""


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)

class SearchFilters(BaseModel):
    domains: List[str] = []
    classifications: List[str] = []
    tags: List[str] = []
    contains_pii: Optional[bool] = None
    rerank_ids: List[int] = []  # product IDs in relevance order (best first)

class SearchAssistResponse(BaseModel):
    filters: SearchFilters
    note: str = ""


class ChatRequest(BaseModel):
    product_id: int
    message: str = Field(..., min_length=1)

class ChatResponse(BaseModel):
    reply: str
    note: str = ""


class SimilarProduct(BaseModel):
    id: int
    name: str
    domain: str = ""
    reason: str = ""

class DuplicateCheckRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    domain: str = ""
    source_systems: str = ""

class DuplicateCheckResponse(BaseModel):
    similar: List[SimilarProduct] = []
    warning: str = ""
    note: str = ""


class ClarifyRequest(BaseModel):
    name: str = ""
    description: str = ""
    domain: str = ""
    source_systems: str = ""
    answers: str = ""  # user's answers to previous questions (empty on first call)

class ClarifyResponse(BaseModel):
    ok: bool              # True = input is good enough, False = needs clarification
    questions: List[str] = []   # follow-up questions when ok=False
    improved: dict = {}   # filled fields when ok=True or answers provided
    message: str = ""     # short explanation shown to user
