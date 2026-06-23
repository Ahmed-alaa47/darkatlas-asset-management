"""
Output parsing strategy
-----------------------
This project uses LangChain's ``llm.with_structured_output(PydanticModel)``
(see chains.py) instead of legacy PydanticOutputParser objects.

Structured output leverages native function-calling / JSON mode on the LLM
provider side, producing validated Pydantic v2 instances directly — no manual
format-instruction injection or retry parsing needed.
"""