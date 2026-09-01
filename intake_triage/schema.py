from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ServiceLine(str, Enum):
    STRATEGY_OM = "STRATEGY_OM"
    MA_TRANSACTION = "MA_TRANSACTION"
    TAX_STRUCTURING = "TAX_STRUCTURING"
    RISK_REGULATORY = "RISK_REGULATORY"
    TECH_DATA = "TECH_DATA"


class ComplexityTier(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class WorkSignal(str, Enum):
    STRATEGY = "strategy"
    TRANSACTION = "transaction"
    TAX = "tax"
    REGULATORY = "regulatory"
    TECHNOLOGY = "technology"


class DeadlineKind(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    NONE = "none"


class CompanySize(str, Enum):
    SME = "sme"
    MID = "mid"
    ENTERPRISE = "enterprise"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Industry(str, Enum):
    FINANCIAL_SERVICES = "financial_services"
    HEALTHCARE = "healthcare"
    INDUSTRIALS = "industrials"
    TECHNOLOGY = "technology"
    ENERGY = "energy"
    CONSUMER = "consumer"
    PROFESSIONAL_SERVICES = "professional_services"
    PUBLIC_SECTOR = "public_sector"
    REAL_ESTATE = "real_estate"
    OTHER = "other"


class AbstainReason(str, Enum):
    LOW_EVIDENCE = "low_evidence"
    CROSS_LEAD_CONFLICT = "cross_lead_conflict"
    HOURS_PROXIMITY = "hours_proximity"
    OUT_OF_TAXONOMY = "out_of_taxonomy"
    EXTRACTION_FAILED = "extraction_failed"


class IntakeKind(str, Enum):
    ENQUIRY = "enquiry"
    VENDOR_PITCH = "vendor_pitch"
    JOB_APPLICANT = "job_applicant"
    OTHER = "other"


class Driver(BaseModel, Generic[T]):
    """Value plus a verbatim evidence span. Null means the text does not say."""

    value: T | None = None
    evidence_span: str | None = None


class Extraction(BaseModel):
    work_signals: list[Driver[WorkSignal]] = Field(default_factory=list)
    jurisdiction_names: Driver[list[str]] = Field(default_factory=Driver)
    entity_count: Driver[int] = Field(default_factory=Driver)
    workstream_count: Driver[int] = Field(default_factory=Driver)
    deadline_kind: Driver[DeadlineKind] = Field(default_factory=Driver)
    regulator_or_investigation: Driver[bool] = Field(default_factory=Driver)
    systems_change: Driver[bool] = Field(default_factory=Driver)
    multi_party: Driver[bool] = Field(default_factory=Driver)
    intake_kind: Driver[IntakeKind] = Field(
        default_factory=lambda: Driver(value=IntakeKind.ENQUIRY)
    )


class Enquiry(BaseModel):
    enquiry_id: str
    submitted_at: datetime
    contact_name: str | None = None
    contact_email: str | None = None
    company_name: str
    industry: Industry
    company_size: CompanySize
    urgency: Urgency
    description: str


class LineScore(BaseModel):
    service_line: ServiceLine
    hours: int
    owner: str
    evidence_spans: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    estimated_hours: int | None
    complexity: ComplexityTier | None
    service_line: ServiceLine | None
    rule_trace: list[str]
    competing_lines: list[LineScore]
    line_scores: list[LineScore]
    null_drivers: list[str]
    low_evidence: bool


class TriageDecision(BaseModel):
    enquiry_id: str
    service_line: ServiceLine | None = None
    complexity: ComplexityTier | None = None
    estimated_hours: int | None = None
    route_to: str | None = None
    abstained: bool
    abstain_reason: AbstainReason | None = None
    competing_lines: list[LineScore] = Field(default_factory=list)
    rule_trace: list[str] = Field(default_factory=list)
    extraction: Extraction
    model_version: str | None = None
    prompt_version: str | None = None
    samples: int = 1
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    decided_at: datetime


def extraction_json_schema() -> dict:
    """Runtime schema for forced tool use. Never hand-write a duplicate."""
    return Extraction.model_json_schema()
