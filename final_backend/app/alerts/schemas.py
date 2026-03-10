from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List
from app.alerts.models import AlertStatus, AlertSeverity, AlertType
from app.donors.models import DonorResponseType


class BloodAlertCreate(BaseModel):
    hospital_id: int
    blood_group: str
    severity: AlertSeverity = AlertSeverity.critical
    search_radius_km: Optional[float] = 10.0
    max_donors: Optional[int] = 10

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()


class DonorAssignment(BaseModel):
    donor_id: int
    user_id: int
    blood_group: str
    reliability_score: float
    distance_km: float
    response_status: DonorResponseType
    responded_at: Optional[datetime]

    class Config:
        from_attributes = True


class BloodAlertResponse(BaseModel):
    id: int
    hospital_id: int
    blood_group: str
    severity: AlertSeverity
    alert_status: AlertStatus
    message: str
    sent_at: datetime
    donors_notified: int
    assignments: List[DonorAssignment]

    class Config:
        from_attributes = True


class DonorAlertResponse(BaseModel):
    alert_id: int
    donor_id: int
    response_status: DonorResponseType

    class Config:
        from_attributes = True


class AlertStatusUpdate(BaseModel):
    alert_id: int
    new_status: AlertStatus