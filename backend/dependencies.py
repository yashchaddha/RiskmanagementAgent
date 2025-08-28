
import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
def get_llm():
    """Get the OpenAI language model instance"""
    return ChatOpenAI(
        model="gpt-4",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY")
    )
