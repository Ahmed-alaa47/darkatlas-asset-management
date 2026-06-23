from datetime import datetime
from typing import Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class AssetType(str, Enum):
    domain = "domain"
    subdomain = "subdomain"
    ip_address = "ip_address"
    service = "service"
    certificate = "certificate"
    technology = "technology"


class AssetStatus(str, Enum):
    active = "active"
    stale = "stale"
    archived = "archived"


# Import / CRUD schemas 

class AssetIn(BaseModel):
    id: Optional[str] = None
    type: AssetType
    value: str
    status: AssetStatus = AssetStatus.active
    source: str = "import"
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    # convenience relationship fields from the sample dataset
    parent: Optional[str] = None
    covers: Optional[str] = None
    resolves_to: Optional[list[str]] = None
    runs_on: Optional[str] = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: AssetType
    value: str
    status: AssetStatus
    first_seen: datetime
    last_seen: datetime
    source: str
    tags: list[str]
    metadata: dict[str, Any]


class ImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[dict]


#AI analysis schemas

class NLQueryFilter(BaseModel):
    """Structured filter produced by the LLM from natural language."""
    asset_type: Optional[AssetType] = Field(
        None, description="Filter by asset type if mentioned")
    status: Optional[AssetStatus] = Field(
        None, description="Filter by status if mentioned")
    tags: list[str] = Field(
        default_factory=list,
        description="Tag filters (e.g. 'production' -> 'prod')")
    value_contains: Optional[str] = Field(
        None, description="Substring to match in asset value")
    metadata_filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata field filters, e.g. {'expires_before': '...'}")
    explanation: str = Field(
        "", description="Brief explanation of the interpreted query")


class RiskFinding(BaseModel):
    asset_id: str
    severity: str  
    description: str


class RiskAssessment(BaseModel):
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: str
    summary: str
    findings: list[RiskFinding]
    recommendations: list[str]


class EnrichmentResult(BaseModel):
    environment: str  
    category: str
    criticality: str  
    confidence: Optional[float] = Field(default=0.5, ge=0.0, le=1.0)
    enriched_metadata: Optional[dict[str, Any]] = Field(default_factory=dict)
    reasoning: str


class ReportSection(BaseModel):
    title: str
    content: str


class AnalysisReport(BaseModel):
    title: str
    executive_summary: str
    sections: Optional[list[ReportSection]]= Field(default_factory=list)
    total_assets: int
    generated_at: str


#Generic AI response wrapper

class AnalyzeRequest(BaseModel):
    mode: str = Field(..., description="nl_query | risk | enrich | report")
    query: Optional[str] = None        
    asset_id: Optional[str] = None     
    asset_ids: Optional[list[str]] = None  
    organization_id: Optional[str] = None


# Typed request schemas for individual endpoints

class ImportRequest(BaseModel):
    organization_id: Optional[str] = Field(
        None, description="Organization ID; defaults to server-configured value")
    assets: list[dict[str, Any]] = Field(
        ..., description="List of asset records to import")


class QueryRequest(BaseModel):
    organization_id: Optional[str] = None
    query: str = Field(..., description="Natural language query string")


class RiskRequest(BaseModel):
    organization_id: Optional[str] = None
    asset_id: Optional[str] = Field(None, description="Single asset ID")
    asset_ids: Optional[list[str]] = Field(None, description="Multiple asset IDs")


class EnrichRequest(BaseModel):
    organization_id: Optional[str] = None


class ReportRequest(BaseModel):
    organization_id: Optional[str] = None
    asset_type: Optional[str] = Field(
        None, description="Optional asset type filter (e.g. 'server', 'certificate')")


class AgentRequest(BaseModel):
    organization_id: Optional[str] = None
    prompt: str = Field(..., description="Free-form prompt for the AI agent")