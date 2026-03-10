from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List, Union
from app.alerts.schemas import DonorAssignment
from app.supply_intelligence.schemas import TransferSuggestion


class DecisionRequest(BaseModel):
    hospital_id: int
    blood_group: str
    forecast_hours: Optional[int] = 24
    search_radius_km: Optional[float] = 30.0
    max_donors: Optional[int] = 10

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()


class MonitorDecision(BaseModel):
    decision_type: str = "monitor"
    hospital_id: int
    hospital_name: str
    blood_group: str
    current_units: int
    projected_inventory_units: int
    shortage_risk: bool
    safe_threshold: int
    recommendation: str


class TransferDecision(BaseModel):
    decision_type: str = "transfer"
    hospital_id: int
    hospital_name: str
    blood_group: str
    shortage_detected: bool
    initial_deficit_units: int
    transfer_suggestions: List[TransferSuggestion]
    remaining_deficit_units: int
    recommendation: str


class DonorAlertDecision(BaseModel):
    decision_type: str = "donor_alert"
    hospital_id: int
    hospital_name: str
    blood_group: str
    alert_id: int
    donors_notified: int
    shortage_details: dict
    transfer_attempted: bool
    remaining_deficit_after_transfer: int
    recommendation: str


class DecisionResponse(BaseModel):
    timestamp: datetime
    hospital_id: int
    blood_group: str
    decision: Union[MonitorDecision, TransferDecision, DonorAlertDecision]