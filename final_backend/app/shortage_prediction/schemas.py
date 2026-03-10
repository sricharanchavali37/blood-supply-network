from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class ShortagePredictionRequest(BaseModel):
    hospital_id: int
    blood_group: str
    forecast_hours: Optional[int] = 24

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()

    @field_validator("forecast_hours")
    @classmethod
    def validate_forecast_hours(cls, v):
        if v <= 0:
            raise ValueError("forecast_hours must be greater than 0")
        if v > 168:
            raise ValueError("forecast_hours cannot exceed 168 (7 days)")
        return v


class ShortagePredictionResponse(BaseModel):
    hospital_id: int
    hospital_name: str
    blood_group: str
    forecast_hours: int
    forecast_end_time: datetime
    current_units: int
    current_ml: int
    expiring_units: int
    expiring_ml: int
    avg_daily_usage_units: float
    expected_usage_units: float
    projected_inventory_units: int
    safe_threshold: int
    shortage_risk: bool
    shortage_probability: str
    recommended_action: str
    days_until_shortage: Optional[float]