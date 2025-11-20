import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel

from database import db, create_document, get_documents
from bson import ObjectId
import requests

# Import schemas
from schemas import User as UserSchema, CropDiagnosis as CropDiagnosisSchema, WeatherAlert as WeatherAlertSchema, MandiPrice as MandiPriceSchema, Notification as NotificationSchema

app = FastAPI(title="Smart Krishi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_BASE = "/api"

# Helpers

def oid_to_str(doc):
    if not doc:
        return doc
    if isinstance(doc, list):
        return [oid_to_str(d) for d in doc]
    if isinstance(doc, dict):
        d = {**doc}
        if d.get("_id"):
            d["id"] = str(d.pop("_id"))
        # convert datetimes to iso
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d
    return doc

# Root and health
@app.get("/")
def read_root():
    return {"name": "Smart Krishi", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            cols = db.list_collection_names()
            response["collections"] = cols
            response["connection_status"] = "Connected"
            response["database"] = "✅ Connected & Working"
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response

# ----------------------
# User APIs
# ----------------------
class RegisterPayload(BaseModel):
    name: str
    phone: str
    village: Optional[str] = None
    district: Optional[str] = None
    crops: Optional[List[str]] = []
    otp: Optional[str] = None  # placeholder, real verification would be via provider

@app.post(f"{BACKEND_BASE}/register")
def register_user(payload: RegisterPayload):
    # In a real system, verify OTP using provider. Here we accept if provided.
    if not payload.phone:
        raise HTTPException(status_code=400, detail="Phone is required")

    user_doc = {
        "name": payload.name,
        "phone": payload.phone,
        "village": payload.village,
        "district": payload.district,
        "crops": payload.crops or [],
        "createdAt": datetime.utcnow(),
    }
    inserted_id = create_document("user", user_doc)
    # mirror userId field for convenience
    db["user"].update_one({"_id": ObjectId(inserted_id)}, {"$set": {"userId": inserted_id}})
    saved = db["user"].find_one({"_id": ObjectId(inserted_id)})
    return oid_to_str(saved)

@app.get(f"{BACKEND_BASE}/user/{{user_id}}")
def get_user(user_id: str):
    doc = db["user"].find_one({"_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return oid_to_str(doc)

# ----------------------
# Disease Detection APIs
# ----------------------
@app.post(f"{BACKEND_BASE}/detect-disease")
async def detect_disease(
    userId: str = Form(...),
    crop: str = Form(...),
    image: UploadFile = File(...)
):
    # This demo stores metadata and simulates ML prediction
    # In production: upload to cloud storage, call ML FastAPI with the file URL
    content = await image.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty image")

    # Simulate upload by ignoring content and forming a fake URL
    image_url = f"https://files.smartkrishi.example/{datetime.utcnow().timestamp()}_{image.filename}"

    # Simulate call to ML microservice
    # ml_resp = requests.post(ML_URL, json={"image_url": image_url, "crop": crop}).json()
    # For now, mock values
    disease = "Leaf Blight"
    probability = 0.87
    recommendation = "Spray copper-based fungicide; remove infected leaves; ensure proper spacing."
    pesticide = "Copper Oxychloride 50% WP"

    record = {
        "userId": userId,
        "crop": crop,
        "imageURL": image_url,
        "diseaseName": disease,
        "probability": probability,
        "recommendation": recommendation,
        "pesticide": pesticide,
        "date": datetime.utcnow(),
    }
    inserted_id = create_document("cropdiagnosis", record)
    db["cropdiagnosis"].update_one({"_id": ObjectId(inserted_id)}, {"$set": {"diagnosisId": inserted_id}})
    saved = db["cropdiagnosis"].find_one({"_id": ObjectId(inserted_id)})
    return oid_to_str(saved)

@app.get(f"{BACKEND_BASE}/diagnosis/{{user_id}}")
def get_diagnosis(user_id: str):
    docs = list(db["cropdiagnosis"].find({"userId": user_id}).sort("date", -1))
    return oid_to_str(docs)

# ----------------------
# Weather API
# ----------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

@app.get(f"{BACKEND_BASE}/weather/{{location}}")
def get_weather(location: str):
    if not OPENWEATHER_API_KEY:
        # Return mock if key not set
        return {
            "location": location,
            "mock": True,
            "current": {"temp": 29, "humidity": 62, "desc": "Partly cloudy"},
            "forecast_3h": [
                {"time": "+3h", "temp": 30, "rain": 0},
                {"time": "+6h", "temp": 31, "rain": 0},
                {"time": "+9h", "temp": 28, "rain": 1},
            ],
            "alerts": ["No severe alerts"]
        }
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        curr = data["list"][0]
        forecast = [
            {"time": item["dt_txt"], "temp": item["main"]["temp"], "rain": item.get("rain", {}).get("3h", 0)}
            for item in data["list"][:5]
        ]
        alerts = []
        for f in forecast:
            if f["rain"] and f["rain"] > 5:
                alerts.append("Heavy rain expected")
        return {
            "location": location,
            "mock": False,
            "current": {"temp": curr["main"]["temp"], "humidity": curr["main"]["humidity"], "desc": curr["weather"][0]["description"]},
            "forecast_3h": forecast,
            "alerts": alerts or ["No severe alerts"]
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather API error: {str(e)[:120]}")

# ----------------------
# Mandi Price API
# ----------------------
@app.get(f"{BACKEND_BASE}/mandi/{{district}}")
def get_mandi_prices(district: str):
    # For now, return the latest prices stored or mock data
    items = list(db["mandiprice"].find({"district": district}).sort("updatedAt", -1)) if db else []
    if items:
        return oid_to_str(items)
    # mock fallback
    return [
        {"district": district, "crop": "Wheat", "price": 1850, "updatedAt": datetime.utcnow().isoformat()},
        {"district": district, "crop": "Rice", "price": 2100, "updatedAt": datetime.utcnow().isoformat()},
    ]

# ----------------------
# Fertilizer Recommendation API
# ----------------------
class FertilizerInput(BaseModel):
    crop: str
    soil: str

@app.post(f"{BACKEND_BASE}/fertilizer")
def fertilizer_recommendation(payload: FertilizerInput):
    # Simple rule-based mock
    base = {
        "Wheat": {"N": 120, "P": 60, "K": 40},
        "Rice": {"N": 100, "P": 50, "K": 50},
        "Cotton": {"N": 150, "P": 60, "K": 60},
    }
    nutrients = base.get(payload.crop, {"N": 90, "P": 40, "K": 40})
    multiplier = 1.0 if payload.soil.lower() in ["loam", "clay"] else 0.9
    rec = {k: round(v * multiplier, 1) for k, v in nutrients.items()}
    cost_estimate = round(rec["N"] * 1.5 + rec["P"] * 2 + rec["K"] * 1.8, 2)
    low_cost_alt = "Use compost + neem cake to replace 20% NPK"
    return {
        "crop": payload.crop,
        "soil": payload.soil,
        "nutrients": rec,
        "costEstimate": cost_estimate,
        "lowCostAlternative": low_cost_alt
    }

# ----------------------
# Notification API (WhatsApp/SMS mock)
# ----------------------
class AlertPayload(BaseModel):
    userId: str
    type: str
    message: Optional[str] = None

@app.post(f"{BACKEND_BASE}/send-alert")
def send_alert(payload: AlertPayload):
    # Mock send using Twilio - just store a notification document
    note = {
        "userId": payload.userId,
        "type": payload.type,
        "message": payload.message or "Test alert from Smart Krishi",
        "timestamp": datetime.utcnow()
    }
    nid = create_document("notification", note)
    return {"sent": True, "id": nid}

# ----------------------
# Admin APIs
# ----------------------
class UpdateMandiPayload(BaseModel):
    district: str
    crop: str
    price: float

@app.post(f"{BACKEND_BASE}/admin/update-mandi")
def admin_update_mandi(payload: UpdateMandiPayload):
    doc = {
        "district": payload.district,
        "crop": payload.crop,
        "price": payload.price,
        "updatedAt": datetime.utcnow()
    }
    mid = create_document("mandiprice", doc)
    db["mandiprice"].update_one({"_id": ObjectId(mid)}, {"$set": {"mandiId": mid}})
    return {"ok": True, "id": mid}

@app.get(f"{BACKEND_BASE}/admin/users")
def admin_users():
    users = list(db["user"].find().sort("createdAt", -1))
    return oid_to_str(users)

@app.get(f"{BACKEND_BASE}/admin/diagnosis")
def admin_diagnosis():
    reports = list(db["cropdiagnosis"].find().sort("date", -1))
    return oid_to_str(reports)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
