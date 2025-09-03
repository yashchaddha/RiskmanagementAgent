# rag_tools.py
import json
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from vector_index import VectorIndexService
from vector_index import ControlsVectorIndexService

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


@tool
def semantic_control_search(
    query: Optional[str],
    user_id: str,
    top_k: int = 50,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Semantic search over a user's controls stored in Zilliz/Milvus.
    Args:
        query: free-text control query.
        user_id: tenant scope.
        top_k: number of results (1-50).
        filters: optional keys: status(str), annex(str), risk_id(str)
    Returns:
        dict: { "summary": str, "results": [ {control_uid,title,objective,status,annex,risk_id,control_text,score}, ... ] }
    """
    filters = filters or {}
    try:
        result = ControlsVectorIndexService.search(
            user_id=user_id,
            query=query or "",
            top_k=int(top_k or 50),
            filters=filters,
        )
        # Ensure stable shape
        res = result or {"summary": "No results.", "results": []}
        res["count"] = len(res.get("results", []))
        return res
    except Exception as e:
        return {"summary": f"Error searching controls: {str(e)}", "results": [], "count": 0}
