import os
import time
import json
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from pymilvus import (
    connections, db, utility,
    FieldSchema, CollectionSchema, DataType, Collection
)
from langchain_openai import OpenAIEmbeddings

load_dotenv()

ZILLIZ_URI = os.getenv("ZILLIZ_URI")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_TOKEN")
ZILLIZ_DB = os.getenv("ZILLIZ_DB", "default")
COLLECTION_NAME = "finalized_risks_index"
EMBED_DIM = 1536  # text-embedding-3-small
CONTROLS_COLLECTION_NAME = "controls_index"

def _connect():
    # idempotent connect
    try:
        connections.connect(
            alias="default",
            uri=ZILLIZ_URI,
            token=ZILLIZ_TOKEN,
            db_name=ZILLIZ_DB,
            timeout=30
        )
    except Exception:
        # if already connected, it's fine
        pass

def _ensure_db():
    _connect()
    try:
        # Make sure DB exists (Zilliz supports logical DBs)
        if ZILLIZ_DB not in db.list_databases():
            db.create_database(ZILLIZ_DB)
    except Exception:
        # Some Zilliz plans don’t use db APIs; safe to ignore if not supported
        pass

def _ensure_collection() -> Collection:
    _ensure_db()
    if not utility.has_collection(COLLECTION_NAME):
        fields = [
            FieldSchema(name="risk_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True, auto_id=False),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="organization_name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="location", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="risk_owner", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="risk_text", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBED_DIM),
            FieldSchema(name="created_at", dtype=DataType.INT64),
            FieldSchema(name="updated_at", dtype=DataType.INT64),
        ]
        schema = CollectionSchema(fields=fields, description="Finalized risks semantic index")
        collection = Collection(name=COLLECTION_NAME, schema=schema, using="default")

        # Create index on vector field
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 1024},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
    else:
        collection = Collection(name=COLLECTION_NAME)

    # Load for search
    try:
        collection.load()
    except Exception:
        # ensure index is created before load in cold starts
        collection.flush()
        collection.load()

    return collection

def _ensure_controls_collection() -> Collection:
    _ensure_db()
    if not utility.has_collection(CONTROLS_COLLECTION_NAME):
        fields = [
            # Primary key - using id from Control model (MongoDB _id)
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True, auto_id=False),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
            # All fields from Control model
            FieldSchema(name="control_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="control_title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="control_description", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="annexA_map", dtype=DataType.VARCHAR, max_length=2048),  # JSON string of list
            FieldSchema(name="linked_risk_ids", dtype=DataType.VARCHAR, max_length=1024),  # JSON string of list
            FieldSchema(name="owner_role", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="process_steps", dtype=DataType.VARCHAR, max_length=4096),  # JSON string of list
            FieldSchema(name="evidence_samples", dtype=DataType.VARCHAR, max_length=4096),  # JSON string of list
            FieldSchema(name="metrics", dtype=DataType.VARCHAR, max_length=2048),  # JSON string of list
            FieldSchema(name="frequency", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="policy_ref", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="rationale", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="assumptions", dtype=DataType.VARCHAR, max_length=2048),
            # Combined text for embedding
            FieldSchema(name="control_text", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBED_DIM),
            FieldSchema(name="created_at", dtype=DataType.INT64),
            FieldSchema(name="updated_at", dtype=DataType.INT64),
        ]
        schema = CollectionSchema(fields=fields, description="Controls semantic index")
        collection = Collection(name=CONTROLS_COLLECTION_NAME, schema=schema, using="default")
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 1024},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
    else:
        collection = Collection(name=CONTROLS_COLLECTION_NAME)

    try:
        collection.load()
    except Exception:
        collection.flush()
        collection.load()
    return collection

def _get_embedder():
    # keep it isolated so we can swap later if needed
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=os.getenv("OPENAI_API_KEY"))

def _compose_sentence(
    risk: Dict[str, Any],
    organization_name: str,
    location: str,
    domain: str
) -> str:
    # Compose ONE canonical sentence with everything useful
    def _v(x): return x if (x is not None and x != "") else "-"
    return (
        f"{_v(organization_name)} in {_v(location)} ({_v(domain)}) — "
        f"Category: {_v(risk.get('category'))}. "
        f"Risk: {_v(risk.get('description'))}. "
        f"Likelihood: {_v(risk.get('likelihood'))}; Impact: {_v(risk.get('impact'))}. "
        f"Treatment: {_v(risk.get('treatment_strategy'))}. "
        f"Asset value: {_v(risk.get('asset_value'))}; Dept: {_v(risk.get('department'))}; "
        f"Owner: {_v(risk.get('risk_owner'))}; Security impact: {_v(risk.get('security_impact'))}; "
        f"Target date: {_v(risk.get('target_date'))}; Progress: {_v(risk.get('risk_progress'))}; "
        f"Residual exposure: {_v(risk.get('residual_exposure'))}."
    )

class VectorIndexService:
    @staticmethod
    def upsert_finalized_risks(
        user_id: str,
        organization_name: str,
        location: str,
        domain: str,
        risks: List[Dict[str, Any]],
    ) -> None:
        """
        risks: list of dicts like the ones you insert into Mongo "risks" array
               each must have at least: _id, description, category, likelihood, impact, treatment_strategy, ...
        """
        if not risks:
            return

        collection = _ensure_collection()
        embedder = _get_embedder()

        # Prepare payloads
        now = int(time.time() * 1000)
        risk_ids = []
        user_ids = []
        orgs, locs, doms = [], [], []
        cats, depts, owners = [], [], []
        texts = []

        for r in risks:
            rid = str(r.get("_id", ""))  # ObjectId -> str
            risk_ids.append(rid)
            user_ids.append(user_id)
            orgs.append(organization_name or "")
            locs.append(location or "")
            doms.append(domain or "")
            cats.append(r.get("category", "") or "")
            depts.append(r.get("department", "") or "")
            owners.append(r.get("risk_owner", "") or "")
            texts.append(_compose_sentence(r, organization_name, location, domain))

        # Embed in batch
        vectors = embedder.embed_documents(texts)

        # Milvus has no native "upsert" on all versions; emulate by delete-then-insert by PK
        expr = f"user_id == '{user_id}' && risk_id in {str(risk_ids)}"
        try:
            collection.delete(expr)
        except Exception:
            pass  # ok if nothing to delete

        data = [
            risk_ids, user_ids, orgs, locs, doms,
            cats, depts, owners, texts, vectors,
            [now]*len(risk_ids), [now]*len(risk_ids)
        ]
        collection.insert(data)
        collection.flush()

    @staticmethod
    def delete_by_risk_id(user_id: str, risk_id: str) -> None:
        collection = _ensure_collection()
        rid = str(risk_id)
        expr = f"user_id == '{user_id}' && risk_id == '{rid}'"
        collection.delete(expr)
        collection.flush()

    @staticmethod
    def _build_filter_expr(user_id: str, filters: Dict[str, Any]) -> str:
        # Always scope by user_id
        clauses = [f"user_id == '{user_id}'"]
        # Optional scalars
        if filters.get("location"):
            clauses.append(f"location == '{filters['location']}'")
        if filters.get("domain"):
            clauses.append(f"domain == '{filters['domain']}'")
        if filters.get("department"):
            clauses.append(f"department == '{filters['department']}'")
        if filters.get("risk_owner"):
            clauses.append(f"risk_owner == '{filters['risk_owner']}'")
        if filters.get("category"):
            cats = filters["category"]
            if isinstance(cats, list) and cats:
                # e.g. category in ["Operational","Legal and Compliance"]
                values = ",".join([f"'{c}'" for c in cats])
                clauses.append(f"category in [{values}]")
        # Date ranges are stored only as ints; if you later persist per-risk timestamps,
        # add them here (created_at/updated_at >=/<=).
        return " && ".join(clauses)

    @staticmethod
    def search(
        user_id: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        similar_to_risk_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns: dict with { "summary": str, "results": [ {risk_id, score, ...}, ... ] }
        """
        filters = filters or {}
        collection = _ensure_collection()
        embedder = _get_embedder()

        # If "similar_to_risk_id" provided, fetch that vector seed via stored text
        if similar_to_risk_id:
            q = collection.query(expr=f"user_id == '{user_id}' && risk_id == '{similar_to_risk_id}'",
                                 output_fields=["risk_text"])
            if q:
                query_text = q[0]["risk_text"]
            else:
                query_text = query or ""
        else:
            query_text = query or ""

        if not query_text:
            # fall back to match-all within user + filters by searching a generic embedding of "*"
            query_text = "find relevant risks for this user"

        qvec = embedder.embed_query(query_text)

        expr = VectorIndexService._build_filter_expr(user_id, filters)
        limit = max(1, min(int(top_k or 10), 50))

        # Ann search
        res = collection.search(
            data=[qvec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=limit,
            expr=expr,
            output_fields=[
                "risk_id", "user_id", "organization_name", "location", "domain",
                "category", "department", "risk_owner", "risk_text"
            ],
        )

        # Flatten results
        hits = []
        for hit in (res[0] if res else []):
            hits.append({
                "risk_id": hit.entity.get("risk_id"),
                "score": float(hit.distance),
                "organization_name": hit.entity.get("organization_name"),
                "location": hit.entity.get("location"),
                "domain": hit.entity.get("domain"),
                "category": hit.entity.get("category"),
                "department": hit.entity.get("department"),
                "risk_owner": hit.entity.get("risk_owner"),
                "risk_text": hit.entity.get("risk_text"),
            })

        # Friendly one-liner summary
        f_cat = filters.get("category")
        scope_bits = []
        if f_cat: scope_bits.append(f"categories={f_cat}")
        if filters.get("location"): scope_bits.append(f"location={filters['location']}")
        if filters.get("domain"): scope_bits.append(f"domain={filters['domain']}")
        if filters.get("department"): scope_bits.append(f"department={filters['department']}")
        if filters.get("risk_owner"): scope_bits.append(f"owner={filters['risk_owner']}")
        scope_str = (", ".join(scope_bits)) if scope_bits else "no filters"
        summary = f"Top {len(hits)} matches for “{query_text}” ({scope_str})."

        return {"summary": summary, "results": hits}


def _compose_control_text(control: Dict[str, Any]) -> str:
    """Compose embedding text using exact Control model field names"""
    def _v(x):
        if x is None:
            return "-"
        if isinstance(x, list):
            return "; ".join(map(str, x))
        if isinstance(x, dict):
            return ", ".join(f"{k}:{v}" for k, v in x.items())
        return str(x)
    
    # Use exact field names from Control model
    control_id = control.get("control_id") or ""
    control_title = control.get("control_title") or ""
    control_description = control.get("control_description") or ""
    objective = control.get("objective") or ""
    owner_role = control.get("owner_role") or ""
    frequency = control.get("frequency") or ""
    status = control.get("status") or ""
    policy_ref = control.get("policy_ref") or ""
    rationale = control.get("rationale") or ""
    assumptions = control.get("assumptions") or ""
    
    # Handle complex fields
    metrics = control.get("metrics") or []
    process_steps = control.get("process_steps") or []
    evidence_samples = control.get("evidence_samples") or []
    linked_risk_ids = control.get("linked_risk_ids") or []
    
    # Handle annexA_map
    annex_ids = []
    annexA_map = control.get("annexA_map") or []
    if isinstance(annexA_map, list):
        for a in annexA_map:
            if isinstance(a, dict) and a.get("id"):
                annex_ids.append(a.get("id"))
    
    # Compose comprehensive text for embedding
    return (
        f"Control ID: {_v(control_id)}. Title: {_v(control_title)}. "
        f"Description: {_v(control_description)}. Objective: {_v(objective)}. "
        f"Owner Role: {_v(owner_role)}. Frequency: {_v(frequency)}. Status: {_v(status)}. "
        f"Policy Reference: {_v(policy_ref)}. Rationale: {_v(rationale)}. "
        f"Assumptions: {_v(assumptions)}. Annex A Mapping: {_v(annex_ids)}. "
        f"Linked Risk IDs: {_v(linked_risk_ids)}. Metrics: {_v(metrics)}. "
        f"Process Steps: {_v(process_steps)}. Evidence Samples: {_v(evidence_samples)}."
    )


class ControlsVectorIndexService:
    @staticmethod
    def upsert_controls(user_id: str, controls: List[Dict[str, Any]]) -> None:
        if not controls:
            return
        collection = _ensure_controls_collection()
        embedder = _get_embedder()
        now = int(time.time() * 1000)
        
        # Prepare rows using exact Control model field names
        ids = []
        user_ids = []
        control_ids = []
        control_titles = []
        control_descriptions = []
        objectives = []
        annexA_maps = []
        linked_risk_ids_list = []
        owner_roles = []
        process_steps_list = []
        evidence_samples_list = []
        metrics_list = []
        frequencies = []
        policy_refs = []
        statuses = []
        rationales = []
        assumptions_list = []
        texts = []
        
        for c in controls:
            # Use 'id' field (MongoDB _id) as primary key
            control_id = str(c.get("id") or c.get("_id") or "")
            if not control_id:
                # skip if we don't have a unique id
                continue
                
            ids.append(control_id)
            user_ids.append(user_id)
            
            # Store all Control model fields
            control_ids.append(c.get("control_id") or "")
            control_titles.append(c.get("control_title") or "")
            control_descriptions.append(c.get("control_description") or "")
            objectives.append(c.get("objective") or "")
            owner_roles.append(c.get("owner_role") or "")
            frequencies.append(c.get("frequency") or "")
            statuses.append(c.get("status") or "")
            policy_refs.append(c.get("policy_ref") or "")
            rationales.append(c.get("rationale") or "")
            assumptions_list.append(c.get("assumptions") or "")
            
            # Handle complex fields - serialize as JSON strings
            annexA_maps.append(json.dumps(c.get("annexA_map") or []))
            linked_risk_ids_list.append(json.dumps(c.get("linked_risk_ids") or []))
            process_steps_list.append(json.dumps(c.get("process_steps") or []))
            evidence_samples_list.append(json.dumps(c.get("evidence_samples") or []))
            metrics_list.append(json.dumps(c.get("metrics") or []))
            
            # Generate embedding text
            texts.append(_compose_control_text(c))

        if not ids:
            return

        vectors = embedder.embed_documents(texts)
        
        # Delete existing records with same IDs, then insert new ones
        expr = f"user_id == '{user_id}' && id in {str(ids)}"
        try:
            collection.delete(expr)
        except Exception:
            pass
            
        data = [
            ids, user_ids, control_ids, control_titles, control_descriptions,
            objectives, annexA_maps, linked_risk_ids_list, owner_roles,
            process_steps_list, evidence_samples_list, metrics_list,
            frequencies, policy_refs, statuses, rationales, assumptions_list,
            texts, vectors, [now]*len(ids), [now]*len(ids)
        ]
        collection.insert(data)
        collection.flush()

    @staticmethod
    def delete_by_control_id(user_id: str, control_id: str) -> None:
        collection = _ensure_controls_collection()
        expr = f"user_id == '{user_id}' && id == '{str(control_id)}'"
        collection.delete(expr)
        collection.flush()

    @staticmethod
    def _build_filter_expr(user_id: str, filters: Dict[str, Any]) -> str:
        clauses = [f"user_id == '{user_id}'"]
        if filters.get("status"):
            clauses.append(f"status == '{filters['status']}'")
        # Annex/risk/category not fully supported server-side; do client-side post-filter
        return " && ".join(clauses)

    @staticmethod
    def search(user_id: str, query: str, top_k: int = 50, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        filters = filters or {}
        collection = _ensure_controls_collection()
        embedder = _get_embedder()
        limit = max(1, min(int(top_k or 50), 50))

        # Heuristic: list-all detection
        qtext = (query or "").strip()
        list_all = False
        ql = qtext.lower()
        if not qtext:
            list_all = True
        elif ("all" in ql and "control" in ql) or ("organizational controls" in ql) or ("my controls" in ql) or ql.startswith("get "):
            list_all = True

        hits = []
        if not list_all:
            # Vector search
            qvec = embedder.embed_query(qtext or "controls for this organization")
            expr = ControlsVectorIndexService._build_filter_expr(user_id, filters)
            
            # Define output fields based on Control model
            output_fields = [
                "id", "user_id", "control_id", "control_title", "control_description",
                "objective", "annexA_map", "linked_risk_ids", "owner_role",
                "process_steps", "evidence_samples", "metrics", "frequency",
                "policy_ref", "status", "rationale", "assumptions", "control_text"
            ]
            
            res = collection.search(
                data=[qvec],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                limit=limit,
                expr=expr,
                output_fields=output_fields,
            )
            for hit in (res[0] if res else []):
                # Parse JSON fields back to lists/objects
                annexA_map = []
                linked_risk_ids = []
                process_steps = []
                evidence_samples = []
                metrics = []
                
                try:
                    annexA_map = json.loads(hit.entity.get("annexA_map") or "[]")
                except:
                    pass
                try:
                    linked_risk_ids = json.loads(hit.entity.get("linked_risk_ids") or "[]")
                except:
                    pass
                try:
                    process_steps = json.loads(hit.entity.get("process_steps") or "[]")
                except:
                    pass
                try:
                    evidence_samples = json.loads(hit.entity.get("evidence_samples") or "[]")
                except:
                    pass
                try:
                    metrics = json.loads(hit.entity.get("metrics") or "[]")
                except:
                    pass
                
                hits.append({
                    "id": hit.entity.get("id"),
                    "score": float(hit.distance),
                    "control_id": hit.entity.get("control_id"),
                    "control_title": hit.entity.get("control_title"),
                    "control_description": hit.entity.get("control_description"),
                    "objective": hit.entity.get("objective"),
                    "annexA_map": annexA_map,
                    "linked_risk_ids": linked_risk_ids,
                    "owner_role": hit.entity.get("owner_role"),
                    "process_steps": process_steps,
                    "evidence_samples": evidence_samples,
                    "metrics": metrics,
                    "frequency": hit.entity.get("frequency"),
                    "policy_ref": hit.entity.get("policy_ref"),
                    "status": hit.entity.get("status"),
                    "rationale": hit.entity.get("rationale"),
                    "assumptions": hit.entity.get("assumptions"),
                    "control_text": hit.entity.get("control_text"),
                })

        # Fallback or list-all: fetch by user filter without ANN
        if list_all or not hits:
            expr = ControlsVectorIndexService._build_filter_expr(user_id, filters)
            output_fields = [
                "id", "user_id", "control_id", "control_title", "control_description",
                "objective", "annexA_map", "linked_risk_ids", "owner_role",
                "process_steps", "evidence_samples", "metrics", "frequency",
                "policy_ref", "status", "rationale", "assumptions", "control_text"
            ]
            rows = collection.query(expr=expr, output_fields=output_fields)
            
            # Apply client-side filters for annex/risk_id
            f = filters or {}
            out = []
            for r in rows:
                # Parse JSON fields
                annexA_map = []
                linked_risk_ids = []
                process_steps = []
                evidence_samples = []
                metrics = []
                
                try:
                    annexA_map = json.loads(r.get("annexA_map") or "[]")
                except:
                    pass
                try:
                    linked_risk_ids = json.loads(r.get("linked_risk_ids") or "[]")
                except:
                    pass
                try:
                    process_steps = json.loads(r.get("process_steps") or "[]")
                except:
                    pass
                try:
                    evidence_samples = json.loads(r.get("evidence_samples") or "[]")
                except:
                    pass
                try:
                    metrics = json.loads(r.get("metrics") or "[]")
                except:
                    pass
                
                # Apply client-side filters
                if f.get("annex"):
                    # Check if any annexA_map item matches
                    annex_match = False
                    for annex_item in annexA_map:
                        if isinstance(annex_item, dict) and annex_item.get("id", "").upper().startswith(str(f["annex"]).upper()):
                            annex_match = True
                            break
                    if not annex_match:
                        continue
                        
                if f.get("risk_id"):
                    if str(f["risk_id"]) not in [str(rid) for rid in linked_risk_ids]:
                        continue
                
                out.append({
                    "id": r.get("id"),
                    "control_id": r.get("control_id"),
                    "control_title": r.get("control_title"),
                    "control_description": r.get("control_description"),
                    "objective": r.get("objective"),
                    "annexA_map": annexA_map,
                    "linked_risk_ids": linked_risk_ids,
                    "owner_role": r.get("owner_role"),
                    "process_steps": process_steps,
                    "evidence_samples": evidence_samples,
                    "metrics": metrics,
                    "frequency": r.get("frequency"),
                    "policy_ref": r.get("policy_ref"),
                    "status": r.get("status"),
                    "rationale": r.get("rationale"),
                    "assumptions": r.get("assumptions"),
                    "control_text": r.get("control_text"),
                })
            hits = out[:limit]
        # Build summary
        f = filters or {}
        summary_bits = []
        if query:
            summary_bits.append(f'query="{query}"')
        if f.get("status"):
            summary_bits.append(f"status={f['status']}")
        if f.get("annex"):
            summary_bits.append(f"annex={f['annex']}")
        if f.get("risk_id"):
            summary_bits.append(f"risk_id={f['risk_id']}")
        summary = f"Top {len(hits)} control matches ({', '.join(summary_bits) if summary_bits else 'no filters'})."
        return {"summary": summary, "results": hits}
