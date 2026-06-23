from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import os

from app.database import engine, Base, get_db
from app import schemas, importer
from app.ai.chains import (
    run_nl_query, run_risk_analysis, run_enrichment, run_report,
)
from app.ai.agent import run_agent


app = FastAPI(
    title="DarkAtlas Asset Management — AI Track",
    description="LangChain-powered attack surface analysis",
    version="1.0.0",
)

API_KEY = os.getenv("API_KEY", "dev-secret-key")
DEFAULT_ORG = os.getenv("DEFAULT_ORG_ID", "org_default")


api_key_header = APIKeyHeader(name="X-API-Key")

def check_auth(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ── Import ──────────────────────────────────────────────────────────

@app.post("/import", response_model=schemas.ImportResult,
          dependencies=[Depends(check_auth)])
def import_assets(payload: schemas.ImportRequest, db: Session = Depends(get_db)):
    org_id = payload.organization_id or DEFAULT_ORG
    if not isinstance(payload.assets, list):
        raise HTTPException(400, "'assets' must be a list")
    return importer.bulk_import(db, payload.assets, org_id)


# ── Unified /analyze endpoint ───────────────────────────────────────

@app.post("/analyze", dependencies=[Depends(check_auth)])
def analyze(req: schemas.AnalyzeRequest, db: Session = Depends(get_db)):
    org_id = req.organization_id or DEFAULT_ORG

    if req.mode == "nl_query":
        if not req.query:
            raise HTTPException(400, "query is required for nl_query mode")
        return run_nl_query(req.query, db, org_id)

    elif req.mode == "risk":
        ids = req.asset_ids or ([req.asset_id] if req.asset_id else [])
        if not ids:
            raise HTTPException(400, "asset_id or asset_ids required")
        return run_risk_analysis(ids, db, org_id)

    elif req.mode == "enrich":
        if not req.asset_id:
            raise HTTPException(400, "asset_id required for enrich mode")
        return run_enrichment(req.asset_id, db, org_id)

    elif req.mode == "report":
        return run_report(db, org_id)

    else:
        raise HTTPException(400, f"Unknown mode: {req.mode}")


# ── Individual capability endpoints ────────────────────────────────

@app.post("/query", dependencies=[Depends(check_auth)])
def natural_language_query(body: schemas.QueryRequest, db: Session = Depends(get_db)):
    org_id = body.organization_id or DEFAULT_ORG
    return run_nl_query(body.query, db, org_id)


@app.post("/risk", dependencies=[Depends(check_auth)])
def risk_analysis(body: schemas.RiskRequest, db: Session = Depends(get_db)):
    org_id = body.organization_id or DEFAULT_ORG
    ids = body.asset_ids or ([body.asset_id] if body.asset_id else [])
    if not ids:
        raise HTTPException(400, "asset_id or asset_ids required")
    return run_risk_analysis(ids, db, org_id)


@app.post("/enrich/{asset_id}", dependencies=[Depends(check_auth)])
def enrich_asset(asset_id: str, body: schemas.EnrichRequest = None,
                 db: Session = Depends(get_db)):
    org_id = (body.organization_id if body else None) or DEFAULT_ORG
    return run_enrichment(asset_id, db, org_id)


@app.post("/report", dependencies=[Depends(check_auth)])
def generate_report(body: schemas.ReportRequest = None,
                    db: Session = Depends(get_db)):
    org_id = (body.organization_id if body else None) or DEFAULT_ORG
    asset_type = body.asset_type if body else None
    return run_report(db, org_id, asset_type)


# ── Bonus: Agentic endpoint ────────────────────────────────────────

@app.post("/agent", dependencies=[Depends(check_auth)])
def agent_endpoint(body: schemas.AgentRequest, db: Session = Depends(get_db)):
    org_id = body.organization_id or DEFAULT_ORG
    return run_agent(body.prompt, db, org_id)