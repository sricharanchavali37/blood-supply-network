# app/alerts/routes.py
#
# FIXES applied:
# 1. Route order: GET /hospital/{hospital_id} BEFORE GET /{alert_id} (already correct,
#    keeping verified).
# 2. log_event() calls for ALERT_CREATED and DONOR_ALERTED — each wrapped in
#    try/except to guarantee pipeline safety.
# 3. db.commit() in create_blood_alert already has proper rollback guard.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timezone
from app.core.database import get_db
from app.core.geolocation import haversine_distance
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus, TargetType
from app.alerts.schemas import (
    BloodAlertCreate,
    BloodAlertResponse,
    DonorAlertResponse,
    DonorAssignment,
    AlertStatusUpdate,
)
from app.inventory.models import BloodUnit, BloodUnitStatus
from app.donors.models import Donor, DonorResponse, DonorResponseType
from app.hospitals.models import Hospital
from app.donor_fatigue_control.utils import filter_donors_by_fatigue, rank_donors

MIN_SAFE_UNITS = 5

router = APIRouter(prefix="/alerts", tags=["Alert Engine"])


def calculate_reliability_score(db: Session, donor: Donor) -> float:
    confirmed_responses_count = (
        db.query(func.count(DonorResponse.id))
        .filter(
            DonorResponse.donor_id == donor.id,
            DonorResponse.response_type == DonorResponseType.accepted
        )
        .scalar()
    ) or 0

    response_ratio = 0.0
    donation_ratio = 0.0

    if donor.total_alerts_received > 0:
        response_ratio = (confirmed_responses_count / donor.total_alerts_received) * 60

    if confirmed_responses_count > 0:
        donation_ratio = (donor.total_donations / confirmed_responses_count) * 40

    return round(response_ratio + donation_ratio, 2)


@router.post("/create", response_model=BloodAlertResponse, status_code=status.HTTP_201_CREATED)
def create_blood_alert(
    payload: BloodAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_roles = ["Hospital Admin", "Lab Technician"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Hospital Admin or Lab Technician can create alerts"
        )

    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    if hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hospital location coordinates are missing"
        )

    # ── Alert deduplication (Requirement 9) ─────────────────────────────────
    # Do NOT create a duplicate alert when an active alert for the same
    # hospital + blood_group already exists. Return the existing alert instead.
    existing_alert = (
        db.query(Alert)
        .filter(
            Alert.target_id == payload.hospital_id,
            Alert.target_type == TargetType.hospital,
            Alert.blood_group == payload.blood_group,
            Alert.status == AlertStatus.active,
        )
        .first()
    )
    if existing_alert:
        # Re-assemble the response from the existing alert to preserve the
        # full contract without creating duplicate donor notifications.
        existing_responses = (
            db.query(DonorResponse)
            .filter(DonorResponse.alert_id == existing_alert.id)
            .all()
        )
        existing_assignments = []
        for resp in existing_responses:
            donor = db.query(Donor).filter(Donor.id == resp.donor_id).first()
            if donor:
                distance = haversine_distance(
                    hospital.latitude, hospital.longitude,
                    donor.latitude, donor.longitude,
                )
                existing_assignments.append(
                    DonorAssignment(
                        donor_id=donor.id,
                        user_id=donor.user_id,
                        blood_group=donor.blood_group,
                        reliability_score=donor.reliability_score,
                        distance_km=distance,
                        response_status=resp.response_type,
                        responded_at=resp.responded_at,
                    )
                )
        return BloodAlertResponse(
            id=existing_alert.id,
            hospital_id=payload.hospital_id,
            blood_group=payload.blood_group,
            severity=existing_alert.severity,
            alert_status=existing_alert.status,
            message=existing_alert.message,
            sent_at=existing_alert.sent_at,
            donors_notified=len(existing_responses),
            assignments=existing_assignments,
        )
    # ── End deduplication guard ──────────────────────────────────────────────

    today = date.today()

    available_units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == payload.hospital_id,
            BloodUnit.blood_group == payload.blood_group,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )

    total_available_units = len(available_units)

    if total_available_units >= MIN_SAFE_UNITS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No shortage detected. Available units: {total_available_units}"
        )

    eligible_donors = (
        db.query(Donor)
        .filter(
            Donor.blood_group == payload.blood_group,
            Donor.is_eligible == True,
        )
        .all()
    )

    seen_donor_ids = set()
    candidate_donors = []

    for donor in eligible_donors:
        if donor.id in seen_donor_ids:
            continue

        distance = haversine_distance(
            hospital.latitude,
            hospital.longitude,
            donor.latitude,
            donor.longitude,
        )

        if distance <= payload.search_radius_km:
            candidate_donors.append({"donor": donor, "distance_km": distance})
            seen_donor_ids.add(donor.id)

    filtered_donors, _, _ = filter_donors_by_fatigue(
        db, candidate_donors, allow_emergency_bypass=False
    )

    emergency_fallback = False

    if len(filtered_donors) == 0 and len(candidate_donors) > 0:
        emergency_fallback = True
        candidate_donors_expanded = []
        expanded_seen = set()

        for donor in eligible_donors:
            if donor.id in expanded_seen:
                continue
            distance = haversine_distance(
                hospital.latitude, hospital.longitude,
                donor.latitude, donor.longitude,
            )
            if distance <= 30.0:
                candidate_donors_expanded.append({"donor": donor, "distance_km": distance})
                expanded_seen.add(donor.id)

        if candidate_donors_expanded:
            filtered_donors, _, _ = filter_donors_by_fatigue(
                db, candidate_donors_expanded, allow_emergency_bypass=False
            )

        if len(filtered_donors) == 0:
            top_reliability = sorted(
                candidate_donors,
                key=lambda d: d["donor"].reliability_score,
                reverse=True,
            )[:payload.max_donors]
            filtered_donors, _, _ = filter_donors_by_fatigue(
                db, top_reliability, allow_emergency_bypass=True
            )

    ranked_donors = rank_donors(filtered_donors)

    final_seen = set()
    unique_ranked = []
    for item in ranked_donors:
        if item["donor"].id not in final_seen:
            unique_ranked.append(item)
            final_seen.add(item["donor"].id)

    selected_donors = unique_ranked[:payload.max_donors]

    message = (
        f"Blood shortage alert for {payload.blood_group} at {hospital.name}. "
        f"{total_available_units} units available (minimum required: {MIN_SAFE_UNITS})."
    )
    if emergency_fallback:
        message += " [Emergency fallback activated - expanded search radius]"

    alert = Alert(
        alert_type=AlertType.shortage,
        blood_group=payload.blood_group,
        severity=payload.severity,
        target_type=TargetType.hospital,
        target_id=payload.hospital_id,
        message=message,
        status=AlertStatus.active,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()  # get alert.id before inserting DonorResponse rows

    assignments = []

    for item in selected_donors:
        donor    = item["donor"]
        distance = item["distance_km"]

        donor_response = DonorResponse(
            donor_id=donor.id,
            alert_id=alert.id,
            response_type=DonorResponseType.no_response,
            responded_at=None,
        )
        db.add(donor_response)
        donor.total_alerts_received += 1

        assignments.append(
            DonorAssignment(
                donor_id=donor.id,
                user_id=donor.user_id,
                blood_group=donor.blood_group,
                reliability_score=donor.reliability_score,
                distance_km=distance,
                response_status=DonorResponseType.no_response,
                responded_at=None,
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist alert"
        )

    db.refresh(alert)

    # Log events — never allowed to break the pipeline
    try:
        from app.events.logger import log_event
        log_event(
            db,
            event_type="ALERT_CREATED",
            entity_type="alert",
            entity_id=alert.id,
            actor_user_id=current_user.id,
            metadata={
                "blood_group": payload.blood_group,
                "hospital_id": payload.hospital_id,
                "severity": payload.severity.value,
                "donors_notified": len(selected_donors),
            },
        )
        for item in selected_donors:
            log_event(
                db,
                event_type="DONOR_ALERTED",
                entity_type="donor",
                entity_id=item["donor"].id,
                actor_user_id=current_user.id,
                metadata={"alert_id": alert.id, "blood_group": payload.blood_group},
            )
        db.commit()
    except Exception:
        pass

    return BloodAlertResponse(
        id=alert.id,
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        severity=payload.severity,
        alert_status=alert.status,
        message=message,
        sent_at=alert.sent_at,
        donors_notified=len(selected_donors),
        assignments=assignments,
    )


@router.post("/respond/{alert_id}", response_model=DonorAlertResponse)
def respond_to_alert(
    alert_id: int,
    response_type: DonorResponseType,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    donor = db.query(Donor).filter(Donor.user_id == current_user.id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor profile not found for current user"
        )

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with id {alert_id} not found"
        )

    donor_response = (
        db.query(DonorResponse)
        .filter(
            DonorResponse.alert_id == alert_id,
            DonorResponse.donor_id == donor.id,
        )
        .first()
    )

    if not donor_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assignment found for this donor and alert"
        )

    if donor_response.response_type != DonorResponseType.no_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response already recorded for this alert"
        )

    donor_response.response_type = response_type
    donor_response.responded_at  = datetime.now(timezone.utc)

    donor.total_responses  += 1
    donor.reliability_score = calculate_reliability_score(db, donor)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record alert response"
        )

    db.refresh(donor_response)

    return DonorAlertResponse(
        alert_id=alert_id,
        donor_id=donor.id,
        response_status=response_type,
    )


@router.patch("/status", response_model=dict)
def update_alert_status(
    payload: AlertStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_roles = ["Hospital Admin", "Lab Technician"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Hospital Admin or Lab Technician can update alert status"
        )

    alert = db.query(Alert).filter(Alert.id == payload.alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with id {payload.alert_id} not found"
        )

    alert.status = payload.new_status

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert status"
        )

    db.refresh(alert)
    return {
        "alert_id": alert.id,
        "new_status": alert.status.value,
        "updated_at": datetime.now(timezone.utc),
    }


# ── IMPORTANT: /hospital/{hospital_id} MUST be declared BEFORE /{alert_id} ──
@router.get("/hospital/{hospital_id}", response_model=list[BloodAlertResponse])
def list_hospital_alerts(
    hospital_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alerts = (
        db.query(Alert)
        .filter(
            Alert.target_id == hospital_id,
            Alert.target_type == TargetType.hospital,
        )
        .order_by(Alert.sent_at.desc())
        .all()
    )

    result = []
    for alert in alerts:
        responses = (
            db.query(DonorResponse)
            .filter(DonorResponse.alert_id == alert.id)
            .all()
        )

        assignments = []
        for resp in responses:
            donor = db.query(Donor).filter(Donor.id == resp.donor_id).first()
            if donor:
                hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
                distance = 0.0
                if hospital and hospital.latitude and hospital.longitude:
                    distance = haversine_distance(
                        hospital.latitude, hospital.longitude,
                        donor.latitude, donor.longitude,
                    )
                assignments.append(
                    DonorAssignment(
                        donor_id=donor.id,
                        user_id=donor.user_id,
                        blood_group=donor.blood_group,
                        reliability_score=donor.reliability_score,
                        distance_km=distance,
                        response_status=resp.response_type,
                        responded_at=resp.responded_at,
                    )
                )

        result.append(
            BloodAlertResponse(
                id=alert.id,
                hospital_id=hospital_id,
                blood_group=alert.blood_group,
                severity=alert.severity,
                alert_status=alert.status,
                message=alert.message,
                sent_at=alert.sent_at,
                donors_notified=len(responses),
                assignments=assignments,
            )
        )

    return result


@router.get("/{alert_id}", response_model=BloodAlertResponse)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with id {alert_id} not found"
        )

    responses = (
        db.query(DonorResponse)
        .filter(DonorResponse.alert_id == alert_id)
        .all()
    )

    assignments = []
    for resp in responses:
        donor = db.query(Donor).filter(Donor.id == resp.donor_id).first()
        if donor:
            hospital = db.query(Hospital).filter(Hospital.id == alert.target_id).first()
            distance = 0.0
            if hospital and hospital.latitude and hospital.longitude:
                distance = haversine_distance(
                    hospital.latitude, hospital.longitude,
                    donor.latitude, donor.longitude,
                )
            assignments.append(
                DonorAssignment(
                    donor_id=donor.id,
                    user_id=donor.user_id,
                    blood_group=donor.blood_group,
                    reliability_score=donor.reliability_score,
                    distance_km=distance,
                    response_status=resp.response_type,
                    responded_at=resp.responded_at,
                )
            )

    return BloodAlertResponse(
        id=alert.id,
        hospital_id=alert.target_id,
        blood_group=alert.blood_group,
        severity=alert.severity,
        alert_status=alert.status,
        message=alert.message,
        sent_at=alert.sent_at,
        donors_notified=len(responses),
        assignments=assignments,
    )
