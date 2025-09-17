import os
from typing import Dict, Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

from knowledge_base import ISO_27001_KNOWLEDGE
from graph_kg import get_driver


load_dotenv()


def ensure_kb_constraints() -> None:
    drv = get_driver()
    cyphers = [
        # We reuse the Annex label for both domains (A.5) and controls (A.5.1)
        "CREATE CONSTRAINT annex_code_unique IF NOT EXISTS FOR (a:Annex) REQUIRE a.code IS UNIQUE",
        "CREATE CONSTRAINT clause_code_unique IF NOT EXISTS FOR (c:Clause) REQUIRE c.code IS UNIQUE",
        "CREATE CONSTRAINT subclause_code_unique IF NOT EXISTS FOR (s:SubClause) REQUIRE s.code IS UNIQUE",
    ]
    with drv.session() as s:
        for c in cyphers:
            try:
                s.run(c)
            except Exception:
                pass


def ingest_iso_knowledge() -> Dict[str, int]:
    """Ingest static ISO 27001 knowledge (clauses + Annex A) into Neo4j."""
    ensure_kb_constraints()
    drv = get_driver()
    kb = ISO_27001_KNOWLEDGE.get("ISO27001_2022", {})

    clauses = kb.get("Clauses", [])
    annex = kb.get("Annex_A", [])

    n_clauses = 0
    n_subclauses = 0
    n_annex_domains = 0
    n_annex_controls = 0

    with drv.session() as s:
        # Clauses and SubClauses
        for clause in clauses:
            code = str(clause.get("id", "")).strip()
            if not code:
                continue
            s.run(
                """
                MERGE (c:Clause {code: $code})
                SET c.title = $title,
                    c.description = $description
                """,
                code=code,
                title=clause.get("title"),
                description=clause.get("description"),
            )
            n_clauses += 1

            for sub in clause.get("subclauses", []) or []:
                scode = str(sub.get("id", "")).strip()
                if not scode:
                    continue
                s.run(
                    """
                    MERGE (sc:SubClause {code: $scode})
                    SET sc.title = $title
                    WITH sc
                    MATCH (c:Clause {code: $code})
                    MERGE (c)-[:HAS_SUBCLAUSE]->(sc)
                    """,
                    scode=scode,
                    title=sub.get("title"),
                    code=code,
                )
                n_subclauses += 1

        # Annex A domains and controls
        for domain in annex:
            dcode = str(domain.get("id", "")).strip()
            if not dcode:
                continue
            s.run(
                """
                MERGE (a:Annex {code: $code})
                SET a.title = $title,
                    a.category = $category,
                    a.description = $description,
                    a.is_domain = true
                """,
                code=dcode,
                title=domain.get("title"),
                category=domain.get("category"),
                description=domain.get("description"),
            )
            n_annex_domains += 1

            for ctrl in domain.get("controls", []) or []:
                ccode = str(ctrl.get("id", "")).strip()
                if not ccode:
                    continue
                s.run(
                    """
                    MERGE (ac:Annex {code: $ccode})
                    SET ac.title = $title,
                        ac.description = $description,
                        ac.is_domain = false
                    WITH ac
                    MATCH (ad:Annex {code: $dcode})
                    MERGE (ad)-[:HAS_CONTROL]->(ac)
                    """,
                    ccode=ccode,
                    title=ctrl.get("title"),
                    description=ctrl.get("description"),
                    dcode=dcode,
                )
                n_annex_controls += 1

    return {
        "clauses": n_clauses,
        "subclauses": n_subclauses,
        "annex_domains": n_annex_domains,
        "annex_controls": n_annex_controls,
    }


def main():
    counts = ingest_iso_knowledge()
    print("ISO knowledge graph ingestion complete:", counts)


if __name__ == "__main__":
    main()

