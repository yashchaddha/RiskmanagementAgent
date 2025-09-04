from fastapi import FastAPI, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from auth import router as auth_router, get_current_user
from agent import run_agent, get_finalized_risks_summary, GREETING_MESSAGE
from database import RiskDatabaseService, RiskProfileDatabaseService, ControlsDatabaseService
from models import Risk, GeneratedRisks, RiskResponse, FinalizedRisks, FinalizedRisksResponse, Control, ControlSelection
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

app = FastAPI(title="Risk Management Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[dict]] = []
    risk_context: Optional[Dict[str, Any]] = {}

class ChatResponse(BaseModel):
    response: str
    conversation_history: List[dict]
    risk_context: Dict[str, Any]

class GreetingRequest(BaseModel):
    user_name: Optional[str] = None

class GreetingResponse(BaseModel):
    greeting: str

class RiskSummaryResponse(BaseModel):
    summary: str

class SaveRisksRequest(BaseModel):
    risks: List[Risk]

class GetRisksResponse(BaseModel):
    success: bool
    message: str
    data: Optional[GeneratedRisks] = None

class FinalizeRisksRequest(BaseModel):
    risks: List[Risk]

@app.get("/")
def read_root():
    return {
        "message": "Risk Management Agent API",
        "version": "1.0.0",
        "description": "AI-powered risk assessment and compliance management platform"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Risk Management Agent"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user=Depends(get_current_user)):
    # Extract user data from current_user
    user_data = {
        "username": current_user.get("username", ""),
        "organization_name": current_user.get("organization_name", ""),
        "location": current_user.get("location", ""),
        "domain": current_user.get("domain", ""),
        "risks_applicable": current_user.get("risks_applicable", [])
    }
    
    # Sanitize incoming risk_context to avoid stale control popups
    incoming_ctx = request.risk_context or {}
    if isinstance(incoming_ctx, dict) and "generated_controls" in incoming_ctx:
        incoming_ctx = {k: v for k, v in incoming_ctx.items() if k != "generated_controls"}

    response, updated_history, updated_risk_context, updated_user_data = run_agent(
        request.message, 
        request.conversation_history, 
        incoming_ctx,
        user_data
    )
    
    return ChatResponse(
        response=response, 
        conversation_history=updated_history,
        risk_context=updated_risk_context
    )


@app.get("/risk-summary/finalized", response_model=RiskSummaryResponse)
async def get_finalized_risks_summary_endpoint(current_user=Depends(get_current_user)):
    """Generate a comprehensive summary based on finalized risks"""
    try:
        user_id = current_user.get("username", "")
        organization_name = current_user.get("organization_name", "")
        location = current_user.get("location", "")
        domain = current_user.get("domain", "")
        
        # Get finalized risks for the user
        result = await RiskDatabaseService.get_user_finalized_risks(user_id)
        
        if not result.success or not result.data:
            return RiskSummaryResponse(
                summary="No finalized risks found. Please finalize some risks first to generate a summary."
            )
        
        # Generate summary based on finalized risks
        summary = get_finalized_risks_summary(
            finalized_risks=result.data.risks,
            organization_name=organization_name,
            location=location,
            domain=domain
        )
        
        return RiskSummaryResponse(summary=summary)
        
    except Exception as e:
        return RiskSummaryResponse(
            summary=f"Error generating finalized risks summary: {str(e)}"
        )

@app.post("/risks/save", response_model=RiskResponse)
async def save_risks(request: SaveRisksRequest, current_user=Depends(get_current_user)):
    """Save generated risks to database"""
    user_id = current_user.get("username", "")
    organization_name = current_user.get("organization_name", "")
    location = current_user.get("location", "")
    domain = current_user.get("domain", "")
    
    result = await RiskDatabaseService.save_generated_risks(
        user_id=user_id,
        organization_name=organization_name,
        location=location,
        domain=domain,
        risks=request.risks
    )
    
    return result

@app.get("/user/preferences")
async def get_user_preferences(current_user=Depends(get_current_user)):
    """Return the user's risk profile preferences including likelihood and impact scales"""
    from database import RiskProfileDatabaseService
    # Default scales
    default_likelihood = ["Low", "Medium", "High", "Severe", "Critical"]
    default_impact = ["Low", "Medium", "High", "Severe", "Critical"]
    user_id = current_user.get("username", "")
    # Retrieve profiles synchronously
    pref_result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
    profiles = []
    if pref_result.success and pref_result.data:
        profiles = pref_result.data.get("profiles", []) or []
    # Use first profile for scales if available
    if profiles:
        first = profiles[0]
        likelihood = [lvl.get("title") for lvl in first.get("likelihoodScale", [])]
        impact = [lvl.get("title") for lvl in first.get("impactScale", [])]
    else:
        likelihood = default_likelihood
        impact = default_impact
    return {
        "success": True,
        "risks_applicable": current_user.get("risks_applicable", []),
        "risk_profiles_count": len(profiles),
        "likelihood": likelihood,
        "impact": impact
    }

class SelectionUpdateRequest(BaseModel):
    is_selected: bool

@app.put("/risks/{risk_index}/selection")
async def update_risk_selection(
    risk_index: int,
    selection: SelectionUpdateRequest,
    current_user=Depends(get_current_user)
):
    """Update risk selection status"""
    user_id = current_user.get("username", "")
    result = await RiskDatabaseService.update_risk_selection(user_id, risk_index, selection.is_selected)
    return result

@app.post("/risks/finalize", response_model=FinalizedRisksResponse)
async def finalize_risks(request: FinalizeRisksRequest, current_user=Depends(get_current_user)):
    """Finalize selected risks by saving them to finalized_risks collection"""
    try:
        user_id = current_user.get("username", "")
        organization_name = current_user.get("organization_name", "")
        location = current_user.get("location", "")
        domain = current_user.get("domain", "")
        
        result = await RiskDatabaseService.save_finalized_risks(
            user_id=user_id,
            organization_name=organization_name,
            location=location,
            domain=domain,
            selected_risks=request.risks
        )
        
        return result
    except Exception as e:
        return FinalizedRisksResponse(
            success=False,
            message=f"Error finalizing risks: {str(e)}",
            data=None
        )

@app.get("/risks/finalized", response_model=FinalizedRisksResponse)
async def get_finalized_risks(current_user=Depends(get_current_user)):
    """Get finalized risks for the current user"""
    try:
        user_id = current_user.get("username", "")
        result = await RiskDatabaseService.get_user_finalized_risks(user_id)
        return result
    except Exception as e:
        return FinalizedRisksResponse(
            success=False,
            message=f"Error retrieving finalized risks: {str(e)}",
            data=None
        )


@app.delete("/risks/finalized/index/{risk_index}", response_model=FinalizedRisksResponse)
async def delete_finalized_risk_by_index(risk_index: int, current_user=Depends(get_current_user)):
    """Delete a specific finalized risk by array index"""
    user_id = current_user.get("username", "")
    result = await RiskDatabaseService.delete_finalized_risk_by_index(user_id, risk_index)
    return result



@app.get("/user/risk-profiles/table")
async def get_user_risk_profiles_table(current_user=Depends(get_current_user)):
    """Get user's risk profiles formatted as a table"""
    try:
        user_id = current_user.get("username", "")
        result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
        
        if result.success:
            profiles = result.data.get("profiles", [])
            
            # Format profiles as table data
            table_data = []
            for profile in profiles:
                risk_type = profile.get("riskType", "")
                definition = profile.get("definition", "")
                likelihood_scale = profile.get("likelihoodScale", [])
                impact_scale = profile.get("impactScale", [])
                
                # Create table row
                table_row = {
                    "riskType": risk_type,
                    "definition": definition,
                    "likelihoodScale": likelihood_scale,
                    "impactScale": impact_scale,
                    "matrixSize": f"{len(likelihood_scale)}x{len(impact_scale)}"
                }
                table_data.append(table_row)
            
            return {
                "success": True,
                "tableData": table_data,
                "totalProfiles": len(profiles)
            }
        else:
            return {
                "success": False,
                "message": result.message,
                "tableData": [],
                "totalProfiles": 0
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving risk profiles: {str(e)}",
            "tableData": [],
            "totalProfiles": 0
                 }

class RiskProfileUpdateRequest(BaseModel):
    riskType: str
    definition: str
    likelihoodScale: list
    impactScale: list

class MatrixRecommendationRequest(BaseModel):
    matrix_size: str

class MatrixConfigurationRequest(BaseModel):
    matrix_size: str
    profiles: list

@app.put("/user/risk-profiles/update")
async def update_user_risk_profile(request: RiskProfileUpdateRequest, current_user=Depends(get_current_user)):
    """Update a specific risk profile for the user"""
    try:
        user_id = current_user.get("username", "")
        result = await RiskProfileDatabaseService.update_risk_profile(
            user_id=user_id,
            risk_type=request.riskType,
            likelihood_scale=request.likelihoodScale,
            impact_scale=request.impactScale
        )
        
        if result.success:
            return {
                "success": True,
                "message": f"Successfully updated {request.riskType} profile"
            }
        else:
            return {
                "success": False,
                "message": result.message
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error updating risk profile: {str(e)}"
        }

@app.post("/user/risk-profiles/matrix-recommendation")
async def create_matrix_recommendation(request: MatrixRecommendationRequest, current_user=Depends(get_current_user)):
    """Get preview data for a specific matrix size using LLM (no database save)"""
    try:
        matrix_size = request.matrix_size
        
        # Check if user already has finalized risks
        user_id = current_user.get("username", "")
        finalized = await RiskDatabaseService.get_user_finalized_risks(user_id)
        if finalized.success and finalized.data and finalized.data.risks:
            return {"success": False, "message": "You already have finalized risks. Cannot generate a new matrix recommendation."}
        # Validate matrix size
        if matrix_size not in ["3x3", "4x4", "5x5"]:
            return {"success": False, "message": "Invalid matrix size. Must be 3x3, 4x4, or 5x5"}

        # Get organization context from current user
        organization_name = current_user.get("organization_name", "the organization")
        location = current_user.get("location", "the current location")
        domain = current_user.get("domain", "the industry domain")
        
        # Generate matrix recommendation using LLM
        result = await RiskProfileDatabaseService.generate_matrix_recommendation_with_llm(
            matrix_size=matrix_size,
            organization_name=organization_name,
            location=location,
            domain=domain,
            user_id=user_id
        )
        
        if result.success:
            return {
                "success": True,
                "message": f"AI-generated {matrix_size} matrix recommendation created successfully for {organization_name}",
                "data": result.data
            }
        else:
            return {
                "success": False,
                "message": result.message
            }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error creating matrix recommendation: {str(e)}"
        }

@app.post("/user/risk-profiles/apply-matrix-recommendation")
async def apply_matrix_recommendation(request: MatrixRecommendationRequest, current_user=Depends(get_current_user)):
    """Apply matrix recommendation by replacing existing profiles"""
    try:
        user_id = current_user.get("username", "")
        matrix_size = request.matrix_size
        
        # Validate matrix size
        if matrix_size not in ["3x3", "4x4", "5x5"]:
            return {
                "success": False,
                "message": "Invalid matrix size. Must be 3x3, 4x4, or 5x5"
            }
        
        # Get organization context from current user
        organization_name = current_user.get("organization_name", "")
        location = current_user.get("location", "")
        domain = current_user.get("domain", "")
        
        result = await RiskProfileDatabaseService.apply_matrix_recommendation(
            user_id=user_id,
            matrix_size=matrix_size,
            organization_name=organization_name,
            location=location,
            domain=domain
        )
        
        if result.success:
            return {
                "success": True,
                "message": f"Successfully applied {matrix_size} matrix configuration. Your risk profiles have been permanently updated.",
                "data": result.data
            }
        else:
            return {
                "success": False,
                "message": result.message
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error applying matrix recommendation: {str(e)}"
        }

@app.post("/user/risk-profiles/apply-matrix-configuration")
async def apply_matrix_configuration(request: MatrixConfigurationRequest, current_user=Depends(get_current_user)):
    """Apply matrix configuration with custom profiles"""
    try:
        user_id = current_user.get("username", "")
        matrix_size = request.matrix_size
        profiles = request.profiles
        
        print(f"DEBUG: Received matrix configuration request - matrix_size: {matrix_size}, profiles count: {len(profiles) if profiles else 0}")
        
        # Validate matrix size
        if matrix_size not in ["3x3", "4x4", "5x5"]:
            return {
                "success": False,
                "message": "Invalid matrix size. Must be 3x3, 4x4, or 5x5"
            }
        
        result = await RiskProfileDatabaseService.apply_matrix_configuration(
            user_id=user_id,
            matrix_size=matrix_size,
            profiles=profiles
        )
        
        if result.success:
            return {
                "success": True,
                "message": f"Successfully applied {matrix_size} matrix configuration with your customizations.",
                "data": result.data
            }
        else:
            return {
                "success": False,
                "message": result.message
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error applying matrix configuration: {str(e)}"
        }

class RiskUpdateRequest(BaseModel):
    risk_index: int
    field: str
    value: str

@app.put("/risks/{risk_index}/update")
async def update_risk_field(
    risk_index: int,
    request: RiskUpdateRequest,
    current_user=Depends(get_current_user)
):
    """Update a specific field of a risk"""
    try:
        user_id = current_user.get("username", "")
        result = await RiskDatabaseService.update_risk_field(
            user_id, 
            risk_index, 
            request.field, 
            request.value
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "message": f"Error updating risk field: {str(e)}"
        }

class SaveControlsRequest(BaseModel):
    controls: List[Control]

@app.post("/controls/save")
async def save_controls(request: SaveControlsRequest, current_user=Depends(get_current_user)):
    """Save selected controls directly to the database using new Control model format"""
    try:
        user_id = current_user.get("username", "")
        
        if not request.controls:
            return {
                "success": False,
                "message": "No controls provided to save"
            }
        
        # Prepare controls with user context
        controls_to_save = []
        for control in request.controls:
            # Use new comprehensive Control model format
            control_dict = control.model_dump()
            control_dict["user_id"] = user_id
            controls_to_save.append(control_dict)
        
        # Save controls to database
        saved_ids = ControlsDatabaseService.save_controls(controls_to_save)

        # Index saved controls in Zilliz/Milvus
        try:
            from vector_index import ControlsVectorIndexService
            # Fetch the saved control documents by _id for embedding
            saved_controls = ControlsDatabaseService.get_controls_by_uids(user_id, saved_ids)
            ControlsVectorIndexService.upsert_controls(user_id, saved_controls)
        except Exception as e:
            print(f"Warning: Failed to index controls: {e}")

        return {
            "success": True,
            "message": f"Successfully saved {len(saved_ids)} controls to the database",
            "data": {
                "saved_count": len(saved_ids),
                "control_ids": saved_ids
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error saving controls: {str(e)}"
        }

@app.get("/controls/all")
async def get_all_controls(current_user=Depends(get_current_user)):
    """Get all controls for the current user"""
    try:
        user_id = current_user.get("username", "")
        controls = ControlsDatabaseService.get_all_user_controls(user_id)
        
        return {
            "success": True,
            "message": f"Retrieved {len(controls)} controls",
            "data": {
                "controls": controls,
                "total_count": len(controls)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving controls: {str(e)}"
        }

@app.get("/controls/status/{status}")
async def get_controls_by_status(status: str, current_user=Depends(get_current_user)):
    """Get controls filtered by implementation status"""
    try:
        user_id = current_user.get("username", "")
        controls = ControlsDatabaseService.get_controls_by_status(status, user_id)
        
        return {
            "success": True,
            "message": f"Retrieved {len(controls)} controls with status '{status}'",
            "data": {
                "controls": controls,
                "status": status,
                "total_count": len(controls)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving controls by status: {str(e)}"
        }

@app.get("/controls/search")
async def search_controls(q: str, current_user=Depends(get_current_user)):
    """Search controls by text query"""
    try:
        user_id = current_user.get("username", "")
        controls = ControlsDatabaseService.search_controls(q, user_id)
        
        return {
            "success": True,
            "message": f"Found {len(controls)} controls matching '{q}'",
            "data": {
                "controls": controls,
                "query": q,
                "total_count": len(controls)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error searching controls: {str(e)}"
        }

@app.get("/controls/risk/{risk_id}")
async def get_controls_by_risk(risk_id: str, current_user=Depends(get_current_user)):
    """Get controls linked to a specific risk"""
    try:
        user_id = current_user.get("username", "")
        controls = ControlsDatabaseService.get_controls_by_linked_risk(risk_id, user_id)
        
        return {
            "success": True,
            "message": f"Found {len(controls)} controls for risk '{risk_id}'",
            "data": {
                "controls": controls,
                "risk_id": risk_id,
                "total_count": len(controls)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving controls for risk: {str(e)}"
        }

class UpdateControlStatusRequest(BaseModel):
    control_id: str
    status: str

@app.put("/controls/status")
async def update_control_status(request: UpdateControlStatusRequest, current_user=Depends(get_current_user)):
    """Update the implementation status of a control"""
    try:
        user_id = current_user.get("username", "")
        
        success = ControlsDatabaseService.update_control(
            request.control_id, 
            user_id, 
            {"status": request.status}
        )
        
        if success:
            return {
                "success": True,
                "message": f"Successfully updated control {request.control_id} status to {request.status}"
            }
        else:
            return {
                "success": False,
                "message": f"Control {request.control_id} not found or no changes made"
            }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error updating control status: {str(e)}"
        }
