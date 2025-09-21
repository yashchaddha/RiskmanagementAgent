import os
from datetime import datetime
from typing import List, Optional, Any, Dict
from pymongo import MongoClient
from bson import ObjectId
from uuid import uuid4
from vector_index import VectorIndexService, ControlVectorIndexService 
from models import Risk, GeneratedRisks, RiskResponse, FinalizedRisk, FinalizedRisks, FinalizedRisksResponse, Control, ControlResponse, ControlsResponse, AnnexAMapping

# Database result wrapper class
class DatabaseResult:
    def __init__(self, success: bool, message: str, data: Any = None):
        self.success = success
        self.message = message
        self.data = data

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
client = MongoClient(MONGODB_URI)
db = client.isoriskagent

# Collections
generated_risks_collection = db.generated_risks
finalized_risks_collection = db.finalized_risks
users_collection = db.users
risk_profiles_collection = db.risk_profiles
controls_collection = db.controls

def _to_str_id(obj):
    if isinstance(obj, dict):
        return {k: _to_str_id(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_str_id(x) for x in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

class RiskDatabaseService:
    @staticmethod
    async def save_generated_risks(
        user_id: str,
        organization_name: str,
        location: str,
        domain: str,
        risks: List[Risk]
    ) -> RiskResponse:
        try:
            # Verify user exists in the users collection
            user = users_collection.find_one({"username": user_id})
            if not user:
                return RiskResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Check if a document already exists for this user
            existing_doc = generated_risks_collection.find_one({"user_ref": user["_id"]})
            
            if existing_doc:
                # Update existing document by appending new risks
                new_risks = [
                    {
                        "description": risk.description,
                        "category": risk.category,
                        "likelihood": risk.likelihood,
                        "impact": risk.impact,
                        "treatment_strategy": risk.treatment_strategy,
                        "is_selected": risk.is_selected,
                        "asset_value": risk.asset_value,
                        "department": risk.department,
                        "risk_owner": risk.risk_owner,
                        "security_impact": risk.security_impact,
                        "target_date": risk.target_date,
                        "risk_progress": risk.risk_progress,
                        "residual_exposure": risk.residual_exposure,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    for risk in risks
                ]
                
                # Append new risks to existing risks array
                # Use .get() to handle cases where existing document might not have "risks" field
                existing_risks = existing_doc.get("risks", [])
                updated_risks = existing_risks + new_risks
                total_risks = len(updated_risks)
                selected_risks = sum(1 for risk in updated_risks if risk["is_selected"])
                
                # Update the existing document
                result = generated_risks_collection.update_one(
                    {"_id": existing_doc["_id"]},
                    {
                        "$set": {
                            "risks": updated_risks,
                            "total_risks": total_risks,
                            "selected_risks": selected_risks,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    # Get the updated document
                    updated_doc = generated_risks_collection.find_one({"_id": existing_doc["_id"]})
                    
                    # Convert to GeneratedRisks model
                    generated_risks = GeneratedRisks(
                        id=str(updated_doc["_id"]),
                        user_id=updated_doc["user_id"],
                        organization_name=updated_doc["organization_name"],
                        location=updated_doc["location"],
                        domain=updated_doc["domain"],
                        risks=[
                            Risk(
                                id=str(risk.get("_id", "")),
                                description=risk["description"],
                                category=risk["category"],
                                likelihood=risk["likelihood"],
                                impact=risk["impact"],
                                treatment_strategy=risk["treatment_strategy"],
                                is_selected=risk["is_selected"],
                                asset_value=risk.get("asset_value"),
                                department=risk.get("department"),
                                risk_owner=risk.get("risk_owner"),
                                security_impact=risk.get("security_impact"),
                                target_date=risk.get("target_date"),
                                risk_progress=risk.get("risk_progress", "Identified"),
                                residual_exposure=risk.get("residual_exposure"),
                                created_at=risk["created_at"],
                                updated_at=risk["updated_at"]
                            )
                            for risk in updated_doc["risks"]
                        ],
                        total_risks=updated_doc["total_risks"],
                        selected_risks=updated_doc["selected_risks"],
                        created_at=updated_doc["created_at"],
                        updated_at=updated_doc["updated_at"]
                    )
                    
                    return RiskResponse(
                        success=True,
                        message=f"Risks appended successfully. Total risks: {total_risks}",
                        data=generated_risks
                    )
                else:
                    return RiskResponse(
                        success=False,
                        message="Failed to update existing risks document",
                        data=None
                    )
            else:
                # Create new document if none exists
                selected_risks = sum(1 for risk in risks if risk.is_selected)
                
                # Create the document with user reference
                risk_document = {
                    "user_id": user_id,
                    "user_ref": user["_id"],  # Reference to the user document
                    "organization_name": organization_name,
                    "location": location,
                    "domain": domain,
                "risks": [
                        {
                            "_id": ObjectId(),
                            "description": risk.description,
                            "category": risk.category,
                            "likelihood": risk.likelihood,
                            "impact": risk.impact,
                            "treatment_strategy": risk.treatment_strategy,
                            "is_selected": risk.is_selected,
                            "asset_value": risk.asset_value,
                            "department": risk.department,
                            "risk_owner": risk.risk_owner,
                            "security_impact": risk.security_impact,
                            "target_date": risk.target_date,
                            "risk_progress": risk.risk_progress,
                            "residual_exposure": risk.residual_exposure,
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                        for risk in risks
                    ],
                    "total_risks": len(risks),
                    "selected_risks": selected_risks,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                
                # Insert into database
                result = generated_risks_collection.insert_one(risk_document)
                
                # Get the inserted document
                inserted_doc = generated_risks_collection.find_one({"_id": result.inserted_id})
                
                # Convert to GeneratedRisks model
                generated_risks = GeneratedRisks(
                    id=str(inserted_doc["_id"]),
                    user_id=inserted_doc["user_id"],
                    organization_name=inserted_doc["organization_name"],
                    location=inserted_doc["location"],
                    domain=inserted_doc["domain"],
                    risks=[
                        Risk(
                            id=str(risk.get("_id", "")),
                            description=risk["description"],
                            category=risk["category"],
                            likelihood=risk["likelihood"],
                            impact=risk["impact"],
                            treatment_strategy=risk["treatment_strategy"],
                            is_selected=risk["is_selected"],
                            asset_value=risk.get("asset_value"),
                            department=risk.get("department"),
                            risk_owner=risk.get("risk_owner"),
                            security_impact=risk.get("security_impact"),
                            target_date=risk.get("target_date"),
                            risk_progress=risk.get("risk_progress", "Identified"),
                            residual_exposure=risk.get("residual_exposure"),
                            created_at=risk["created_at"],
                            updated_at=risk["updated_at"]
                        )
                        for risk in inserted_doc["risks"]
                    ],
                    total_risks=inserted_doc["total_risks"],
                    selected_risks=inserted_doc["selected_risks"],
                    created_at=inserted_doc["created_at"],
                    updated_at=inserted_doc["updated_at"]
                )
                
                return RiskResponse(
                    success=True,
                    message="Risks saved successfully",
                    data=generated_risks
                )
            
        except Exception as e:
            return RiskResponse(
                success=False,
                message=f"Error saving risks: {str(e)}",
                data=None
            )
    
    
    @staticmethod
    async def update_risk_selection(user_id: str, risk_index: int, is_selected: bool) -> RiskResponse:
        try:
            # Find the user's document first
            user = users_collection.find_one({"username": user_id})
            if not user:
                return RiskResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find the user's generated risks document
            risk_doc = generated_risks_collection.find_one({"user_ref": user["_id"]})
            if not risk_doc:
                return RiskResponse(
                    success=False,
                    message="No generated risks found for this user",
                    data=None
                )
            
            # Check if the risk index is valid
            risks_array = risk_doc.get("risks", [])
            if risk_index >= len(risks_array):
                return RiskResponse(
                    success=False,
                    message="Invalid risk index",
                    data=None
                )
            
            # Update the specific risk's selection status
            result = generated_risks_collection.update_one(
                {"_id": risk_doc["_id"]},
                {
                    "$set": {
                        f"risks.{risk_index}.is_selected": is_selected,
                        f"risks.{risk_index}.updated_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                # Also update the selected_risks count
                updated_doc = generated_risks_collection.find_one({"_id": risk_doc["_id"]})
                selected_count = sum(1 for risk in updated_doc["risks"] if risk["is_selected"])
                
                generated_risks_collection.update_one(
                    {"_id": risk_doc["_id"]},
                    {
                        "$set": {
                            "selected_risks": selected_count
                        }
                    }
                )
                
                return RiskResponse(
                    success=True,
                    message="Risk selection updated successfully",
                    data=None
                )
            else:
                return RiskResponse(
                    success=False,
                    message="Risk not found or no changes made",
                    data=None
                )
                
        except Exception as e:
            return RiskResponse(
                success=False,
                message=f"Error updating risk selection: {str(e)}",
                data=None
            )
    
    
    @staticmethod
    async def save_finalized_risks(
        user_id: str,
        organization_name: str,
        location: str,
        domain: str,
        selected_risks: List[Risk]
    ) -> FinalizedRisksResponse:
        """Save selected risks as finalized risks"""
        try:
            print(f"DEBUG: save_finalized_risks called with user_id={user_id}")
            print(f"DEBUG: selected_risks type: {type(selected_risks)}")
            print(f"DEBUG: selected_risks length: {len(selected_risks) if selected_risks else 'None'}")
            
            # Verify user exists in the users collection
            user = users_collection.find_one({"username": user_id})
            if not user:
                return FinalizedRisksResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Filter only selected risks
            finalized_risks = [risk for risk in selected_risks if risk.is_selected]
            print(f"DEBUG: finalized_risks length: {len(finalized_risks)}")
            
            if not finalized_risks:
                return FinalizedRisksResponse(
                    success=False,
                    message="No risks selected for finalization",
                    data=None
                )
            
            print(f"DEBUG: About to check existing document for user._id: {user.get('_id')}")
            # Check if a finalized risks document already exists for this user
            existing_doc = finalized_risks_collection.find_one({"user_ref": user["_id"]})
            
            if existing_doc:
                # Update existing document by appending new finalized risks
                new_finalized_risks = [
                    {
                        "_id": ObjectId(),
                        "description": risk.description,
                        "category": risk.category,
                        "likelihood": risk.likelihood,
                        "impact": risk.impact,
                        "treatment_strategy": risk.treatment_strategy,
                        "asset_value": risk.asset_value,
                        "department": risk.department,
                        "risk_owner": risk.risk_owner,
                        "security_impact": risk.security_impact,
                        "target_date": risk.target_date,
                        "risk_progress": risk.risk_progress,
                        "residual_exposure": risk.residual_exposure,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    for risk in finalized_risks
                ]
                
                # Append new finalized risks to existing risks array
                # Use .get() to handle cases where existing document might not have "risks" field
                existing_risks = existing_doc.get("risks", [])
                updated_risks = existing_risks + new_finalized_risks
                total_risks = len(updated_risks)
                
                print(f"DEBUG: existing_risks length: {len(existing_risks)}")
                print(f"DEBUG: new_finalized_risks length: {len(new_finalized_risks)}")
                print(f"DEBUG: updated_risks length: {len(updated_risks)}")
                
                # Update the existing document
                result = finalized_risks_collection.update_one(
                    {"_id": existing_doc["_id"]},
                    {
                        "$set": {
                            "risks": updated_risks,
                            "total_risks": total_risks,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    # Get the updated document
                    updated_doc = finalized_risks_collection.find_one({"_id": existing_doc["_id"]})
                    
                    # Convert to FinalizedRisks model
                    finalized_risks_model = FinalizedRisks(
                        id=str(updated_doc["_id"]),
                        user_id=updated_doc["user_id"],
                        organization_name=updated_doc["organization_name"],
                        location=updated_doc["location"],
                        domain=updated_doc["domain"],
                        risks=[
                            FinalizedRisk(
                                id=str(risk.get("_id", "")),
                                description=risk["description"],
                                category=risk["category"],
                                likelihood=risk["likelihood"],
                                impact=risk["impact"],
                                treatment_strategy=risk["treatment_strategy"],
                                asset_value=risk.get("asset_value"),
                                department=risk.get("department"),
                                risk_owner=risk.get("risk_owner"),
                                security_impact=risk.get("security_impact"),
                                target_date=risk.get("target_date"),
                                risk_progress=risk.get("risk_progress", "Identified"),
                                residual_exposure=risk.get("residual_exposure"),
                                created_at=risk["created_at"],
                                updated_at=risk["updated_at"]
                            )
                            for risk in updated_doc["risks"]
                        ],
                        total_risks=updated_doc["total_risks"],
                        created_at=updated_doc["created_at"],
                        updated_at=updated_doc["updated_at"]
                    )

                    # Update the vector index
                    # Use the newly appended risks from the database for vector indexing
                    risks_dicts = new_finalized_risks
                    print(f"DEBUG: About to call VectorIndexService.upsert_finalized_risks")
                    print(f"DEBUG: risks_dicts type: {type(risks_dicts)}")
                    print(f"DEBUG: risks_dicts length: {len(risks_dicts) if risks_dicts else 'None'}")
                    if risks_dicts:
                        print(f"DEBUG: First risk dict keys: {list(risks_dicts[0].keys()) if risks_dicts[0] else 'No first item'}")
                    
                    VectorIndexService.upsert_finalized_risks(
                        user_id=user_id,
                        organization_name=organization_name,
                        location=location,
                        domain=domain,
                        risks=risks_dicts
                    )

                    return FinalizedRisksResponse(
                        success=True,
                        message=f"Successfully finalized {len(finalized_risks)} risks. Total finalized risks: {total_risks}",
                        data=finalized_risks_model
                    )
                else:
                    return FinalizedRisksResponse(
                        success=False,
                        message="Failed to update existing finalized risks document",
                        data=None
                    )
            else:
                # Create new document if none exists
                # Create the finalized risks document
                finalized_document = {
                    "user_id": user_id,
                    "user_ref": user["_id"],  # Reference to the user document
                    "organization_name": organization_name,
                    "location": location,
                    "domain": domain,
                    "risks": [
                        {
                            "_id": ObjectId(),
                            "description": risk.description,
                            "category": risk.category,
                            "likelihood": risk.likelihood,
                            "impact": risk.impact,
                            "treatment_strategy": risk.treatment_strategy,
                            "asset_value": risk.asset_value,
                            "department": risk.department,
                            "risk_owner": risk.risk_owner,
                            "security_impact": risk.security_impact,
                            "target_date": risk.target_date,
                            "risk_progress": risk.risk_progress,
                            "residual_exposure": risk.residual_exposure,
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                        for risk in finalized_risks
                    ],
                    "total_risks": len(finalized_risks),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                
                # Insert into database
                result = finalized_risks_collection.insert_one(finalized_document)
                
                # Get the inserted document
                inserted_doc = finalized_risks_collection.find_one({"_id": result.inserted_id})
                
                # Convert to FinalizedRisks model
                finalized_risks_model = FinalizedRisks(
                    id=str(inserted_doc["_id"]),
                    user_id=inserted_doc["user_id"],
                    organization_name=inserted_doc["organization_name"],
                    location=inserted_doc["location"],
                    domain=inserted_doc["domain"],
                    risks=[
                        FinalizedRisk(
                            id=str(risk.get("_id", "")),
                            description=risk["description"],
                            category=risk["category"],
                            likelihood=risk["likelihood"],
                            impact=risk["impact"],
                            treatment_strategy=risk["treatment_strategy"],
                            asset_value=risk.get("asset_value"),
                            department=risk.get("department"),
                            risk_owner=risk.get("risk_owner"),
                            security_impact=risk.get("security_impact"),
                            target_date=risk.get("target_date"),
                            risk_progress=risk.get("risk_progress", "Identified"),
                            residual_exposure=risk.get("residual_exposure"),
                            created_at=risk["created_at"],
                            updated_at=risk["updated_at"]
                        )
                        for risk in inserted_doc["risks"]
                    ],
                    total_risks=inserted_doc["total_risks"],
                    created_at=inserted_doc["created_at"],
                    updated_at=inserted_doc["updated_at"]
                )

                # Convert Risk objects to dictionaries for vector service
                # Use the risks that were just inserted into the database
                risks_dicts = inserted_doc["risks"]
                print(f"DEBUG: About to call VectorIndexService.upsert_finalized_risks (new document)")
                print(f"DEBUG: risks_dicts type: {type(risks_dicts)}")
                print(f"DEBUG: risks_dicts length: {len(risks_dicts) if risks_dicts else 'None'}")
                if risks_dicts:
                    print(f"DEBUG: First risk dict keys: {list(risks_dicts[0].keys()) if risks_dicts[0] else 'No first item'}")
                
                VectorIndexService.upsert_finalized_risks(
                    user_id=user_id,
                    organization_name=organization_name,
                    location=location,
                    domain=domain,
                    risks=risks_dicts
                )

                return FinalizedRisksResponse(
                    success=True,
                    message=f"Successfully finalized {len(finalized_risks)} risks",
                    data=finalized_risks_model
                )
            
        except Exception as e:
            print(f"DEBUG: Exception in save_finalized_risks: {str(e)}")
            print(f"DEBUG: Exception type: {type(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return FinalizedRisksResponse(
                success=False,
                message=f"Error finalizing risks: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def get_user_finalized_risks(user_id: str) -> FinalizedRisksResponse:
        """Get finalized risks for a user"""
        try:
            # Verify user exists first
            user = users_collection.find_one({"username": user_id})
            if not user:
                return FinalizedRisksResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find the user's finalized risks document (only one per user now)
            finalized_doc = finalized_risks_collection.find_one({"user_ref": user["_id"]})
            
            if not finalized_doc:
                return FinalizedRisksResponse(
                    success=True,
                    message="No finalized risks found for this user",
                    data=None
                )
            
            # Convert to FinalizedRisks model
            risks = [
                FinalizedRisk(
                    id=str(risk.get("_id", "")),
                    description=risk["description"],
                    category=risk["category"],
                    likelihood=risk["likelihood"],
                    impact=risk["impact"],
                    treatment_strategy=risk["treatment_strategy"],
                    asset_value=risk.get("asset_value"),
                    department=risk.get("department"),
                    risk_owner=risk.get("risk_owner"),
                    security_impact=risk.get("security_impact"),
                    target_date=risk.get("target_date"),
                    risk_progress=risk.get("risk_progress", "Identified"),
                    residual_exposure=risk.get("residual_exposure"),
                    created_at=risk["created_at"],
                    updated_at=risk["updated_at"]
                )
                for risk in finalized_doc["risks"]
            ]
            
            finalized_risks = FinalizedRisks(
                id=str(finalized_doc["_id"]),
                user_id=finalized_doc["user_id"],
                organization_name=finalized_doc["organization_name"],
                location=finalized_doc["location"],
                domain=finalized_doc["domain"],
                risks=risks,
                total_risks=finalized_doc["total_risks"],
                created_at=finalized_doc["created_at"],
                updated_at=finalized_doc["updated_at"]
            )
            
            return FinalizedRisksResponse(
                success=True,
                message=f"Found {len(risks)} finalized risks for this user",
                data=finalized_risks
            )
            
        except Exception as e:
            return FinalizedRisksResponse(
                success=False,
                message=f"Error retrieving finalized risks: {str(e)}",
                data=None
            )
    

    @staticmethod
    async def delete_finalized_risk_by_index(user_id: str, risk_index: int) -> FinalizedRisksResponse:
        """Delete a specific finalized risk by its array index"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return FinalizedRisksResponse(success=False, message=f"User {user_id} not found", data=None)
            
            # Find user's finalized risks document
            existing_doc = finalized_risks_collection.find_one({"user_ref": user["_id"]})
            if not existing_doc:
                return FinalizedRisksResponse(success=False, message="No finalized risks found for user", data=None)
            
            # Get risks array and validate index
            risks = existing_doc.get("risks", [])
            if risk_index < 0 or risk_index >= len(risks):
                return FinalizedRisksResponse(success=False, message=f"Invalid risk index {risk_index}. Available indices: 0-{len(risks)-1}", data=None)
            
            print(f"DEBUG DELETE BY INDEX: Deleting risk at index {risk_index} from {len(risks)} total risks")
            
            # Remove risk at the specified index
            risks.pop(risk_index)
            new_total = len(risks)
            
            if new_total <= 0:
                # No risks remain; delete the entire finalized_risks document
                print(f"DEBUG DELETE BY INDEX: No risks remaining, deleting entire document for user {user_id}")
                delete_result = finalized_risks_collection.delete_one({"_id": existing_doc["_id"]})
                print(f"DEBUG DELETE BY INDEX: Document deletion result: {delete_result.deleted_count} document(s) deleted")
                
                # Return empty FinalizedRisks model to indicate all risks deleted
                empty_finalized_model = FinalizedRisks(
                    id="",
                    user_id=existing_doc.get("user_id", ""),
                    organization_name=existing_doc.get("organization_name", ""),
                    location=existing_doc.get("location", ""),
                    domain=existing_doc.get("domain", ""),
                    risks=[],
                    total_risks=0,
                    created_at=existing_doc.get("created_at"),
                    updated_at=datetime.utcnow()
                )
                return FinalizedRisksResponse(
                    success=True,
                    message="Last finalized risk deleted; all finalized risks removed.",
                    data=empty_finalized_model
                )
            
            # Update document with remaining risks
            result = finalized_risks_collection.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": {"risks": risks, "total_risks": new_total, "updated_at": datetime.utcnow()}}
            )
            
            if result.modified_count == 0:
                return FinalizedRisksResponse(success=False, message="Failed to delete risk", data=None)
            
            # Retrieve updated document
            updated_doc = finalized_risks_collection.find_one({"_id": existing_doc["_id"]})
            
            # Convert remaining risks to FinalizedRisk models
            updated_risks = [
                FinalizedRisk(
                    id=str(r.get("_id", "")),
                    description=r["description"],
                    category=r["category"],
                    likelihood=r["likelihood"],
                    impact=r["impact"],
                    treatment_strategy=r["treatment_strategy"],
                    asset_value=r.get("asset_value"),
                    department=r.get("department"),
                    risk_owner=r.get("risk_owner"),
                    security_impact=r.get("security_impact"),
                    target_date=r.get("target_date"),
                    risk_progress=r.get("risk_progress", "Identified"),
                    residual_exposure=r.get("residual_exposure"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in updated_doc.get("risks", [])
            ]
            
            finalized_model = FinalizedRisks(
                id=str(updated_doc["_id"]),
                user_id=updated_doc.get("user_id", ""),
                organization_name=updated_doc.get("organization_name", ""),
                location=updated_doc.get("location", ""),
                domain=updated_doc.get("domain", ""),
                risks=updated_risks,
                total_risks=updated_doc.get("total_risks", 0),
                created_at=updated_doc.get("created_at"),
                updated_at=updated_doc.get("updated_at")
            )
            
            return FinalizedRisksResponse(success=True, message=f"Risk at index {risk_index} deleted successfully", data=finalized_model)
            
        except Exception as e:
            return FinalizedRisksResponse(success=False, message=f"Error deleting risk by index: {str(e)}", data=None)


    @staticmethod
    async def update_risk_field(
        user_id: str,
        risk_index: int,
        field: str,
        value: str
    ) -> dict:
        """Update a specific field of a risk"""
        try:
            # Verify user exists in the users collection
            user = users_collection.find_one({"username": user_id})
            if not user:
                return {
                    "success": False,
                    "message": f"User {user_id} not found in database"
                }
            
            # Find the user's generated risks document
            generated_doc = generated_risks_collection.find_one({"user_ref": user["_id"]})
            
            if not generated_doc:
                return {
                    "success": False,
                    "message": f"No generated risks found for user {user_id}"
                }
            
            # Check if risk_index is valid
            if risk_index < 0 or risk_index >= len(generated_doc["risks"]):
                return {
                    "success": False,
                    "message": f"Invalid risk index {risk_index}"
                }
            
            # Validate field name
            valid_fields = [
                "description", "category", "likelihood", "impact", "treatment_strategy",
                "asset_value", "department", "risk_owner", "security_impact", 
                "target_date", "risk_progress", "residual_exposure"
            ]
            if field not in valid_fields:
                return {
                    "success": False,
                    "message": f"Invalid field '{field}'. Valid fields are: {', '.join(valid_fields)}"
                }
            
            # Update the specific field
            update_path = f"risks.{risk_index}.{field}"
            result = generated_risks_collection.update_one(
                {"_id": generated_doc["_id"]},
                {
                    "$set": {
                        update_path: value,
                        f"risks.{risk_index}.updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                return {
                    "success": True,
                    "message": f"Successfully updated {field} for risk {risk_index}",
                    "field": field,
                    "value": value
                }
            else:
                return {
                    "success": False,
                    "message": f"No changes made to risk {risk_index}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating risk field: {str(e)}"
            }

class RiskProfileDatabaseService:
    """Service for managing user risk profiles"""
    
    @staticmethod
    async def create_default_risk_profiles(user_id: str) -> DatabaseResult:
        """Create default risk profiles for a new user"""
        try:
            # Default risk profiles data
            default_profiles = [
                {
                    "userId": user_id,
                    "riskType": "Strategic Risk",
                    "definition": "Risks associated with a company's long-term business strategy, market position, competitive advantage, or the effectiveness of its strategic decisions. This includes risks related to market shifts, innovation, mergers & acquisitions, or failing to adapt to a changing environment.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "Strategic pivot fundamentally alters market, but no negative impact."},
                        {"level": 2, "title": "Unlikely", "description": "Minor miscalculation in market trends; easily correctable."},
                        {"level": 3, "title": "Moderate", "description": "Strategy faces moderate market resistance; slight competitive erosion."},
                        {"level": 4, "title": "Likely", "description": "Significant competitive pressure; market share decline; strategy clearly underperforms."},
                        {"level": 5, "title": "Almost Certain", "description": "Strategy is failing; company losing competitive edge; business model becoming obsolete."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Minor deviation from strategic goals; easily course-corrected; negligible impact on market position."},
                        {"level": 2, "title": "Minor", "description": "Slight loss of competitive advantage; minor delay in strategic objectives; <5% revenue impact."},
                        {"level": 3, "title": "Moderate", "description": "Noticeable decline in market share; delay in achieving key strategic milestones; 5-15% revenue impact; moderate reputational damage."},
                        {"level": 4, "title": "Major", "description": "Significant threat to long-term viability or market leadership; inability to achieve core strategic objectives; 15-30% revenue impact; major reputational damage; significant talent loss."},
                        {"level": 5, "title": "Catastrophic", "description": "Strategic failure leading to business model collapse, company dissolution, or inability to compete effectively; >30% revenue impact; severe reputational damage; mass talent exodus."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Operational Risk",
                    "definition": "Risks arising from inadequate or failed internal processes, people, and systems, or from external events that disrupt day-to-day operations. This includes technology failures, human error, supply chain disruptions, process inefficiencies, or fraud.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "Process highly robust; almost no chance of failure or human error."},
                        {"level": 2, "title": "Unlikely", "description": "Minor, isolated operational glitch possible."},
                        {"level": 3, "title": "Moderate", "description": "Occasional process inefficiencies or system minor errors expected."},
                        {"level": 4, "title": "Likely", "description": "Frequent minor disruptions or a single significant disruption probable."},
                        {"level": 5, "title": "Almost Certain", "description": "Systemic failures or constant operational inefficiencies are the norm."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Minimal disruption (<1 hour); minor inconvenience; easily resolved; negligible financial loss (<$1,000)."},
                        {"level": 2, "title": "Minor", "description": "Short-term disruption (1-4 hours); minor impact on productivity; some customer inconvenience; financial loss ($1,000 - $10,000)."},
                        {"level": 3, "title": "Moderate", "description": "Significant disruption (4-24 hours); noticeable impact on service delivery; moderate productivity loss; financial loss ($10,000 - $100,000); limited reputational damage."},
                        {"level": 4, "title": "Major", "description": "Extended disruption (>24 hours to several days); critical impact on core operations; severe loss of productivity; significant financial loss ($100,000 - $1,000,000); major reputational damage; potential regulatory scrutiny."},
                        {"level": 5, "title": "Catastrophic", "description": "Prolonged or complete operational shutdown; inability to deliver critical services; massive financial loss (>$1,000,000); severe reputational damage; potential business failure; significant regulatory and legal action."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Financial Risk",
                    "definition": "Risks associated with a company's financial health, market fluctuations, or poor financial management. This encompasses market risk (interest rates, currency, stock prices), credit risk (defaults), liquidity risk (cash flow), and investment risk.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "Financial markets extremely stable; almost no chance of adverse movement."},
                        {"level": 2, "title": "Unlikely", "description": "Minor market fluctuations or isolated credit issues possible."},
                        {"level": 3, "title": "Moderate", "description": "Anticipated market volatility or some credit defaults in portfolio."},
                        {"level": 4, "title": "Likely", "description": "Significant market downturn probable; increasing number of credit defaults; tightening liquidity."},
                        {"level": 5, "title": "Almost Certain", "description": "Severe financial crisis, recession, or widespread defaults are expected."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Negligible financial loss (e.g., <0.1% of annual revenue); minor budget overrun easily absorbed."},
                        {"level": 2, "title": "Minor", "description": "Small financial loss (e.g., 0.1-1% of annual revenue); requires minor budget reallocation; no impact on profitability."},
                        {"level": 3, "title": "Moderate", "description": "Noticeable financial loss (e.g., 1-5% of annual revenue); impacts quarterly earnings; requires management attention; may affect short-term cash flow."},
                        {"level": 4, "title": "Major", "description": "Substantial financial loss (e.g., 5-15% of annual revenue); significant impact on profitability and cash flow; may require external financing; potential credit rating downgrade."},
                        {"level": 5, "title": "Catastrophic", "description": "Severe financial loss (e.g., >15% of annual revenue); threat to solvency or going concern; potential for bankruptcy; major credit rating downgrade; inability to meet obligations."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Compliance Risk",
                    "definition": "Risks of failing to adhere to laws, regulations, industry standards, ethical guidelines, or internal policies. Consequences can include fines, legal penalties, sanctions, loss of license, or reputational damage.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "All processes robustly designed for compliance; almost no chance of violation."},
                        {"level": 2, "title": "Unlikely", "description": "Minor, isolated non-compliance incident possible."},
                        {"level": 3, "title": "Moderate", "description": "Some areas of potential non-compliance identified; minor breaches might occur."},
                        {"level": 4, "title": "Likely", "description": "Several non-compliance issues probable; high chance of a significant breach occurring."},
                        {"level": 5, "title": "Almost Certain", "description": "Widespread non-compliance or known, ongoing violations."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Very minor internal policy breach; no external consequence; no financial penalty."},
                        {"level": 2, "title": "Minor", "description": "Minor policy or regulatory breach; small administrative fine (<$10,000); internal warning; no public exposure."},
                        {"level": 3, "title": "Moderate", "description": "Noticeable regulatory violation; moderate fine ($10,000 - $100,000); public reprimand; minor legal action; some reputational damage."},
                        {"level": 4, "title": "Major", "description": "Significant regulatory breach; substantial fines ($100,000 - $1,000,000+); civil lawsuits; temporary suspension of license; major reputational damage; C-suite involvement."},
                        {"level": 5, "title": "Catastrophic", "description": "Severe violation leading to massive fines (>$1,000,000+), criminal charges, permanent loss of license/operating ability, forced divestiture, class-action lawsuits, irreversible reputational damage, executive arrests."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Reputational Risk",
                    "definition": "The potential for negative public perception, brand damage, or loss of trust from stakeholders (customers, investors, employees, regulators) due to various factors like product failures, unethical behavior, data breaches, or poor customer service.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "Impeccable public image; virtually no chance of adverse publicity."},
                        {"level": 2, "title": "Unlikely", "description": "Minor negative customer feedback or isolated public complaint."},
                        {"level": 3, "title": "Moderate", "description": "Localized negative media coverage or social media buzz."},
                        {"level": 4, "title": "Likely", "description": "Significant negative media coverage or widespread negative social media campaign probable."},
                        {"level": 5, "title": "Almost Certain", "description": "Crisis situation with sustained, overwhelmingly negative public opinion and media scrutiny."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Isolated negative comment; no change in public perception."},
                        {"level": 2, "title": "Minor", "description": "Localized negative publicity; minor erosion of trust among a small segment; no measurable financial impact."},
                        {"level": 3, "title": "Moderate", "description": "Regional or national negative media coverage; noticeable decline in customer loyalty/sales (e.g., 1-5% decline); moderate difficulty in attracting talent."},
                        {"level": 4, "title": "Major", "description": "Widespread negative media coverage and public outcry; significant loss of customer base/sales (e.g., 5-15% decline); investor concern; major difficulty in talent acquisition/retention; senior management changes."},
                        {"level": 5, "title": "Catastrophic", "description": "Irreversible brand damage; complete loss of public trust; massive decline in revenue and market share (>15% decline); significant stock price drop; inability to attract or retain talent; existential threat to the organization."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Health and Safety Risk",
                    "definition": "Risks related to the well-being of employees, customers, or the public, arising from workplace conditions, processes, or products.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "All safety protocols meticulously followed; virtually no chance of an incident."},
                        {"level": 2, "title": "Unlikely", "description": "Minor near-misses occasionally occur; low probability of actual injury."},
                        {"level": 3, "title": "Moderate", "description": "Small incidents or minor injuries occur occasionally; some non-compliance with safety procedures."},
                        {"level": 4, "title": "Likely", "description": "Regular minor injuries or a high probability of a single major injury occurring."},
                        {"level": 5, "title": "Almost Certain", "description": "Frequent injuries or high probability of severe injuries/fatalities."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "No injury; minor first-aid required; no lost time."},
                        {"level": 2, "title": "Minor", "description": "Minor injury requiring medical attention; no lost time or <1 day lost time; minor discomfort."},
                        {"level": 3, "title": "Moderate", "description": "Moderate injury requiring professional medical treatment; 1-3 days lost time; some temporary disability."},
                        {"level": 4, "title": "Major", "description": "Severe injury requiring hospitalization; >3 days lost time; permanent partial disability; significant regulatory investigation; substantial fines."},
                        {"level": 5, "title": "Catastrophic", "description": "Fatality, multiple fatalities, or severe permanent debilitating injury; major regulatory investigation and significant fines; legal prosecution; severe reputational damage."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                },
                {
                    "userId": user_id,
                    "riskType": "Environmental Risk",
                    "definition": "Risks related to environmental damage, pollution, non-compliance with environmental regulations, or the impact of natural disasters and climate change on operations or assets.",
                    "likelihoodScale": [
                        {"level": 1, "title": "Rare", "description": "Environmentally friendly operations; virtually no chance of harmful emissions or spills."},
                        {"level": 2, "title": "Unlikely", "description": "Minor, isolated environmental incident possible."},
                        {"level": 3, "title": "Moderate", "description": "Occasional minor environmental breaches or small-scale incidents expected."},
                        {"level": 4, "title": "Likely", "description": "High probability of a significant environmental incident (e.g., moderate spill, air quality breach)."},
                        {"level": 5, "title": "Almost Certain", "description": "Known, ongoing environmental damage or high probability of a large-scale disaster."}
                    ],
                    "impactScale": [
                        {"level": 1, "title": "Insignificant", "description": "Very minor environmental impact; easily remediated; no regulatory action or public concern."},
                        {"level": 2, "title": "Minor", "description": "Localized minor environmental impact; minimal remediation cost (<$10,000); minor regulatory notice; localized public concern."},
                        {"level": 3, "title": "Moderate", "description": "Regional environmental impact; moderate remediation cost ($10,000 - $100,000); moderate regulatory fines; noticeable public/media attention."},
                        {"level": 4, "title": "Major", "description": "Significant environmental damage (e.g., large-scale pollution of air/water/soil); substantial remediation cost ($100,000 - $1,000,000+); major regulatory fines/penalties; legal action; significant reputational damage."},
                        {"level": 5, "title": "Catastrophic", "description": "Widespread and irreversible environmental damage; massive remediation costs (>$1,000,000+); severe regulatory penalties, criminal charges; forced shutdown of operations; severe and lasting reputational damage; significant harm to ecosystems or human health."}
                    ],
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
            ]
            
            # Insert all default profiles
            result = risk_profiles_collection.insert_many(default_profiles)
            
            # Get the inserted profile IDs
            profile_ids = [str(profile_id) for profile_id in result.inserted_ids]
            
            return DatabaseResult(
                success=True,
                message=f"Created {len(default_profiles)} default risk profiles for user {user_id}",
                data={"inserted_count": len(result.inserted_ids), "profile_ids": profile_ids}
            )
            
        except Exception as e:
            return DatabaseResult(
                success=False,
                message=f"Error creating default risk profiles: {str(e)}",
                data=None
            )
    
    @staticmethod
    def get_user_risk_profiles(user_id: str) -> DatabaseResult:
        """Get all risk profiles for a user"""
        try:
            profiles = list(risk_profiles_collection.find({"userId": user_id}))
            return DatabaseResult(
                success=True,
                message=f"Retrieved {len(profiles)} risk profiles for user {user_id}",
                data={"profiles": profiles}
            )
        except Exception as e:
            return DatabaseResult(
                success=False,
                message=f"Error retrieving risk profiles: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def update_risk_profile(user_id: str, risk_type: str, likelihood_scale: list, impact_scale: list) -> DatabaseResult:
        """Update a specific risk profile for a user"""
        try:
            result = risk_profiles_collection.update_one(
                {"userId": user_id, "riskType": risk_type},
                {
                    "$set": {
                        "likelihoodScale": likelihood_scale,
                        "impactScale": impact_scale,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                return DatabaseResult(
                    success=True,
                    message=f"Updated risk profile for {risk_type}",
                    data={"modified_count": result.modified_count}
                )
            else:
                return DatabaseResult(
                    success=False,
                    message=f"Risk profile for {risk_type} not found",
                    data=None
                )
                
        except Exception as e:
            return DatabaseResult(
                success=False,
                message=f"Error updating risk profile: {str(e)}",
                data=None
            )



    @staticmethod
    async def apply_matrix_recommendation(user_id: str, matrix_size: str, organization_name: str = None, location: str = None, domain: str = None) -> DatabaseResult:
        """Apply matrix recommendation by replacing existing profiles"""
        try:
            # First, delete existing profiles for this user
            risk_profiles_collection.delete_many({"userId": user_id})
            
            # If organization context is provided, use LLM-generated recommendation
            if organization_name and location and domain:
                result = await RiskProfileDatabaseService.generate_matrix_recommendation_with_llm(
                    matrix_size, organization_name, location, domain, user_id
                )
                
                if result.success:
                    # Create profiles from LLM-generated data
                    profile_ids = []
                    for profile in result.data["profiles"]:
                        profile_data = {
                            "userId": user_id,
                            "riskType": profile["riskType"],
                            "definition": profile["definition"],
                            "likelihoodScale": profile["likelihoodScale"],
                            "impactScale": profile["impactScale"],
                            "matrixSize": profile["matrixSize"],
                            "createdAt": datetime.utcnow(),
                            "updatedAt": datetime.utcnow()
                        }
                        
                        result_insert = risk_profiles_collection.insert_one(profile_data)
                        profile_ids.append(str(result_insert.inserted_id))
                    
                    # Update user's risks_applicable field
                    users_collection.update_one(
                        {"username": user_id},
                        {"$set": {"risks_applicable": profile_ids}}
                    )
                    
                    return DatabaseResult(True, f"Successfully applied AI-generated {matrix_size} matrix recommendation", {"profile_ids": profile_ids})
                else:
                    # Fallback: return error if LLM generation fails
                    return DatabaseResult(False, "Failed to generate matrix recommendation and no fallback available")
            else:
                # Return error if no organization context provided
                return DatabaseResult(False, "Organization context required for matrix recommendation")
            
        except Exception as e:
            return DatabaseResult(False, f"Error applying matrix recommendation: {str(e)}")

    @staticmethod
    async def apply_matrix_configuration(user_id: str, matrix_size: str, profiles: list) -> DatabaseResult:
        """Apply matrix configuration with custom profiles"""
        try:
            # First, delete existing profiles for this user
            risk_profiles_collection.delete_many({"userId": user_id})
            
            # Create new profiles with the custom data
            profile_ids = []
            for profile_data in profiles:
                profile_doc = {
                    "userId": user_id,
                    "riskType": profile_data["riskType"],
                    "definition": profile_data["definition"],
                    "likelihoodScale": profile_data["likelihoodScale"],
                    "impactScale": profile_data["impactScale"],
                    "matrixSize": matrix_size,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                result = risk_profiles_collection.insert_one(profile_doc)
                profile_ids.append(str(result.inserted_id))
            
            # Update user's risks_applicable field
            users_collection.update_one(
                {"username": user_id},
                {"$set": {"risks_applicable": profile_ids}}
            )
            
            return DatabaseResult(True, f"Successfully applied {matrix_size} matrix configuration with customizations", {"profile_ids": profile_ids})
            
        except Exception as e:
            return DatabaseResult(False, f"Error applying matrix configuration: {str(e)}")

    @staticmethod
    async def generate_matrix_recommendation_with_llm(matrix_size: str, organization_name: str, location: str, domain: str, user_id: str = None) -> DatabaseResult:
        """Generate matrix recommendation using LLM based on organization context and user's existing risk profiles"""
        try:
            from openai import OpenAI
            import json
            import os
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return DatabaseResult(False, "OpenAI API key not configured")
            
            client = OpenAI(api_key=api_key)
            
            # Get user's existing risk profiles to include all their risk categories
            existing_risk_categories = []
            if user_id:
                profiles_result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
                if profiles_result.success and profiles_result.data and profiles_result.data.get("profiles"):
                    existing_profiles = profiles_result.data.get("profiles", [])
                    existing_risk_categories = [profile.get("riskType", "") for profile in existing_profiles if profile.get("riskType")]
            
            # If no existing profiles, use default comprehensive set
            if not existing_risk_categories:
                existing_risk_categories = [
                    "Strategic Risk", "Operational Risk", "Financial Risk", "Compliance Risk",
                    "Reputational Risk", "Health and Safety Risk", "Environmental Risk", "Technology Risk",
                    "Cybersecurity Risk", "Supply Chain Risk", "Market Risk", "Regulatory Risk"
                ]
            
            # Create risk categories JSON for the prompt
            risk_categories_json = ",\n    ".join([
                f'{{"riskType": "{category}", "definition": "Context-specific definition for {organization_name} in {domain} industry"}}'
                for category in existing_risk_categories
            ])
            
            # Create prompt for LLM to generate matrix scales
            prompt = f"""You are an expert Risk Management Specialist. Generate a {matrix_size} risk matrix specifically tailored for {organization_name} located in {location} operating in the {domain} domain.

Create likelihood and impact scales that are relevant to this organization's specific context, industry, and location.

IMPORTANT: Include ALL the following risk categories in your response. Do not limit to just 3 categories.

Return ONLY valid JSON in this exact format:

{{
  "matrix_scales": {{
    "likelihood": [
      {{"level": 1, "title": "Scale Title", "description": "Detailed description"}},
      {{"level": 2, "title": "Scale Title", "description": "Detailed description"}},
      {{"level": 3, "title": "Scale Title", "description": "Detailed description"}}
    ],
    "impact": [
      {{"level": 1, "title": "Scale Title", "description": "Detailed description"}},
      {{"level": 2, "title": "Scale Title", "description": "Detailed description"}},
      {{"level": 3, "title": "Scale Title", "description": "Detailed description"}}
    ]
  }},
  "risk_categories": [
    {risk_categories_json}
  ]
}}

For {matrix_size} matrix:
- Likelihood scale should have {matrix_size.split('x')[0]} levels
- Impact scale should have {matrix_size.split('x')[1]} levels
- Make scales relevant to {domain} industry and {location} location
- Ensure descriptions are specific to {organization_name}'s context
- Use appropriate terminology for the industry and region
- Include ALL {len(existing_risk_categories)} risk categories listed above

IMPORTANT: Return ONLY valid JSON. Do not include any other text."""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON from response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                
                if "matrix_scales" in data and "risk_categories" in data:
                    # Create preview profiles using LLM-generated data
                    preview_profiles = []
                    for category in data["risk_categories"]:
                        profile_data = {
                            "riskType": category["riskType"],
                            "definition": category["definition"],
                            "likelihoodScale": data["matrix_scales"]["likelihood"],
                            "impactScale": data["matrix_scales"]["impact"],
                            "matrixSize": matrix_size
                        }
                        preview_profiles.append(profile_data)
                    
                    return DatabaseResult(True, "Matrix recommendation generated successfully", {
                        "profiles": preview_profiles,
                        "matrix_size": matrix_size,
                        "totalProfiles": len(preview_profiles)
                    })
                else:
                    return DatabaseResult(False, "Invalid response format from LLM")
            else:
                return DatabaseResult(False, "No valid JSON found in LLM response")
                
        except json.JSONDecodeError as e:
            return DatabaseResult(False, f"Error parsing JSON response: {str(e)}")
        except Exception as e:
            return DatabaseResult(False, f"Error generating matrix recommendation: {str(e)}")


class ControlDatabaseService:
    """Service for managing control entities"""

    @staticmethod
    def _format_annexa_mappings_for_vector(mappings: Optional[List[Any]]) -> str:
        """Create a consistent string representation for Annex A mappings."""
        formatted: List[str] = []
        if not mappings:
            return ""

        for mapping in mappings:
            item = mapping
            # Support both dicts and pydantic objects
            if hasattr(item, "dict"):
                item = item.dict()
            ann_id = str((item or {}).get("id", "")).strip()
            title = str((item or {}).get("title", "")).strip()

            if ann_id and title:
                formatted.append(f"{ann_id} - {title}")
            elif ann_id:
                formatted.append(ann_id)
            elif title:
                formatted.append(title)

        # Ensure deterministic ordering for reproducible embeddings
        formatted = sorted({entry for entry in formatted if entry})
        return "; ".join(formatted)

    @staticmethod
    def _format_linked_risk_ids_for_vector(linked_ids: Optional[List[Any]]) -> str:
        """Normalize linked risk identifiers into a stable string."""
        if not linked_ids:
            return ""
        cleaned = []
        for value in linked_ids:
            text = str(value).strip()
            if text:
                cleaned.append(text)
        # Deduplicate while preserving order of first appearance
        seen = set()
        ordered = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ", ".join(ordered)

    @staticmethod
    def _prepare_vector_payload(user_doc: dict, control_source: Any) -> tuple[str, str, str, Dict[str, Any]]:
        """Build the payload required by ControlVectorIndexService from Mongo records."""
        org = str((user_doc or {}).get("organization_name", "") or "").strip()
        location = str((user_doc or {}).get("location", "") or "").strip()
        domain = str((user_doc or {}).get("domain", "") or "").strip()

        source_data: Dict[str, Any]
        if hasattr(control_source, "dict"):
            source_data = control_source.dict()
        elif isinstance(control_source, dict):
            source_data = control_source
        else:
            # Fallback to attribute access for dataclass-like objects
            source_data = {
                "control_id": getattr(control_source, "control_id", ""),
                "control_title": getattr(control_source, "control_title", ""),
                "control_description": getattr(control_source, "control_description", ""),
                "objective": getattr(control_source, "objective", ""),
                "annexA_map": getattr(control_source, "annexA_map", []),
                "owner_role": getattr(control_source, "owner_role", ""),
                "status": getattr(control_source, "status", ""),
                "linked_risk_ids": getattr(control_source, "linked_risk_ids", []),
            }

        annex_source = source_data.get("annexA_map")
        if annex_source is None and source_data.get("annexa_mappings") is not None:
            annexa_value = str(source_data.get("annexa_mappings") or "").strip()
        else:
            annexa_value = ControlDatabaseService._format_annexa_mappings_for_vector(annex_source)

        linked_source = source_data.get("linked_risk_ids")
        if isinstance(linked_source, str):
            linked_value = linked_source.strip()
        else:
            linked_value = ControlDatabaseService._format_linked_risk_ids_for_vector(linked_source)

        payload = {
            "control_id": str(source_data.get("control_id", "") or "").strip(),
            "control_title": str(source_data.get("control_title", "") or "").strip(),
            "control_description": str(source_data.get("control_description", "") or "").strip(),
            "objective": str(source_data.get("objective", "") or "").strip(),
            "owner_role": str(source_data.get("owner_role", "") or "").strip(),
            "status": str(source_data.get("status", "") or "").strip(),
            "annexa_mappings": annexa_value,
            "linked_risk_ids": linked_value,
        }

        return org, location, domain, payload

    @staticmethod
    def _sync_control_vector_entry(user_doc: dict, control_doc: dict, user_id: str) -> None:
        """Push control changes to the vector index while shielding the main flow."""
        if not control_doc:
            return
        try:
            org, location, domain, payload = ControlDatabaseService._prepare_vector_payload(user_doc, control_doc)
            if not payload.get("control_id"):
                return
            ControlVectorIndexService.upsert_finalized_controls(
                user_id=user_id,
                organization_name=org,
                location=location,
                domain=domain,
                controls=[payload]
            )
        except Exception as exc:
            print(f"Warning: Failed to sync control to vector index: {exc}")
    
    @staticmethod
    async def save_control(
        user_id: str,
        control_id: str,
        control_title: str,
        control_description: str,
        objective: str,
        annexA_map: List[dict] = None,
        linked_risk_ids: List[str] = None,
        owner_role: str = "",
        process_steps: List[str] = None,
        evidence_samples: List[str] = None,
        metrics: List[str] = None,
        frequency: str = "",
        policy_ref: str = "",
        status: str = "Active",
        rationale: str = "",
        assumptions: str = ""
    ) -> ControlResponse:
        """Save a new control for a user"""
        try:
            # Verify user exists in the users collection
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Set defaults for optional lists
            annexA_map = annexA_map or []
            linked_risk_ids = linked_risk_ids or []
            process_steps = process_steps or []
            evidence_samples = evidence_samples or []
            metrics = metrics or []
            
            # Create the control document
            control_document = {
                "user_id": user_id,
                "user_ref": user["_id"],
                "control_id": control_id,
                "control_title": control_title,
                "control_description": control_description,
                "objective": objective,
                "annexA_map": annexA_map,
                "linked_risk_ids": linked_risk_ids,
                "owner_role": owner_role,
                "process_steps": process_steps,
                "evidence_samples": evidence_samples,
                "metrics": metrics,
                "frequency": frequency,
                "policy_ref": policy_ref,
                "status": status,
                "rationale": rationale,
                "assumptions": assumptions,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Insert into database
            result = controls_collection.insert_one(control_document)
            
            # Get the inserted document
            inserted_doc = controls_collection.find_one({"_id": result.inserted_id})
            
            # Convert to Control model
            control = Control(
                id=str(inserted_doc["_id"]),
                control_id=inserted_doc["control_id"],
                control_title=inserted_doc["control_title"],
                control_description=inserted_doc["control_description"],
                objective=inserted_doc["objective"],
                annexA_map=[AnnexAMapping(**mapping) for mapping in inserted_doc["annexA_map"]],
                linked_risk_ids=inserted_doc["linked_risk_ids"],  # Will be populated by actual FinalizedRisk objects in link function
                owner_role=inserted_doc["owner_role"],
                process_steps=inserted_doc["process_steps"],
                evidence_samples=inserted_doc["evidence_samples"],
                metrics=inserted_doc["metrics"],
                frequency=inserted_doc["frequency"],
                policy_ref=inserted_doc["policy_ref"],
                status=inserted_doc["status"],
                rationale=inserted_doc["rationale"],
                assumptions=inserted_doc["assumptions"],
                user_id=inserted_doc["user_id"],
                created_at=inserted_doc["created_at"],
                updated_at=inserted_doc["updated_at"]
            )
            
            # Add vector indexing after successful control creation
            ControlDatabaseService._sync_control_vector_entry(user, inserted_doc, user_id)

            return ControlResponse(
                success=True,
                message="Control saved successfully",
                data=control
            )
            
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error saving control: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def get_user_controls(user_id: str) -> ControlsResponse:
        """Get all controls for a specific user"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlsResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find all controls for this user
            control_docs = list(controls_collection.find({"user_ref": user["_id"]}))
            
            # Convert to Control models
            controls = []
            for doc in control_docs:
                control = Control(
                    id=str(doc["_id"]),
                    control_id=doc["control_id"],
                    control_title=doc["control_title"],
                    control_description=doc["control_description"],
                    objective=doc["objective"],
                    annexA_map=[AnnexAMapping(**mapping) for mapping in doc.get("annexA_map", [])],
                    linked_risk_ids=doc.get("linked_risk_ids", []),
                    owner_role=doc["owner_role"],
                    process_steps=doc.get("process_steps", []),
                    evidence_samples=doc.get("evidence_samples", []),
                    metrics=doc.get("metrics", []),
                    frequency=doc["frequency"],
                    policy_ref=doc["policy_ref"],
                    status=doc["status"],
                    rationale=doc["rationale"],
                    assumptions=doc["assumptions"],
                    user_id=doc["user_id"],
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"]
                )
                controls.append(control)
            
            return ControlsResponse(
                success=True,
                message=f"Found {len(controls)} controls for user {user_id}",
                data=controls
            )
            
        except Exception as e:
            return ControlsResponse(
                success=False,
                message=f"Error retrieving controls: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def get_control_by_id(user_id: str, control_id: str) -> ControlResponse:
        """Get a specific control by its control_id"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find the control
            control_doc = controls_collection.find_one({
                "user_ref": user["_id"],
                "control_id": control_id
            })
            
            if not control_doc:
                return ControlResponse(
                    success=False,
                    message=f"Control with ID {control_id} not found for user {user_id}",
                    data=None
                )
            
            # Convert to Control model
            control = Control(
                id=str(control_doc["_id"]),
                control_id=control_doc["control_id"],
                control_title=control_doc["control_title"],
                control_description=control_doc["control_description"],
                objective=control_doc["objective"],
                annexA_map=[AnnexAMapping(**mapping) for mapping in control_doc.get("annexA_map", [])],
                linked_risk_ids=[],  # Will be populated by actual risk objects in link function
                owner_role=control_doc["owner_role"],
                process_steps=control_doc.get("process_steps", []),
                evidence_samples=control_doc.get("evidence_samples", []),
                metrics=control_doc.get("metrics", []),
                frequency=control_doc["frequency"],
                policy_ref=control_doc["policy_ref"],
                status=control_doc["status"],
                rationale=control_doc["rationale"],
                assumptions=control_doc["assumptions"],
                user_id=control_doc["user_id"],
                created_at=control_doc["created_at"],
                updated_at=control_doc["updated_at"]
            )
            
            return ControlResponse(
                success=True,
                message="Control found successfully",
                data=control
            )
            
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error retrieving control: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def update_control(
        user_id: str, 
        control_id: str, 
        update_data: dict
    ) -> ControlResponse:
        """Update an existing control"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Verify control exists
            control_doc = controls_collection.find_one({
                "user_ref": user["_id"],
                "control_id": control_id
            })
            
            if not control_doc:
                return ControlResponse(
                    success=False,
                    message=f"Control with ID {control_id} not found for user {user_id}",
                    data=None
                )
            
            # Valid fields that can be updated
            valid_fields = [
                "control_title", "control_description", "objective", "annexA_map",
                "linked_risk_ids", "owner_role", "process_steps", "evidence_samples",
                "metrics", "frequency", "policy_ref", "status", "rationale", "assumptions"
            ]
            
            # Filter update_data to only include valid fields
            filtered_update_data = {k: v for k, v in update_data.items() if k in valid_fields}
            filtered_update_data["updated_at"] = datetime.utcnow()
            
            # Update the control
            result = controls_collection.update_one(
                {"_id": control_doc["_id"]},
                {"$set": filtered_update_data}
            )
            
            if result.modified_count > 0:
                # Get the updated document
                updated_doc = controls_collection.find_one({"_id": control_doc["_id"]})
                
                # Convert to Control model
                control = Control(
                    id=str(updated_doc["_id"]),
                    control_id=updated_doc["control_id"],
                    control_title=updated_doc["control_title"],
                    control_description=updated_doc["control_description"],
                    objective=updated_doc["objective"],
                    annexA_map=[AnnexAMapping(**mapping) for mapping in updated_doc.get("annexA_map", [])],
                    linked_risk_ids=updated_doc.get("linked_risk_ids", []),
                    owner_role=updated_doc["owner_role"],
                    process_steps=updated_doc.get("process_steps", []),
                    evidence_samples=updated_doc.get("evidence_samples", []),
                    metrics=updated_doc.get("metrics", []),
                    frequency=updated_doc["frequency"],
                    policy_ref=updated_doc["policy_ref"],
                    status=updated_doc["status"],
                    rationale=updated_doc["rationale"],
                    assumptions=updated_doc["assumptions"],
                    user_id=updated_doc["user_id"],
                    created_at=updated_doc["created_at"],
                    updated_at=updated_doc["updated_at"]
                )

                # Keep vector index in sync with control changes
                ControlDatabaseService._sync_control_vector_entry(user, updated_doc, user_id)

                return ControlResponse(
                    success=True,
                    message="Control updated successfully",
                    data=control
                )
            else:
                return ControlResponse(
                    success=False,
                    message="No changes were made to the control",
                    data=None
                )
                
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error updating control: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def delete_control_by_id(user_id: str, control_id: str) -> ControlResponse:
        """Delete a specific control by its control_id"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Verify control exists
            control_doc = controls_collection.find_one({
                "user_ref": user["_id"],
                "control_id": control_id
            })
            
            if not control_doc:
                return ControlResponse(
                    success=False,
                    message=f"Control with ID {control_id} not found for user {user_id}",
                    data=None
                )
            
            # Delete the control
            result = controls_collection.delete_one({"_id": control_doc["_id"]})
            
            if result.deleted_count > 0:
                # Add vector index deletion
                try:
                    ControlVectorIndexService.delete_by_control_id(user_id, control_id)
                except Exception as e:
                    print(f"Warning: Failed to delete control from vector database: {e}")
                
                return ControlResponse(
                    success=True,
                    message=f"Control {control_id} deleted successfully",
                    data=None
                )
            else:
                return ControlResponse(
                    success=False,
                    message="Failed to delete control",
                    data=None
                )
                
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error deleting control: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def link_control_to_risks(
        user_id: str,
        control_id: str,
        risk_ids: List[str]
    ) -> ControlResponse:
        """Link a control to specific finalized risks"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Verify control exists
            control_doc = controls_collection.find_one({
                "user_ref": user["_id"],
                "control_id": control_id
            })
            
            if not control_doc:
                return ControlResponse(
                    success=False,
                    message=f"Control with ID {control_id} not found for user {user_id}",
                    data=None
                )
            
            # Verify risks exist in finalized_risks collection
            finalized_risks_doc = finalized_risks_collection.find_one({"user_ref": user["_id"]})
            if not finalized_risks_doc:
                return ControlResponse(
                    success=False,
                    message="No finalized risks found for user",
                    data=None
                )
            
            # Validate that all risk_ids exist in the user's finalized risks
            valid_risk_ids = []
            for risk_id in risk_ids:
                # Find risk by its _id in the risks array
                risk_found = False
                for risk in finalized_risks_doc.get("risks", []):
                    if str(risk.get("_id", "")) == risk_id:
                        valid_risk_ids.append(risk_id)
                        risk_found = True
                        break
                
                if not risk_found:
                    return ControlResponse(
                        success=False,
                        message=f"Risk with ID {risk_id} not found in finalized risks",
                        data=None
                    )
            
            # Update the control with linked risk IDs
            result = controls_collection.update_one(
                {"_id": control_doc["_id"]},
                {
                    "$set": {
                        "linked_risk_ids": valid_risk_ids,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                updated_doc = controls_collection.find_one({"_id": control_doc["_id"]})
                ControlDatabaseService._sync_control_vector_entry(user, updated_doc, user_id)
                return ControlResponse(
                    success=True,
                    message=f"Control linked to {len(valid_risk_ids)} risks successfully",
                    data=None
                )
            else:
                return ControlResponse(
                    success=False,
                    message="Failed to link control to risks",
                    data=None
                )
                
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error linking control to risks: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def get_controls_by_risk_id(user_id: str, risk_id: str) -> ControlsResponse:
        """Get all controls linked to a specific risk"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlsResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find controls that have this risk_id in their linked_risk_ids array
            control_docs = list(controls_collection.find({
                "user_ref": user["_id"],
                "linked_risk_ids": {"$in": [risk_id]}
            }))
            
            # Convert to Control models
            controls = []
            for doc in control_docs:
                control = Control(
                    id=str(doc["_id"]),
                    control_id=doc["control_id"],
                    control_title=doc["control_title"],
                    control_description=doc["control_description"],
                    objective=doc["objective"],
                    annexA_map=[AnnexAMapping(**mapping) for mapping in doc.get("annexA_map", [])],
                    linked_risk_ids=[],  # Will be populated by actual risk objects in link function
                    owner_role=doc["owner_role"],
                    process_steps=doc.get("process_steps", []),
                    evidence_samples=doc.get("evidence_samples", []),
                    metrics=doc.get("metrics", []),
                    frequency=doc["frequency"],
                    policy_ref=doc["policy_ref"],
                    status=doc["status"],
                    rationale=doc["rationale"],
                    assumptions=doc["assumptions"],
                    user_id=doc["user_id"],
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"]
                )
                controls.append(control)
            
            return ControlsResponse(
                success=True,
                message=f"Found {len(controls)} controls linked to risk {risk_id}",
                data=controls
            )
            
        except Exception as e:
            return ControlsResponse(
                success=False,
                message=f"Error retrieving controls by risk: {str(e)}",
                data=None
            )
    
    @staticmethod
    async def update_control_status(
        user_id: str,
        control_id: str,
        status: str
    ) -> ControlResponse:
        """Update a control's status"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return ControlResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Verify control exists
            control_doc = controls_collection.find_one({
                "user_ref": user["_id"],
                "control_id": control_id
            })
            
            if not control_doc:
                return ControlResponse(
                    success=False,
                    message=f"Control with ID {control_id} not found for user {user_id}",
                    data=None
                )
            
            # Valid statuses
            valid_statuses = ["Active", "Inactive", "Under Review", "Deprecated", "Draft"]
            if status not in valid_statuses:
                return ControlResponse(
                    success=False,
                    message=f"Invalid status. Valid statuses: {', '.join(valid_statuses)}",
                    data=None
                )
            
            # Update the status
            result = controls_collection.update_one(
                {"_id": control_doc["_id"]},
                {
                    "$set": {
                        "status": status,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                updated_doc = controls_collection.find_one({"_id": control_doc["_id"]})
                ControlDatabaseService._sync_control_vector_entry(user, updated_doc, user_id)
                return ControlResponse(
                    success=True,
                    message=f"Control status updated to {status}",
                    data=None
                )
            else:
                return ControlResponse(
                    success=False,
                    message="No changes were made to control status",
                    data=None
                )
                
        except Exception as e:
            return ControlResponse(
                success=False,
                message=f"Error updating control status: {str(e)}",
                data=None
            )
        
