from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import json
import os

from app.database import engine, Base, get_db
from app import schemas, importer
from app.ai.chains import (
    run_nl_query, run_risk_analysis, run_enrichment, run_report,
)

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


#import
@app.post("/import", response_model=schemas.ImportResult,
          dependencies=[Depends(check_auth)])
def import_assets(payload: dict, db: Session = Depends(get_db)):
    org_id = payload.get("organization_id", DEFAULT_ORG)
    records = payload.get("assets", [])
    if not isinstance(records, list):
        raise HTTPException(400, "'assets' must be a list")
    return importer.bulk_import(db, records, org_id)


#analyze endpoint with mode
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


#one endpoint per capability

@app.post("/query", dependencies=[Depends(check_auth)])
def natural_language_query(body: dict, db: Session = Depends(get_db)):
    org_id = body.get("organization_id", DEFAULT_ORG)
    return run_nl_query(body["query"], db, org_id)


@app.post("/risk", dependencies=[Depends(check_auth)])
def risk_analysis(body: dict, db: Session = Depends(get_db)):
    org_id = body.get("organization_id", DEFAULT_ORG)
    ids = body.get("asset_ids") or [body["asset_id"]]
    return run_risk_analysis(ids, db, org_id)


@app.post("/enrich/{asset_id}", dependencies=[Depends(check_auth)])
def enrich_asset(asset_id: str, body: dict = None, db: Session = Depends(get_db)):
    org_id = (body or {}).get("organization_id", DEFAULT_ORG)
    return run_enrichment(asset_id, db, org_id)


@app.post("/report", dependencies=[Depends(check_auth)])
def generate_report(body: dict = None, db: Session = Depends(get_db)):
    org_id = (body or {}).get("organization_id", DEFAULT_ORG)
    asset_type = (body or {}).get("asset_type")
    return run_report(db, org_id, asset_type)