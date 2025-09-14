from pydantic import BaseModel
from typing import List, Optional, TypedDict
from datetime import datetime

class LLMState(TypedDict):
    input: str
    output: str
    conversation_history: list
    risk_context: dict  # Store risk assessment context
    user_data: dict  # Store user organization data
    active_mode: str  # Track current active node for stickiness
    risk_generation_requested: bool  # Flag to indicate if risk generation is needed
    risk_register_requested: bool  # Flag to indicate if risk register access is needed
    matrix_recommendation_requested: bool  # Flag to indicate if matrix recommendation is needed
    is_audit_related: bool  # Flag to indicate if query is audit-related
    is_risk_related: bool  # Flag to indicate if query is risk-related
    is_risk_knowledge_related: bool  # Flag to indicate if query is about risk knowledge/profiles
    # Control-related flags
    control_generation_requested: bool  # Flag to indicate if control generation is needed
    is_control_related: bool  # Flag to indicate if query is control-related
    control_target: str  # Target control node: generate_control_node, control_library_node, control_knowledge_node, clarify
    control_parameters: dict  # Parameters for control operations
    # Additional context fields used by control generation
    risk_description: str  # Raw risk description text when mode = risk_description

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

class AnnexAMapping(BaseModel):
    id: str
    title: str 

class Control(BaseModel):
    id: Optional[str] = None
    control_id: str
    control_title: str
    control_description: str
    objective: str
    annexA_map: List[AnnexAMapping]
    linked_risk_ids: List[str]
    owner_role: str
    process_steps: List[str]
    evidence_samples: List[str]
    metrics: List[str]
    frequency: str
    policy_ref: str
    status: str
    rationale: str
    assumptions: str
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ControlResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Control] = None

class ControlsResponse(BaseModel):
    success: bool
    message: str
    data: Optional[List[Control]] = None
