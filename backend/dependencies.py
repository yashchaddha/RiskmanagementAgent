
import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
from langsmith import traceable

LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")

load_dotenv()

def get_embedder():
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=os.getenv("OPENAI_API_KEY"))

def get_llm():
    """Get the OpenAI language model instance"""
    return ChatOpenAI(
        model="gpt-4o",
        seed=1234,
        api_key=os.getenv("OPENAI_API_KEY")
    )

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="make_llm_call_with_history")
def make_llm_call_with_history(system_prompt: str, user_input: str, conversation_history: list) -> str:
    """Standardized LLM call that includes conversation history for context"""
    llm = get_llm()
    
    # Build messages with conversation history for context
    messages = []
    
    # Add system message
    messages.append(SystemMessage(content=system_prompt))
    
    # Add conversation history as context (last 5 exchanges to avoid token limits)
    recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
    for exchange in recent_history:
        if exchange.get("user"):
            messages.append(HumanMessage(content=exchange["user"]))
        if exchange.get("assistant"):
            messages.append(AIMessage(content=exchange["assistant"]))
    
    # Add current user input
    messages.append(HumanMessage(content=user_input))
    
    # Make the call
    response = llm.invoke(messages)
    return response.content
