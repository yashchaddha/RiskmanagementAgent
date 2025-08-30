# rag_tools.py
import json
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from vector_index import VectorIndexService  # uses Zilliz + OpenAI embeddings (1536-d)

@tool
def semantic_risk_search(
    query: str,
    user_id: str,
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    similar_to_risk_id: Optional[str] = None,
) -> str:
    """
    Semantic search over a user's finalized risks (Zilliz/Milvus).
    Args:
        query: free-text query. Ignored if similar_to_risk_id is set (used as fallback).
        user_id: tenant scope (MANDATORY).
        top_k: number of results (1-50).
        filters: optional keys: category(list[str]), location, domain, department, risk_owner.
        similar_to_risk_id: if set, find risks similar to that finalized risk id.

    Returns:
        A string with BOTH a short natural-language summary and a JSON array of matches.
        Example:
        "Top 5 matches for “privacy risks in Mumbai” (owner=Rohan).
         JSON results:
         [ { ... }, ... ]"
    """
    result = VectorIndexService.search(
        user_id=user_id,
        query=query,
        top_k=int(top_k or 10),
        filters=filters or {},
        similar_to_risk_id=similar_to_risk_id,
    )

    # Return BOTH: short summary + JSON array
    summary = result.get("summary", "No matches found.")
    results_json = json.dumps(result.get("results", []), ensure_ascii=False, indent=2)
    return f"{summary}"
