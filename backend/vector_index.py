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
from openai import OpenAI

from dependencies import get_llm

load_dotenv()

ZILLIZ_URI = os.getenv("ZILLIZ_URI")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_TOKEN")
ZILLIZ_DB = os.getenv("ZILLIZ_DB", "default")
COLLECTION_NAME = "finalized_risks_index"
COLLECTION_VERSION = "v2"  # Increment when schema changes
VERSIONED_COLLECTION_NAME = f"{COLLECTION_NAME}_{COLLECTION_VERSION}"
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
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="likelihood", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="impact", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="treatment_strategy", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="risk_owner", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="asset_value", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="security_impact", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="target_date", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="risk_progress", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="residual_exposure", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="risk_text", dtype=DataType.VARCHAR, max_length=8192),
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

def _truncate_field(value: str, max_length: int) -> str:
    """Truncate a string field to the specified max length"""
    if not value:
        return ""
    value_str = str(value)
    if len(value_str) <= max_length:
        return value_str
    # Truncate and add ellipsis
    return value_str[:max_length-3] + "..."

def _compose_sentence(
    risk: Dict[str, Any],
    organization_name: str,
    location: str,
    domain: str
) -> str:
    """Convert risk JSON to a comprehensive natural language paragraph using LLM"""
    def _v(x): 
        return str(x).strip() if (x is not None and str(x).strip() != "" and str(x).strip() != "None") else None

    try:
        llm = get_llm()

        # Prepare comprehensive risk data payload
        payload = {
            "organization_name": _v(organization_name),
            "location": _v(location),
            "domain": _v(domain),
            "description": _v(risk.get("description")),
            "category": _v(risk.get("category")),
            "likelihood": _v(risk.get("likelihood")),
            "impact": _v(risk.get("impact")),
            "treatment_strategy": _v(risk.get("treatment_strategy")),
            "department": _v(risk.get("department")),
            "risk_owner": _v(risk.get("risk_owner")),
            "asset_value": _v(risk.get("asset_value")),
            "security_impact": _v(risk.get("security_impact")),
            "target_date": _v(risk.get("target_date")),
            "risk_progress": _v(risk.get("risk_progress")),
            "residual_exposure": _v(risk.get("residual_exposure")),
        }

        # Filter out None values for cleaner prompt
        filtered_payload = {k: v for k, v in payload.items() if v is not None}

        # Enhanced LLM prompt for comprehensive paragraph generation
        user_prompt = f"""
Convert the following risk data into a comprehensive, natural language paragraph suitable for semantic search. 

Requirements:
- Write a detailed 2-3 sentence paragraph that captures all the key risk information
- Use natural, flowing language that would be easy to search semantically
- Include organization context, risk details, and mitigation information
- Do not use bullet points or structured formats
- Make it sound like a professional risk assessment description

Risk Data:
{json.dumps(filtered_payload, indent=2, ensure_ascii=False)}

Write only the paragraph, no other text or formatting:
"""

        resp = llm.invoke([
            {"role": "system", "content": "You are a professional risk management expert who writes comprehensive, searchable risk descriptions. Create detailed paragraphs that capture all relevant risk information in natural language."},
            {"role": "user", "content": user_prompt}
        ])
        
        text = (resp.content or "").strip()
        # Clean up the text - remove extra whitespace and ensure proper sentence ending
        text = " ".join(text.split())
        if text and not text.endswith((".", "!", "?")):
            text += "."
        
        if text:
            return text
            
    except Exception as e:
        print(f"Error in LLM-based sentence composition: {e}")
        # Fallback to structured format if LLM fails
        pass
    
    # Enhanced fallback format with all attributes
    parts = []
    if _v(organization_name):
        parts.append(f"{_v(organization_name)}")
    if _v(location):
        parts.append(f"located in {_v(location)}")
    if _v(domain):
        parts.append(f"operating in {_v(domain)} domain")
    
    org_context = ", ".join(parts) if parts else "Organization"
    
    risk_desc = _v(risk.get("description")) or "Unspecified risk"
    category = _v(risk.get("category")) or "General"
    likelihood = _v(risk.get("likelihood")) or "Unknown"
    impact = _v(risk.get("impact")) or "Unknown"
    
    paragraph = f"{org_context} faces a {category.lower()} risk: {risk_desc}. This risk has a {likelihood.lower()} likelihood of occurrence with {impact.lower()} potential impact."
    
    # Add treatment strategy if available
    treatment = _v(risk.get("treatment_strategy"))
    if treatment:
        paragraph += f" The planned treatment strategy involves {treatment.lower()}."
    
    # Add additional details if available
    details = []
    if _v(risk.get("department")):
        details.append(f"managed by {_v(risk.get('department'))} department")
    if _v(risk.get("risk_owner")):
        details.append(f"owned by {_v(risk.get('risk_owner'))}")
    if _v(risk.get("asset_value")):
        details.append(f"affecting assets valued at {_v(risk.get('asset_value'))}")
    if _v(risk.get("security_impact")) and _v(risk.get("security_impact")).lower() == "yes":
        details.append("with security implications")
    if _v(risk.get("target_date")):
        details.append(f"targeted for completion by {_v(risk.get('target_date'))}")
    if _v(risk.get("risk_progress")):
        details.append(f"currently in {_v(risk.get('risk_progress')).lower()} status")
    if _v(risk.get("residual_exposure")):
        details.append(f"with {_v(risk.get('residual_exposure')).lower()} residual exposure")
    
    if details:
        paragraph += f" This risk is {', '.join(details)}."
    
    return paragraph

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

        # Prepare payloads with all risk attributes
        now = int(time.time() * 1000)
        risk_ids = []
        user_ids = []
        orgs, locs, doms = [], [], []
        cats, descs, likelihoods, impacts, treatments = [], [], [], [], []
        depts, owners, asset_vals = [], [], []
        security_impacts, target_dates, progresses, residual_exposures = [], [], [], []
        texts = []

        for r in risks:
            rid = str(r.get("_id", ""))  # ObjectId -> str
            risk_ids.append(rid)
            user_ids.append(_truncate_field(user_id, 128))
            orgs.append(_truncate_field(organization_name or "", 256))
            locs.append(_truncate_field(location or "", 128))
            doms.append(_truncate_field(domain or "", 128))
            
            # Core risk attributes with truncation
            cats.append(_truncate_field(r.get("category", "") or "", 128))
            descs.append(_truncate_field(r.get("description", "") or "", 1024))
            likelihoods.append(_truncate_field(r.get("likelihood", "") or "", 128))
            impacts.append(_truncate_field(r.get("impact", "") or "", 128))
            treatments.append(_truncate_field(r.get("treatment_strategy", "") or "", 8192))
            
            # Additional risk attributes with truncation
            depts.append(_truncate_field(r.get("department", "") or "", 128))
            owners.append(_truncate_field(r.get("risk_owner", "") or "", 128))
            asset_vals.append(_truncate_field(r.get("asset_value", "") or "", 128))
            security_impacts.append(_truncate_field(r.get("security_impact", "") or "", 128))
            target_dates.append(_truncate_field(r.get("target_date", "") or "", 128))
            progresses.append(_truncate_field(r.get("risk_progress", "") or "", 128))
            residual_exposures.append(_truncate_field(r.get("residual_exposure", "") or "", 128))
            
            # Generate comprehensive natural language paragraph using LLM
            # Don't truncate risk_text as it's used for semantic search
            risk_text = _compose_sentence(r, organization_name, location, domain)
            texts.append(risk_text)

        # Embed in batch the generated natural language paragraphs
        vectors = embedder.embed_documents(texts)

        # Milvus has no native "upsert" on all versions; emulate by delete-then-insert by PK
        expr = f"user_id == '{user_id}' && risk_id in {str(risk_ids)}"
        try:
            collection.delete(expr)
        except Exception:
            pass  # ok if nothing to delete

        # Insert data with all attributes
        data = [
            risk_ids, user_ids, orgs, locs, doms,
            cats, descs, likelihoods, impacts, treatments,
            depts, owners, asset_vals, security_impacts, target_dates,
            progresses, residual_exposures, texts, vectors,
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
        
        # Optional scalar filters
        if filters.get("location"):
            clauses.append(f"location == '{filters['location']}'")
        if filters.get("domain"):
            clauses.append(f"domain == '{filters['domain']}'")
        if filters.get("department"):
            clauses.append(f"department == '{filters['department']}'")
        if filters.get("risk_owner"):
            clauses.append(f"risk_owner == '{filters['risk_owner']}'")
        if filters.get("likelihood"):
            clauses.append(f"likelihood == '{filters['likelihood']}'")
        if filters.get("impact"):
            clauses.append(f"impact == '{filters['impact']}'")
        if filters.get("security_impact"):
            clauses.append(f"security_impact == '{filters['security_impact']}'")
        if filters.get("risk_progress"):
            clauses.append(f"risk_progress == '{filters['risk_progress']}'")
        if filters.get("residual_exposure"):
            clauses.append(f"residual_exposure == '{filters['residual_exposure']}'")
            
        # Category filter (can be a list)
        if filters.get("category"):
            cats = filters["category"]
            if isinstance(cats, list) and cats:
                # e.g. category in ["Operational","Legal and Compliance"]
                values = ",".join([f"'{c}'" for c in cats])
                clauses.append(f"category in [{values}]")
            elif isinstance(cats, str):
                clauses.append(f"category == '{cats}'")
                
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
                "category", "description", "likelihood", "impact", "treatment_strategy",
                "department", "risk_owner", "asset_value", "security_impact", 
                "target_date", "risk_progress", "residual_exposure", "risk_text"
            ],
        )

        # Flatten results with all risk attributes
        hits = []
        for hit in (res[0] if res else []):
            hits.append({
                "risk_id": hit.entity.get("risk_id"),
                "score": float(hit.distance),
                "organization_name": hit.entity.get("organization_name"),
                "location": hit.entity.get("location"),
                "domain": hit.entity.get("domain"),
                "category": hit.entity.get("category"),
                "description": hit.entity.get("description"),
                "likelihood": hit.entity.get("likelihood"),
                "impact": hit.entity.get("impact"),
                "treatment_strategy": hit.entity.get("treatment_strategy"),
                "department": hit.entity.get("department"),
                "risk_owner": hit.entity.get("risk_owner"),
                "asset_value": hit.entity.get("asset_value"),
                "security_impact": hit.entity.get("security_impact"),
                "target_date": hit.entity.get("target_date"),
                "risk_progress": hit.entity.get("risk_progress"),
                "residual_exposure": hit.entity.get("residual_exposure"),
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
