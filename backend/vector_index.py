import os
import time
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
            FieldSchema(name="control_uid", dtype=DataType.VARCHAR, max_length=128, is_primary=True, auto_id=False),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="annex", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="risk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="control_text", dtype=DataType.VARCHAR, max_length=4096),
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
    def _v(x):
        if x is None:
            return "-"
        if isinstance(x, list):
            return "; ".join(map(str, x))
        if isinstance(x, dict):
            return ", ".join(f"{k}:{v}" for k, v in x.items())
        return str(x)
    title = control.get("control_title") or control.get("title") or ""
    desc = control.get("control_description") or control.get("description") or ""
    objective = control.get("objective") or ""
    owner = control.get("owner_role") or control.get("owner") or ""
    freq = control.get("frequency") or ""
    status = control.get("status") or ""
    policy = control.get("policy_ref") or ""
    metrics = control.get("metrics") or []
    steps = control.get("process_steps") or []
    evidence = control.get("evidence_samples") or control.get("evidence") or []
    # Annex handling (new or legacy)
    annex_ids = []
    aam = control.get("annexA_map") or []
    if isinstance(aam, list):
        for a in aam:
            if isinstance(a, dict) and a.get("id"):
                annex_ids.append(a.get("id"))
    ann_legacy = control.get("annex_reference") or ""
    if ann_legacy:
        annex_ids.append(str(ann_legacy))
    linked = control.get("linked_risk_ids") or []
    # Compose
    return (
        f"Title: {_v(title)}. Objective: {_v(objective)}. Description: {_v(desc)}. "
        f"Owner: {_v(owner)}. Frequency: {_v(freq)}. Status: {_v(status)}. Policy: {_v(policy)}. "
        f"Annex: {_v(annex_ids)}. Linked risks: {_v(linked)}. "
        f"Metrics: {_v(metrics)}. Steps: {_v(steps)}. Evidence: {_v(evidence)}."
    )


class ControlsVectorIndexService:
    @staticmethod
    def upsert_controls(user_id: str, controls: List[Dict[str, Any]]) -> None:
        if not controls:
            return
        collection = _ensure_controls_collection()
        embedder = _get_embedder()
        now = int(time.time() * 1000)
        # Prepare rows
        control_uids = []
        user_ids = []
        titles = []
        objectives = []
        statuses = []
        annexes = []
        risk_ids = []
        texts = []
        for c in controls:
            uid = str(c.get("_id") or c.get("id") or c.get("control_uid") or "")
            if not uid:
                # skip if we don't have a unique id
                continue
            control_uids.append(uid)
            user_ids.append(user_id)
            title = c.get("control_title") or c.get("title") or ""
            titles.append(title)
            objectives.append(c.get("objective") or "")
            statuses.append(c.get("status") or "")
            # choose first annex id for filtering; full list stays in text
            annex = ""
            aam = c.get("annexA_map") or []
            if isinstance(aam, list) and aam:
                first = aam[0]
                if isinstance(first, dict):
                    annex = first.get("id") or ""
            if not annex:
                annex = c.get("annex_reference") or ""
            annexes.append(annex)
            rid = ""
            linked = c.get("linked_risk_ids") or []
            if isinstance(linked, list) and linked:
                rid = str(linked[0])
            else:
                rid = str(c.get("risk_id") or "")
            risk_ids.append(rid)
            texts.append(_compose_control_text(c))

        if not control_uids:
            return

        vectors = embedder.embed_documents(texts)
        # delete-then-insert
        expr = f"user_id == '{user_id}' && control_uid in {str(control_uids)}"
        try:
            collection.delete(expr)
        except Exception:
            pass
        data = [
            control_uids, user_ids, titles, objectives, statuses,
            annexes, risk_ids, texts, vectors,
            [now]*len(control_uids), [now]*len(control_uids)
        ]
        collection.insert(data)
        collection.flush()

    @staticmethod
    def delete_by_control_uid(user_id: str, control_uid: str) -> None:
        collection = _ensure_controls_collection()
        expr = f"user_id == '{user_id}' && control_uid == '{str(control_uid)}'"
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
            res = collection.search(
                data=[qvec],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                limit=limit,
                expr=expr,
                output_fields=[
                    "control_uid", "user_id", "title", "objective", "status", "annex", "risk_id", "control_text"
                ],
            )
            for hit in (res[0] if res else []):
                hits.append({
                    "control_uid": hit.entity.get("control_uid"),
                    "score": float(hit.distance),
                    "title": hit.entity.get("title"),
                    "objective": hit.entity.get("objective"),
                    "status": hit.entity.get("status"),
                    "annex": hit.entity.get("annex"),
                    "risk_id": hit.entity.get("risk_id"),
                    "control_text": hit.entity.get("control_text"),
                })

        # Fallback or list-all: fetch by user filter without ANN
        if list_all or not hits:
            expr = ControlsVectorIndexService._build_filter_expr(user_id, filters)
            rows = collection.query(expr=expr, output_fields=[
                "control_uid", "user_id", "title", "objective", "status", "annex", "risk_id", "control_text"
            ])
            # Apply client-side filters for annex/risk_id
            f = filters or {}
            out = []
            for r in rows:
                if f.get("annex") and not str(r.get("annex") or "").upper().startswith(str(f["annex"]).upper()):
                    continue
                if f.get("risk_id") and str(r.get("risk_id") or "") != str(f["risk_id"]):
                    continue
                out.append({
                    "control_uid": r.get("control_uid"),
                    "title": r.get("title"),
                    "objective": r.get("objective"),
                    "status": r.get("status"),
                    "annex": r.get("annex"),
                    "risk_id": r.get("risk_id"),
                    "control_text": r.get("control_text"),
                })
            hits = out[:limit]
        # Client-side optional filtering for annex, risk_id
        f = filters or {}
        if f.get("annex"):
            pref = str(f["annex"]).upper()
            hits = [h for h in hits if str(h.get("annex") or "").upper().startswith(pref)]
        if f.get("risk_id"):
            rid = str(f["risk_id"]).strip()
            hits = [h for h in hits if str(h.get("risk_id") or "") == rid]

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
