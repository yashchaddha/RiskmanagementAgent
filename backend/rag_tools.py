import logging
import os
import re
from typing import Optional, Dict, Any, List, Set

from langchain_core.tools import tool
from database import RiskProfileDatabaseService
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient


logger = logging.getLogger(__name__)

_MILVUS_CLIENT: Optional[MilvusClient] = None


def init_vector_clients() -> None:
    """Initialise global Milvus/Zilliz client once at startup."""
    global _MILVUS_CLIENT

    if _MILVUS_CLIENT is not None:
        return

    zilliz_uri = os.getenv("ZILLIZ_URI")
    zilliz_token = os.getenv("ZILLIZ_TOKEN")

    if not zilliz_uri or not zilliz_token:
        logger.warning("ZILLIZ connection not configured; vector search tools will be disabled")
        return

    try:
        _MILVUS_CLIENT = MilvusClient(
            uri=zilliz_uri,
            token=zilliz_token,
            secure=True,
        )
        logger.info("Connected to Zilliz/Milvus at startup")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialise Milvus client", exc_info=exc)
        raise


def get_milvus_client() -> Optional[MilvusClient]:
    """Return shared Milvus client, initialising lazily if needed."""
    global _MILVUS_CLIENT
    if _MILVUS_CLIENT is None:
        init_vector_clients()
    return _MILVUS_CLIENT


def _extract_annex_ids_from_text(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    return {match.upper() for match in re.findall(r"A\.\d+(?:\.\d+)?", text, flags=re.IGNORECASE)}


def _tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token}


def _rerank_control_results(query: str, results: List[Dict[str, Any]], filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    if not results:
        return results

    query_lower = (query or "").lower()
    query_annex_ids = _extract_annex_ids_from_text(query)
    query_tokens = _tokenize(query_lower)
    filter_status = (filters or {}).get("status", "").lower()

    for result in results:
        similarity = float(result.get("similarity_score") or result.get("score") or 0.0)
        boost = 0.0

        annex_ids = _extract_annex_ids_from_text(result.get("annexa_mappings"))
        if query_annex_ids and annex_ids:
            matches = query_annex_ids.intersection(annex_ids)
            if matches:
                boost += 0.15 * len(matches)

        status_value = (result.get("status") or "").lower()
        if filter_status and status_value == filter_status:
            boost += 0.05
        else:
            for status_term in ["active", "inactive", "under review", "deprecated", "draft"]:
                if status_term in query_lower and status_value == status_term:
                    boost += 0.05
                    break

        owner_role = (result.get("owner_role") or "").lower()
        if owner_role and owner_role in query_lower:
            boost += 0.05

        linked_ids = result.get("linked_risk_ids") or ""
        for token in re.split(r",|;", linked_ids):
            rid = token.strip().lower()
            if rid and rid in query_lower:
                boost += 0.05
                break

        text_blob = " ".join(filter(None, [
            result.get("summary"),
            result.get("description"),
            result.get("title"),
            result.get("objective"),
        ])).lower()
        if text_blob:
            overlap = len(query_tokens.intersection(_tokenize(text_blob)))
            if overlap:
                boost += min(0.05, overlap * 0.005)

        result["score_boost"] = boost
        result["reranked_score"] = similarity + boost

    results.sort(key=lambda item: item.get("reranked_score", item.get("similarity_score", 0.0)), reverse=True)
    return results

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
        
        client = get_milvus_client()

        if client is None:
            return {
                "hits": [], 
                "count": 0, 
                "error": "Missing ZILLIZ_URI or ZILLIZ_TOKEN environment variables. Please configure your .env file.", 
                "query": query, 
                "category": category
            }

        OUTPUT_FIELDS = ["doc_id", "text"]

        # Auto-infer category from query patterns if not specified or is "all"
        cat = (category or "all").lower()
        if cat == "all":
            import re
            query_lower = query.lower()
            # Check for Annex A patterns
            if (re.search(r'\ba\.\d+(?:\.\d+)?\b', query_lower) or 
                'annex a' in query_lower or 
                any(term in query_lower for term in ['control', 'cryptographic', 'access control', 'key management'])):
                cat = "annex_a"
            # Check for clause patterns  
            elif (re.search(r'\bclause\s+\d+(?:\.\d+)?\b', query_lower) or
                  any(term in query_lower for term in ['leadership', 'isms scope', 'planning', 'support'])):
                cat = "clauses"

        # Check if this is an exact ID lookup (e.g., "A.5.6", "A.8.24")
        import re
        exact_id_match = re.match(r'^A\.\d+(?:\.\d+)?$', query.strip())
        
        if exact_id_match:
            # For exact ID lookups, try direct query first
            try:
                direct_results = client.query(
                    collection_name="iso_knowledge_index",
                    filter=f"doc_id == '{query.strip()}'",
                    output_fields=OUTPUT_FIELDS,
                    limit=1
                )
                if direct_results:
                    print(f"[DEBUG] Found exact match for {query.strip()}")
                    return {
                        "hits": [{
                            "id": direct_results[0].get("doc_id"),
                            "text": direct_results[0].get("text"),
                            "score": 1.0  # Perfect match
                        }],
                        "count": 1,
                        "query": query,
                        "category": category
                    }
            except Exception as e:
                print(f"[DEBUG] Direct lookup failed: {e}, falling back to semantic search")

        # Apply filtering based on doc_id patterns from embeddings creation:
        #  - Annex A domains/controls: "A.5", "A.8.24", etc.
        #  - Clauses/subclauses: "4", "5.2", etc. (numeric, no 'A.' prefix)
        filter_expr = None
        if cat == "annex_a":
            filter_expr = "doc_id like 'A.%'"
        elif cat == "clauses":
            filter_expr = None

        print(f"[DEBUG] knowledge_base_search: query='{query}', category='{category}' -> resolved_cat='{cat}', filter='{filter_expr}'")

        results = client.search(
            collection_name="iso_knowledge_index",
            data=[query_vec],
            anns_field="embedding",
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
        client = get_milvus_client()

        if client is None:
            return {
                "hits": [],
                "count": 0,
                "error": "Vector index not configured",
                "query": query,
                "user_id": user_id,
            }
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


@tool("semantic_risk_search_simple")
def semantic_risk_search_simple(query: str, user_id: str, top_k: int = 5) -> dict:
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
        client = get_milvus_client()

        if client is None:
            return {
                "hits": [],
                "count": 0,
                "error": "Vector index not configured",
                "query": query,
                "user_id": user_id,
            }
        OUTPUT_FIELDS = ["risk_text"]
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

        client = get_milvus_client()
        if client is None:
            return {
                "hits": [],
                "count": 0,
                "error": "Vector index not configured",
                "query": query,
                "user_id": user_id,
                "filters": filters,
            }
        
        # Build filter expression using Milvus scalar filtering
        filter_exp = f"user_id == '{user_id}'"
        if filters:
            for field, value in filters.items():
                if not value or not value.strip():
                    continue
                values = [v.strip() for v in value.split(',') if v.strip()]
                if not values:
                    continue
                
                if field == "annexa_mappings":
                    # Use LIKE for partial matching on annex mappings
                    if len(values) == 1:
                        filter_exp += f" && annexa_mappings like '%{values[0]}%'"
                    else:
                        like_conditions = [f"annexa_mappings like '%{v}%'" for v in values]
                        filter_exp += f" && ({' || '.join(like_conditions)})"
                elif field == "linked_risk_ids":
                    # Use LIKE for partial matching on linked risk IDs
                    if len(values) == 1:
                        filter_exp += f" && linked_risk_ids like '%{values[0]}%'"
                    else:
                        like_conditions = [f"linked_risk_ids like '%{v}%'" for v in values]
                        filter_exp += f" && ({' || '.join(like_conditions)})"
                else:
                    # Exact match for other fields
                    if len(values) == 1:
                        filter_exp += f" && {field} == '{values[0]}'"
                    else:
                        quoted_values = [f"'{v}'" for v in values]
                        filter_exp += f" && {field} in [{','.join(quoted_values)}]"
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
                similarity = score if score is not None else 0.0
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
                    "similarity_score": similarity,
                    "score": similarity
                })
        hits = _rerank_control_results(query, hits, filters)
        print(f"🔍 semantic_control_search found {len(hits)} hits (post-rerank)")
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

        client = get_milvus_client()
        if client is None:
            return {
                "hits": [],
                "count": 0,
                "error": "Vector index not configured",
                "query": query,
                "user_id": user_id,
                "linked_risk_ids": linked_risk_ids,
            }
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
