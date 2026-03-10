from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List


class DonorFatiguePreviewRequest(BaseModel):
    hospital_id: int
    blood_group: str
    search_radius_km: Optional[float] = 10.0
    max_donors: Optional[int] = 10

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()


class FilteredDonor(BaseModel):
    donor_id: int
    user_id: int
    blood_group: str
    reliability_score: float
    distance_km: float
    last_alert_time: Optional[datetime]
    total_donations: int
    is_eligible: bool
    cooldown_active: bool
    decline_suppression_active: bool


class DonorFatiguePreviewResponse(BaseModel):
    hospital_id: int
    blood_group: str
    search_radius_km: float
    total_candidates: int
    filtered_by_cooldown: int
    filtered_by_decline: int
    remaining_donors: int
    emergency_fallback_triggered: bool
    recommended_donors: List[FilteredDonor]