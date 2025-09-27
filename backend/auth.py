import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
print(f"SECRET_KEY loaded: {'*' * len(SECRET_KEY) if SECRET_KEY else 'NOT SET'}")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60000
MONGO_URI = os.getenv("MONGODB_URI")

client = MongoClient(MONGO_URI)
db = client["isoriskagent"]
users_collection = db["users"]

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

class UserCreate(BaseModel):
    username: str
    password: str
    organization_name: str
    location: str
    domain: str
    risks_applicable: list = []  # Array of risk category IDs from risk profile collection

class Token(BaseModel):
    access_token: str
    token_type: str

# Utility functions
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Signup endpoint
@router.post("/signup", response_model=Token)
def signup(user: UserCreate):
    if users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    user_data = {
        "username": user.username, 
        "hashed_password": hashed_password,
        "organization_name": user.organization_name,
        "location": user.location,
        "domain": user.domain,
        "risks_applicable": user.risks_applicable,
        "created_at": datetime.utcnow()
    }
    
    users_collection.insert_one(user_data)
    
    # Create default risk profiles for the new user and get their IDs
    try:
        from database import RiskProfileDatabaseService, AuditDatabaseService
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            profile_result = loop.run_until_complete(
                RiskProfileDatabaseService.create_default_risk_profiles(user.username)
            )
            audit_result = loop.run_until_complete(
                AuditDatabaseService.create_user_audit_items(user.username)
            )
        finally:
            loop.close()

        if profile_result.success and profile_result.data and profile_result.data.get("profile_ids"):
            profile_ids = profile_result.data.get("profile_ids", [])
            users_collection.update_one(
                {"username": user.username},
                {"$set": {"risks_applicable": profile_ids}}
            )
            print(f"Successfully created {len(profile_ids)} risk profiles for user {user.username}")
        else:
            print(
                f"Warning: Failed to create default risk profiles for user {user.username}: {profile_result.message}"
            )

        if audit_result.success:
            created_total = audit_result.data.get("created") if isinstance(audit_result.data, dict) else None
            print(
                f"Successfully initialized audit clauses for user {user.username}" +
                (f" ({created_total} items)" if created_total else "")
            )
        else:
            print(
                f"Warning: Failed to initialize audit clauses for user {user.username}: {audit_result.message}"
            )
    except Exception as e:
        print(f"Warning: Error during post-signup initialization for user {user.username}: {str(e)}")
    
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Login endpoint
@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token({"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Dependency to get current user
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as e:
        print(f"JWT Error: {e}")
        raise credentials_exception
    user = users_collection.find_one({"username": username})
    if user is None:
        print(f"User not found for username: {username}")
        raise credentials_exception
    return user
