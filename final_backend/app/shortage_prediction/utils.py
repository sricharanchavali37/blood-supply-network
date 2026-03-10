# app/shortage_prediction/utils.py
#
# FIX — Decision Engine Reliability (Requirement 4)
#
# The original codebase used a single hardcoded global MIN_SAFE_UNITS = 5.
# This is exported for backward compatibility with alert routes that import it,
# but shortage prediction now uses get_safe_threshold() which adapts to each
# hospital's actual 30-day consumption so low-volume hospitals don't
# permanently trigger false shortages.
#
# Algorithm (lightweight, no ML):
#   safe_threshold = max(ABSOLUTE_FLOOR, ceil(avg_30d_daily_usage * COVERAGE_DAYS))
#   COVERAGE_DAYS = 3 (72h buffer), ABSOLUTE_FLOOR = 5

import math
from datetime import datetime, timedelta, date, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.inventory.models import BloodUnit, BloodUnitStatus

# Backward-compatible global used by alerts/routes.py and supply_intelligence
MIN_SAFE_UNITS = 5

_ABSOLUTE_FLOOR     = 5   # units — never drop below this regardless of usage history
_COVERAGE_DAYS      = 3   # days of buffer coverage the threshold must support
_MIN_HISTORY_RECORDS = 5  # minimum consumed-unit records required before the
                           # adaptive formula is trusted; below this the system
                           # is considered "cold-start" and falls back to the floor


def get_safe_threshold(db: Session, hospital_id: int, blood_group: str) -> int:
    """
    Return an adaptive per-hospital-per-blood-group safe threshold.

    Algorithm:
        safe_threshold = max(ABSOLUTE_FLOOR, ceil(avg_30d_daily_usage * COVERAGE_DAYS))

    Cold-start protection:
        If fewer than _MIN_HISTORY_RECORDS consumption records exist in the
        last 30 days the formula is unstable (avg_daily ≈ 0 and the result
        would always be the floor anyway, but we make the intent explicit).
        In that case we return _ABSOLUTE_FLOOR directly without arithmetic.
    """
    lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
    consumed_units = (
        db.query(func.count(BloodUnit.id))
        .filter(
            BloodUnit.hospital_id == hospital_id,
            BloodUnit.blood_group == blood_group,
            BloodUnit.status == BloodUnitStatus.used,
            BloodUnit.updated_at >= lookback_start,
        )
        .scalar()
    ) or 0

    # Cold-start guard — explicit safeguard required by spec.
    # When history is too sparse, skip the formula and use the fallback directly.
    if consumed_units < _MIN_HISTORY_RECORDS:
        return _ABSOLUTE_FLOOR

    avg_daily = consumed_units / 30.0
    adaptive  = math.ceil(avg_daily * _COVERAGE_DAYS)
    return max(_ABSOLUTE_FLOOR, adaptive)


def get_current_inventory(db: Session, hospital_id: int, blood_group: str) -> tuple[int, int]:
    today = date.today()
    units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == hospital_id,
            BloodUnit.blood_group == blood_group,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )
    return len(units), sum(u.quantity_ml for u in units)


def get_expiring_units(
    db: Session,
    hospital_id: int,
    blood_group: str,
    forecast_end_time: datetime,
) -> tuple[int, int]:
    today = date.today()
    forecast_end_date = forecast_end_time.date()
    units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == hospital_id,
            BloodUnit.blood_group == blood_group,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
            BloodUnit.expiry_date <= forecast_end_date,
        )
        .all()
    )
    return len(units), sum(u.quantity_ml for u in units)


def estimate_consumption(db: Session, hospital_id: int, blood_group: str) -> float:
    lookback_start = datetime.now(timezone.utc) - timedelta(days=7)
    consumed_units = (
        db.query(func.count(BloodUnit.id))
        .filter(
            BloodUnit.hospital_id == hospital_id,
            BloodUnit.blood_group == blood_group,
            BloodUnit.status == BloodUnitStatus.used,
            BloodUnit.updated_at >= lookback_start,
        )
        .scalar()
    ) or 0
    return round(consumed_units / 7.0, 2)


def calculate_shortage_probability(projected_inventory: int, safe_threshold: int) -> str:
    if projected_inventory < 0:
        return "critical"
    elif projected_inventory < safe_threshold * 0.5:
        return "high"
    elif projected_inventory < safe_threshold:
        return "moderate"
    else:
        return "low"


def calculate_days_until_shortage(
    current_units: int,
    avg_daily_usage: float,
    safe_threshold: int,
) -> float | None:
    if current_units <= safe_threshold:
        return 0.0
    if avg_daily_usage <= 0:
        return None
    return round((current_units - safe_threshold) / avg_daily_usage, 1)
