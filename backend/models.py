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