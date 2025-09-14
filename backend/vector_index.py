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

# Controls collection constants
CONTROLS_COLLECTION_NAME = "finalized_controls_index"
CONTROLS_COLLECTION_VERSION = "v2"
VERSIONED_CONTROLS_COLLECTION_NAME = f"{CONTROLS_COLLECTION_NAME}_{CONTROLS_COLLECTION_VERSION}"

EMBED_DIM = 1536  # text-embedding-3-small dimension
EMBED_DIM_LARGE = 12288  # text-embedding-3-large dimension

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

def _ensure_controls_collection() -> Collection:
    _ensure_db()
    if not utility.has_collection(CONTROLS_COLLECTION_NAME):
        fields = [
            FieldSchema(name="control_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True, auto_id=False),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="organization_name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="location", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="control_title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="control_description", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="owner_role", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="frequency", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="policy_ref", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="rationale", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="assumptions", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="annexa_mappings", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="process_steps", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="evidence_samples", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="metrics", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="linked_risk_ids", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="control_text", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBED_DIM_LARGE),
            FieldSchema(name="created_at", dtype=DataType.INT64),
            FieldSchema(name="updated_at", dtype=DataType.INT64),
        ]
        schema = CollectionSchema(fields=fields, description="Finalized controls semantic index")
        collection = Collection(name=CONTROLS_COLLECTION_NAME, schema=schema, using="default")

        # Create index on vector field
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 1024},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
    else:
        collection = Collection(name=CONTROLS_COLLECTION_NAME)

    # Load for search
    try:
        collection.load()
    except Exception:
        # ensure index is created before load in cold starts
        collection.flush()
        collection.load()

    return collection

def _get_embedder(model: str = "text-embedding-3-small"):
    # keep it isolated so we can swap later if needed
    return OpenAIEmbeddings(model=model, api_key=os.getenv("OPENAI_API_KEY"))

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
            "risk_id": _v(risk.get("_id")),
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

def _compose_control_sentence(
    control: Dict[str, Any],
    organization_name: str,
    location: str,
    domain: str
) -> str:
    """Convert control JSON to a comprehensive natural language paragraph using LLM"""
    def _v(x): 
        return str(x).strip() if (x is not None and str(x).strip() != "" and str(x).strip() != "None") else None

    def _flatten_list(items, prefix=""):
        """Helper to flatten list fields into readable text"""
        if not items:
            return None
        if isinstance(items, list):
            clean_items = [str(item).strip() for item in items if item and str(item).strip()]
            if clean_items:
                return f"{prefix}{', '.join(clean_items)}" if prefix else ", ".join(clean_items)
        return _v(items)

    def _flatten_annexa_mappings(mappings):
        """Convert AnnexA mappings to readable format"""
        if not mappings:
            return None
        if isinstance(mappings, list):
            formatted = []
            for mapping in mappings:
                if isinstance(mapping, dict):
                    id_val = mapping.get("id", "")
                    title = mapping.get("title", "")
                    if id_val and title:
                        formatted.append(f"{id_val} ({title})")
                    elif id_val:
                        formatted.append(str(id_val))
            return f"ISO 27001: {', '.join(formatted)}" if formatted else None
        return _v(mappings)

    try:
        llm = get_llm()

        # Prepare comprehensive control data payload with flattened arrays
        payload = {
            "organization_name": _v(organization_name),
            "location": _v(location),
            "domain": _v(domain),
            "control_id": _v(control.get("control_id")),
            "control_title": _v(control.get("control_title")),
            "control_description": _v(control.get("control_description")),
            "objective": _v(control.get("objective")),
            "owner_role": _v(control.get("owner_role")),
            "frequency": _v(control.get("frequency")),
            "policy_ref": _v(control.get("policy_ref")),
            "status": _v(control.get("status")),
            "rationale": _v(control.get("rationale")),
            "assumptions": _v(control.get("assumptions")),
            "iso_mappings": _flatten_annexa_mappings(control.get("annexA_map")),
            "process_steps": _flatten_list(control.get("process_steps")),
            "evidence_samples": _flatten_list(control.get("evidence_samples")),
            "metrics": _flatten_list(control.get("metrics")),
            "linked_risks": _flatten_list(control.get("linked_risk_ids")),
        }

        # Filter out None values for cleaner prompt
        filtered_payload = {k: v for k, v in payload.items() if v is not None}

        # Enhanced LLM prompt for comprehensive control paragraph generation
        user_prompt = f"""
Convert the following control data into a comprehensive, natural language paragraph suitable for semantic search.

Requirements:
- Write a detailed paragraph that captures all the key control information
- Use natural, flowing language that would be easy to search semantically
- Include organization context, control details, implementation approach, and compliance mappings
- Do not use bullet points or structured formats
- Make it sound like a professional control description
- Include ISO 27001 Annex A mappings if present

Control Data:
{json.dumps(filtered_payload, indent=2, ensure_ascii=False)}

Write only the paragraph, no other text or formatting:
"""

        resp = llm.invoke([
            {"role": "system", "content": "You are a professional internal controls expert who writes comprehensive, searchable control descriptions. Create detailed paragraphs that capture all relevant control information in natural language."},
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
        print(f"Error in LLM-based control sentence composition: {e}")
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
    
    control_title = _v(control.get("control_title"))
    control_desc = _v(control.get("control_description"))
    objective = _v(control.get("objective"))
    
    paragraph = f"{org_context} implements {control_title}: {control_desc}. This control aims to {objective.lower()}."
    
    # Add implementation details if available
    details = []
    if _v(control.get("owner_role")):
        details.append(f"managed by {_v(control.get('owner_role'))}")
    if _v(control.get("frequency")):
        details.append(f"performed {_v(control.get('frequency')).lower()}")
    if _v(control.get("status")):
        details.append(f"currently {_v(control.get('status')).lower()}")
    
    # Add flattened array information
    process_steps = _flatten_list(control.get("process_steps"))
    if process_steps:
        details.append(f"involving steps: {process_steps}")
    
    evidence_samples = _flatten_list(control.get("evidence_samples"))
    if evidence_samples:
        details.append(f"evidenced by: {evidence_samples}")
    
    metrics = _flatten_list(control.get("metrics"))
    if metrics:
        details.append(f"measured through: {metrics}")
    
    annexa_info = _flatten_annexa_mappings(control.get("annexA_map"))
    if annexa_info:
        details.append(f"mapped to {annexa_info}")
    
    if details:
        paragraph += f" This control is {', '.join(details)}."
    
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


class ControlVectorIndexService:
    """Service for managing control vector embeddings"""
    
    @staticmethod
    def upsert_finalized_controls(
        user_id: str,
        organization_name: str,
        location: str,
        domain: str,
        controls: List[Dict[str, Any]],
    ) -> None:
        """
        controls: list of dicts like the ones from ControlDatabaseService
                  each must have at least: control_id, control_title, control_description, objective, ...
        """
        if not controls:
            return

        collection = _ensure_controls_collection()
        embedder = _get_embedder(model="text-embedding-3-large")

        # Prepare payloads with all control attributes
        now = int(time.time() * 1000)
        control_ids = []
        user_ids = []
        orgs, locs, doms = [], [], []
        titles, descriptions, objectives = [], [], []
        owner_roles, frequencies, policy_refs, statuses = [], [], [], []
        rationales, assumptions_list = [], []
        annexa_mappings, process_steps_list, evidence_samples_list, metrics_list = [], [], [], []
        linked_risk_ids_list = []
        texts = []

        def _flatten_to_string(items, max_length=None):
            """Helper to flatten list to comma-separated string"""
            if not items:
                return ""
            if isinstance(items, list):
                clean_items = [str(item).strip() for item in items if item and str(item).strip()]
                result = ", ".join(clean_items)
            else:
                result = str(items) if items else ""
            
            return _truncate_field(result, max_length) if max_length else result

        def _flatten_annexa_to_string(mappings):
            """Convert AnnexA mappings to string format"""
            if not mappings:
                return ""
            if isinstance(mappings, list):
                formatted = []
                for mapping in mappings:
                    if isinstance(mapping, dict):
                        id_val = mapping.get("id", "")
                        title = mapping.get("title", "")
                        if id_val and title:
                            formatted.append(f"{id_val}:{title}")
                        elif id_val:
                            formatted.append(str(id_val))
                result = ", ".join(formatted)
            else:
                result = str(mappings) if mappings else ""
            
            return _truncate_field(result, 2048)

        for c in controls:
            cid = str(c.get("control_id", ""))
            control_ids.append(cid)
            user_ids.append(_truncate_field(user_id, 128))
            orgs.append(_truncate_field(organization_name or "", 256))
            locs.append(_truncate_field(location or "", 128))
            doms.append(_truncate_field(domain or "", 128))
            
            # Core control attributes with truncation
            titles.append(_truncate_field(c.get("control_title", "") or "", 512))
            descriptions.append(_truncate_field(c.get("control_description", "") or "", 8192))
            objectives.append(_truncate_field(c.get("objective", "") or "", 8192))
            owner_roles.append(_truncate_field(c.get("owner_role", "") or "", 128))
            frequencies.append(_truncate_field(c.get("frequency", "") or "", 128))
            policy_refs.append(_truncate_field(c.get("policy_ref", "") or "", 512))
            statuses.append(_truncate_field(c.get("status", "") or "", 128))
            rationales.append(_truncate_field(c.get("rationale", "") or "", 8192))
            assumptions_list.append(_truncate_field(c.get("assumptions", "") or "", 8192))
            
            # Flatten array attributes
            annexa_mappings.append(_flatten_annexa_to_string(c.get("annexA_map")))
            process_steps_list.append(_flatten_to_string(c.get("process_steps"), 8192))
            evidence_samples_list.append(_flatten_to_string(c.get("evidence_samples"), 8192))
            metrics_list.append(_flatten_to_string(c.get("metrics"), 4096))
            linked_risk_ids_list.append(_flatten_to_string(c.get("linked_risk_ids"), 2048))
            
            # Generate comprehensive natural language paragraph using LLM
            control_text = _compose_control_sentence(c, organization_name, location, domain)
            texts.append(control_text)

        # Embed in batch the generated natural language paragraphs
        vectors = embedder.embed_documents(texts)

        # Milvus has no native "upsert" on all versions; emulate by delete-then-insert by PK
        expr = f"user_id == '{user_id}' && control_id in {str(control_ids)}"
        try:
            collection.delete(expr)
        except Exception:
            pass  # ok if nothing to delete

        # Insert data with all attributes
        data = [
            control_ids, user_ids, orgs, locs, doms,
            titles, descriptions, objectives, owner_roles, frequencies,
            policy_refs, statuses, rationales, assumptions_list,
            annexa_mappings, process_steps_list, evidence_samples_list, metrics_list,
            linked_risk_ids_list, texts, vectors,
            [now]*len(control_ids), [now]*len(control_ids)
        ]
        collection.insert(data)
        collection.flush()

    @staticmethod
    def delete_by_control_id(user_id: str, control_id: str) -> None:
        """Delete a specific control from vector index"""
        collection = _ensure_controls_collection()
        cid = str(control_id)
        expr = f"user_id == '{user_id}' && control_id == '{cid}'"
        collection.delete(expr)
        collection.flush()

    @staticmethod
    def search_controls(
        user_id: str,
        query_text: str,
        filters: Dict[str, Any] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search controls using semantic similarity"""
        if not query_text.strip():
            return []
        
        collection = _ensure_controls_collection()
        embedder = _get_embedder()
        
        # Generate embedding for query
        query_vector = embedder.embed_query(query_text)
        
        # Build filter expression
        filters = filters or {}
        filter_expr = ControlVectorIndexService._build_controls_filter_expr(user_id, filters)
        
        # Search parameters
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }
        
        # Perform semantic search
        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=limit,
            expr=filter_expr,
            output_fields=[
                "control_id", "control_title", "control_description", "objective",
                "owner_role", "frequency", "status", "control_text", "annexa_mappings",
                "process_steps", "evidence_samples", "metrics", "linked_risk_ids"
            ]
        )
        
        # Format results
        formatted_results = []
        for hit in results[0]:
            result = {
                "control_id": hit.entity.get("control_id"),
                "control_title": hit.entity.get("control_title"),
                "control_description": hit.entity.get("control_description"),
                "objective": hit.entity.get("objective"),
                "owner_role": hit.entity.get("owner_role"),
                "frequency": hit.entity.get("frequency"),
                "status": hit.entity.get("status"),
                "control_text": hit.entity.get("control_text"),
                "annexa_mappings": hit.entity.get("annexa_mappings"),
                "process_steps": hit.entity.get("process_steps"),
                "evidence_samples": hit.entity.get("evidence_samples"),
                "metrics": hit.entity.get("metrics"),
                "linked_risk_ids": hit.entity.get("linked_risk_ids"),
                "similarity_score": hit.score,
            }
            formatted_results.append(result)
        
        return formatted_results

    @staticmethod
    def _build_controls_filter_expr(user_id: str, filters: Dict[str, Any]) -> str:
        """Build Milvus filter expression for controls"""
        # Always scope by user_id
        clauses = [f"user_id == '{user_id}'"]
        
        # Optional scalar filters
        if filters.get("location"):
            clauses.append(f"location == '{filters['location']}'")
        if filters.get("domain"):
            clauses.append(f"domain == '{filters['domain']}'")
        if filters.get("owner_role"):
            clauses.append(f"owner_role == '{filters['owner_role']}'")
        if filters.get("frequency"):
            clauses.append(f"frequency == '{filters['frequency']}'")
        if filters.get("status"):
            clauses.append(f"status == '{filters['status']}'")
        
        # Control-specific filters could be added here
        # if filters.get("iso_control"):  # for filtering by specific ISO controls
        #     clauses.append(f"annexa_mappings like '%{filters['iso_control']}%'")
        
        return " && ".join(clauses)
