from langchain_core.prompts import ChatPromptTemplate

#1. Natural-language query -> structured filter
NL_QUERY_SYSTEM = """You are a query translator for an Attack Surface Monitoring
asset database. Convert the user's natural-language request into a structured
filter that will be executed against a real database.

CRITICAL RULES:
- You produce ONLY a filter object. You NEVER produce asset IDs, asset values,
  or asset lists. The database returns real assets.
- Map synonyms: "production" -> tag "prod", "staging" -> "staging", "dev" -> "dev".
- For expired certificates, set metadata_filters.expires_before to today's date.
- For expiring-soon certificates, set metadata_filters.expires_before to a date
  30 days from now.
- If the query is out of scope (not about assets), return empty filters and
  explain in the explanation field.
- Tag names should be lowercased.

Available asset types: domain, subdomain, ip_address, service, certificate, technology
Available statuses: active, stale, archived

{format_instructions}
"""

nl_query_prompt = ChatPromptTemplate.from_messages([
    ("system", NL_QUERY_SYSTEM),
    ("human", "Today is {today}. User query: {query}"),
])


#2. Risk scoring & summarization
RISK_SYSTEM = """You are a security risk analyst for an Attack Surface Monitoring
platform. Analyze the provided assets and produce a risk assessment.

You will receive a JSON list of real assets from the database. You MUST:
- Only reference asset_id values that appear in the provided data.
- NEVER invent asset IDs or values.
- Consider: expired/expiring TLS certificates, sensitive exposed services
  (SSH/RDP/Telnet/FTP), end-of-life technologies, exposed databases,
  stale assets that may be forgotten.
- risk_score: 0-100 (higher = more risk).
- risk_level: low (0-24), medium (25-49), high (50-74), critical (75-100).

{format_instructions}
"""

risk_prompt = ChatPromptTemplate.from_messages([
    ("system", RISK_SYSTEM),
    ("human", "Assets to analyze (JSON):\n{assets_json}"),
])


#3. Automated enrichment & categorization
ENRICH_SYSTEM = """You are an asset enrichment agent for an Attack Surface
Monitoring platform. Given a raw asset, classify it and suggest enriched metadata.

Classification rules:
- environment: prod / staging / dev / unknown
  * Heuristics: value contains "api.", "www.", "prod" -> prod
    "staging", "stage" -> staging; "dev", "test" -> dev
- category: e.g. web_service, api_endpoint, mail_server, dns, cdn,
  database, certificate, infrastructure, unknown
- criticality: low / medium / high
  * Exposed databases, auth services, production = high
  * Dev/test = low; everything else = medium

You MUST NOT change the asset's canonical value. Only suggest metadata additions.
If uncertain, set confidence lower.

{format_instructions}
"""

enrich_prompt = ChatPromptTemplate.from_messages([
    ("system", ENRICH_SYSTEM),
    ("human", "Asset (JSON):\n{asset_json}"),
])


#4. Natural-language report generation
REPORT_SYSTEM = """You are generating a security inventory and risk report for
an Attack Surface Monitoring platform.

You will receive:
1. Pre-computed statistics (asset counts by type, status, risk indicators).
   These are GROUND TRUTH — do not contradict them.
2. A JSON list of notable assets (high-risk subset).

Rules:
- Only reference asset IDs from the provided data.
- Use the provided statistics verbatim for any numbers.
- Structure the report with clear sections.
- Be concise and actionable.

{format_instructions}
"""

report_prompt = ChatPromptTemplate.from_messages([
    ("system", REPORT_SYSTEM),
    ("human",
     "Statistics:\n{stats_json}\n\nNotable assets:\n{assets_json}"),
])