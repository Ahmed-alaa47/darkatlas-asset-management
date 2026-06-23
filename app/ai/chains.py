import json
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy.orm import Session

from app.ai.llm import get_llm
from app.ai.prompts import (
    nl_query_prompt, risk_prompt, enrich_prompt, report_prompt,
)
from app.ai.guardrails import (
    validate_nl_query_filter, validate_risk_assessment,
    validate_enrichment, validate_report,
)
from app.schemas import (
    NLQueryFilter, RiskAssessment, EnrichmentResult, AnalysisReport,AssetType
)
from app.crud import filter_assets, get_asset
from app.models import Asset

_report_cache = {}

# Chain 1: Natural-language asset query

def run_nl_query(query: str, db: Session, org_id: str) -> dict:
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(NLQueryFilter)
    chain = nl_query_prompt | structured_llm

    today = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        flt = chain.invoke({"query": query, "today": today})
        # LangChain might return a dict depending on the provider
        if isinstance(flt, dict):
            flt = NLQueryFilter(**flt)
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}", "matches": [], "count": 0}

    flt = validate_nl_query_filter(flt)
    query_lower = query.lower()
    if "certificate" in query_lower or "cert" in query_lower:
        flt.asset_type = AssetType.certificate
    elif "subdomain" in query_lower:
        flt.asset_type = AssetType.subdomain
    elif "ip address" in query_lower or "ip_address" in query_lower:
        flt.asset_type = AssetType.ip_address
    elif "service" in query_lower or "port" in query_lower:
        flt.asset_type = AssetType.service
    elif "domain" in query_lower:
        flt.asset_type = AssetType.domain
    elif "technology" in query_lower or "tech" in query_lower:
        flt.asset_type = AssetType.technology
    # --------------------------------

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

def run_risk_analysis(asset_ids: list[str], db: Session, org_id: str) -> dict:
    assets = (
        db.query(Asset)
        .filter(Asset.id.in_(asset_ids), Asset.organization_id == org_id)
        .all()
    )
    if not assets:
        return {"error": "No assets found for given IDs"}

    assets_json = json.dumps([
        {"id": a.id, "type": a.type, "value": a.value, "status": a.status,
         "tags": a.tags, "metadata": a.metadata_ or {}}
        for a in assets
    ], default=str)

    llm = get_llm(temperature=0.1)
    # Use json_mode to force pure JSON output instead of function calling
    structured_llm = llm.with_structured_output(RiskAssessment, method="json_mode")
    chain = risk_prompt | structured_llm

    try:
        assessment = chain.invoke({"assets_json": assets_json})
        if isinstance(assessment, dict):
            assessment = RiskAssessment(**assessment)
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}"}

    assessment = validate_risk_assessment(assessment, db, org_id)
    return assessment.model_dump()


# Chain 3: Automated enrichment & categorization

def run_enrichment(asset_id: str, db: Session, org_id: str, persist: bool = True) -> dict:
    asset = get_asset(db, asset_id, org_id)
    if not asset:
        return {"error": f"Asset {asset_id} not found"}

    asset_json = json.dumps({
        "id": asset.id, "type": asset.type, "value": asset.value,
        "status": asset.status, "tags": asset.tags, "metadata": asset.metadata_ or {}
    }, default=str)

    llm = get_llm(temperature=0.1)
    structured_llm = llm.with_structured_output(EnrichmentResult)
    chain = enrich_prompt | structured_llm

    try:
        result = chain.invoke({"asset_json": asset_json})
        # LangChain might return a dict depending on the provider
        if isinstance(result, dict):
            result = EnrichmentResult(**result)
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}"}

    result = validate_enrichment(result, asset)

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
        if result.environment != "unknown":
            tags = set(asset.tags or [])
            tags.add(result.environment)
            asset.tags = list(tags)
        db.commit()

    return {"asset_id": asset.id, "enrichment": result.model_dump()}


# Chain 4: Natural-language report generation

def _compute_stats(assets: list[Asset]) -> dict:
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
                    if exp_date < today: expired_certs += 1
                    elif exp_date < soon: expiring_soon += 1
                except: pass
        if a.type == "service":
            val = a.value.lower()
            if any(p in val for p in ["22/tcp", "3389/tcp", "23/tcp", "21/tcp", "3306/tcp", "5432/tcp"]):
                sensitive_services += 1

    return {
        "total_assets": len(assets), "by_type": dict(type_counts),
        "by_status": dict(status_counts), "expired_certificates": expired_certs,
        "expiring_soon_certificates": expiring_soon,
        "sensitive_services": sensitive_services, "end_of_life_technologies": eol_tech,
    }

def run_report(db: Session, org_id: str, asset_type: str = None) -> dict:
    # 1. Check if we have a cached report for this organization
    cache_key = f"{org_id}_{asset_type}"
    if cache_key in _report_cache:
        return {
            "report": _report_cache[cache_key]["report"],
            "stats": _report_cache[cache_key]["stats"],
            "cached": True 
        }

    # 2. If not in cache, fetch from DB
    q = db.query(Asset).filter(Asset.organization_id == org_id)
    if asset_type: q = q.filter(Asset.type == asset_type)
    assets = q.all()

    stats = _compute_stats(assets)
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
                    if exp_date < today + timedelta(days=30): include = True
                except: pass
        if a.type == "service":
            if any(p in a.value.lower() for p in ["22/", "3389/", "23/", "3306/", "5432/"]):
                include = True
        if include:
            notable.append({"id": a.id, "type": a.type, "value": a.value, "metadata": meta})

    notable = notable[:50]
    llm = get_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(AnalysisReport)
    chain = report_prompt | structured_llm

    try:
        report = chain.invoke({
            "stats_json": json.dumps(stats, indent=2),
            "assets_json": json.dumps(notable, default=str, indent=2)
        })
        if isinstance(report, dict):
            report = AnalysisReport(**report)
    except Exception as e:
        return {"error": f"LLM parsing failed: {str(e)}", "stats": stats}

    report = validate_report(report, db, org_id)
    report.total_assets = stats["total_assets"]
    report.generated_at = datetime.utcnow().isoformat()

    # 3. Save the successful result to cache before returning
    _report_cache[cache_key] = {
        "report": report.model_dump(),
        "stats": stats
    }

    return {
        "report": report.model_dump(),
        "stats": stats,
        "cached": False
    }