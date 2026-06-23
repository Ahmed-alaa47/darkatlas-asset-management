from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from app.ai.llm import get_llm
from app.ai.chains import run_risk_analysis, run_enrichment, run_report, run_nl_query

def run_agent(prompt: str, db: Session, org_id: str) -> dict:
    llm = get_llm(temperature=0.0)
    
    # We define the tools inside this function so they can capture `db` and `org_id`from the local scope.
    # This prevents LangChain from trying to convert `Session`into a JSON Schema for the LLM, and also prevents the LLM from hallucinating org_ids.
    
    @tool
    def query_assets(query: str) -> dict:
        """Use this tool to find assets in the database using natural language."""
        return run_nl_query(query, db, org_id)

    @tool
    def analyze_risk(asset_ids: list[str]) -> dict:
        """Use this tool to calculate the risk score for a specific list of asset IDs."""
        return run_risk_analysis(asset_ids, db, org_id)

    @tool
    def enrich_asset(asset_id: str) -> dict:
        """Use this tool to classify and enrich a single asset's metadata."""
        return run_enrichment(asset_id, db, org_id)

    @tool
    def generate_report() -> dict:
        """Use this tool to generate a full security report for an organization."""
        return run_report(db, org_id)
        
    tools = [query_assets, analyze_risk, enrich_asset, generate_report]
    
    system_prompt = f"""
    You are an expert security assistant for organization {org_id}.
    You have access to a database of assets via tools.
    Always use the provided tools to answer the user's question. 
    Do not guess asset IDs; use the query_assets tool if you need to find an ID first.
    """
    
    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    
    result = executor.invoke({
        "input": prompt
    })
    
    return result