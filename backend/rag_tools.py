from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from database import RiskProfileDatabaseService
import os
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient
from typing import List, Dict, Any

@tool("get_risk_profiles")
def get_risk_profiles(user_id: str) -> dict:
    """
    Retrieve user's comprehensive risk profiles for intelligent risk generation.
    
    Args:
        user_id: User identifier
        
    Returns:
        Complete risk profile data including categories, scales, and definitions
    """
    print(f"🔍 get_risk_profiles called with user_id: '{user_id}'")
    try:
        print(f"🔍 Calling RiskProfileDatabaseService.get_user_risk_profiles('{user_id}')")
        result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
        
        if result.success and result.data and result.data.get("profiles"):
            profiles = result.data.get("profiles", [])
            print(f"🔍 Found {len(profiles)} profiles for user")
            
            # Extract useful data for risk generation
            risk_categories = []
            likelihood_scales = {}
            impact_scales = {}
            
            for profile in profiles:
                risk_type = profile.get("riskType", "")
                if risk_type:
                    risk_categories.append(risk_type)
                    
                    # Extract scales with descriptions
                    likelihood_scale = profile.get("likelihoodScale", [])
                    impact_scale = profile.get("impactScale", [])
                    
                    likelihood_scales[risk_type] = [
                        {"level": item.get("level"), "title": item.get("title"), "description": item.get("description", "")}
                        for item in likelihood_scale
                    ]
                    impact_scales[risk_type] = [
                        {"level": item.get("level"), "title": item.get("title"), "description": item.get("description", "")}
                        for item in impact_scale
                    ]
            
            print(f"🔍 Successfully extracted {len(risk_categories)} risk categories: {risk_categories}")
            return {
                "success": True,
                "risk_categories": risk_categories,
                "likelihood_scales": likelihood_scales,
                "impact_scales": impact_scales,
                "profiles_count": len(profiles),
                "user_id": user_id
            }
        
        print(f"🔍 No risk profiles found - returning error")
        return {
            "success": False,
            "error": "No risk profiles found",
            "risk_categories": [],
            "user_id": user_id
        }
        
    except Exception as e:
        print(f"🔍 Exception in get_risk_profiles: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "risk_categories": [],
            "user_id": user_id
        }


@tool("knowledge_base_search")
def knowledge_base_search(query: str, category: str = "all", top_k: int = 5) -> dict:
    """
    Search ISO 27001:2022 knowledge base for relevant clauses, controls, and information.
    Returns relevant entries from the knowledge base using semantic search.

    Args:
        query: User's question about ISO 27001 standards, clauses, or controls
        category: Filter by category - "clauses", "annex_a", or "all" (default)
        top_k: Number of results to return (default 5)
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vec: List[float] = emb.embed_query(query)
        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        
        OUTPUT_FIELDS = ["doc_id", "text"]
        
        # No filtering for now with simplified schema
        filter_expr = None
        
        results = client.search(
            collection_name="iso_knowledge_index",
            data=[query_vec],
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=filter_expr if filter_expr else None,
        )

        hits: List[Dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass

                hits.append({
                    "id": entity.get("doc_id"),
                    "text": entity.get("text"),
                    "score": score
                })

        return {
            "hits": hits,
            "count": len(hits),
            "query": query,
            "category": category
        }

    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "category": category}


@tool("semantic_risk_search")
def semantic_risk_search(query: str, user_id: str, top_k: int = 5) -> dict:
    """
    Semantically search the user's finalized risks stored in Zilliz/Milvus.
    Returns a JSON payload of the top matches (with scores) filtered by user_id.

    Args:
        query: Free-text user query about risks.
        user_id: Tenant scoping (strictly filter to this user).
        top_k: Number of results to return.
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vec: List[float] = emb.embed_query(query)
        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        OUTPUT_FIELDS = [
            "risk_id", "user_id", "organization_name", "location", "domain", 
            "category", "description", "likelihood", "impact", "treatment_strategy",
            "department", "risk_owner", "asset_value", "security_impact", 
            "target_date", "risk_progress", "residual_exposure", "risk_text"
        ]
        expr = f"user_id == '{user_id}'"

        print(f"🔍 semantic_risk_search: query='{query}', user_id='{user_id}', top_k={top_k}")
        results = client.search(
            collection_name="finalized_risks_index",
            data=[query_vec],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=expr,
        )

        hits: List[Dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass

                hits.append({
                    "risk_id": entity.get("risk_id"),
                    "score": score,
                    "user_id": entity.get("user_id"),
                    "organization_name": entity.get("organization_name"),
                    "location": entity.get("location"),
                    "domain": entity.get("domain"),
                    "category": entity.get("category"),
                    "description": entity.get("description"),
                    "likelihood": entity.get("likelihood"),
                    "impact": entity.get("impact"),
                    "treatment_strategy": entity.get("treatment_strategy"),
                    "department": entity.get("department"),
                    "risk_owner": entity.get("risk_owner"),
                    "asset_value": entity.get("asset_value"),
                    "security_impact": entity.get("security_impact"),
                    "target_date": entity.get("target_date"),
                    "risk_progress": entity.get("risk_progress"),
                    "residual_exposure": entity.get("residual_exposure"),
                    "risk_text": entity.get("risk_text"),
                })

        print(f"🔍 semantic_risk_search found {len(hits)} hits")
        print(f"🔍 Returning hits: {hits}")

        return {
            "hits": hits,
            "count": len(hits),
            "query": query,
            "user_id": user_id
        }

    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id}

@tool("semantic_control_search")
def semantic_control_search(query: str, user_id: str, filters: Optional[Dict[str, str]] = None, top_k: int = 5) -> dict:
    """
    Hybrid search for controls using Milvus scalar filtering + semantic search.
    
    Args:
        query: Search query text for semantic similarity
        user_id: User identifier (always applied as filter)
        filters: Dict of field filters, e.g. {"owner_role": "CIO", "status": "Active", "annexa_mappings": "A.5.30"}
        top_k: Number of results to return
    
    Returns:
        {
          "query": str,
          "user_id": str, 
          "count": int,
          "hits": [{"control_id": str, "title": str, "score": float, ...}]
        }
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)

        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        
        # Build filter expression using Milvus scalar filtering
        filter_exp = f"user_id == '{user_id}'"
        if filters:
            for field, value in filters.items():
                if field == "annexa_mappings":
                    # Use LIKE for partial matching on annex mappings
                    filter_exp += f" && annexa_mappings like '%{value}%'"
                elif field == "linked_risk_ids":
                    # Use LIKE for partial matching on linked risk IDs
                    filter_exp += f" && linked_risk_ids like '%{value}%'"
                else:
                    # Exact match for other fields
                    filter_exp += f" && {field} == '{value}'"
        # Only fetch allowed fields from the controls schema
        OUTPUT_FIELDS = [
            "control_id", "control_title", "control_description", "objective", "owner_role", "status", "annexa_mappings", "linked_risk_ids", "control_text", "user_id"
        ]

        print(f"🔍 semantic_control_search: query='{query}', user_id='{user_id}', filters={filters}, top_k={top_k}")

        res = client.search(
            collection_name="finalized_controls",
            data=[qv],
            anns_field="embedding",
            limit=min(top_k, 8),
            output_fields=OUTPUT_FIELDS,
            filter=filter_exp
        )

        hits: List[Dict[str, Any]] = []
        if res and len(res) > 0:
            for hit in res[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass
                hits.append({
                    "control_id": entity.get("control_id"),
                    "title": entity.get("control_title"),
                    "description": entity.get("control_description"),
                    "objective": entity.get("objective"),
                    "owner_role": entity.get("owner_role"),
                    "status": entity.get("status"),
                    "annexa_mappings": entity.get("annexa_mappings"),
                    "linked_risk_ids": entity.get("linked_risk_ids"),
                    "summary": entity.get("control_text"),
                    "score": score
                })
        print(f"🔍 semantic_control_search found {len(hits)} hits")
        print(f"🔍 Returning hits: {hits}")
        return {"hits": hits, "count": len(hits), "query": query, "user_id": user_id}
    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id}


@tool("fetch_controls_by_id")
def fetch_controls_by_id(query: str, user_id: str, linked_risk_ids: Optional[str] = None, top_k: int = 2) -> dict:
    """
    Return ONLY lightweight metadata for the best-matching controls.
    Schema:
      {
        "query": str,
        "user_id": str,
        "count": int,
        "hits": [
          {
            "control_id": str,
            "title": str,
            "summary": str,     # <= 200 chars
            "score": float
          }
        ]
      }
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)

        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        filter_exp = f"user_id == '{user_id}'"
        if linked_risk_ids and linked_risk_ids.strip():
            filter_exp += f" && linked_risk_ids like '%{linked_risk_ids.strip()}%'"
        # Only fetch allowed fields from the controls schema
        OUTPUT_FIELDS = [
            "control_id", "control_title", "control_description", "objective", "owner_role", "status", "annexa_mappings", "linked_risk_ids", "control_text", "user_id", "created_at", "updated_at"
        ]

        print(f"🔍 fetch_controls_by_id: query='{query}', user_id='{user_id}', linked_risk_ids='{linked_risk_ids}', top_k={top_k}")

        res = client.search(
            collection_name="finalized_controls",
            data=[qv],
            anns_field="embedding",
            limit=min(top_k, 2),
            output_fields=OUTPUT_FIELDS,
            filter=filter_exp
        )

        hits: List[Dict[str, Any]] = []
        if res and len(res) > 0:
            for hit in res[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass
                hits.append({
                    "control_id": entity.get("control_id"),
                    "title": entity.get("control_title"),
                    "summary": entity.get("control_text"),
                    "score": score
                })
        print(f"🔍 semantic_control_search found {len(hits)} hits")
        print(f"🔍 Returning hits: {hits}")
        return {"hits": hits, "count": len(hits), "query": query, "user_id": user_id}
    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id, "linked_risk_ids": linked_risk_ids}


# @tool("fetch_controls_by_id")
# def fetch_controls_by_id(query: str, user_id: str) -> dict:
#     """
#     Fetch small, display-ready records for a shortlist of controls.
#     Only returns fields suitable for UI/answering (no embeddings).
#     """
#     try:

#         client = MilvusClient(
#             uri=os.getenv("ZILLIZ_URI"),
#             token=os.getenv("ZILLIZ_TOKEN"),
#             secure=True
#         )

#         # If you also keep Mongo as source of truth, read there by IDs.
#         # If only Zilliz, issue a query (depends on your schema; below is pseudo):
#         OUTPUT_FIELDS = [
#             "control_id", "control_title", "control_description", "objective", "annexa_mappings", "linked_risk_ids", "owner_role", "process_steps", "evidence_samples", "metrics", "frequency", "policy_ref", "status", "rationale", "assumptions", "control_text", "user_id", "created_at", "updated_at"
#         ]

#         # Pseudo-impl: You might maintain a parallel KV store, or query Milvus by expr:
#         expr = f"user_id == '{user_id}' && control_id in [{','.join([repr(i) for i in control_ids])}]"
#         res = client.query(
#             collection_name="finalized_controls",
#             expr=expr,
#             output_fields=OUTPUT_FIELDS
#         )

#         def clip(s: str, n: int = 500) -> str:
#             if not s: return s
#             s = s.strip().replace("\n", " ")
#             return (s[:n] + "…") if len(s) > n else s

#         controls = []
#         for r in (res or []):
#             controls.append({
#                 "control_id": r.get("control_id"),
#                 "title": clip(r.get("control_title"), 140),
#                 "description": clip(r.get("control_description"), 600),
#                 "objective": clip(r.get("objective"), 300),
#                 "annex": r.get("annexa_mappings"),
#                 "metrics": r.get("metrics"),
#                 "frequency": r.get("frequency"),
#                 "owner_role": r.get("owner_role"),
#                 "policy_ref": r.get("policy_ref"),
#                 "status": r.get("status"),
#                 "evidence_samples": r.get("evidence_samples"),
#             })

#         return {"controls": controls, "count": len(controls), "user_id": user_id}
#     except Exception as e:
#         return {"controls": [], "count": 0, "error": str(e), "user_id": user_id}
