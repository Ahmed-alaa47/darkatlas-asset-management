# DarkAtlas Asset Management — AI Track

## Overview
DarkAtlas Asset Management (AI Track) is a FastAPI-based web application tailored for LangChain-powered attack surface analysis. It provides an intelligent interface to manage assets, enrich asset data, analyze security risks, and answer natural language queries using AI capabilities.

## Purpose
The primary goal of this project is to serve as an intelligent backend for asset tracking and security analysis. It allows organizations to:
- Bulk import and deduplicate assets.
- Use natural language to query their asset inventory.
- Conduct automated risk assessments on specific assets.
- Enrich existing assets with AI-driven insights.
- Generate comprehensive security reports.

## Getting Started

### Prerequisites
- Python 3.10+
- Docker and Docker Compose (if running via Docker)
- An OpenAI API Key (or supported LLM provider keys) for LangChain

### How to Run

#### Option 1: Running with Docker (Recommended)
1. Clone the repository and navigate to the project root:
   ```bash
   cd darkatlas-asset-management
   ```
2. Copy the example environment variables file and fill in your keys:
   ```bash
   cp .env.example .env
   ```
3. Build and start the containers:
   ```bash
   docker-compose up --build
   ```
4. The API will be accessible at `http://localhost:8000`. You can explore the interactive Swagger documentation at `http://localhost:8000/docs`.

#### Option 2: Running Locally
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```
2. Set up the `.env` file:
   ```bash
   cp .env.example .env
   ```
3. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## API Documentation

All protected endpoints require an `x-api-key` header for authentication. 

### General Endpoints

#### 1. Health Check
Check the operational status of the API.
- **Endpoint:** `GET /health`
- **Output:**
  ```json
  {
    "status": "ok",
    "time": "2023-10-25T12:00:00.000000"
  }
  ```

#### 2. Import Assets
Bulk import and deduplicate assets for an organization.
- **Endpoint:** `POST /import`
- **Headers:** `x-api-key: <your_api_key>`
- **Input (JSON):**
  ```json
  {
    "organization_id": "org_default",
    "assets": [
      {
        "name": "web-server-01",
        "type": "server",
        "ip_address": "192.168.1.10"
      }
    ]
  }
  ```
- **Output (JSON):** (Follows `schemas.ImportResult` model)
  ```json
  {
    "imported_count": 1,
    "duplicates_ignored": 0,
    "status": "success"
  }
  ```

---

### AI Capability Endpoints

#### 3. Natural Language Query
Query your asset inventory using plain English.
- **Endpoint:** `POST /query`
- **Headers:** `x-api-key: <your_api_key>`
- **Input (JSON):**
  ```json
  {
    "organization_id": "org_default",
    "query": "Show me all databases with critical vulnerabilities."
  }
  ```

#### 4. Risk Analysis
Perform a LangChain-powered risk analysis on specific assets.
- **Endpoint:** `POST /risk`
- **Headers:** `x-api-key: <your_api_key>`
- **Input (JSON):**
  ```json
  {
    "organization_id": "org_default",
    "asset_ids": ["asset_abc123", "asset_def456"]
  }
  ```
  *(Note: You can also pass `"asset_id": "..."` for a single asset)*

#### 5. Enrich Asset
Enrich an existing asset with additional AI-gathered context.
- **Endpoint:** `POST /enrich/{asset_id}`
- **Headers:** `x-api-key: <your_api_key>`
- **Input (JSON):**
  ```json
  {
    "organization_id": "org_default"
  }
  ```

#### 6. Generate Report
Generate a comprehensive security report for the organization or a specific asset type.
- **Endpoint:** `POST /report`
- **Headers:** `x-api-key: <your_api_key>`
- **Input (JSON):**
  ```json
  {
    "organization_id": "org_default",
    "asset_type": "server"
  }
  ```

### Advanced Route: Aggregated `/analyze`
Alternatively, you can use the multi-purpose `/analyze` endpoint by passing a `mode` parameter:
- **Endpoint:** `POST /analyze`
- **Modes:** `"nl_query"`, `"risk"`, `"enrich"`, `"report"`
- **Example Input (JSON):**
  ```json
  {
    "organization_id": "org_default",
    "mode": "nl_query",
    "query": "Summarize my cloud assets"
  }
  ```
