from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from database import RiskProfileDatabaseService
import os
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient
from typing import List, Dict, Any
from graph_kg import (
    graph_filter_controls_ids,
    graph_filter_risk_ids,
    graph_reasoning_search,
    graph_find_related_entities,
    graph_contextual_risk_search,
)

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


@tool("graph_filter_controls")
def graph_filter_controls(filters_json: dict) -> dict:
    """
    Deterministically filter controls via Neo4j and return candidate control_ids.
    filters_json keys may include: owner_role, status, department, location, domain,
    annex_prefix, impact_gte, likelihood_gte, risk_ids (list).
    """
    try:
        ids = graph_filter_controls_ids(filters_json or {})
        return {"ids": ids, "count": len(ids)}
    except Exception as e:
        return {"ids": [], "count": 0, "error": str(e)}


@tool("graph_filter_risks")
def graph_filter_risks(filters_json: dict) -> dict:
    """
    Deterministically filter risks via Neo4j and return candidate risk_ids.
    filters_json keys may include: department, location, domain, impact_gte, likelihood_gte, unmitigated.
    """
    try:
        ids = graph_filter_risk_ids(filters_json or {})
        print(f"🔍 graph_filter_risks returning {len(ids)} ids")
        print(f"🔍 ids: {ids}")
        return {"ids": ids, "count": len(ids)}
    except Exception as e:
        return {"ids": [], "count": 0, "error": str(e)}


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

@tool("hybrid_risk_search")
def hybrid_risk_search(
    query: str,
    user_id: str,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> dict:
    """
    Graph-first + semantic for risks. Uses Neo4j to get candidate risk_ids, then
    constrains Milvus search within those. Falls back to unconstrained if empty.
    Automatically infers graph filters from semantic queries when filters not provided.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        from pymilvus import MilvusClient

        def _infer_filters_from_query(query_text: str) -> Dict[str, Any]:
            """Infer graph filters from semantic query text"""
            inferred = {}
            query_lower = query_text.lower()
            
            # Category-based filtering
            if any(term in query_lower for term in ['cyber', 'security', 'breach', 'malware', 'ransomware', 'hacking', 'phishing', 'cybersecurity']):
                inferred['category'] = 'Technology'
            elif any(term in query_lower for term in ['financial', 'budget', 'cost', 'revenue', 'cash flow']):
                inferred['category'] = 'Financial'
            elif any(term in query_lower for term in ['operational', 'operations', 'process', 'workflow']):
                inferred['category'] = 'Operational'
            elif any(term in query_lower for term in ['compliance', 'regulatory', 'legal', 'audit', 'gdpr', 'hipaa']):
                inferred['category'] = 'Legal and Compliance'
            elif any(term in query_lower for term in ['reputation', 'brand', 'image', 'public']):
                inferred['category'] = 'Reputational'
            elif any(term in query_lower for term in ['strategic', 'strategy', 'business', 'competitive']):
                inferred['category'] = 'Strategic'
            elif any(term in query_lower for term in ['safety', 'health', 'workplace', 'injury']):
                inferred['category'] = 'Safety'
            elif any(term in query_lower for term in ['project', 'schedule', 'timeline', 'delivery']):
                inferred['category'] = 'Project Management'
            
            # Department filtering - only if explicitly mentioned
            if 'finance department' in query_lower or 'financial department' in query_lower:
                inferred['department'] = 'Finance'
            elif 'hr department' in query_lower or 'human resources department' in query_lower:
                inferred['department'] = 'Human Resources'
            elif 'it department' in query_lower or 'information technology department' in query_lower:
                inferred['department'] = 'IT'
            
            # Impact/likelihood filtering
            if any(term in query_lower for term in ['high impact', 'critical', 'severe']):
                inferred['impact_gte'] = 4
            elif any(term in query_lower for term in ['medium impact', 'moderate']):
                inferred['impact_gte'] = 3
            
            if any(term in query_lower for term in ['high likelihood', 'probable', 'likely']):
                inferred['likelihood_gte'] = 4
            elif any(term in query_lower for term in ['medium likelihood']):
                inferred['likelihood_gte'] = 3
                
            # Unmitigated risks
            if any(term in query_lower for term in ['unmitigated', 'uncontrolled', 'no controls']):
                inferred['unmitigated'] = True
                
            return inferred

        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)
        client = MilvusClient(uri=os.getenv("ZILLIZ_URI"), token=os.getenv("ZILLIZ_TOKEN"), secure=True)
        print(f"🔍 hybrid_risk_search: query='{query}', user_id='{user_id}', filters={filters}, top_k={top_k}")
        
        # If no explicit filters provided, try to infer from query
        if not filters:
            filters = _infer_filters_from_query(query)
            print(f"🔍 hybrid_risk_search: inferred filters from query: {filters}")
        
        candidate_ids: List[str] = []
        if filters:
            try:
                candidate_ids = graph_filter_risk_ids(filters)
                print(f"🔍 hybrid_risk_search: graph filter returned {len(candidate_ids)} candidates")
            except Exception as e:
                print(f"🔍 hybrid_risk_search: Error occurred while filtering graph risks: {e}")
                candidate_ids = []

        expr = f"user_id == '{user_id}'"
        print(f"🔍 hybrid_risk_search: candidate_ids from graph: {candidate_ids}")
        if candidate_ids:
            # Milvus string set filter
            quoted = ",".join([f"'{x}'" for x in candidate_ids])
            expr += f" && risk_id in [{quoted}]"
            print(f"🔍 hybrid_risk_search: applying graph constraint to {len(candidate_ids)} candidates")
        else:
            print(f"🔍 hybrid_risk_search: no graph candidates, using pure semantic search")

        OUTPUT_FIELDS = [
            "risk_id", "user_id", "organization_name", "location", "domain",
            "category", "description", "likelihood", "impact", "treatment_strategy",
            "department", "risk_owner", "asset_value", "security_impact",
            "target_date", "risk_progress", "residual_exposure", "risk_text",
        ]
        print(f"🔍 hybrid_risk_search: final Milvus filter expression: {expr}")
        res = client.search(
            collection_name="finalized_risks_index",
            data=[qv],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=expr,
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
        print(f"🔍 hybrid_risk_search found {len(hits)} hits")
        print(f"🔍 Returning hits: {hits}")
        return {"hits": hits, "count": len(hits), "query": query, "user_id": user_id, "candidate_ids": candidate_ids}
    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id, "filters": filters}


@tool("advanced_graph_reasoning")
def advanced_graph_reasoning(
    query: str,
    user_id: str,
    reasoning_type: str = "multi_hop",
    max_hops: int = 3,
    top_k: int = 5
) -> dict:
    """
    Industry-standard advanced graph reasoning for complex queries.
    Supports multi-hop traversal, relationship context, and path-based scoring.
    
    Args:
        query: Natural language query
        user_id: User identifier for scoping
        reasoning_type: 'multi_hop', 'contextual', or 'relationship_aware'
        max_hops: Maximum relationship hops (1-3)
        top_k: Number of results to return
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        from pymilvus import MilvusClient
        
        print(f"🧠 advanced_graph_reasoning: query='{query}', type='{reasoning_type}', hops={max_hops}")
        
        # Extract entities and concepts from query
        def _extract_query_entities(query_text: str) -> Dict[str, Any]:
            """Extract entities and concepts from natural language query"""
            entities = {}
            query_lower = query_text.lower()
            
            # Category extraction
            if any(term in query_lower for term in ['cyber', 'security', 'breach']):
                entities['category'] = 'Technology'
            elif any(term in query_lower for term in ['financial', 'budget']):
                entities['category'] = 'Financial'
            elif any(term in query_lower for term in ['operational', 'process']):
                entities['category'] = 'Operational'
            elif any(term in query_lower for term in ['compliance', 'regulatory']):
                entities['category'] = 'Legal and Compliance'
            
            # Impact/likelihood extraction
            if any(term in query_lower for term in ['high impact', 'critical']):
                entities['impact_level'] = 4
            elif any(term in query_lower for term in ['medium impact']):
                entities['impact_level'] = 3
                
            if any(term in query_lower for term in ['likely', 'probable']):
                entities['likelihood_level'] = 4
                
            return entities
        
        query_entities = _extract_query_entities(query)
        print(f"🧠 Extracted entities: {query_entities}")
        
        if reasoning_type == "multi_hop":
            # Multi-hop reasoning across relationships
            reasoning_results = graph_reasoning_search(
                query_entities=query_entities,
                max_hops=max_hops
            )
            
            # Get risk IDs from reasoning paths
            risk_ids = []
            for path in reasoning_results['paths']:
                for node in path['nodes']:
                    if node['type'] == 'Risk' and node['id']:
                        risk_ids.append(node['id'])
            
            # Remove duplicates and limit
            risk_ids = list(set(risk_ids))[:top_k]
            
        elif reasoning_type == "contextual":
            # Contextual search with relationship information
            contextual_results = graph_contextual_risk_search(query_entities)
            risk_ids = [r['risk_id'] for r in contextual_results['contextual_risks'][:top_k]]
            
        else:  # relationship_aware
            # Simple filter but with relationship context
            risk_ids = graph_filter_risk_ids(query_entities)[:top_k]
            
        print(f"🧠 Graph reasoning found {len(risk_ids)} candidate risk IDs")
        
        if not risk_ids:
            return {
                "hits": [],
                "count": 0,
                "reasoning_type": reasoning_type,
                "query": query,
                "user_id": user_id,
                "message": "No risks found through graph reasoning"
            }
        
        # Now get detailed risk information with semantic search constraint
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)
        client = MilvusClient(uri=os.getenv("ZILLIZ_URI"), token=os.getenv("ZILLIZ_TOKEN"), secure=True)
        
        # Constrain semantic search to graph-reasoned candidates
        quoted_ids = ",".join([f"'{rid}'" for rid in risk_ids])
        expr = f"user_id == '{user_id}' && risk_id in [{quoted_ids}]"
        
        OUTPUT_FIELDS = [
            "risk_id", "user_id", "organization_name", "location", "domain",
            "category", "description", "likelihood", "impact", "treatment_strategy",
            "department", "risk_owner", "asset_value", "security_impact",
            "target_date", "risk_progress", "residual_exposure", "risk_text",
        ]
        
        res = client.search(
            collection_name="finalized_risks_index",
            data=[qv],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=expr,
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
                
                # Add relationship context
                risk_id = entity.get("risk_id")
                related_entities = graph_find_related_entities(risk_id, "risk", max_depth=2)
                
                hit_data = {
                    "risk_id": risk_id,
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
                    # Enhanced context from graph reasoning
                    "related_controls_count": len(related_entities['related_controls']),
                    "related_annexes_count": len(related_entities['related_annexes']),
                    "relationship_context": related_entities['relationship_context'][:3],  # Top 3 relationships
                    "reasoning_score": score * (1 + len(related_entities['related_controls']) * 0.1)  # Boost score based on relationships
                }
                hits.append(hit_data)
        
        print(f"🧠 Advanced reasoning returned {len(hits)} contextualized hits")
        
        return {
            "hits": hits,
            "count": len(hits),
            "reasoning_type": reasoning_type,
            "query": query,
            "user_id": user_id,
            "graph_candidates": risk_ids,
            "reasoning_metadata": {
                "extracted_entities": query_entities,
                "max_hops_used": max_hops,
                "total_graph_candidates": len(risk_ids)
            }
        }
        
    except Exception as e:
        print(f"🧠 Error in advanced_graph_reasoning: {e}")
        return {
            "hits": [],
            "count": 0,
            "error": str(e),
            "reasoning_type": reasoning_type,
            "query": query,
            "user_id": user_id
        }

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


@tool("hybrid_control_search")
def hybrid_control_search(
    query: str,
    user_id: str,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> dict:
    """
    Graph-first + semantic for controls. Uses Neo4j to get candidate control_ids,
    then constrains Milvus search within those. Falls back to unconstrained if empty.
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)
        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True,
        )

        candidate_ids: List[str] = []
        if filters:
            try:
                candidate_ids = graph_filter_controls_ids(filters)
            except Exception:
                candidate_ids = []

        # Build scalar filter for Milvus
        expr = f"user_id == '{user_id}'"
        if candidate_ids:
            quoted = ",".join([f"'{x}'" for x in candidate_ids])
            expr += f" && control_id in [{quoted}]"
        elif filters:
            # If no graph candidates, degrade to Milvus scalar filters like existing function
            for field, value in filters.items():
                if field == "annexa_mappings":
                    expr += f" && annexa_mappings like '%{value}%'"
                elif field == "linked_risk_ids":
                    expr += f" && linked_risk_ids like '%{value}%'"
                else:
                    expr += f" && {field} == '{value}'"

        OUTPUT_FIELDS = [
            "control_id", "control_title", "control_description", "objective", "owner_role", "status", "annexa_mappings", "linked_risk_ids", "control_text", "user_id",
        ]

        res = client.search(
            collection_name="finalized_controls",
            data=[qv],
            anns_field="embedding",
            limit=min(top_k, 8),
            output_fields=OUTPUT_FIELDS,
            filter=expr,
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
                    "score": score,
                })

        return {"hits": hits, "count": len(hits), "query": query, "user_id": user_id, "candidate_ids": candidate_ids}
    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id, "filters": filters}


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


@tool("contextual_control_reasoning")
def contextual_control_reasoning(
    query: str,
    user_id: str,
    include_risk_context: bool = True,
    include_annex_context: bool = True,
    top_k: int = 5
) -> dict:
    """
    Find controls with full relationship context including mapped risks and annexes.
    Industry-standard approach for understanding control effectiveness and coverage.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        from pymilvus import MilvusClient
        
        print(f"🎛️ contextual_control_reasoning: query='{query}', include_risks={include_risk_context}")
        
        # Extract control-relevant filters
        def _extract_control_filters(query_text: str) -> Dict[str, Any]:
            filters = {}
            query_lower = query_text.lower()
            
            # Status filtering
            if 'active' in query_lower:
                filters['status'] = 'Active'
            elif 'inactive' in query_lower:
                filters['status'] = 'Inactive'
                
            # Owner role filtering
            if 'cio' in query_lower:
                filters['owner_role'] = 'CIO'
            elif 'cso' in query_lower:
                filters['owner_role'] = 'CSO'
                
            # Annex prefix filtering
            if 'a.5' in query_lower or 'a5' in query_lower:
                filters['annex_prefix'] = 'A.5'
            elif 'a.8' in query_lower or 'a8' in query_lower:
                filters['annex_prefix'] = 'A.8'
                
            return filters
        
        filters = _extract_control_filters(query)
        print(f"🎛️ Extracted control filters: {filters}")
        
        # Get control candidates through graph filtering
        control_ids = graph_filter_controls_ids(filters)
        print(f"🎛️ Graph filtering found {len(control_ids)} control candidates")
        
        if not control_ids:
            return {
                "hits": [],
                "count": 0,
                "query": query,
                "user_id": user_id,
                "message": "No controls found matching the criteria"
            }
        
        # Get semantic similarity within graph candidates
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        qv: List[float] = emb.embed_query(query)
        client = MilvusClient(uri=os.getenv("ZILLIZ_URI"), token=os.getenv("ZILLIZ_TOKEN"), secure=True)
        
        quoted_ids = ",".join([f"'{cid}'" for cid in control_ids])
        expr = f"user_id == '{user_id}' && control_id in [{quoted_ids}]"
        
        OUTPUT_FIELDS = [
            "control_id", "control_title", "control_description", "objective", 
            "owner_role", "status", "annexa_mappings", "linked_risk_ids", "control_text", "user_id"
        ]
        
        res = client.search(
            collection_name="finalized_controls",
            data=[qv],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=expr,
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
                
                control_id = entity.get("control_id")
                
                # Get relationship context
                control_context = graph_find_related_entities(control_id, "control", max_depth=2)
                
                hit_data = {
                    "control_id": control_id,
                    "title": entity.get("control_title"),
                    "description": entity.get("control_description"),
                    "objective": entity.get("objective"),
                    "owner_role": entity.get("owner_role"),
                    "status": entity.get("status"),
                    "annexa_mappings": entity.get("annexa_mappings"),
                    "linked_risk_ids": entity.get("linked_risk_ids"),
                    "summary": entity.get("control_text"),
                    "score": score
                }
                
                # Add contextual information
                if include_risk_context:
                    hit_data["mitigated_risks"] = control_context['related_risks']
                    hit_data["risk_coverage_score"] = len(control_context['related_risks'])
                    
                if include_annex_context:
                    hit_data["mapped_annexes"] = control_context['related_annexes']
                    hit_data["compliance_coverage"] = len(control_context['related_annexes'])
                
                # Enhanced scoring based on relationships
                relationship_boost = (
                    len(control_context['related_risks']) * 0.1 + 
                    len(control_context['related_annexes']) * 0.05
                )
                hit_data["contextual_score"] = score * (1 + relationship_boost)
                hit_data["relationship_summary"] = control_context['relationship_context'][:3]
                
                hits.append(hit_data)
        
        # Sort by contextual score
        hits.sort(key=lambda x: x.get("contextual_score", 0), reverse=True)
        
        print(f"🎛️ Contextual control reasoning returned {len(hits)} hits")
        
        return {
            "hits": hits,
            "count": len(hits),
            "query": query,
            "user_id": user_id,
            "graph_candidates": control_ids,
            "reasoning_metadata": {
                "filters_used": filters,
                "include_risk_context": include_risk_context,
                "include_annex_context": include_annex_context,
                "total_graph_candidates": len(control_ids)
            }
        }
        
    except Exception as e:
        print(f"🎛️ Error in contextual_control_reasoning: {e}")
        return {
            "hits": [],
            "count": 0,
            "error": str(e),
            "query": query,
            "user_id": user_id
        }
