# app/donors/routes.py
#
# FIXES applied:
# 1. Route order: GET / → POST /register → POST /donation → POST /response →
#    GET /{id}/heatmap → GET /{id}   (heatmap MUST come before /{id})
# 2. record_donor_response: upsert logic for pre-seeded no_response records.
# 3. record_donation: wrapped db.commit() in try/except with rollback.
# 4. log_event() for DONOR_ACCEPTED, DONOR_DECLINED, DONATION_RECORDED —
#    each wrapped in try/except to guarantee pipeline safety.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta, timezone

from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User

from app.donors.models import (
    Donor,
    DonorResponse as DonorResponseModel,
    DonorResponseType,
)

from app.donors.schemas import (
    DonorCreate,
    DonorResponse,
    DonationRecord,
    DonorAlertResponseCreate,
    DonorAlertResponseModel,
    DonorHeatmapEntry,
    DonorHeatmapResponse,
)

ELIGIBILITY_DAYS = 90

router = APIRouter(prefix="/donors", tags=["Donors"])


def calculate_reliability_score(db: Session, donor: Donor) -> float:
    confirmed_responses_count = (
        db.query(func.count(DonorResponseModel.id))
        .filter(
            DonorResponseModel.donor_id == donor.id,
            DonorResponseModel.response_type == DonorResponseType.accepted
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


# ── Route order matters in FastAPI ─────────────────────────────────────────
# Static/fixed path segments MUST be declared before parameterised routes.
# GET /              → list_donors
# POST /register     → register_donor
# POST /donation     → record_donation
# POST /response     → record_donor_response
# GET /{id}/heatmap  → donor_heatmap   ← MUST come before GET /{id}
# GET /{id}          → get_donor
# ──────────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[DonorResponse])
def list_donors(
    blood_group: str | None = None,
    is_eligible: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Donor)
    if blood_group:
        query = query.filter(Donor.blood_group == blood_group.upper())
    if is_eligible is not None:
        query = query.filter(Donor.is_eligible == is_eligible)
    return query.order_by(Donor.reliability_score.desc()).all()


@router.post("/register", response_model=DonorResponse, status_code=status.HTTP_201_CREATED)
def register_donor(
    payload: DonorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot register donor for another user"
        )

    existing_donor = db.query(Donor).filter(Donor.user_id == payload.user_id).first()
    if existing_donor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Donor already registered for this user"
        )

    donor = Donor(
        user_id=payload.user_id,
        blood_group=payload.blood_group,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_eligible=True,
        reliability_score=0.0,
        total_donations=0,
        total_alerts_received=0,
        total_responses=0,
    )
    db.add(donor)
    try:
        db.commit()
        db.refresh(donor)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register donor: {str(e)}"
        )
    return donor


@router.post("/donation", response_model=DonorResponse)
def record_donation(
    payload: DonationRecord,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_roles = ["Hospital Admin", "Lab Technician"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Hospital Admin or Lab Technician can record donations"
        )

    donor = db.query(Donor).filter(Donor.id == payload.donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )

    donor.last_donation_date  = payload.donation_date
    donor.next_eligible_date  = payload.donation_date + timedelta(days=ELIGIBILITY_DAYS)
    donor.is_eligible         = False
    donor.total_donations    += 1
    donor.reliability_score   = calculate_reliability_score(db, donor)

    try:
        db.commit()
        db.refresh(donor)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record donation: {str(e)}"
        )

    # Log event — must never break the pipeline
    try:
        from app.events.logger import log_event
        log_event(
            db,
            event_type="DONATION_RECORDED",
            entity_type="donor",
            entity_id=donor.id,
            actor_user_id=current_user.id,
            metadata={
                "donation_date": str(payload.donation_date),
                "total_donations": donor.total_donations,
                "next_eligible_date": str(donor.next_eligible_date),
            },
        )
        db.commit()
    except Exception:
        pass

    return donor


@router.post("/response", response_model=DonorAlertResponseModel, status_code=status.HTTP_201_CREATED)
def record_donor_response(
    payload: DonorAlertResponseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record or update a donor's response to an alert (upsert).

    FIX: POST /alerts/create pre-seeds a DonorResponse with response_type=no_response
    for every notified donor. The original implementation raised 400 whenever any
    existing record was found, so donors could NEVER respond — the upsert path
    below updates the pre-seeded record instead of rejecting it.
    A real (non-no_response) duplicate IS still rejected.
    """
    donor = db.query(Donor).filter(Donor.id == payload.donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )

    if current_user.id != donor.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot record response for another donor"
        )

    existing_response = (
        db.query(DonorResponseModel)
        .filter(
            DonorResponseModel.donor_id == payload.donor_id,
            DonorResponseModel.alert_id == payload.alert_id
        )
        .first()
    )

    if existing_response:
        if existing_response.response_type != DonorResponseType.no_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Donor already responded to this alert"
            )
        # Upsert: update the pre-seeded no_response record
        existing_response.response_type = payload.response_type
        existing_response.responded_at  = datetime.now(timezone.utc)
        response = existing_response
    else:
        # No pre-seeded record: create fresh
        response = DonorResponseModel(
            donor_id=payload.donor_id,
            alert_id=payload.alert_id,
            response_type=payload.response_type,
            responded_at=datetime.now(timezone.utc),
        )
        db.add(response)

    donor.total_responses  += 1
    donor.reliability_score = calculate_reliability_score(db, donor)

    try:
        db.commit()
        db.refresh(response)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record donor response: {str(e)}"
        )

    # Log event — must never break the pipeline
    try:
        from app.events.logger import log_event
        event_type = (
            "DONOR_ACCEPTED" if payload.response_type == DonorResponseType.accepted
            else "DONOR_DECLINED"
        )
        log_event(
            db,
            event_type=event_type,
            entity_type="donor",
            entity_id=donor.id,
            actor_user_id=current_user.id,
            metadata={"alert_id": payload.alert_id, "response_type": payload.response_type.value},
        )
        db.commit()
    except Exception:
        pass

    return response


@router.get("/{donor_id}/heatmap", response_model=DonorHeatmapResponse)
def donor_heatmap(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a 365-day heatmap of confirmed donation responses for a donor.

    NOTE: This must appear BEFORE GET /{donor_id} in the router declaration,
    otherwise FastAPI matches "heatmap" as the donor_id integer and returns 422.
    """
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor with id {donor_id} not found"
        )

    end_date   = date.today()
    start_date = end_date - timedelta(days=364)

    accepted_responses = (
        db.query(DonorResponseModel)
        .filter(
            DonorResponseModel.donor_id == donor_id,
            DonorResponseModel.response_type == DonorResponseType.accepted,
            DonorResponseModel.responded_at.isnot(None),
        )
        .all()
    )

    counts: dict[date, int] = {}
    for resp in accepted_responses:
        if resp.responded_at is None:
            continue
        resp_date = (
            resp.responded_at.date()
            if hasattr(resp.responded_at, "date")
            else resp.responded_at
        )
        if start_date <= resp_date <= end_date:
            counts[resp_date] = counts.get(resp_date, 0) + 1

    heatmap_data = []
    current_day = start_date
    for _ in range(365):
        heatmap_data.append(
            DonorHeatmapEntry(
                date=current_day,
                confirmed_response_count=counts.get(current_day, 0),
            )
        )
        current_day += timedelta(days=1)

    return DonorHeatmapResponse(donor_id=donor_id, heatmap_data=heatmap_data)


@router.get("/{donor_id}", response_model=DonorResponse)
def get_donor(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor with id {donor_id} not found"
        )
    return donor
