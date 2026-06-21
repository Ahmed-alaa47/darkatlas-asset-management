from langchain_core.output_parsers import PydanticOutputParser
from app.schemas import (
    NLQueryFilter, RiskAssessment, EnrichmentResult, AnalysisReport,
)

nl_query_parser = PydanticOutputParser(pydantic_object=NLQueryFilter)
risk_parser = PydanticOutputParser(pydantic_object=RiskAssessment)
enrichment_parser = PydanticOutputParser(pydantic_object=EnrichmentResult)
report_parser = PydanticOutputParser(pydantic_object=AnalysisReport)