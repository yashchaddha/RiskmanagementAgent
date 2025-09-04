from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Risk(BaseModel):
    id: Optional[str] = None
    description: str
    category: str
    likelihood: str
    impact: str
    treatment_strategy: str
    is_selected: bool = True
    # New user input fields
    asset_value: Optional[str] = None
    department: Optional[str] = None
    risk_owner: Optional[str] = None
    security_impact: Optional[str] = None
    target_date: Optional[str] = None
    risk_progress: Optional[str] = "Identified"
    residual_exposure: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class GeneratedRisks(BaseModel):
    id: Optional[str] = None
    user_id: str
    organization_name: str
    location: str
    domain: str
    risks: List[Risk]
    total_risks: int
    selected_risks: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RiskResponse(BaseModel):
    success: bool
    message: str
    data: Optional[GeneratedRisks] = None

class FinalizedRisk(BaseModel):
    id: Optional[str] = None
    description: str
    category: str
    likelihood: str
    impact: str
    treatment_strategy: str
    # New user input fields
    asset_value: Optional[str] = None
    department: Optional[str] = None
    risk_owner: Optional[str] = None
    security_impact: Optional[str] = None
    target_date: Optional[str] = None
    risk_progress: Optional[str] = "Identified"
    residual_exposure: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FinalizedRisks(BaseModel):
    id: Optional[str] = None  # MongoDB _id for this collection
    user_id: str
    organization_name: str
    location: str
    domain: str
    risks: List[FinalizedRisk]
    total_risks: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FinalizedRisksResponse(BaseModel):
    success: bool
    message: str
    data: Optional[FinalizedRisks] = None 

# Annex A mapping model
class AnnexAMapping(BaseModel):
    id: str  # e.g., "A.5.29"
    title: str  # e.g., "Information security during disruption"

# Comprehensive Control model based on new format
class Control(BaseModel):
    id: Optional[str] = None  # MongoDB _id
    control_id: str  # e.g., "C-001" 
    control_title: str  # e.g., "ICT Readiness & BCP for Regional Failover"
    control_description: str  # What this control addresses
    objective: str  # Business objective of the control
    annexA_map: List[AnnexAMapping]  # List of mapped ISO 27001 Annex A controls
    linked_risk_ids: List[str]  # Risk IDs this control addresses
    owner_role: str  # e.g., "SRE Manager"
    process_steps: List[str]  # Step-by-step implementation process
    evidence_samples: List[str]  # Examples of evidence for this control
    metrics: List[str]  # Measurable outcomes/KPIs
    frequency: str  # How often this control is executed/reviewed
    policy_ref: str  # Reference to related policy
    status: str  # e.g., "Implemented", "Planned", "In Progress"
    rationale: str  # Why this control is necessary
    assumptions: str  # Any assumptions made
    user_id: Optional[str] = None  # For multi-tenancy
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ControlSelection(BaseModel):
    session_id: str
    selected_control_ids: List[str]