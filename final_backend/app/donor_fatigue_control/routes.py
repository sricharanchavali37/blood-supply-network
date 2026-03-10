from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from app.core.database import get_db
from app.core.geolocation import haversine_distance
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.donors.models import Donor
from app.hospitals.models import Hospital
from app.donor_fatigue_control.schemas import (
    DonorFatiguePreviewRequest,
    DonorFatiguePreviewResponse,
    FilteredDonor,
)
from app.donor_fatigue_control.utils import (
    filter_donors_by_fatigue,
    rank_donors,
)

router = APIRouter(prefix="/donor-fatigue", tags=["Donor Fatigue Control"])


@router.post("/preview", response_model=DonorFatiguePreviewResponse)
def preview_filtered_donors(
    payload: DonorFatiguePreviewRequest,
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
            candidate_donors.append({
                "donor": donor,
                "distance_km": distance,
            })
            seen_donor_ids.add(donor.id)

    total_candidates = len(candidate_donors)

    filtered_donors, cooldown_filtered, decline_filtered = filter_donors_by_fatigue(
        db, candidate_donors, allow_emergency_bypass=False
    )

    emergency_fallback = False

    if len(filtered_donors) == 0 and total_candidates > 0:
        emergency_fallback = True
        candidate_donors_expanded = []
        expanded_seen = set()

        for donor in eligible_donors:
            if donor.id in expanded_seen:
                continue

            distance = haversine_distance(
                hospital.latitude,
                hospital.longitude,
                donor.latitude,
                donor.longitude,
            )

            if distance <= 30.0:
                candidate_donors_expanded.append({
                    "donor": donor,
                    "distance_km": distance,
                })
                expanded_seen.add(donor.id)

        if len(candidate_donors_expanded) > 0:
            filtered_donors, _, _ = filter_donors_by_fatigue(
                db, candidate_donors_expanded, allow_emergency_bypass=False
            )

        if len(filtered_donors) == 0:
            top_reliability = sorted(
                candidate_donors,
                key=lambda d: d["donor"].reliability_score,
                reverse=True
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
    
    selected = unique_ranked[:payload.max_donors]

    recommended = []
    for item in selected:
        donor = item["donor"]
        recommended.append(
            FilteredDonor(
                donor_id=donor.id,
                user_id=donor.user_id,
                blood_group=donor.blood_group,
                reliability_score=donor.reliability_score,
                distance_km=item["distance_km"],
                last_alert_time=item.get("last_alert_time"),
                total_donations=donor.total_donations,
                is_eligible=donor.is_eligible,
                cooldown_active=item.get("cooldown_active", False),
                decline_suppression_active=item.get("decline_suppression_active", False),
            )
        )

    return DonorFatiguePreviewResponse(
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        search_radius_km=payload.search_radius_km,
        total_candidates=total_candidates,
        filtered_by_cooldown=cooldown_filtered,
        filtered_by_decline=decline_filtered,
        remaining_donors=len(unique_ranked),
        emergency_fallback_triggered=emergency_fallback,
        recommended_donors=recommended,
    )