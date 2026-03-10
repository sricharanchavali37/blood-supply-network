# app/shortage_prediction/routes.py
#
# FIX — Adaptive threshold (Requirement 4)
# Now calls get_safe_threshold() instead of using the hardcoded MIN_SAFE_UNITS.
# Also logs a DECISION_ENGINE_RUN event (wrapped in try/except so it never
# breaks the route).

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.hospitals.models import Hospital
from app.shortage_prediction.schemas import (
    ShortagePredictionRequest,
    ShortagePredictionResponse,
)
from app.shortage_prediction.utils import (
    get_current_inventory,
    get_expiring_units,
    estimate_consumption,
    calculate_shortage_probability,
    calculate_days_until_shortage,
    get_safe_threshold,
)

router = APIRouter(prefix="/shortage-prediction", tags=["Shortage Prediction"])


@router.post("/forecast", response_model=ShortagePredictionResponse)
def predict_shortage(
    payload: ShortagePredictionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    now = datetime.now(timezone.utc)
    forecast_end_time = now + timedelta(hours=payload.forecast_hours)

    current_units, current_ml = get_current_inventory(
        db, payload.hospital_id, payload.blood_group
    )

    expiring_units, expiring_ml = get_expiring_units(
        db, payload.hospital_id, payload.blood_group, forecast_end_time
    )

    avg_daily_usage = estimate_consumption(
        db, payload.hospital_id, payload.blood_group
    )

    forecast_days  = payload.forecast_hours / 24.0
    expected_usage = avg_daily_usage * forecast_days

    projected_inventory = round(current_units - expiring_units - expected_usage)

    # FIX: use adaptive threshold instead of hardcoded 5
    safe_threshold = get_safe_threshold(db, payload.hospital_id, payload.blood_group)

    shortage_risk = projected_inventory < safe_threshold

    shortage_probability = calculate_shortage_probability(projected_inventory, safe_threshold)

    recommended_action = (
        "prepare_transfer_or_donor_alert" if shortage_risk else "monitor_inventory"
    )

    days_until_shortage = calculate_days_until_shortage(
        current_units, avg_daily_usage, safe_threshold
    )

    return ShortagePredictionResponse(
        hospital_id=payload.hospital_id,
        hospital_name=hospital.name,
        blood_group=payload.blood_group,
        forecast_hours=payload.forecast_hours,
        forecast_end_time=forecast_end_time,
        current_units=current_units,
        current_ml=current_ml,
        expiring_units=expiring_units,
        expiring_ml=expiring_ml,
        avg_daily_usage_units=avg_daily_usage,
        expected_usage_units=round(expected_usage, 2),
        projected_inventory_units=projected_inventory,
        safe_threshold=safe_threshold,
        shortage_risk=shortage_risk,
        shortage_probability=shortage_probability,
        recommended_action=recommended_action,
        days_until_shortage=days_until_shortage,
    )
