import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()


def get_llm(temperature: float = 0.2):
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=temperature,
        )