from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import List, Dict
from app.donors.models import Donor, DonorResponse, DonorResponseType


def get_last_alert_time(db: Session, donor_id: int) -> datetime | None:
    """Get the timestamp of the last alert received by donor."""
    # DonorResponse uses `responded_at` (not `created_at`)
    # We fall back to the BaseModel `created_at` when responded_at is NULL
    last_response = (
        db.query(DonorResponse)
        .filter(DonorResponse.donor_id == donor_id)
        .order_by(DonorResponse.created_at.desc())
        .first()
    )
    if last_response is None:
        return None
    return last_response.responded_at or last_response.created_at


def get_last_decline_time(db: Session, donor_id: int) -> datetime | None:
    """Get the timestamp of the last declined alert by donor."""
    last_decline = (
        db.query(DonorResponse)
        .filter(
            DonorResponse.donor_id == donor_id,
            DonorResponse.response_type == DonorResponseType.declined,
        )
        .order_by(DonorResponse.created_at.desc())
        .first()
    )
    if last_decline is None:
        return None
    return last_decline.responded_at or last_decline.created_at


def filter_donors_by_fatigue(
    db: Session,
    candidate_donors: List[Dict],
    allow_emergency_bypass: bool = False,
) -> tuple[List[Dict], int, int]:
    """
    Filter donors based on cooldown and decline suppression rules.

    Returns:
        (filtered_donors, cooldown_filtered_count, decline_filtered_count)
    """
    now = datetime.now(timezone.utc)
    cooldown_threshold = now - timedelta(hours=24)
    decline_threshold = now - timedelta(hours=48)

    filtered_donors = []
    cooldown_filtered = 0
    decline_filtered = 0

    for item in candidate_donors:
        donor = item["donor"]

        last_alert_time = get_last_alert_time(db, donor.id)
        last_decline_time = get_last_decline_time(db, donor.id)

        cooldown_active = last_alert_time is not None and last_alert_time > cooldown_threshold
        decline_active = last_decline_time is not None and last_decline_time > decline_threshold

        if allow_emergency_bypass:
            filtered_donors.append({
                **item,
                "last_alert_time": last_alert_time,
                "cooldown_active": cooldown_active,
                "decline_suppression_active": decline_active,
            })
        else:
            if cooldown_active:
                cooldown_filtered += 1
                continue

            if decline_active:
                decline_filtered += 1
                continue

            filtered_donors.append({
                **item,
                "last_alert_time": last_alert_time,
                "cooldown_active": False,
                "decline_suppression_active": False,
            })

    return filtered_donors, cooldown_filtered, decline_filtered


def rank_donors(donors: List[Dict]) -> List[Dict]:
    """
    Rank donors by:
    1. reliability_score DESC
    2. last_alert_time ASC (None values last)
    """
    # Use a timezone-aware sentinel for None values so comparison with
    # timezone-aware last_alert_time values never raises TypeError.
    _SENTINEL = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    return sorted(
        donors,
        key=lambda d: (
            -d["donor"].reliability_score,
            d["last_alert_time"] if d["last_alert_time"] else _SENTINEL,
        ),
    )
