
import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from dotenv import load_dotenv
from langsmith.wrappers import wrap_openai

load_dotenv()

def get_embedder():
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=os.getenv("OPENAI_API_KEY"))

def get_llm():
    """Get the OpenAI language model instance"""
    return ChatOpenAI(
        model="gpt-4",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY")
    )
