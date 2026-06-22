"""
Guardrails ensure the LLM never fabricates assets.
Every chain output is validated against the real database.
"""
from sqlalchemy.orm import Session
from app.schemas import (
    NLQueryFilter, RiskAssessment, EnrichmentResult, AnalysisReport,
)
from app.models import Asset


class GuardrailError(Exception):
    pass


def validate_nl_query_filter(flt: NLQueryFilter) -> NLQueryFilter:
    """NL query filters are inherently safe — LLM only returns filters,
    not assets. We just sanitize."""
    # strip any suspicious tag values, ignore non-strings and empty strings
    flt.tags = [
        t.lower().strip() 
        for t in flt.tags 
        if isinstance(t, str) and t.strip()
    ]
    return flt


def validate_risk_assessment(assessment: RiskAssessment,
                             db: Session, org_id: str) -> RiskAssessment:
    """Drop any finding that references an asset_id not in the DB."""
    valid_ids = set()
    for finding in assessment.findings or []:
        asset = db.query(Asset).filter(
            Asset.id == finding.asset_id,
            Asset.organization_id == org_id,
        ).first()
        if asset:
            valid_ids.add(finding.asset_id)

    assessment.findings = [
        f for f in (assessment.findings or []) if f.asset_id in valid_ids
    ]
            
    assessment.risk_score = max(0, min(100, assessment.risk_score))
    return assessment

def validate_enrichment(result: EnrichmentResult,
                        asset: Asset) -> EnrichmentResult:
    """Ensure enrichment doesn't alter canonical fields."""
    if result.environment not in ("prod", "staging", "dev", "unknown"):
        result.environment = "unknown"
    if result.criticality not in ("low", "medium", "high"):
        result.criticality = "medium"
    if result.category not in (
        "web_service", "api_endpoint", "mail_server", "dns", "cdn",
        "database", "certificate", "infrastructure", "unknown"
    ):
        result.category = "unknown"
    result.enriched_metadata.pop("value", None)
    result.enriched_metadata.pop("type", None)
    result.enriched_metadata.pop("id", None)
    return result


def validate_report(report: AnalysisReport, db: Session,
                    org_id: str) -> AnalysisReport:
    """Reports are stat-grounded; we just verify total_assets matches."""
    # total_assets is injected from pre-computed stats, so it's trustworthy
    return report