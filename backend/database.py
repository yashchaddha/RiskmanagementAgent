import os
from datetime import datetime
from typing import List, Optional, Any
from pymongo import MongoClient
from bson import ObjectId
from models import Risk, GeneratedRisks, RiskResponse, FinalizedRisk, FinalizedRisks, FinalizedRisksResponse

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
risk_profiles_collection = db.risk_profiles # Added for risk profile collection

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
                updated_risks = existing_doc["risks"] + new_risks
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
    async def get_user_risks(user_id: str) -> RiskResponse:
        try:
            # Verify user exists first
            user = users_collection.find_one({"username": user_id})
            if not user:
                return RiskResponse(
                    success=False,
                    message=f"User {user_id} not found in database",
                    data=None
                )
            
            # Find the user's generated risks document (only one per user now)
            risk_doc = generated_risks_collection.find_one({"user_ref": user["_id"]})
            
            if not risk_doc:
                return RiskResponse(
                    success=True,
                    message="No risks found for this user",
                    data=None
                )
            
            # Convert to GeneratedRisks model
            risks = [
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
                for risk in risk_doc["risks"]
            ]
            
            generated_risks = GeneratedRisks(
                id=str(risk_doc["_id"]),
                user_id=risk_doc["user_id"],
                organization_name=risk_doc["organization_name"],
                location=risk_doc["location"],
                domain=risk_doc["domain"],
                risks=risks,
                total_risks=risk_doc["total_risks"],
                selected_risks=risk_doc["selected_risks"],
                created_at=risk_doc["created_at"],
                updated_at=risk_doc["updated_at"]
            )
            
            return RiskResponse(
                success=True,
                message=f"Found {len(risks)} risks for this user",
                data=generated_risks
            )
            
        except Exception as e:
            return RiskResponse(
                success=False,
                message=f"Error retrieving risks: {str(e)}",
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
            if risk_index >= len(risk_doc["risks"]):
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
    async def get_all_risks_with_users() -> RiskResponse:
        """Get all generated risks with user information for admin purposes"""
        try:
            # Aggregate to join with users collection
            pipeline = [
                {
                    "$lookup": {
                        "from": "users",
                        "localField": "user_id",
                        "foreignField": "username",
                        "as": "user_info"
                    }
                },
                {
                    "$unwind": "$user_info"
                },
                {
                    "$sort": {"created_at": -1}
                }
            ]
            
            risk_documents = list(generated_risks_collection.aggregate(pipeline))
            
            if not risk_documents:
                return RiskResponse(
                    success=True,
                    message="No risks found in database",
                    data=None
                )
            
            # Convert to GeneratedRisks models
            generated_risks_list = []
            for doc in risk_documents:
                risks = [
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
                    for risk in doc["risks"]
                ]
                
                generated_risks = GeneratedRisks(
                    id=str(doc["_id"]),
                    user_id=doc["user_id"],
                    organization_name=doc["organization_name"],
                    location=doc["location"],
                    domain=doc["domain"],
                    risks=risks,
                    total_risks=doc["total_risks"],
                    selected_risks=doc["selected_risks"],
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"]
                )
                generated_risks_list.append(generated_risks)
            
            return RiskResponse(
                success=True,
                message=f"Found {len(generated_risks_list)} risk assessments",
                data=generated_risks_list
            )
            
        except Exception as e:
            return RiskResponse(
                success=False,
                message=f"Error retrieving all risks: {str(e)}",
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
            
            if not finalized_risks:
                return FinalizedRisksResponse(
                    success=False,
                    message="No risks selected for finalization",
                    data=None
                )
            
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
                updated_risks = existing_doc["risks"] + new_finalized_risks
                total_risks = len(updated_risks)
                
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
                
                return FinalizedRisksResponse(
                    success=True,
                    message=f"Successfully finalized {len(finalized_risks)} risks",
                    data=finalized_risks_model
                )
            
        except Exception as e:
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
    async def delete_finalized_risk(user_id: str, risk_id: str) -> FinalizedRisksResponse:
        """Delete a specific finalized risk by its ID"""
        try:
            # Verify user exists
            user = users_collection.find_one({"username": user_id})
            if not user:
                return FinalizedRisksResponse(success=False, message=f"User {user_id} not found", data=None)
            # Find user's finalized risks document
            existing_doc = finalized_risks_collection.find_one({"user_ref": user["_id"]})
            if not existing_doc:
                return FinalizedRisksResponse(success=False, message="No finalized risks found for user", data=None)
            # Ensure the risk to delete exists
            risks = existing_doc.get("risks", [])
            if not any(str(risk.get("_id", "")) == risk_id for risk in risks):
                return FinalizedRisksResponse(success=False, message="Risk not found", data=None)
            # Remove the risk
            from bson import ObjectId
            try:
                # Try to convert to ObjectId if it's a valid ObjectId string
                risk_object_id = ObjectId(risk_id)
                result = finalized_risks_collection.update_one(
                    {"_id": existing_doc["_id"]},
                    {"$pull": {"risks": {"_id": risk_object_id}}}
                )
            except Exception:
                # If conversion fails, it might be stored as string, so try string comparison
                result = finalized_risks_collection.update_one(
                    {"_id": existing_doc["_id"]},
                    {"$pull": {"risks": {"_id": risk_id}}}
                )
            if result.modified_count == 0:
                return FinalizedRisksResponse(success=False, message="Failed to delete risk", data=None)
            # Determine new total and handle empty case
            new_total = len(risks) - 1
            if new_total <= 0:
                # No risks remain; delete the entire document
                finalized_risks_collection.delete_one({"_id": existing_doc["_id"]})
                # Return empty FinalizedRisks model instead of None
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
                    message="All finalized risks deleted; document removed.",
                    data=empty_finalized_model
                )
            # Update remaining document with new count and timestamp
            finalized_risks_collection.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": {"total_risks": new_total, "updated_at": datetime.utcnow()}}
            )
            # Retrieve updated document
            updated_doc = finalized_risks_collection.find_one({"_id": existing_doc["_id"]})
            # Convert to FinalizedRisks model
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
            return FinalizedRisksResponse(success=True, message="Risk deleted successfully", data=finalized_model)
        except Exception as e:
            return FinalizedRisksResponse(success=False, message=f"Error deleting risk: {str(e)}", data=None)

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


class UserDatabaseService:
    @staticmethod
    async def update_user_preferences(
        username: str,
        likelihood: List[str],
        impact: List[str]
    ) -> dict:
        """Update user's risk preference settings"""
        try:

            # Update user document with new preferences
            result = users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "likelihood": likelihood,
                        "impact": impact,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                return {
                    "success": True,
                    "message": f"Successfully updated preferences for user {username}",
                    "likelihood": likelihood,
                    "impact": impact
                }
            else:
                return {
                    "success": False,
                    "message": f"User {username} not found or no changes made",
                    "likelihood": None,
                    "impact": None
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating user preferences: {str(e)}",
                "likelihood": None,
                "impact": None
            }

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
    def get_matrix_preview_data(matrix_size: str) -> dict:
        """Get preview data for a specific matrix size without saving to database"""
        # Define matrix-specific scales
        matrix_scales = {
            "3x3": {
                "likelihood": [
                    {"level": 1, "title": "Low", "description": "Unlikely to occur"},
                    {"level": 2, "title": "Medium", "description": "May occur occasionally"},
                    {"level": 3, "title": "High", "description": "Likely to occur frequently"}
                ],
                "impact": [
                    {"level": 1, "title": "Low", "description": "Minimal impact on operations"},
                    {"level": 2, "title": "Medium", "description": "Moderate impact on operations"},
                    {"level": 3, "title": "High", "description": "Significant impact on operations"}
                ]
            },
            "4x4": {
                "likelihood": [
                    {"level": 1, "title": "Rare", "description": "Very unlikely to occur"},
                    {"level": 2, "title": "Unlikely", "description": "May occur in exceptional circumstances"},
                    {"level": 3, "title": "Likely", "description": "Expected to occur"},
                    {"level": 4, "title": "Very Likely", "description": "Almost certain to occur"}
                ],
                "impact": [
                    {"level": 1, "title": "Minor", "description": "Minimal impact on objectives"},
                    {"level": 2, "title": "Moderate", "description": "Noticeable impact on objectives"},
                    {"level": 3, "title": "Major", "description": "Significant impact on objectives"},
                    {"level": 4, "title": "Severe", "description": "Critical impact on objectives"}
                ]
            },
            "5x5": {
                "likelihood": [
                    {"level": 1, "title": "Rare", "description": "Very unlikely to occur"},
                    {"level": 2, "title": "Unlikely", "description": "May occur in exceptional circumstances"},
                    {"level": 3, "title": "Possible", "description": "Could occur"},
                    {"level": 4, "title": "Likely", "description": "Expected to occur"},
                    {"level": 5, "title": "Very Likely", "description": "Almost certain to occur"}
                ],
                "impact": [
                    {"level": 1, "title": "Minor", "description": "Minimal impact on objectives"},
                    {"level": 2, "title": "Moderate", "description": "Noticeable impact on objectives"},
                    {"level": 3, "title": "Major", "description": "Significant impact on objectives"},
                    {"level": 4, "title": "Severe", "description": "Critical impact on objectives"},
                    {"level": 5, "title": "Critical", "description": "Catastrophic impact on objectives"}
                ]
            }
        }
        
        # Get the scales for the requested matrix size
        scales = matrix_scales.get(matrix_size, matrix_scales["5x5"])
        
        # Define risk categories
        risk_categories = [
            {
                "riskType": "Strategic Risk",
                "definition": "Risks related to long-term business objectives, market positioning, and strategic decisions that could impact the organization's ability to achieve its goals.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Operational Risk",
                "definition": "Risks arising from day-to-day business processes, systems, and procedures that could affect operational efficiency and effectiveness.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Financial Risk",
                "definition": "Risks related to financial performance, cash flow, investments, and financial reporting that could impact the organization's financial stability.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Compliance Risk",
                "definition": "Risks associated with regulatory requirements, legal obligations, and compliance frameworks that could result in penalties or legal action.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Reputational Risk",
                "definition": "Risks that could damage the organization's brand image, stakeholder relationships, and market reputation.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Health and Safety Risk",
                "definition": "Risks related to employee and public safety, workplace hazards, and health-related incidents that could result in injuries or health issues.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Environmental Risk",
                "definition": "Risks associated with environmental impact, sustainability, and environmental compliance that could affect the organization's environmental footprint.",
                "matrixSize": matrix_size
            },
            {
                "riskType": "Technology Risk",
                "definition": "Risks related to IT systems, cybersecurity, data protection, and technological infrastructure that could impact digital operations.",
                "matrixSize": matrix_size
            }
        ]
        
        # Create preview data without saving to database
        preview_profiles = []
        for category in risk_categories:
            profile_data = {
                "riskType": category["riskType"],
                "definition": category["definition"],
                "likelihoodScale": scales["likelihood"],
                "impactScale": scales["impact"],
                "matrixSize": matrix_size
            }
            preview_profiles.append(profile_data)
        
        return {
            "matrix_size": matrix_size,
            "profiles": preview_profiles
        }

    @staticmethod
    async def create_matrix_risk_profiles(user_id: str, matrix_size: str) -> DatabaseResult:
        """Create risk profiles for a specific matrix size (3x3, 4x4, 5x5)"""
        try:
            # Get preview data
            preview_data = RiskProfileDatabaseService.get_matrix_preview_data(matrix_size)
            
            # Create new profiles with the specified matrix size
            profile_ids = []
            for profile in preview_data["profiles"]:
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
                
                result = risk_profiles_collection.insert_one(profile_data)
                profile_ids.append(str(result.inserted_id))
            
            # Update user's risks_applicable field
            users_collection.update_one(
                {"username": user_id},
                {"$set": {"risks_applicable": profile_ids}}
            )
            
            return DatabaseResult(True, f"Successfully created {matrix_size} risk profiles", {"profile_ids": profile_ids})
            
        except Exception as e:
            return DatabaseResult(False, f"Error creating matrix risk profiles: {str(e)}")

    @staticmethod
    async def apply_matrix_recommendation(user_id: str, matrix_size: str, organization_name: str = None, location: str = None, domain: str = None) -> DatabaseResult:
        """Apply matrix recommendation by replacing existing profiles"""
        try:
            # First, delete existing profiles for this user
            risk_profiles_collection.delete_many({"userId": user_id})
            
            # If organization context is provided, use LLM-generated recommendation
            if organization_name and location and domain:
                result = await RiskProfileDatabaseService.generate_matrix_recommendation_with_llm(
                    matrix_size, organization_name, location, domain
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
                    # Fallback to default matrix if LLM generation fails
                    return await RiskProfileDatabaseService.create_matrix_risk_profiles(user_id, matrix_size)
            else:
                # Use default matrix if no organization context provided
                return await RiskProfileDatabaseService.create_matrix_risk_profiles(user_id, matrix_size)
            
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
    async def generate_matrix_recommendation_with_llm(matrix_size: str, organization_name: str, location: str, domain: str) -> DatabaseResult:
        """Generate matrix recommendation using LLM based on organization context"""
        try:
            from openai import OpenAI
            import json
            import os
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return DatabaseResult(False, "OpenAI API key not configured")
            
            client = OpenAI(api_key=api_key)
            
            # Create prompt for LLM to generate matrix scales
            prompt = f"""You are an expert Risk Management Specialist. Generate a {matrix_size} risk matrix specifically tailored for {organization_name} located in {location} operating in the {domain} domain.

Create likelihood and impact scales that are relevant to this organization's specific context, industry, and location.

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
    {{
      "riskType": "Strategic Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Operational Risk", 
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Financial Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Compliance Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Reputational Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Health and Safety Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Environmental Risk",
      "definition": "Context-specific definition for {organization_name}"
    }},
    {{
      "riskType": "Technology Risk",
      "definition": "Context-specific definition for {organization_name}"
    }}
  ]
}}

For {matrix_size} matrix:
- Likelihood scale should have {matrix_size.split('x')[0]} levels
- Impact scale should have {matrix_size.split('x')[1]} levels
- Make scales relevant to {domain} industry and {location} location
- Ensure descriptions are specific to {organization_name}'s context
- Use appropriate terminology for the industry and region

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