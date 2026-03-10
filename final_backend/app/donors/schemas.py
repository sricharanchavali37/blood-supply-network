from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional
from app.donors.models import DonorResponseType


class DonorCreate(BaseModel):
    """
    Schema for POST /donors/register.
    
    NOTE: `user_id` must equal the authenticated user's ID.
    Obtain your user_id from POST /auth/login (decode JWT or call GET /auth/me).
    """
    user_id: int
    blood_group: str
    latitude: float
    longitude: float

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": 1,
                "blood_group": "O+",
                "latitude": 17.385,
                "longitude": 78.4867,
            }
        }
    }


class DonorResponse(BaseModel):
    id: int
    user_id: int
    blood_group: str
    latitude: float
    longitude: float
    is_eligible: bool
    last_donation_date: Optional[date]
    next_eligible_date: Optional[date]
    reliability_score: float
    total_donations: int
    total_alerts_received: int
    total_responses: int

    class Config:
        from_attributes = True


class DonationRecord(BaseModel):
    donor_id: int
    donation_date: date


class DonorAlertResponseCreate(BaseModel):
    donor_id: int
    alert_id: int
    response_type: DonorResponseType


class DonorAlertResponseModel(BaseModel):
    id: int
    donor_id: int
    alert_id: int
    response_type: DonorResponseType
    # responded_at is a DateTime in the DB model, not a date
    responded_at: Optional[datetime]

    class Config:
        from_attributes = True


class DonorHeatmapEntry(BaseModel):
    date: date
    confirmed_response_count: int


class DonorHeatmapResponse(BaseModel):
    donor_id: int
    heatmap_data: list[DonorHeatmapEntry]
