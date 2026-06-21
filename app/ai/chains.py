import json
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy.orm import Session
from langchain_core.runnables import RunnablePassthrough

from app.ai.llm import get_llm
from app.ai.prompts import (
    nl_query_prompt, risk_prompt, enrich_prompt, report_prompt,
)
from app.ai.output_parsers import (
    nl_query_parser, risk_parser, enrichment_parser, report_parser,
)
from app.ai.guardrails import (
    validate_nl_query_filter, validate_risk_assessment,
    validate_enrichment, validate_report,
)
from app.schemas import (
    NLQueryFilter, RiskAssessment, EnrichmentResult, AnalysisReport,
)
from app.crud import filter_assets, get_asset
from app.models import Asset


# Chain 1: Natural-language asset query

def build_nl_query_chain():
    llm = get_llm(temperature=0.0)
    chain = (
        nl_query_prompt
        | llm
        | nl_query_parser
    )
    return chain


def run_nl_query(query: str, db: Session, org_id: str) -> dict:
    """
    Full pipeline: NL -> structured filter (LLM) -> DB query -> real assets.
    The LLM never returns assets; it only returns a filter.
    """
    chain = build_nl_query_chain()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        flt: NLQueryFilter = chain.invoke({
            "query": query,
            "today": today,
            "format_instructions": nl_query_parser.get_format_instructions(),
        })
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}", "matches": []}

    flt = validate_nl_query_filter(flt)

    # Execute the filter against the REAL database
    assets = filter_assets(db, org_id, flt)

    return {
        "interpreted_filter": flt.model_dump(),
        "matches": [
            {
                "id": a.id, "type": a.type, "value": a.value,
                "status": a.status, "tags": a.tags,
            }
            for a in assets
        ],
        "count": len(assets),
    }


# Chain 2: Risk scoring & summarization

def build_risk_chain():
    llm = get_llm(temperature=0.1)
    chain = (risk_prompt | llm | risk_parser)
    return chain


def run_risk_analysis(asset_ids: list[str], db: Session,
                      org_id: str) -> dict:
    """Analyze risk for a group of assets by ID."""
    assets = (
        db.query(Asset)
        .filter(Asset.id.in_(asset_ids),
                Asset.organization_id == org_id)
        .all()
    )
    if not assets:
        return {"error": "No assets found for given IDs"}

    assets_json = json.dumps([
        {
            "id": a.id, "type": a.type, "value": a.value,
            "status": a.status, "tags": a.tags,
            "metadata": a.metadata_ or {},
        }
        for a in assets
    ], default=str)

    chain = build_risk_chain()
    try:
        assessment: RiskAssessment = chain.invoke({
            "assets_json": assets_json,
            "format_instructions": risk_parser.get_format_instructions(),
        })
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}"}

    # GUARDRAIL: drop findings referencing non-existent assets
    assessment = validate_risk_assessment(assessment, db, org_id)

    return assessment.model_dump()


# Chain 3: Automated enrichment & categorization

def build_enrichment_chain():
    llm = get_llm(temperature=0.1)
    chain = (enrich_prompt | llm | enrichment_parser)
    return chain


def run_enrichment(asset_id: str, db: Session, org_id: str,
                   persist: bool = True) -> dict:
    asset = get_asset(db, asset_id, org_id)
    if not asset:
        return {"error": f"Asset {asset_id} not found"}

    asset_json = json.dumps({
        "id": asset.id, "type": asset.type, "value": asset.value,
        "status": asset.status, "tags": asset.tags,
        "metadata": asset.metadata_ or {},
    }, default=str)

    chain = build_enrichment_chain()
    try:
        result: EnrichmentResult = chain.invoke({
            "asset_json": asset_json,
            "format_instructions": enrichment_parser.get_format_instructions(),
        })
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}"}

    # GUARDRAIL: validate classification values, strip canonical fields
    result = validate_enrichment(result, asset)

    # Persist enrichment into metadata + tags
    if persist:
        meta = dict(asset.metadata_ or {})
        meta.update(result.enriched_metadata)
        meta["_enrichment"] = {
            "environment": result.environment,
            "category": result.category,
            "criticality": result.criticality,
            "confidence": result.confidence,
        }
        asset.metadata_ = meta
        # add environment as a tag for filtering
        if result.environment != "unknown":
            tags = set(asset.tags or [])
            tags.add(result.environment)
            asset.tags = list(tags)
        db.commit()

    return {
        "asset_id": asset.id,
        "enrichment": result.model_dump(),
    }


# Chain 4: Natural-language report generation

def build_report_chain():
    llm = get_llm(temperature=0.3)
    chain = (report_prompt | llm | report_parser)
    return chain


def _compute_stats(assets: list[Asset]) -> dict:
    """Pre-compute statistics from REAL data — LLM must use these numbers."""
    today = datetime.utcnow()
    soon = today + timedelta(days=30)

    type_counts = Counter(a.type for a in assets)
    status_counts = Counter(a.status for a in assets)

    expired_certs = 0
    expiring_soon = 0
    sensitive_services = 0
    eol_tech = 0

    for a in assets:
        meta = a.metadata_ or {}
        if a.type == "certificate":
            expires = meta.get("expires")
            if expires:
                try:
                    exp_date = datetime.fromisoformat(str(expires).split("T")[0])
                    if exp_date < today:
                        expired_certs += 1
                    elif exp_date < soon:
                        expiring_soon += 1
                except (ValueError, TypeError):
                    pass
        if a.type == "service":
            val = a.value.lower()
            if any(p in val for p in ["22/tcp", "3389/tcp", "23/tcp",
                                       "21/tcp", "3306/tcp", "5432/tcp",
                                       "6379/tcp", "27017/tcp"]):
                sensitive_services += 1
        if a.type == "technology":
            version = str(meta.get("version", ""))
            name = str(meta.get("name", "")).lower()
            # crude EOL detection
            if any(t in name for t in ["php5", "openssl 1.0",
                                        "apache 2.2", "nginx 1.10"]):
                eol_tech += 1

    return {
        "total_assets": len(assets),
        "by_type": dict(type_counts),
        "by_status": dict(status_counts),
        "expired_certificates": expired_certs,
        "expiring_soon_certificates": expiring_soon,
        "sensitive_services": sensitive_services,
        "end_of_life_technologies": eol_tech,
    }


def run_report(db: Session, org_id: str,
               asset_type: str = None) -> dict:
    """Generate an inventory/risk report over the dataset (or a subset)."""
    q = db.query(Asset).filter(Asset.organization_id == org_id)
    if asset_type:
        q = q.filter(Asset.type == asset_type)
    assets = q.all()

    stats = _compute_stats(assets)

    # pick notable assets (certs + sensitive services) for the LLM context
    notable = []
    today = datetime.utcnow()
    for a in assets:
        meta = a.metadata_ or {}
        include = False
        if a.type == "certificate":
            expires = meta.get("expires")
            if expires:
                try:
                    exp_date = datetime.fromisoformat(str(expires).split("T")[0])
                    if exp_date < today + timedelta(days=30):
                        include = True
                except (ValueError, TypeError):
                    pass
        if a.type == "service":
            val = a.value.lower()
            if any(p in val for p in ["22/", "3389/", "23/", "21/",
                                       "3306/", "5432/", "6379/", "27017/"]):
                include = True
        if include:
            notable.append({
                "id": a.id, "type": a.type, "value": a.value,
                "status": a.status, "metadata": meta,
            })

    notable = notable[:50]

    chain = build_report_chain()
    try:
        report: AnalysisReport = chain.invoke({
            "stats_json": json.dumps(stats, indent=2),
            "assets_json": json.dumps(notable, default=str, indent=2),
            "format_instructions": report_parser.get_format_instructions(),
        })
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}", "stats": stats}

    report = validate_report(report, db, org_id)
    report.total_assets = stats["total_assets"]  # force ground truth
    report.generated_at = datetime.utcnow().isoformat()

    return {
        "report": report.model_dump(),
        "stats": stats,
    }