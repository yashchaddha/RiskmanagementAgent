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
