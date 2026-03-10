from pydantic import BaseModel
from typing import Optional

class ShortageCheckRequest(BaseModel):
    hospital_id: int
    blood_group: str


class ShortageStatus(BaseModel):
    hospital_id: int
    blood_group: str
    total_available_units: int
    total_available_ml: int
    min_safe_units: int
    is_shortage: bool


class DonorTargetRequest(BaseModel):
    hospital_id: int
    blood_group: str
    search_radius_km: Optional[float] = 10.0
    max_results: Optional[int] = 10


class TargetedDonor(BaseModel):
    donor_id: int
    user_id: int
    blood_group: str
    reliability_score: float
    distance_km: float
    is_eligible: bool
    total_donations: int
    latitude: float
    longitude: float


class DonorTargetResponse(BaseModel):
    hospital_id: int
    blood_group: str
    search_radius_km: float
    donors_found: int
    recommended_donors: list[TargetedDonor]