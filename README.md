# DarkAtlas Asset Management — AI Track

## Overview

DarkAtlas Asset Management is a **FastAPI** backend for LangChain-powered attack surface analysis. It ingests, deduplicates, and persists asset inventories, then exposes four AI analysis features — all grounded in real data, validated by guardrails, and producing structured Pydantic outputs.

## Architecture

```
┌─────────────┐     ┌───────────────────────────┐     ┌──────────────┐
│   Client     │────▶│  FastAPI (typed schemas)   │────▶│ PostgreSQL   │
│  (curl/UI)   │◀────│  auth via X-API-Key        │◀────│ (SQLAlchemy) │
└─────────────┘     └───────────┬───────────────┘     └──────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    LangChain Chains    │
                    │  • NL Query            │
                    │  • Risk Analysis       │
                    │  • Enrichment          │
                    │  • Report Generation   │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Guardrails Layer     │
                    │  validate against DB   │
                    └───────────────────────┘
```

## Key Design Decisions

| Concept | Implementation |
|---|---|
| **Structured output** | `llm.with_structured_output(PydanticModel)` — native function-calling, no manual parsing |
| **Grounding** | Every chain receives real DB data; reports get pre-computed stats as ground truth |
| **Guardrails** | Post-LLM validation layer strips fabricated asset IDs, clamps scores, sanitizes tags |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (recommended)
- An OpenAI API key (or any OpenAI-compatible provider)

### Option 1: Docker (Recommended)

```bash
git clone <repo-url> && cd darkatlas-asset-management

# Configure environment
cp .env.example .env
# Edit .env → set OPENAI_API_KEY and API_KEY

# Start
docker-compose up --build
```

The API is live at `http://localhost:8000` — Swagger docs at `http://localhost:8000/docs`.

### Option 2: Local

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit with your keys

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` |  | — | Your LLM provider API key |
| `OPENAI_MODEL` | — | `gpt-4o-mini` | Model name |
| `OPENAI_BASE_URL` | — | OpenAI default | Custom base URL (for proxies / other providers) |
| `API_KEY` |  | Your Key | API authentication key for all protected endpoints |
| `DATABASE_URL` | — | `postgresql://darkatlas:darkatlas@localhost:5432/darkatlas` | PostgreSQL connection string |
| `DEFAULT_ORG_ID` | — | `org_default` | Default organization ID |

---

## Running Tests

```bash
# Unit tests (no API key needed)
pytest tests/ -v

# Integration tests (requires OPENAI_API_KEY in .env)
pytest tests/ -v  # LLM tests auto-skip if no key is set
```

---

## API Reference

All protected endpoints require the `X-API-Key` header.

### Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "time": "2025-06-22T12:00:00.000000"
}
```

---

### 1. Import Assets

Bulk import with automatic deduplication. Re-importing the same `(org, type, value)` tuple updates `last_seen`, merges tags (union), and shallow-merges metadata.

```bash
curl -X POST http://localhost:8000/import \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "org_default",
    "assets": [
      {
        "id": "a1",
        "type": "domain",
        "value": "example.com",
        "status": "active",
        "tags": ["root"],
        "metadata": {}
      },
      {
        "id": "a2",
        "type": "subdomain",
        "value": "api.example.com",
        "status": "active",
        "tags": ["prod"],
        "metadata": {},
        "parent": "a1"
      },
      {
        "id": "a3",
        "type": "certificate",
        "value": "CN=api.example.com",
        "status": "active",
        "tags": [],
        "metadata": {"issuer": "Lets Encrypt", "expires": "2025-01-02"},
        "covers": "a2"
      },
      {
        "id": "a4",
        "type": "service",
        "value": "22/tcp",
        "status": "active",
        "tags": [],
        "metadata": {"banner": "OpenSSH 7.4"}
      },
      {
        "id": "a5",
        "type": "technology",
        "value": "nginx",
        "status": "active",
        "tags": [],
        "metadata": {"version": "1.10.3"}
      }
    ]
  }'
```

**Example output:**

```json
{
  "imported": 5,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
```

Re-importing the same payload:

```json
{
  "imported": 0,
  "updated": 5,
  "skipped": 0,
  "errors": []
}
```

---

### 2. Natural Language Query

Translates a plain-English question into structured filters, executes them against the real database, and returns matching assets.

**Prompt → LLM → `NLQueryFilter` (Pydantic) → DB query → real assets**

```bash
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "org_default",
    "query": "Show me all certificates"
  }'
```

**Example output:**

```json
{
  "interpreted_filter": {
    "asset_type": "certificate",
    "status": null,
    "tags": [],
    "value_contains": null,
    "metadata_filters": {},
    "explanation": "Filtering for all certificate assets"
  },
  "matches": [
    {
      "id": "a3",
      "type": "certificate",
      "value": "CN=api.example.com",
      "status": "active",
      "tags": []
    }
  ],
  "count": 1
}
```

**More example prompts:**

| Prompt | Expected filter |
|---|---|
| `"Find all production subdomains"` | `asset_type: subdomain, tags: ["prod"]` |
| `"Show me stale domains"` | `asset_type: domain, status: stale` |
| `"List services on port 22"` | `asset_type: service, value_contains: "22"` |

---

### 3. Risk Analysis

Analyzes specific assets and produces a scored risk assessment. The guardrails layer drops any finding that references an asset ID not in the database.

**Real asset data → LLM → `RiskAssessment` (Pydantic) → guardrail validation → response**

```bash
curl -X POST http://localhost:8000/risk \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "org_default",
    "asset_ids": ["a3", "a4"]
  }'
```

**Example output:**

```json
{
  "risk_score": 72,
  "risk_level": "high",
  "summary": "Expired TLS certificate and exposed SSH service present significant risk.",
  "findings": [
    {
      "asset_id": "a3",
      "severity": "high",
      "description": "Certificate CN=api.example.com expired on 2025-01-02."
    },
    {
      "asset_id": "a4",
      "severity": "medium",
      "description": "SSH service (22/tcp) running OpenSSH 7.4 — outdated version with known CVEs."
    }
  ],
  "recommendations": [
    "Immediately renew the expired certificate for api.example.com.",
    "Upgrade OpenSSH to the latest stable version and restrict SSH access via firewall rules."
  ]
}
```

---

### 4. Enrich Asset

Classifies a single asset and enriches its metadata. Persists the enrichment back to the database.

**Single asset → LLM → `EnrichmentResult` (Pydantic) → guardrail validation → DB update**

```bash
curl -X POST http://localhost:8000/enrich/a2 \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"organization_id": "org_default"}'
```

**Example output:**

```json
{
  "asset_id": "a2",
  "enrichment": {
    "environment": "prod",
    "category": "api_endpoint",
    "criticality": "high",
    "confidence": 0.9,
    "enriched_metadata": {
      "likely_purpose": "Primary API gateway",
      "exposure_level": "internet-facing"
    },
    "reasoning": "Subdomain 'api.example.com' with 'prod' tag indicates a production API endpoint. API services are critical due to direct internet exposure."
  }
}
```

---

### 5. Generate Report

Produces a structured security report grounded in pre-computed statistics. The LLM receives real stats as ground truth and cannot contradict them.

**DB stats + notable assets → LLM → `AnalysisReport` (Pydantic) → response**

Reports are cached in-memory by `(org_id, asset_type)`. Subsequent calls return the cached version instantly.

```bash
curl -X POST http://localhost:8000/report \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "org_default",
    "asset_type": "certificate"
  }'
```

**Example output:**

```json
{
  "report": {
    "title": "Certificate Security Report — org_default",
    "executive_summary": "1 certificate asset found, with 1 expired certificate requiring immediate attention.",
    "sections": [
      {
        "title": "Certificate Status",
        "content": "CN=api.example.com — expired on 2025-01-02. Immediate renewal required."
      }
    ],
    "total_assets": 1,
    "generated_at": "2025-06-22T12:00:00"
  },
  "stats": {
    "total_assets": 1,
    "by_type": {"certificate": 1},
    "by_status": {"active": 1},
    "expired_certificates": 1,
    "expiring_soon_certificates": 0,
    "sensitive_services": 0,
    "end_of_life_technologies": 0
  },
  "cached": false
}
```

---

### 6. Unified `/analyze` Endpoint

A single endpoint that dispatches to any of the four chains based on the `mode` parameter.

```bash
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "nl_query",
    "organization_id": "org_default",
    "query": "Show me all active domains"
  }'
```

| Mode | Required Fields | Maps To |
|---|---|---|
| `nl_query` | `query` | `/query` |
| `risk` | `asset_id` or `asset_ids` | `/risk` |
| `enrich` | `asset_id` | `/enrich/{asset_id}` |
| `report` | — | `/report` |

---



## Project Structure

```
├── app/
│   ├── main.py            # FastAPI app, all endpoints
│   ├── database.py        # SQLAlchemy engine & session
│   ├── models.py          # Asset & AssetRelationship ORM models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── crud.py            # Database operations (upsert, filter, graph)
│   ├── importer.py        # Bulk import with dedup & relationship linking
│   └── ai/
│       ├── llm.py         # LLM provider configuration
│       ├── prompts.py     # ChatPromptTemplate definitions (4 chains)
│       ├── chains.py      # Chain execution logic (NL query, risk, enrich, report)
│       ├── guardrails.py  # Post-LLM validation (strip hallucinated IDs, clamp scores)
│       └── output_parsers.py  # Strategy documentation
├── tests/
│   ├── conftest.py        # SQLite fixtures & sample data
│   ├── test_ai.py         # Guardrail, filter, and LLM integration tests
│   └── test_import.py     # Dedup, merge, relationship, and multi-tenancy tests
├── Dockerfile
├── docker-compose.yml     # PostgreSQL + app
├── requirements.txt
└── .env.example
```
