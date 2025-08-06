from fastapi import FastAPI, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from auth import router as auth_router, get_current_user
from agent import run_agent, get_risk_assessment_summary, get_finalized_risks_summary, GREETING_MESSAGE
from database import RiskDatabaseService, RiskProfileDatabaseService
from models import Risk, GeneratedRisks, RiskResponse, FinalizedRisks, FinalizedRisksResponse
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

class RiskSummaryRequest(BaseModel):
    conversation_history: List[dict]
    risk_context: Optional[Dict[str, Any]] = {}

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

@app.get("/test-auth")
async def test_auth(current_user=Depends(get_current_user)):
    return {
        "message": "Authentication successful",
        "user": {
            "username": current_user.get("username"),
            "organization_name": current_user.get("organization_name"),
            "location": current_user.get("location"),
            "domain": current_user.get("domain")
        }
    }

@app.get("/test-no-auth")
async def test_no_auth():
    return {"message": "No authentication required"}

@app.post("/greeting", response_model=GreetingResponse)
async def get_greeting_endpoint(request: GreetingRequest, current_user=Depends(get_current_user)):
    # Return the static greeting message
    return GreetingResponse(greeting=GREETING_MESSAGE)

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
    
    response, updated_history, updated_risk_context, updated_user_data = run_agent(
        request.message, 
        request.conversation_history, 
        request.risk_context,
        user_data
    )
    
    # Note: User preferences are now managed through risk profiles
    # Risk profile updates are handled separately through the risk profile system
    
    return ChatResponse(
        response=response, 
        conversation_history=updated_history,
        risk_context=updated_risk_context
    )

@app.post("/risk-summary", response_model=RiskSummaryResponse)
async def get_risk_summary(request: RiskSummaryRequest, current_user=Depends(get_current_user)):
    """Generate a summary of the risk assessment session"""
    summary = get_risk_assessment_summary(request.conversation_history, request.risk_context)
    return RiskSummaryResponse(summary=summary)

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

@app.get("/risks/user", response_model=RiskResponse)
async def get_user_risks(current_user=Depends(get_current_user)):
    """Get all risks for the current user"""
    user_id = current_user.get("username", "")
    result = await RiskDatabaseService.get_user_risks(user_id)
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

@app.get("/risk-categories")
async def get_risk_categories():
    """Get available risk categories for reference"""
    return {
        "risk_categories": [
            {
                "category": "Competition",
                "description": "Risks related to competitive pressures and market competition",
                "examples": ["New market entrants", "Price wars", "Product obsolescence", "Market share loss"]
            },
            {
                "category": "External",
                "description": "Risks arising from external factors beyond organizational control",
                "examples": ["Economic downturns", "Political changes", "Natural disasters", "Supply chain disruptions"]
            },
            {
                "category": "Financial",
                "description": "Risks related to financial performance and stability",
                "examples": ["Market volatility", "Credit risk", "Liquidity risk", "Currency fluctuations"]
            },
            {
                "category": "Innovation",
                "description": "Risks associated with innovation and technological advancement",
                "examples": ["R&D failures", "Technology adoption", "Innovation disruption", "Patent issues"]
            },
            {
                "category": "Internal",
                "description": "Risks arising from internal organizational factors",
                "examples": ["Employee turnover", "Management changes", "Internal conflicts", "Resource constraints"]
            },
            {
                "category": "Legal and Compliance",
                "description": "Risks of non-compliance with laws, regulations, and standards",
                "examples": ["Regulatory violations", "Data protection breaches", "Industry standards", "Contractual obligations"]
            },
            {
                "category": "Operational",
                "description": "Risks arising from internal processes, people, and systems",
                "examples": ["Process failures", "Human error", "System breakdowns", "Equipment malfunctions"]
            },
            {
                "category": "Project Management",
                "description": "Risks related to project execution and delivery",
                "examples": ["Scope creep", "Timeline delays", "Budget overruns", "Resource allocation"]
            },
            {
                "category": "Reputational",
                "description": "Risks to the organization's reputation and brand",
                "examples": ["Negative publicity", "Social media crises", "Stakeholder concerns", "Brand damage"]
            },
            {
                "category": "Safety",
                "description": "Risks related to workplace safety and health",
                "examples": ["Workplace accidents", "Health hazards", "Safety violations", "Emergency situations"]
            },
            {
                "category": "Strategic",
                "description": "Risks affecting the organization's ability to achieve its objectives",
                "examples": ["Strategic misalignment", "Market changes", "Business model disruption", "Merger integration"]
            },
            {
                "category": "Technology",
                "description": "Risks related to information technology and digital systems",
                "examples": ["Data breaches", "System failures", "Technology obsolescence", "Cybersecurity threats"]
            }
        ]
    }

@app.get("/compliance-frameworks")
async def get_compliance_frameworks():
    """Get common compliance frameworks and regulations"""
    return {
        "compliance_frameworks": [
            {
                "name": "SOX (Sarbanes-Oxley Act)",
                "description": "Financial reporting and corporate governance regulations",
                "applicable_to": ["Public companies", "Financial institutions"]
            },
            {
                "name": "GDPR (General Data Protection Regulation)",
                "description": "Data protection and privacy regulations for EU citizens",
                "applicable_to": ["Organizations handling EU data", "Global companies"]
            },
            {
                "name": "HIPAA (Health Insurance Portability and Accountability Act)",
                "description": "Healthcare data protection and privacy regulations",
                "applicable_to": ["Healthcare providers", "Health insurers", "Business associates"]
            },
            {
                "name": "PCI-DSS (Payment Card Industry Data Security Standard)",
                "description": "Security standards for payment card data",
                "applicable_to": ["Merchants", "Payment processors", "Financial institutions"]
            },
            {
                "name": "ISO 27001",
                "description": "Information security management system standard",
                "applicable_to": ["All organizations", "IT service providers"]
            },
            {
                "name": "SOC 2",
                "description": "Service Organization Control 2 for security, availability, and confidentiality",
                "applicable_to": ["Cloud service providers", "SaaS companies"]
            }
        ]
    }

@app.get("/admin/risks/all")
async def get_all_risks_with_users():
    """Admin endpoint to get all generated risks with user information"""
    try:
        result = await RiskDatabaseService.get_all_risks_with_users()
        return result
    except Exception as e:
        return RiskResponse(
            success=False,
            message=f"Error retrieving all risks: {str(e)}",
            data=None
        )

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


@app.get("/user/risk-profiles")
async def get_user_risk_profiles(current_user=Depends(get_current_user)):
    """Get user's risk profiles"""
    try:
        user_id = current_user.get("username", "")
        result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
        
        if result.success:
            return {
                "success": True,
                "profiles": result.data.get("profiles", [])
            }
        else:
            return {
                "success": False,
                "message": result.message,
                "profiles": []
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving risk profiles: {str(e)}",
            "profiles": []
        }

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
            domain=domain
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