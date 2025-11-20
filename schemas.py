"""
Database Schemas for Smart Krishi

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class User(BaseModel):
    userId: Optional[str] = Field(None, description="Public user id (same as _id string)")
    name: str
    phone: str
    village: Optional[str] = None
    district: Optional[str] = None
    crops: List[str] = Field(default_factory=list)
    createdAt: Optional[datetime] = None

class CropDiagnosis(BaseModel):
    diagnosisId: Optional[str] = None
    userId: str
    crop: str
    imageURL: Optional[str] = None
    diseaseName: str
    probability: float
    recommendation: str
    pesticide: Optional[str] = None
    date: Optional[datetime] = None

class WeatherAlert(BaseModel):
    userId: str
    location: str
    lastAlertSent: Optional[datetime] = None

class MandiPrice(BaseModel):
    mandiId: Optional[str] = None
    district: str
    crop: str
    price: float
    updatedAt: Optional[datetime] = None

class Notification(BaseModel):
    userId: str
    type: Literal["weather", "mandi", "fertilizer"]
    message: str
    timestamp: Optional[datetime] = None

class OTPVerification(BaseModel):
    phone: str
    code: str
    expiresAt: datetime
    verified: bool = False
