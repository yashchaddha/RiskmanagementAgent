import os
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
from pymongo.collection import Collection

# Local Mongo collections are imported lazily to avoid circular imports

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def ensure_constraints() -> None:
    """Create minimal labels, uniqueness constraints and indexes if missing."""
    drv = get_driver()
    cyphers = [
        # Uniqueness
        "CREATE CONSTRAINT risk_id_unique IF NOT EXISTS FOR (r:Risk) REQUIRE r.risk_id IS UNIQUE",
        "CREATE CONSTRAINT control_id_unique IF NOT EXISTS FOR (c:Control) REQUIRE c.control_id IS UNIQUE",
        "CREATE CONSTRAINT annex_code_unique IF NOT EXISTS FOR (a:Annex) REQUIRE a.code IS UNIQUE",
        # Org uniqueness on name (keep simple for now)
        "CREATE CONSTRAINT org_name_unique IF NOT EXISTS FOR (o:Org) REQUIRE o.name IS UNIQUE",
        # Common lookup indexes (optional; IF NOT EXISTS not supported for indexes < Neo4j 5.10)
        "CREATE INDEX control_owner_idx IF NOT EXISTS FOR (c:Control) ON (c.owner_role)",
        "CREATE INDEX control_status_idx IF NOT EXISTS FOR (c:Control) ON (c.status)",
        "CREATE INDEX risk_department_idx IF NOT EXISTS FOR (r:Risk) ON (r.department)",
        "CREATE INDEX risk_asset_value_idx IF NOT EXISTS FOR (r:Risk) ON (r.asset_value_level)",
    ]
    with drv.session() as s:
        for c in cyphers:
            try:
                s.run(c)
            except Exception:
                # Some editions may not support IF NOT EXISTS for indexes; ignore failures
                pass

def _parse_annex_codes(annexA_map: Optional[List[Dict[str, Any]]]) -> List[Tuple[str, Optional[str]]]:
    """Return [(code, title)] list from control.annexA_map-like structures."""
    if not annexA_map:
        return []
    acc: List[Tuple[str, Optional[str]]] = []
    for item in annexA_map:
        code = str(item.get("id") or item.get("code") or "").strip()
        if not code:
            continue
        title = item.get("title")
        acc.append((code, title))
    return acc


def upsert_org(name: Optional[str], location: Optional[str], domain: Optional[str]) -> None:
    print("Upserting Org:", name)
    if not name:
        return
    drv = get_driver()
    with drv.session() as s:
        s.run(
            """
            MERGE (o:Org {name: $name})
            ON CREATE SET o.location = $location, o.domain = $domain
            ON MATCH SET  o.location = coalesce($location, o.location),
                          o.domain = coalesce($domain, o.domain)
            """,
            name=name,
            location=location,
            domain=domain,
        )
    print("Upserted Org:", name)


def upsert_risk(risk: Dict[str, Any], org: Dict[str, Optional[str]]) -> None:
    risk_id = str(risk.get("_id") or risk.get("risk_id") or "").strip()
    if not risk_id:
        return
    likelihood = risk.get("likelihood")
    impact = risk.get("impact")
    asset_value = risk.get("asset_value")
    try:
        asset_value_level = int(str(asset_value).strip()) if str(asset_value).strip().isdigit() else None
    except Exception:
        asset_value_level = None
    drv = get_driver()
    with drv.session() as s:
        s.run(
            """
            MERGE (r:Risk {risk_id: $risk_id})
            SET r.description = $description,
                r.category = $category,
                r.likelihood = $likelihood,
                r.impact = $impact,
                r.asset_value = $asset_value,
                r.department = $department,
                r.risk_owner = $risk_owner,
                r.treatment_strategy = $treatment_strategy,
                r.security_impact = $security_impact,
                r.target_date = $target_date,
                r.risk_progress = $risk_progress,
                r.residual_exposure = $residual_exposure,
                r.location = $location,
                r.domain = $domain,
                r.organization_name = $organization_name,
                r.likelihood_level = $likelihood_level,
                r.impact_level = $impact_level,
                r.asset_value_level = $asset_value_level,
                r.created_at = $created_at,
                r.updated_at = $updated_at
            """,
            risk_id=risk_id,
            description=risk.get("description"),
            category=risk.get("category"),
            likelihood=likelihood,
            impact=impact,
            asset_value=asset_value,
            department=risk.get("department"),
            risk_owner=risk.get("risk_owner"),
            treatment_strategy=risk.get("treatment_strategy"),
            security_impact=risk.get("security_impact"),
            target_date=risk.get("target_date"),
            risk_progress=risk.get("risk_progress"),
            residual_exposure=risk.get("residual_exposure"),
            location=org.get("location"),
            domain=org.get("domain"),
            organization_name=org.get("organization_name"),
            likelihood_level=risk.get("likelihood"), 
            impact_level=risk.get("impact"),
            asset_value_level=asset_value_level,
            created_at=risk.get("created_at"),
            updated_at=risk.get("updated_at"),
        )
        # BELONGS_TO Org
        if org.get("organization_name"):
            s.run(
                """
                MATCH (r:Risk {risk_id: $risk_id})
                MERGE (o:Org {name: $org_name})
                ON CREATE SET o.location = $location, o.domain = $domain
                MERGE (r)-[:BELONGS_TO]->(o)
                """,
                risk_id=risk_id,
                org_name=org.get("organization_name"),
                location=org.get("location"),
                domain=org.get("domain"),
            )


def upsert_control(ctrl: Dict[str, Any], org: Dict[str, Optional[str]]) -> None:
    control_id = str(ctrl.get("control_id") or "").strip()
    if not control_id:
        return
    drv = get_driver()
    annex_codes = _parse_annex_codes(ctrl.get("annexA_map"))
    with drv.session() as s:
        s.run(
            """
            MERGE (c:Control {control_id: $control_id})
            SET c.control_title = $control_title,
                c.control_description = $control_description,
                c.objective = $objective,
                c.owner_role = $owner_role,
                c.status = $status
            """,
            control_id=control_id,
            control_title=ctrl.get("control_title"),
            control_description=ctrl.get("control_description"),
            objective=ctrl.get("objective"),
            owner_role=ctrl.get("owner_role"),
            status=ctrl.get("status"),
        )
        # BELONGS_TO Org
        if org.get("organization_name"):
            s.run(
                """
                MATCH (c:Control {control_id: $control_id})
                MERGE (o:Org {name: $org_name})
                ON CREATE SET o.location = $location, o.domain = $domain
                MERGE (c)-[:BELONGS_TO]->(o)
                """,
                control_id=control_id,
                org_name=org.get("organization_name"),
                location=org.get("location"),
                domain=org.get("domain"),
            )
        # MAPS_TO Annex
        for code, title in annex_codes:
            s.run(
                """
                MERGE (a:Annex {code: $code})
                ON CREATE SET a.title = $title
                ON MATCH SET  a.title = coalesce($title, a.title)
                WITH a
                MATCH (c:Control {control_id: $control_id})
                MERGE (c)-[:MAPS_TO]->(a)
                """,
                code=code,
                title=title,
                control_id=control_id,
            )
        # MITIGATES -> Risk (by linked_risk_ids)
        for rid in (ctrl.get("linked_risk_ids") or []):
            if not rid:
                continue
            s.run(
                """
                MATCH (c:Control {control_id: $control_id})
                MERGE (r:Risk {risk_id: $risk_id})
                MERGE (c)-[:MITIGATES]->(r)
                """,
                control_id=control_id,
                risk_id=str(rid),
            )


def graph_filter_controls_ids(filters: Dict[str, Any]) -> List[str]:
    """Deterministic control candidate IDs via Neo4j."""
    drv = get_driver()
    owner_role = filters.get("owner_role")
    status = filters.get("status")
    dept = filters.get("department")
    location = filters.get("location")
    domain = filters.get("domain")
    annex_prefix = filters.get("annex_prefix")
    impact_gte = filters.get("impact_gte")
    likelihood_gte = filters.get("likelihood_gte")
    risk_ids = filters.get("risk_ids") or []

    where_clauses = []
    params: Dict[str, Any] = {}

    if owner_role:
        where_clauses.append("c.owner_role = $owner_role")
        params["owner_role"] = owner_role
    if status:
        where_clauses.append("c.status = $status")
        params["status"] = status
    if dept:
        where_clauses.append("r.department = $department")
        params["department"] = dept
    if location:
        where_clauses.append("r.location = $location")
        params["location"] = location
    if domain:
        where_clauses.append("r.domain = $domain")
        params["domain"] = domain
    if annex_prefix:
        where_clauses.append("a.code STARTS WITH $annex_prefix")
        params["annex_prefix"] = annex_prefix
    if impact_gte is not None:
        where_clauses.append("r.impact_level >= $impact_gte")
        params["impact_gte"] = int(impact_gte)
    if likelihood_gte is not None:
        where_clauses.append("r.likelihood_level >= $likelihood_gte")
        params["likelihood_gte"] = int(likelihood_gte)
    if risk_ids:
        where_clauses.append("r.risk_id IN $risk_ids")
        params["risk_ids"] = [str(x) for x in risk_ids]

    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cypher = f"""
    MATCH (c:Control)
    OPTIONAL MATCH (c)-[:MITIGATES]->(r:Risk)
    OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
    {where_str}
    RETURN DISTINCT c.control_id AS id
    LIMIT 1000
    """
    with drv.session() as s:
        res = s.run(cypher, **params)
        return [rec["id"] for rec in res]


def graph_filter_risk_ids(filters: Dict[str, Any]) -> List[str]:
    """Deterministic risk candidate IDs via Neo4j."""
    drv = get_driver()
    dept = filters.get("department")
    location = filters.get("location")
    domain = filters.get("domain")
    category = filters.get("category")
    impact_gte = filters.get("impact_gte")
    likelihood_gte = filters.get("likelihood_gte")
    unmitigated = filters.get("unmitigated", False)
    asset_value_gte = filters.get("asset_value_gte")
    asset_value_lte = filters.get("asset_value_lte")

    where_clauses = []
    params: Dict[str, Any] = {}
    if dept:
        where_clauses.append("r.department = $department")
        params["department"] = dept
    if location:
        where_clauses.append("r.location = $location")
        params["location"] = location
    if domain:
        where_clauses.append("r.domain = $domain")
        params["domain"] = domain
    if category:
        where_clauses.append("r.category = $category")
        params["category"] = category
    if impact_gte is not None:
        where_clauses.append("r.impact_level >= $impact_gte")
        params["impact_gte"] = int(impact_gte)
    if likelihood_gte is not None:
        where_clauses.append("r.likelihood_level >= $likelihood_gte")
        params["likelihood_gte"] = int(likelihood_gte)
    if asset_value_gte is not None:
        where_clauses.append("r.asset_value_level >= $asset_value_gte")
        params["asset_value_gte"] = int(asset_value_gte)
    if asset_value_lte is not None:
        where_clauses.append("r.asset_value_level <= $asset_value_lte")
        params["asset_value_lte"] = int(asset_value_lte)

    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    if unmitigated:
        cypher = f"""
        MATCH (r:Risk)
        {where_str}
        WHERE NOT EXISTS( ( :Control )-[:MITIGATES]->(r) )
        RETURN DISTINCT r.risk_id AS id
        LIMIT 1000
        """
    else:
        cypher = f"""
        MATCH (r:Risk)
        {where_str}
        RETURN DISTINCT r.risk_id AS id
        LIMIT 1000
        """
    with drv.session() as s:
        res = s.run(cypher, **params)
        return [rec["id"] for rec in res]

def graph_reasoning_search(
    query_entities: Dict[str, Any], 
    max_hops: int = 3,
    entity_types: List[str] = None
) -> Dict[str, Any]:
    """
    Advanced multi-hop reasoning for finding related entities through relationships.
    Industry standard approach used by Microsoft GraphRAG and Meta's RoP.
    """
    drv = get_driver()
    entity_types = entity_types or ['Risk', 'Control', 'Annex', 'Org']
    
    results = {
        'paths': [],
        'entities': {},
        'relationships': [],
        'reasoning_score': 0.0
    }
    
    with drv.session() as s:
        # Multi-hop traversal with relationship context
        cypher = f"""
        MATCH path = (start)-[*1..{max_hops}]-(end)
        WHERE (start:Risk OR start:Control OR start:Annex)
          AND (end:Risk OR end:Control OR end:Annex)
          AND start <> end
        WITH path, nodes(path) as path_nodes, relationships(path) as path_rels
        WHERE ANY(node IN path_nodes WHERE 
          ANY(key IN keys($query_entities) WHERE 
            node[key] IS NOT NULL AND node[key] = $query_entities[key]
          )
        )
        RETURN path, 
               [node IN path_nodes | {{id: coalesce(node.risk_id, node.control_id, node.code), 
                                      type: labels(node)[0], 
                                      properties: properties(node)}}] as nodes,
               [rel IN path_rels | {{type: type(rel), properties: properties(rel)}}] as relationships,
               length(path) as path_length
        ORDER BY path_length ASC
        LIMIT 100
        """
        
        try:
            res = s.run(cypher, query_entities=query_entities)
            for record in res:
                path_data = {
                    'nodes': record['nodes'],
                    'relationships': record['relationships'],
                    'length': record['path_length'],
                    'score': 1.0 / (record['path_length'] + 1)  # Shorter paths score higher
                }
                results['paths'].append(path_data)
                
                # Aggregate unique entities
                for node in record['nodes']:
                    entity_id = node['id']
                    if entity_id not in results['entities']:
                        results['entities'][entity_id] = node
                        
        except Exception as e:
            print(f"Error in graph reasoning search: {e}")
            
    # Calculate overall reasoning score
    if results['paths']:
        results['reasoning_score'] = sum(path['score'] for path in results['paths']) / len(results['paths'])
    
    return results


def graph_find_related_entities(
    entity_id: str, 
    entity_type: str,
    relationship_types: List[str] = None,
    max_depth: int = 2
) -> Dict[str, Any]:
    """
    Find entities related to a given entity through specific relationship types.
    Implements relationship-aware traversal patterns.
    """
    drv = get_driver()
    relationship_types = relationship_types or ['MITIGATES', 'MAPS_TO', 'BELONGS_TO']
    
    results = {
        'related_risks': [],
        'related_controls': [],
        'related_annexes': [],
        'related_orgs': [],
        'relationship_context': []
    }
    
    with drv.session() as s:
        # Dynamic relationship traversal based on entity type
        if entity_type.lower() == 'risk':
            entity_match = f"(start:Risk {{risk_id: $entity_id}})"
        elif entity_type.lower() == 'control':
            entity_match = f"(start:Control {{control_id: $entity_id}})"
        elif entity_type.lower() == 'annex':
            entity_match = f"(start:Annex {{code: $entity_id}})"
        else:
            entity_match = f"(start:Org {{name: $entity_id}})"
            
        # Multi-directional traversal
        cypher = f"""
        MATCH {entity_match}
        OPTIONAL MATCH (start)-[r1:MITIGATES|MAPS_TO|BELONGS_TO*1..{max_depth}]-(related)
        WHERE related <> start
        WITH start, related, r1
        RETURN DISTINCT 
               related,
               labels(related) as entity_labels,
               type(r1[0]) as relationship_type,
               size(r1) as relationship_distance,
               properties(related) as entity_properties
        ORDER BY relationship_distance ASC
        LIMIT 50
        """
        
        try:
            res = s.run(cypher, entity_id=entity_id)
            for record in res:
                if not record['related']:
                    continue
                    
                entity_labels = record['entity_labels']
                entity_props = record['entity_properties']
                rel_type = record['relationship_type']
                distance = record['relationship_distance']
                
                entity_data = {
                    'properties': entity_props,
                    'relationship_type': rel_type,
                    'distance': distance
                }
                
                if 'Risk' in entity_labels:
                    entity_data['id'] = entity_props.get('risk_id')
                    results['related_risks'].append(entity_data)
                elif 'Control' in entity_labels:
                    entity_data['id'] = entity_props.get('control_id')
                    results['related_controls'].append(entity_data)
                elif 'Annex' in entity_labels:
                    entity_data['id'] = entity_props.get('code')
                    results['related_annexes'].append(entity_data)
                elif 'Org' in entity_labels:
                    entity_data['id'] = entity_props.get('name')
                    results['related_orgs'].append(entity_data)
                    
                results['relationship_context'].append({
                    'from_type': entity_type,
                    'to_type': entity_labels[0] if entity_labels else 'Unknown',
                    'relationship': rel_type,
                    'distance': distance
                })
                
        except Exception as e:
            print(f"Error finding related entities: {e}")
    
    return results


def graph_contextual_risk_search(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Industry-standard contextual search that considers relationships and context.
    Returns risks with their full relationship context.
    """
    drv = get_driver()
    
    # Build base conditions
    where_clauses = []
    params = {}
    
    if filters.get('category'):
        where_clauses.append("r.category = $category")
        params['category'] = filters['category']
    if filters.get('department'):
        where_clauses.append("r.department = $department")
        params['department'] = filters['department']
    if filters.get('impact_gte'):
        where_clauses.append("r.impact_level >= $impact_gte")
        params['impact_gte'] = int(filters['impact_gte'])
    if filters.get('likelihood_gte'):
        where_clauses.append("r.likelihood_level >= $likelihood_gte")
        params['likelihood_gte'] = int(filters['likelihood_gte'])
        
    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    
    # Advanced contextual query with relationship information
    cypher = f"""
    MATCH (r:Risk)
    OPTIONAL MATCH (r)-[:BELONGS_TO]->(org:Org)
    OPTIONAL MATCH (r)<-[:MITIGATES]-(c:Control)
    OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
    {where_str}
    WITH r, org, 
         collect(DISTINCT {{
           control_id: c.control_id,
           control_title: c.control_title,
           status: c.status,
           owner_role: c.owner_role
         }}) as controls,
         collect(DISTINCT {{
           code: a.code,
           title: a.title,
           is_domain: a.is_domain
         }}) as annexes
    RETURN r.risk_id as risk_id,
           properties(r) as risk_properties,
           properties(org) as org_properties,
           controls,
           annexes,
           size(controls) as control_count,
           size(annexes) as annex_count
    ORDER BY control_count DESC, annex_count DESC
    LIMIT 100
    """
    
    results = {
        'contextual_risks': [],
        'total_found': 0,
        'relationship_stats': {
            'total_controls': 0,
            'total_annexes': 0,
            'avg_controls_per_risk': 0,
            'avg_annexes_per_risk': 0
        }
    }
    
    with drv.session() as s:
        try:
            res = s.run(cypher, **params)
            risk_data = []
            total_controls = 0
            total_annexes = 0
            
            for record in res:
                risk_info = {
                    'risk_id': record['risk_id'],
                    'risk_properties': record['risk_properties'],
                    'org_properties': record['org_properties'],
                    'related_controls': [c for c in record['controls'] if c['control_id']],
                    'related_annexes': [a for a in record['annexes'] if a['code']],
                    'control_count': record['control_count'],
                    'annex_count': record['annex_count'],
                    'context_score': record['control_count'] + record['annex_count']  # Simple scoring
                }
                risk_data.append(risk_info)
                total_controls += record['control_count']
                total_annexes += record['annex_count']
                
            results['contextual_risks'] = risk_data
            results['total_found'] = len(risk_data)
            
            if risk_data:
                results['relationship_stats'] = {
                    'total_controls': total_controls,
                    'total_annexes': total_annexes,
                    'avg_controls_per_risk': total_controls / len(risk_data),
                    'avg_annexes_per_risk': total_annexes / len(risk_data)
                }
                
        except Exception as e:
            print(f"Error in contextual risk search: {e}")
    
    return results
