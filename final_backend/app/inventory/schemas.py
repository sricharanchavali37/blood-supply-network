from pydantic import BaseModel, field_validator
from datetime import date
from typing import Optional
from app.inventory.models import BloodUnitStatus


class BloodUnitCreate(BaseModel):
    """
    Schema for POST /inventory/units.

    Fields:
      - blood_group:      One of A+, A-, B+, B-, AB+, AB-, O+, O-
      - quantity_ml:      Volume in millilitres (positive integer, e.g. 450)
      - collection_date:  Date the unit was collected (YYYY-MM-DD)
      - hospital_id:      ID of the hospital this unit belongs to

    Note: expiry_date is automatically computed as collection_date + 42 days.
          Do NOT send expiry_date in the request body.
    """
    blood_group: str
    quantity_ml: int
    collection_date: date
    hospital_id: int

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()

    @field_validator("quantity_ml")
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("quantity_ml must be greater than 0")
        return v

    @field_validator("collection_date")
    @classmethod
    def validate_collection_date(cls, v):
        if v > date.today():
            raise ValueError("collection_date cannot be in the future")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "blood_group": "O+",
                "quantity_ml": 450,
                "collection_date": "2025-03-01",
                "hospital_id": 1,
            }
        }
    }


class BloodUnitResponse(BaseModel):
    id: int
    blood_group: str
    quantity_ml: int
    collection_date: date
    expiry_date: date
    status: BloodUnitStatus
    hospital_id: int

    model_config = {
        "from_attributes": True,
        "use_enum_values": True,
    }


class BloodUnitUse(BaseModel):
    blood_group: str
    quantity_ml: int
    hospital_id: int

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v):
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if v.upper() not in valid:
            raise ValueError(f"blood_group must be one of {valid}")
        return v.upper()

    @field_validator("quantity_ml")
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("quantity_ml must be greater than 0")
        return v


class AvailabilityResponse(BaseModel):
    hospital_id: int
    blood_group: str
    total_available_units: int
    total_available_ml: int
    expiring_next_7_days: int
    expiry_risk_ratio: float


class AvailabilitySummaryResponse(BaseModel):
    hospital_id: int
    summary: list[AvailabilityResponse]
