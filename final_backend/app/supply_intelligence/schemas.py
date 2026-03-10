from pydantic import BaseModel, field_validator
from typing import Optional, List


class SupplyAnalysisRequest(BaseModel):
    hospital_id: int
    blood_group: str

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()


class SupplyAnalysisResponse(BaseModel):
    hospital_id: int
    hospital_name: str
    blood_group: str
    total_available_units: int
    total_available_ml: int
    safe_threshold: int
    surplus_units: int
    deficit_units: int
    is_shortage: bool


class TransferRecommendationRequest(BaseModel):
    hospital_id: int
    blood_group: str
    search_radius_km: Optional[float] = 30.0

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()


class TransferSuggestion(BaseModel):
    from_hospital_id: int
    from_hospital_name: str
    to_hospital_id: int
    to_hospital_name: str
    blood_group: str
    suggested_units: int
    suggested_ml: int
    distance_km: float
    donor_hospital_remaining: int


class TransferRecommendationResponse(BaseModel):
    requesting_hospital_id: int
    requesting_hospital_name: str
    blood_group: str
    initial_deficit_units: int
    transfer_suggestions: List[TransferSuggestion]
    remaining_deficit_units: int
    donor_alert_required: bool
    search_radius_km: float