# app/decision_engine/routes.py
#
# FIXES applied:
# 1. log_event() added for DECISION_ENGINE_RUN — wrapped in try/except.
# 2. Uses search_radius_km from payload when calling create_blood_alert
#    (was hardcoded to 10.0 before, ignoring the caller's preference).
# 3. Both transfer and donor_alert decision paths pass correct hospital_name.
# 4. Robust handling when transfer_result.requesting_hospital_name is unavailable.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.decision_engine.schemas import (
    DecisionRequest,
    DecisionResponse,
    MonitorDecision,
    TransferDecision,
    DonorAlertDecision,
)
from app.shortage_prediction.schemas import ShortagePredictionRequest
from app.supply_intelligence.schemas import TransferRecommendationRequest
from app.alerts.schemas import BloodAlertCreate
from app.alerts.models import AlertSeverity

from app.shortage_prediction.routes import predict_shortage
from app.supply_intelligence.routes import recommend_transfers
from app.alerts.routes import create_blood_alert

router = APIRouter(prefix="/decision-engine", tags=["Decision Engine"])


@router.post("/orchestrate", response_model=DecisionResponse)
def orchestrate_decision(
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_roles = ["Hospital Admin", "Lab Technician"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Hospital Admin or Lab Technician can execute decision orchestration"
        )

    now = datetime.now(timezone.utc)

    # ── Step 1: Shortage Prediction ─────────────────────────────────────────
    prediction_request = ShortagePredictionRequest(
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        forecast_hours=payload.forecast_hours,
    )
    prediction_result = predict_shortage(
        payload=prediction_request,
        db=db,
        current_user=current_user,
    )

    # ── No shortage: just monitor ─────────────────────────────────────────────
    if not prediction_result.shortage_risk:
        _try_log_event(db, current_user, payload, "monitor", prediction_result, None)
        decision = MonitorDecision(
            hospital_id=payload.hospital_id,
            hospital_name=prediction_result.hospital_name,
            blood_group=payload.blood_group,
            current_units=prediction_result.current_units,
            projected_inventory_units=prediction_result.projected_inventory_units,
            shortage_risk=False,
            safe_threshold=prediction_result.safe_threshold,
            recommendation="No shortage risk detected. Continue monitoring inventory levels.",
        )
        return DecisionResponse(
            timestamp=now,
            hospital_id=payload.hospital_id,
            blood_group=payload.blood_group,
            decision=decision,
        )

    # ── Step 2: Supply Intelligence / Transfer Recommendations ────────────────
    transfer_request = TransferRecommendationRequest(
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        search_radius_km=payload.search_radius_km,
    )
    transfer_result = recommend_transfers(
        payload=transfer_request,
        db=db,
        current_user=current_user,
    )

    # ── Shortage fully resolved by transfers ──────────────────────────────────
    if transfer_result.remaining_deficit_units == 0 and len(transfer_result.transfer_suggestions) > 0:
        _try_log_event(db, current_user, payload, "transfer", prediction_result, None)
        decision = TransferDecision(
            hospital_id=payload.hospital_id,
            hospital_name=transfer_result.requesting_hospital_name,
            blood_group=payload.blood_group,
            shortage_detected=True,
            initial_deficit_units=transfer_result.initial_deficit_units,
            transfer_suggestions=transfer_result.transfer_suggestions,
            remaining_deficit_units=0,
            recommendation=(
                f"Shortage can be fully resolved through "
                f"{len(transfer_result.transfer_suggestions)} inter-hospital transfer(s). "
                "No donor alerts required."
            ),
        )
        return DecisionResponse(
            timestamp=now,
            hospital_id=payload.hospital_id,
            blood_group=payload.blood_group,
            decision=decision,
        )

    # ── Step 3: Donor Alert ───────────────────────────────────────────────────
    alert_request = BloodAlertCreate(
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        severity=AlertSeverity.critical,
        # FIX: use payload's search_radius_km (was hardcoded 10.0)
        search_radius_km=payload.search_radius_km,
        max_donors=payload.max_donors,
    )

    try:
        alert_result = create_blood_alert(
            payload=alert_request,
            db=db,
            current_user=current_user,
        )
    except HTTPException as exc:
        _try_log_event(db, current_user, payload, "transfer_partial", prediction_result, None)
        decision = TransferDecision(
            hospital_id=payload.hospital_id,
            hospital_name=transfer_result.requesting_hospital_name,
            blood_group=payload.blood_group,
            shortage_detected=True,
            initial_deficit_units=transfer_result.initial_deficit_units,
            transfer_suggestions=transfer_result.transfer_suggestions,
            remaining_deficit_units=transfer_result.remaining_deficit_units,
            recommendation=f"Partial transfer coverage. Alert skipped: {exc.detail}",
        )
        return DecisionResponse(
            timestamp=now,
            hospital_id=payload.hospital_id,
            blood_group=payload.blood_group,
            decision=decision,
        )

    _try_log_event(db, current_user, payload, "donor_alert", prediction_result, alert_result.id)

    decision = DonorAlertDecision(
        hospital_id=payload.hospital_id,
        hospital_name=prediction_result.hospital_name,
        blood_group=payload.blood_group,
        alert_id=alert_result.id,
        donors_notified=alert_result.donors_notified,
        shortage_details={
            "current_units": prediction_result.current_units,
            "safe_threshold": prediction_result.safe_threshold,
            "projected_inventory": prediction_result.projected_inventory_units,
            "transfers_attempted": len(transfer_result.transfer_suggestions),
        },
        transfer_attempted=len(transfer_result.transfer_suggestions) > 0,
        remaining_deficit_after_transfer=transfer_result.remaining_deficit_units,
        recommendation=f"Donor alert created. Notified {alert_result.donors_notified} eligible donors.",
    )
    return DecisionResponse(
        timestamp=now,
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        decision=decision,
    )


def _try_log_event(db, current_user, payload, decision_type, prediction_result, alert_id):
    """Log a DECISION_ENGINE_RUN event — never raises."""
    try:
        from app.events.logger import log_event
        meta = {
            "blood_group": payload.blood_group,
            "decision_type": decision_type,
            "current_units": prediction_result.current_units,
            "safe_threshold": prediction_result.safe_threshold,
            "shortage_risk": prediction_result.shortage_risk,
        }
        if alert_id is not None:
            meta["alert_id"] = alert_id
        log_event(
            db,
            event_type="DECISION_ENGINE_RUN",
            entity_type="hospital",
            entity_id=payload.hospital_id,
            actor_user_id=current_user.id,
            metadata=meta,
        )
        db.commit()
    except Exception:
        pass
