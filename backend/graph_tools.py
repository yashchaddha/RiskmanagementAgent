from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.tools import tool
from neo4j import Record

# Reuse the single driver created in your KG module
from graph_kg import get_driver

# -------------------------
# Helpers
# -------------------------

_SEVERITY_IMPACT_MAP = {
    "critical": 4, "severe": 4, "very high": 4,
    "high": 3,
    "medium": 2, "moderate": 2,
    "low": 1, "minor": 1,
}

_SEVERITY_LIKELIHOOD_MAP = {
    "almost certain": 4, "certain": 4, "frequent": 4,
    "likely": 3, "probable": 3,
    "possible": 2, "occasional": 2,
    "rare": 1, "unlikely": 1,
}

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _keywords_from_hints(hints: Union[str, Dict[str, Any], None]) -> List[str]:
    if hints is None:
        return []
    if isinstance(hints, str):
        toks = re.findall(r"[A-Za-z0-9\.]+", hints.lower())
        return [t for t in toks if len(t) >= 3]
    if isinstance(hints, dict):
        kws: List[str] = []
        val = hints.get("keywords")
        if isinstance(val, str):
            kws.extend([t for t in re.findall(r"[A-Za-z0-9\.]+", val.lower()) if len(t) >= 3])
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    kws.append(v.strip().lower())
        q = hints.get("query")
        if isinstance(q, str) and q.strip():
            kws.extend([t for t in re.findall(r"[A-Za-z0-9\.]+", q.lower()) if len(t) >= 3])
        return list(dict.fromkeys(kws))
    return []

def _extract_soft_hints(hints: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    """Pull soft hints (category, department, annex_code/prefix, owner_role, status) without hard filtering."""
    result: Dict[str, Any] = {
        "category": None,
        "department": None,
        "annex_code": None,
        "annex_prefix": None,
        "owner_role": None,
        "status": None,
    }
    if hints is None:
        return result
    if isinstance(hints, dict):
        for k in list(result.keys()):
            v = hints.get(k)
            if isinstance(v, str) and v.strip():
                result[k] = v.strip()
        if result["annex_prefix"] is None and isinstance(hints.get("annex"), str):
            ap = hints["annex"].strip()
            if ap:
                result["annex_prefix"] = ap
        return result
    s = hints
    code_match = re.search(r"\bA\.\d+(?:\.\d+)?\b", s, re.IGNORECASE)
    if code_match:
        result["annex_code"] = code_match.group(0)
    prefix_match = re.search(r"\bA\.\d+\.\b", s, re.IGNORECASE)
    if prefix_match:
        result["annex_prefix"] = prefix_match.group(0)
    return result

def _paginate(page: int, top_k: int) -> Tuple[int, int]:
    page = max(int(page or 1), 1)
    top_k = max(min(int(top_k or 10), 100), 1)
    return (page, top_k)

def _severity_score_fields(alias: str = "r") -> str:
    """Return Cypher for severity scoring using string scales (no filtering)."""
    return f"""
      (CASE toLower({alias}.impact)
            WHEN 'critical' THEN 4 WHEN 'severe' THEN 4 WHEN 'very high' THEN 4
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2 WHEN 'moderate' THEN 2
            WHEN 'low' THEN 1 ELSE 0 END)
    +
      (CASE toLower({alias}.likelihood)
            WHEN 'almost certain' THEN 4 WHEN 'certain' THEN 4 WHEN 'frequent' THEN 4
            WHEN 'likely' THEN 3 WHEN 'probable' THEN 3
            WHEN 'possible' THEN 2 WHEN 'occasional' THEN 2
            WHEN 'rare' THEN 1 WHEN 'unlikely' THEN 1 ELSE 0 END)
    """

def _kw_score_expr(text_expr: str, param_name: str) -> str:
    """Cypher expr: number of $param_name keywords contained in lower(text_expr)."""
    return f"size([k IN ${param_name} WHERE toLower(coalesce({text_expr}, '')) CONTAINS k])"

# -------------------------
# 1) graph_search_risks
# -------------------------
@tool("graph_search_risks")
def graph_search_risks(hints: Union[str, Dict[str, Any], None], org: str, top_k: int = 10, page: int = 1) -> Dict[str, Any]:
    """
    Intent-first risk discovery. Returns risks within an org with relationship-aware ranking.
    - No hard filtering on impact/likelihood (string scales).
    - Hints are used to BOOST (category/department/annex matches, keywords).
    """
    drv = get_driver()
    page, top_k = _paginate(page, top_k)
    skip = (page - 1) * top_k
    print("Graph risk search tool called:")
    kw_list = _keywords_from_hints(hints)
    soft = _extract_soft_hints(hints)
    params: Dict[str, Any] = {
        "org": org,
        "keywords": kw_list,
        "category": soft.get("category"),
        "department": soft.get("department"),
        "annex_code": soft.get("annex_code"),
        "annex_prefix": soft.get("annex_prefix"),
        "skip": skip,
        "limit": top_k,
    }
    print(f"Params: {params}")
    cypher = f"""
    MATCH (r:Risk)-[:BELONGS_TO]->(o:Org {{name:$org}})
    OPTIONAL MATCH (r)<-[:MITIGATES]-(c:Control)
    OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
    WITH r,
         count(DISTINCT c) AS controls_count,
         count(DISTINCT a) AS annex_count,
         {_kw_score_expr('r.description', 'keywords')} +
         {_kw_score_expr('r.category', 'keywords')} +
         {_kw_score_expr('r.department', 'keywords')} AS kw_score,
         size([x IN collect(DISTINCT a) WHERE ($annex_code IS NOT NULL AND toLower(x.code) = toLower($annex_code))
                                        OR ($annex_prefix IS NOT NULL AND toLower(x.code) STARTS WITH toLower($annex_prefix))]) AS annex_hit,
         CASE WHEN $category IS NOT NULL AND toLower(r.category) = toLower($category) THEN 2 ELSE 0 END AS cat_hit,
         CASE WHEN $department IS NOT NULL AND toLower(r.department) = toLower($department) THEN 2 ELSE 0 END AS dept_hit,
         {_severity_score_fields('r')} AS severity_score
    WITH r, controls_count, annex_count, kw_score, annex_hit, cat_hit, dept_hit, severity_score,
         (controls_count*1.0) + (annex_count*0.7) + (kw_score*0.6) + (annex_hit*2.0) + (cat_hit*1.0) + (dept_hit*1.0) + (severity_score*0.3)
         AS score
    ORDER BY score DESC, controls_count DESC, annex_count DESC, r.risk_id ASC
    SKIP $skip LIMIT $limit
    RETURN r {{
        .risk_id, .description, .category, .department, .impact, .likelihood
    }} AS risk,
    controls_count, annex_count, score
    """
    items: List[Dict[str, Any]] = []
    with drv.session() as s:
        res = s.run(cypher, params)
        for rec in res:
            r = rec["risk"]
            items.append({
                "id": r["risk_id"],
                "kind": "risk",
                "description": r.get("description"),
                "category": r.get("category"),
                "department": r.get("department"),
                "impact": r.get("impact"),
                "likelihood": r.get("likelihood"),
                "controls_count": rec["controls_count"],
                "annex_count": rec["annex_count"],
                "score": rec["score"],
            })
    return {
        "items": items,
        "page": page,
        "top_k": top_k,
        "count": len(items),
        "scoring_notes": [
            "score = controls_count + 0.7*annex_count + 0.6*keyword_hits + 2*annex_hit + cat/department boosts + 0.3*severity_score"
        ],
    }

# -------------------------
# 2) graph_search_controls
# -------------------------
@tool("graph_search_controls")
def graph_search_controls(hints: Union[str, Dict[str, Any], None], org: str, top_k: int = 10, page: int = 1) -> Dict[str, Any]:
    """
    Intent-first control discovery. Returns controls for an org with coverage-aware ranking.
    Hints like department are applied softly via mitigated risks, not as hard filters.
    """
    drv = get_driver()
    page, top_k = _paginate(page, top_k)
    skip = (page - 1) * top_k
    
    kw_list = _keywords_from_hints(hints)
    soft = _extract_soft_hints(hints)
    params: Dict[str, Any] = {
        "org": org,
        "keywords": kw_list,
        "department": soft.get("department"),
        "owner_role": soft.get("owner_role"),
        "status": soft.get("status"),
        "skip": skip,
        "limit": top_k,
    }
    cypher = f"""
    MATCH (c:Control)-[:BELONGS_TO]->(:Org {{name:$org}})
    OPTIONAL MATCH (c)-[:MITIGATES]->(r:Risk)
    OPTIONAL MATCH (c)-[:MAPS_TO]->(a:Annex)
    WITH c,
         count(DISTINCT r) AS risks_count,
         count(DISTINCT a) AS annex_count,
         {_kw_score_expr('c.control_title', 'keywords')} +
         {_kw_score_expr('c.control_description', 'keywords')} AS kw_score,
         CASE WHEN $owner_role IS NOT NULL AND toLower(c.owner_role) = toLower($owner_role) THEN 1 ELSE 0 END AS owner_hit,
         CASE WHEN $status IS NOT NULL AND toLower(c.status) = toLower($status) THEN 1 ELSE 0 END AS status_hit,
         size([x IN collect(DISTINCT r) WHERE $department IS NOT NULL AND toLower(x.department) = toLower($department)]) AS dept_cov
    WITH c, risks_count, annex_count, kw_score, owner_hit, status_hit, dept_cov,
         (risks_count*1.0) + (annex_count*0.6) + (kw_score*0.6) + (owner_hit*0.5) + (status_hit*0.4) + (dept_cov*0.7) AS score
    ORDER BY score DESC, risks_count DESC, annex_count DESC, c.control_id ASC
    SKIP $skip LIMIT $limit
    RETURN c {{
        .control_id, .control_title, .status, .owner_role
    }} AS control,
    risks_count, annex_count, score
    """
    items: List[Dict[str, Any]] = []
    with drv.session() as s:
        res = s.run(cypher, params)
        for rec in res:
            c = rec["control"]
            items.append({
                "id": c["control_id"],
                "kind": "control",
                "title": c.get("control_title"),
                "status": c.get("status"),
                "owner_role": c.get("owner_role"),
                "risks_count": rec["risks_count"],
                "annex_count": rec["annex_count"],
                "score": rec["score"],
            })
    return {
        "items": items,
        "page": page,
        "top_k": top_k,
        "count": len(items),
        "scoring_notes": [
            "score = risks_count + 0.6*annex_count + 0.6*keyword_hits + dept_coverage boost + owner/status boosts"
        ],
    }

# -------------------------
# 3) graph_search_annexes
# -------------------------
@tool("graph_search_annexes")
def graph_search_annexes(hints: Union[str, Dict[str, Any], None], org: Optional[str] = None, top_k: int = 10, page: int = 1) -> Dict[str, Any]:
    """
    Discover Annex clauses relevant to (optionally) the org. Coverage = controls and mitigated risks connected to the org.
    If org is None, counts consider all orgs.
    """
    drv = get_driver()
    page, top_k = _paginate(page, top_k)
    skip = (page - 1) * top_k
    
    kw_list = _keywords_from_hints(hints)
    soft = _extract_soft_hints(hints)
    params: Dict[str, Any] = {
        "org": org,
        "keywords": kw_list,
        "annex_code": soft.get("annex_code"),
        "annex_prefix": soft.get("annex_prefix"),
        "skip": skip,
        "limit": top_k,
    }
    where_org = "WHERE o.name = $org" if org else ""
    cypher = f"""
    MATCH (a:Annex)
    OPTIONAL MATCH (c:Control)-[:MAPS_TO]->(a)
    OPTIONAL MATCH (c)-[:BELONGS_TO]->(o:Org) {where_org}
    OPTIONAL MATCH (c)-[:MITIGATES]->(r:Risk)
    WITH a,
         count(DISTINCT CASE WHEN o IS NULL AND $org IS NOT NULL THEN NULL ELSE c END) AS controls_count,
         count(DISTINCT CASE WHEN o IS NULL AND $org IS NOT NULL THEN NULL ELSE r END) AS risks_count,
         {_kw_score_expr('a.title', 'keywords')} AS kw_score,
         CASE WHEN $annex_code IS NOT NULL AND toLower(a.code) = toLower($annex_code) THEN 2 ELSE 0 END AS code_hit,
         CASE WHEN $annex_prefix IS NOT NULL AND toLower(a.code) STARTS WITH toLower($annex_prefix) THEN 1 ELSE 0 END AS prefix_hit
    WITH a, controls_count, risks_count, kw_score, code_hit, prefix_hit,
         (controls_count*1.0) + (risks_count*0.8) + (kw_score*0.6) + (code_hit*2.0) + (prefix_hit*1.0) AS score
    ORDER BY score DESC, controls_count DESC, risks_count DESC, a.code ASC
    SKIP $skip LIMIT $limit
    RETURN a {{ .code, .title }} AS annex, controls_count, risks_count, score
    """
    items: List[Dict[str, Any]] = []
    with drv.session() as s:
        res = s.run(cypher, params)
        for rec in res:
            a = rec["annex"]
            items.append({
                "id": a["code"],
                "kind": "annex",
                "code": a.get("code"),
                "title": a.get("title"),
                "controls_count": rec["controls_count"],
                "risks_count": rec["risks_count"],
                "score": rec["score"],
            })
    return {
        "items": items,
        "page": page,
        "top_k": top_k,
        "count": len(items),
        "scoring_notes": [
            "score = controls_count + 0.8*risks_count + 0.6*keyword_hits + code/prefix boosts"
        ],
    }

# -------------------------
# 4) graph_related
# -------------------------
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
    relation_types = relation_types or ["MITIGATES", "MAPS_TO", "BELONGS_TO"]
    params: Dict[str, Any] = {
        "id": anchor_id,
        "hops": int(max(1, hops)),
        "types": relation_types,
        "top_k": int(max(1, top_k)),
        "org": org,
    }
    # optional org constraint for discovered Risk/Control nodes
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

# -------------------------
# 5) graph_hydrate
# -------------------------
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
