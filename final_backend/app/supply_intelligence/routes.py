from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from app.core.database import get_db
from app.core.geolocation import haversine_distance
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.inventory.models import BloodUnit, BloodUnitStatus
from app.hospitals.models import Hospital
from app.supply_intelligence.schemas import (
    SupplyAnalysisRequest,
    SupplyAnalysisResponse,
    TransferRecommendationRequest,
    TransferRecommendationResponse,
    TransferSuggestion,
)

MIN_SAFE_UNITS = 5

router = APIRouter(prefix="/supply-intelligence", tags=["Supply Intelligence"])


@router.post("/analyze", response_model=SupplyAnalysisResponse)
def analyze_supply(
    payload: SupplyAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

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
    total_available_ml = sum(u.quantity_ml for u in available_units)
    safe_threshold = MIN_SAFE_UNITS

    surplus_units = max(0, total_available_units - safe_threshold)
    deficit_units = max(0, safe_threshold - total_available_units)
    is_shortage = total_available_units < safe_threshold

    return SupplyAnalysisResponse(
        hospital_id=payload.hospital_id,
        hospital_name=hospital.name,
        blood_group=payload.blood_group,
        total_available_units=total_available_units,
        total_available_ml=total_available_ml,
        safe_threshold=safe_threshold,
        surplus_units=surplus_units,
        deficit_units=deficit_units,
        is_shortage=is_shortage,
    )


@router.post("/transfer-recommendations", response_model=TransferRecommendationResponse)
def recommend_transfers(
    payload: TransferRecommendationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requesting_hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not requesting_hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    if requesting_hospital.latitude is None or requesting_hospital.longitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requesting hospital location coordinates are missing"
        )

    today = date.today()

    requesting_units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == payload.hospital_id,
            BloodUnit.blood_group == payload.blood_group,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )

    requesting_available = len(requesting_units)
    initial_deficit = max(0, MIN_SAFE_UNITS - requesting_available)

    if initial_deficit == 0:
        return TransferRecommendationResponse(
            requesting_hospital_id=payload.hospital_id,
            requesting_hospital_name=requesting_hospital.name,
            blood_group=payload.blood_group,
            initial_deficit_units=0,
            transfer_suggestions=[],
            remaining_deficit_units=0,
            donor_alert_required=False,
            search_radius_km=payload.search_radius_km,
        )

    all_hospitals = (
        db.query(Hospital)
        .filter(
            Hospital.id != payload.hospital_id,
            Hospital.is_active == True,
        )
        .all()
    )

    candidate_hospitals = []

    for hospital in all_hospitals:
        if hospital.latitude is None or hospital.longitude is None:
            continue

        distance = haversine_distance(
            requesting_hospital.latitude,
            requesting_hospital.longitude,
            hospital.latitude,
            hospital.longitude,
        )

        if distance <= payload.search_radius_km:
            units = (
                db.query(BloodUnit)
                .filter(
                    BloodUnit.hospital_id == hospital.id,
                    BloodUnit.blood_group == payload.blood_group,
                    BloodUnit.status == BloodUnitStatus.available,
                    BloodUnit.expiry_date >= today,
                )
                .order_by(BloodUnit.expiry_date.asc())
                .all()
            )

            available_count = len(units)
            surplus = max(0, available_count - MIN_SAFE_UNITS)

            if surplus > 0:
                candidate_hospitals.append({
                    "hospital": hospital,
                    "distance_km": distance,
                    "available_units": available_count,
                    "surplus_units": surplus,
                    "units": units,
                })

    candidate_hospitals.sort(key=lambda c: c["distance_km"])

    transfer_suggestions = []
    remaining_deficit = initial_deficit

    for candidate in candidate_hospitals:
        if remaining_deficit <= 0:
            break

        transferable_units = min(candidate["surplus_units"], remaining_deficit)

        if transferable_units > 0:
            selected_units = candidate["units"][:transferable_units]
            total_ml = sum(u.quantity_ml for u in selected_units)

            transfer_suggestions.append(
                TransferSuggestion(
                    from_hospital_id=candidate["hospital"].id,
                    from_hospital_name=candidate["hospital"].name,
                    to_hospital_id=payload.hospital_id,
                    to_hospital_name=requesting_hospital.name,
                    blood_group=payload.blood_group,
                    suggested_units=transferable_units,
                    suggested_ml=total_ml,
                    distance_km=candidate["distance_km"],
                    donor_hospital_remaining=candidate["available_units"] - transferable_units,
                )
            )

            remaining_deficit -= transferable_units

    donor_alert_required = remaining_deficit > 0

    return TransferRecommendationResponse(
        requesting_hospital_id=payload.hospital_id,
        requesting_hospital_name=requesting_hospital.name,
        blood_group=payload.blood_group,
        initial_deficit_units=initial_deficit,
        transfer_suggestions=transfer_suggestions,
        remaining_deficit_units=remaining_deficit,
        donor_alert_required=donor_alert_required,
        search_radius_km=payload.search_radius_km,
    )