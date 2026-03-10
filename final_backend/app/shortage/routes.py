from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from math import radians, sin, cos, sqrt, atan2
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.inventory.models import BloodUnit, BloodUnitStatus
from app.donors.models import Donor
from app.hospitals.models import Hospital
from app.shortage.schemas import (
    ShortageCheckRequest,
    ShortageStatus,
    DonorTargetRequest,
    DonorTargetResponse,
    TargetedDonor,
)

MIN_SAFE_UNITS = 5
EARTH_RADIUS_KM = 6371.0

router = APIRouter(prefix="/shortage", tags=["Shortage Detection"])


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points on Earth using Haversine formula.
    Returns distance in kilometers.
    """
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = EARTH_RADIUS_KM * c
    return round(distance, 2)


@router.post("/check", response_model=ShortageStatus)
def check_shortage(
    payload: ShortageCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    blood_group_upper = payload.blood_group.upper()
    valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if blood_group_upper not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid blood_group. Must be one of {valid}"
        )

    today = date.today()

    available_units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == payload.hospital_id,
            BloodUnit.blood_group == blood_group_upper,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )

    total_available_units = len(available_units)
    total_available_ml = sum(u.quantity_ml for u in available_units)
    is_shortage = total_available_units < MIN_SAFE_UNITS

    return ShortageStatus(
        hospital_id=payload.hospital_id,
        blood_group=blood_group_upper,
        total_available_units=total_available_units,
        total_available_ml=total_available_ml,
        min_safe_units=MIN_SAFE_UNITS,
        is_shortage=is_shortage,
    )


@router.post("/target-donors", response_model=DonorTargetResponse)
def target_donors(
    payload: DonorTargetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    blood_group_upper = payload.blood_group.upper()
    valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if blood_group_upper not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid blood_group. Must be one of {valid}"
        )

    today = date.today()

    available_units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == payload.hospital_id,
            BloodUnit.blood_group == blood_group_upper,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )

    total_available_units = len(available_units)

    if total_available_units >= MIN_SAFE_UNITS:
        return DonorTargetResponse(
            hospital_id=payload.hospital_id,
            blood_group=blood_group_upper,
            search_radius_km=payload.search_radius_km,
            donors_found=0,
            recommended_donors=[],
        )

    eligible_donors = (
        db.query(Donor)
        .filter(
            Donor.blood_group == blood_group_upper,
            Donor.is_eligible == True,
        )
        .all()
    )

    seen_donor_ids = set()
    targeted_donors = []

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
            targeted_donors.append(
                TargetedDonor(
                    donor_id=donor.id,
                    user_id=donor.user_id,
                    blood_group=donor.blood_group,
                    reliability_score=donor.reliability_score,
                    distance_km=distance,
                    is_eligible=donor.is_eligible,
                    total_donations=donor.total_donations,
                    latitude=donor.latitude,
                    longitude=donor.longitude,
                )
            )
            seen_donor_ids.add(donor.id)

    targeted_donors.sort(key=lambda d: d.reliability_score, reverse=True)

    recommended = targeted_donors[: payload.max_results]

    return DonorTargetResponse(
        hospital_id=payload.hospital_id,
        blood_group=blood_group_upper,
        search_radius_km=payload.search_radius_km,
        donors_found=len(targeted_donors),
        recommended_donors=recommended,
    )