import os
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
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
