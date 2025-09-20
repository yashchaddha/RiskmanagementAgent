from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.tools import tool
from neo4j import Record
from graph_kg import get_driver

@tool("graph_related")
def graph_related(anchor_id: str, anchor_type: str, relation_types: Optional[List[str]] = None, hops: int = 2, org: Optional[str] = None, top_k: int = 20) -> Dict[str, Any]:
    """
    Expand around an anchor (risk/control/annex/org) up to N hops using specific relationship types.
    Returns related nodes grouped by type plus relationship context (path types and distance).
    """
    drv = get_driver()
    label_map = {
        "risk": ("Risk", "risk_id"),
        "control": ("Control", "control_id"),
        "annex": ("Annex", "code"),
        "org": ("Org", "name"),
    }
    if anchor_type.lower() not in label_map:
        raise ValueError("anchor_type must be one of: risk, control, annex, org")
    label, key = label_map[anchor_type.lower()]
    relation_types = relation_types or ["MITIGATES", "MAPS_TO", "BELONGS_TO", "CONTAINS"]
    params: Dict[str, Any] = {
        "id": anchor_id,
        "hops": int(max(1, hops)),
        "types": relation_types,
        "top_k": int(max(1, top_k)),
        "org": org,
    }
    org_filter = ""
    if org:
        org_filter = "AND ( (n:Risk)-[:BELONGS_TO]->(:Org {name:$org}) OR (n:Control)-[:BELONGS_TO]->(:Org {name:$org}) OR n:Annex OR n:Org )"
    cypher = f"""
    MATCH (start:{label} {{{key}: $id}})
    MATCH p = (start)-[rels*1..$hops]-(n)
    WHERE ALL(r IN rels WHERE type(r) IN $types)
      {org_filter}
    WITH n, p, relationships(p) AS rtypes, length(p) AS dist
    RETURN labels(n) AS labels, properties(n) AS props, [r IN rtypes | type(r)] AS rel_types, dist
    ORDER BY dist ASC
    LIMIT $top_k
    """
    out = {
        "related_risks": [],
        "related_controls": [],
        "related_annexes": [],
        "related_orgs": [],
        "relationship_context": [],
    }
    with drv.session() as s:
        for rec in s.run(cypher, params):
            labels = rec["labels"]
            props = rec["props"]
            rel_types = rec["rel_types"]
            dist = rec["dist"]
            if "Risk" in labels:
                out["related_risks"].append({"id": props.get("risk_id"), **props})
            elif "Control" in labels:
                out["related_controls"].append({"id": props.get("control_id"), **props})
            elif "Annex" in labels:
                out["related_annexes"].append({"id": props.get("code"), **props})
            elif "Org" in labels:
                out["related_orgs"].append({"id": props.get("name"), **props})
            out["relationship_context"].append({
                "to_type": labels[0] if labels else "Unknown",
                "distance": dist,
                "path_types": rel_types
            })
    return out

@tool("graph_hydrate")
def graph_hydrate(kind: str, ids: List[str], org: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic detail fetcher. Hydrates risks/controls/annexes by IDs plus linked context (counts and minimal linked lists).
    - For risks/controls, if org is provided, BELONGS_TO must match; otherwise return across orgs.
    """
    drv = get_driver()
    if not ids:
        return {"items": []}
    kind_l = kind.lower()
    params: Dict[str, Any] = {"ids": ids, "org": org}
    items: List[Dict[str, Any]] = []
    if kind_l == "risk":
        org_match = "MATCH (r:Risk) " if not org else "MATCH (r:Risk)-[:BELONGS_TO]->(:Org {name:$org}) "
        cypher = f"""
        {org_match}
        WHERE r.risk_id IN $ids
        OPTIONAL MATCH (r)<-[:MITIGATES]-(c:Control)
        OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
        WITH r, collect(DISTINCT c) AS cs, collect(DISTINCT a) AS as
        RETURN r {{ .risk_id, .description, .category, .department, .impact, .likelihood }} AS risk,
               [x IN cs | x {{ .control_id, .control_title, .status }}] AS controls,
               [x IN as | x {{ .code, .title }}] AS annexes
        """
        with drv.session() as s:
            for rec in s.run(cypher, params):
                r = rec["risk"]
                controls = rec["controls"]
                annexes = rec["annexes"]
                items.append({
                    "id": r["risk_id"],
                    "kind": "risk",
                    **r,
                    "controls": controls,
                    "annexes": annexes,
                    "controls_count": len(controls),
                    "annex_count": len(annexes),
                })
    elif kind_l == "control":
        org_match = "MATCH (c:Control) " if not org else "MATCH (c:Control)-[:BELONGS_TO]->(:Org {name:$org}) "
        cypher = f"""
        {org_match}
        WHERE c.control_id IN $ids
        OPTIONAL MATCH (c)-[:MITIGATES]->(r:Risk)
        OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
        WITH c, collect(DISTINCT r) AS rs, collect(DISTINCT a) AS as
        RETURN c {{ .control_id, .control_title, .status, .owner_role }} AS control,
               [x IN rs | x {{ .risk_id, .description, .category, .department }}] AS risks,
               [x IN as | x {{ .code, .title }}] AS annexes
        """
        with drv.session() as s:
            for rec in s.run(cypher, params):
                c = rec["control"]
                risks = rec["risks"]
                annexes = rec["annexes"]
                items.append({
                    "id": c["control_id"],
                    "kind": "control",
                    **c,
                    "risks": risks,
                    "annexes": annexes,
                    "risks_count": len(risks),
                    "annex_count": len(annexes),
                })
    elif kind_l == "annex":
        cypher = """
        MATCH (a:Annex)
        WHERE a.code IN $ids
        OPTIONAL MATCH (c:Control)-[:MAPS_TO]->(a)
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(o:Org)
        OPTIONAL MATCH (c)-[:MITIGATES]->(r:Risk)
        WITH a, c, o, r
        WHERE $org IS NULL OR o.name = $org
        WITH a, collect(DISTINCT CASE WHEN $org IS NOT NULL AND o.name <> $org THEN NULL ELSE c END) AS cs,
             collect(DISTINCT CASE WHEN $org IS NOT NULL AND o.name <> $org THEN NULL ELSE r END) AS rs
        RETURN a { .code, .title } AS annex,
               [x IN cs WHERE x IS NOT NULL | x { .control_id, .control_title, .status }] AS controls,
               [x IN rs WHERE x IS NOT NULL | x { .risk_id, .description, .category, .department }] AS risks
        """
        with drv.session() as s:
            for rec in s.run(cypher, params):
                a = rec["annex"]
                controls = rec["controls"]
                risks = rec["risks"]
                items.append({
                    "id": a["code"],
                    "kind": "annex",
                    **a,
                    "controls": controls,
                    "risks": risks,
                    "controls_count": len(controls),
                    "risks_count": len(risks),
                })
    else:
        raise ValueError("kind must be one of: risk, control, annex")
    return {"items": items}

@tool("natural_language_query")
def nl_graph_query(question: str, org: Optional[str] = None) -> Dict[str, Any]:
    """
    Convert natural language questions to Cypher queries for the knowledge graph.

    Examples:
    - "find risks assigned to pranav"
    - "show controls that mitigate HR risks"
    - "what annexes are mapped to by controls"
    - "find all controls for organization ABC"
    """
    from langchain_openai import ChatOpenAI

    drv = get_driver()

    # Get current schema information
    schema_info = """
    Graph Schema:

    Node Types:
    - Risk: risk_id, risk_owner, department, category, description, impact, likelihood, asset_value, etc.
    - Control: control_id, control_title, control_description, status, owner_role, objective
    - Annex: code, title, category, description, is_domain
    - Org: name, domain, location
    - User: username, user_id

    Relationships:
    - Risk -[:BELONGS_TO]-> Org
    - Control -[:BELONGS_TO]-> Org
    - Control -[:MITIGATES]-> Risk
    - Control -[:MAPS_TO]-> Annex
    - Annex -[:CONTAINS]-> Annex (parent/child hierarchy)
    - User -[:OWNS]-> Org

    Important Notes:
    - risk_owner is stored as a string property (e.g., "Pranav"), not a relationship
    - Use toLower() for case-insensitive string matching
    - Annex codes follow pattern A.X.Y (e.g., A.5.1, A.5.2)
    """

    # Few-shot examples for common query patterns
    examples = """
    Example Queries:

    Q: "find risks assigned to pranav"
    A: MATCH (r:Risk) WHERE toLower(r.risk_owner) = toLower("pranav") RETURN r

    Q: "show controls that mitigate HR risks"
    A: MATCH (c:Control)-[:MITIGATES]->(r:Risk) WHERE toLower(r.department) = "hr" RETURN c, r

    Q: "what controls map to annex A.5.1"
    A: MATCH (c:Control)-[:MAPS_TO]->(a:Annex {code: "A.5.1"}) RETURN c, a

    Q: "find all risks in organization ABC"
    A: MATCH (r:Risk)-[:BELONGS_TO]->(o:Org {name: "ABC"}) RETURN r

    Q: "show annexes that have controls"
    A: MATCH (a:Annex)<-[:MAPS_TO]-(c:Control) RETURN a, count(c) as control_count
    """

    # Build the prompt
    org_context = f"Focus on organization: {org}" if org else "Consider all organizations"

    prompt = f"""
    You are an expert at converting natural language questions to Cypher queries for a Neo4j knowledge graph.

    {schema_info}

    {examples}

    User Question: "{question}"
    {org_context}

    Instructions:
    1. Generate a valid Cypher query that answers the question
    2. Use case-insensitive matching with toLower() for string properties
    3. Return relevant nodes and relationships
    4. If organization is specified, add appropriate BELONGS_TO filters
    5. Limit results to 50 unless otherwise specified

    Return only the Cypher query, no explanation:
    """

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = llm.invoke(prompt)
        cypher_query = response.content.strip()

        # Clean up the query (remove markdown formatting if present)
        if cypher_query.startswith("```"):
            cypher_query = cypher_query.split("```")[1]
            if cypher_query.startswith("cypher"):
                cypher_query = cypher_query[6:].strip()

        # Execute the query
        with drv.session() as s:
            result = s.run(cypher_query)
            records = []
            for record in result:
                # Convert neo4j record to dict
                record_dict = {}
                for key in record.keys():
                    value = record[key]
                    if hasattr(value, '_properties'):  # Neo4j Node
                        record_dict[key] = dict(value._properties)
                        record_dict[key]['_labels'] = list(value.labels)
                    elif hasattr(value, '_start_node'):  # Neo4j Relationship
                        record_dict[key] = {
                            'type': value.type,
                            'properties': dict(value._properties)
                        }
                    else:
                        record_dict[key] = value
                records.append(record_dict)

            return {
                "question": question,
                "cypher_query": cypher_query,
                "results": records,
                "count": len(records)
            }

    except Exception as e:
        return {
            "question": question,
            "error": str(e),
            "cypher_query": cypher_query if 'cypher_query' in locals() else "Failed to generate query"
        }

@tool("execute_cypher")
def execute_cypher(query: str, org: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a Cypher query directly against the Neo4j knowledge graph.

    Parameters:
    - query: The Cypher query to execute
    - org: Optional organization filter to add to queries

    Returns the query results as a list of records.
    """
    drv = get_driver()

    try:
        with drv.session() as s:
            # Add org parameter for potential use in queries
            params = {"org": org} if org else {}
            print("Executing Cypher Query:", query)
            result = s.run(query, params)

            records = []
            for record in result:
                # Convert neo4j record to dict
                record_dict = {}
                for key in record.keys():
                    value = record[key]
                    if hasattr(value, '_properties'):  # Neo4j Node
                        record_dict[key] = dict(value._properties)
                        record_dict[key]['_labels'] = list(value.labels)
                    elif hasattr(value, '_start_node'):  # Neo4j Relationship
                        record_dict[key] = {
                            'type': value.type,
                            'properties': dict(value._properties)
                        }
                    else:
                        record_dict[key] = value
                records.append(record_dict)

            print("Cypher Query Results:", records)

            return {
                "query": query,
                "results": records,
                "count": len(records),
                "success": True
            }

    except Exception as e:
        return {
            "query": query,
            "error": str(e),
            "success": False,
            "results": []
        }

@tool("get_field_values")
def get_field_values(field: str, search_term: Optional[str] = None, node_type: str = "Risk") -> Dict[str, Any]:
    """
    Get actual field values from the graph to help with semantic matching.

    Parameters:
    - field: The field name to get values for (e.g., "impact", "likelihood", "department")
    - search_term: Optional search term to filter values (e.g., "high" to find high-related values)
    - node_type: Node type to search (default: "Risk")

    Examples:
    - get_field_values("impact") -> all impact values
    - get_field_values("impact", "high") -> impact values containing "high"
    - get_field_values("department") -> all department values
    """
    drv = get_driver()

    try:
        print(f"Fetching field values for field: {field}, search_term: {search_term}, node_type: {node_type}")
        with drv.session() as s:
            # Build dynamic query based on node type
            if node_type.lower() == "risk":
                label = "Risk"
                property_field = f"r.{field}"
            elif node_type.lower() == "control":
                label = "Control"
                property_field = f"c.{field}"
            else:
                label = "Risk"  # Default fallback
                property_field = f"r.{field}"

            # Get distinct values for the field
            query = f"""
            MATCH (n:{label})
            WHERE n.{field} IS NOT NULL
            RETURN DISTINCT n.{field} as value
            ORDER BY value
            """

            result = s.run(query)
            all_values = [record["value"] for record in result if record["value"]]

            # Filter by search term if provided
            if search_term:
                search_lower = search_term.lower()
                filtered_values = [v for v in all_values if search_lower in str(v).lower()]
                print(f"Result: Filtered values for field: {field}, search_term: {search_term} -> {filtered_values}")
                return {
                    "field": field,
                    "search_term": search_term,
                    "matching_values": filtered_values,
                    "all_values": all_values,
                    "success": True
                }
            else:
                print(f"Result: All values for field: {field} -> {all_values}")
                return {
                    "field": field,
                    "all_values": all_values,
                    "success": True
                }

    except Exception as e:
        return {
            "field": field,
            "error": str(e),
            "success": False,
            "all_values": []
        }
