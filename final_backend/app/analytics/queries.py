from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, date, timezone
from app.hospitals.models import Hospital
from app.donors.models import Donor, DonorResponse, DonorResponseType
from app.inventory.models import BloodUnit, BloodUnitStatus
from app.alerts.models import Alert, AlertStatus, AlertType


def get_system_overview(db: Session) -> dict:
    """Calculate system-wide overview statistics — safe when tables are empty."""
    total_hospitals = db.query(func.count(Hospital.id)).scalar() or 0
    total_donors = db.query(func.count(Donor.id)).scalar() or 0

    today = date.today()
    total_blood_units = (
        db.query(func.count(BloodUnit.id))
        .filter(
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .scalar()
    ) or 0

    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.status == AlertStatus.active)
        .scalar()
    ) or 0

    last_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    alerts_last_24h = (
        db.query(func.count(Alert.id))
        .filter(Alert.sent_at >= last_24h)
        .scalar()
    ) or 0

    accepted_donations_last_24h = (
        db.query(func.count(DonorResponse.id))
        .filter(
            DonorResponse.response_type == DonorResponseType.accepted,
            DonorResponse.responded_at.isnot(None),
            DonorResponse.responded_at >= last_24h,
        )
        .scalar()
    ) or 0

    return {
        "total_hospitals": total_hospitals,
        "total_donors": total_donors,
        "total_blood_units": total_blood_units,
        "active_alerts": active_alerts,
        "alerts_last_24h": alerts_last_24h,
        "accepted_donations_last_24h": accepted_donations_last_24h,
    }


def get_alert_performance(db: Session) -> dict:
    """Calculate alert system performance metrics — safe when tables are empty."""
    alerts_created = db.query(func.count(Alert.id)).scalar() or 0
    donors_notified = db.query(func.count(DonorResponse.id)).scalar() or 0

    responses_received = (
        db.query(func.count(DonorResponse.id))
        .filter(DonorResponse.response_type != DonorResponseType.no_response)
        .scalar()
    ) or 0

    accepted_responses = (
        db.query(func.count(DonorResponse.id))
        .filter(DonorResponse.response_type == DonorResponseType.accepted)
        .scalar()
    ) or 0

    success_rate = (
        round(accepted_responses / donors_notified, 4)
        if donors_notified > 0
        else 0.0
    )

    # Only fetch response-time data when there is data — avoids crash on empty join
    avg_response_time_minutes = 0.0
    if responses_received > 0:
        response_data = (
            db.query(
                DonorResponse.responded_at,
                Alert.sent_at,
            )
            .join(Alert, DonorResponse.alert_id == Alert.id)
            .filter(
                DonorResponse.response_type != DonorResponseType.no_response,
                DonorResponse.responded_at.isnot(None),
            )
            .all()
        )

        if response_data:
            response_times = []
            for row in response_data:
                try:
                    # Normalize both datetimes to UTC-naive for arithmetic
                    # to avoid TypeError when one is tz-aware and one is not.
                    responded = row.responded_at
                    sent = row.sent_at
                    if responded is not None and sent is not None:
                        if hasattr(responded, "tzinfo") and responded.tzinfo is not None:
                            responded = responded.replace(tzinfo=None)
                        if hasattr(sent, "tzinfo") and sent.tzinfo is not None:
                            sent = sent.replace(tzinfo=None)
                        delta = (responded - sent).total_seconds() / 60
                        response_times.append(delta)
                except Exception:
                    pass
            if response_times:
                avg_response_time_minutes = round(
                    sum(response_times) / len(response_times), 2
                )

    return {
        "alerts_created": alerts_created,
        "donors_notified": donors_notified,
        "responses_received": responses_received,
        "accepted_responses": accepted_responses,
        "success_rate": success_rate,
        "avg_response_time_minutes": avg_response_time_minutes,
    }


def get_blood_group_stability(db: Session) -> list:
    """Analyze supply stability across blood groups — safe when tables are empty."""
    blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

    last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
    today = date.today()

    stability_data = []

    for bg in blood_groups:
        shortage_count = (
            db.query(func.count(Alert.id))
            .filter(
                Alert.alert_type == AlertType.shortage,
                Alert.blood_group == bg,
                Alert.sent_at >= last_30_days,
            )
            .scalar()
        ) or 0

        subquery = (
            db.query(
                BloodUnit.hospital_id,
                func.count(BloodUnit.id).label("unit_count"),
            )
            .filter(
                BloodUnit.blood_group == bg,
                BloodUnit.status == BloodUnitStatus.available,
                BloodUnit.expiry_date >= today,
            )
            .group_by(BloodUnit.hospital_id)
            .subquery()
        )

        avg_inventory = (
            db.query(func.avg(subquery.c.unit_count)).scalar()
        )
        avg_inventory = float(avg_inventory) if avg_inventory is not None else 0.0

        stability_data.append({
            "blood_group": bg,
            "shortage_count_30_days": shortage_count,
            "avg_inventory_units": round(avg_inventory, 2),
        })

    return stability_data


def get_donor_leaderboard(db: Session) -> list:
    """Get top donors by reliability score — safe when table is empty."""
    donors = (
        db.query(Donor)
        .order_by(Donor.reliability_score.desc())
        .limit(10)
        .all()
    )

    leaderboard = []

    for donor in donors:
        total_responses = (
            db.query(func.count(DonorResponse.id))
            .filter(
                DonorResponse.donor_id == donor.id,
                DonorResponse.response_type != DonorResponseType.no_response,
            )
            .scalar()
        ) or 0

        accepted_responses = (
            db.query(func.count(DonorResponse.id))
            .filter(
                DonorResponse.donor_id == donor.id,
                DonorResponse.response_type == DonorResponseType.accepted,
            )
            .scalar()
        ) or 0

        leaderboard.append({
            "donor_id": donor.id,
            "reliability_score": donor.reliability_score,
            "total_alerts_received": donor.total_alerts_received,
            "total_responses": total_responses,
            "accepted_responses": accepted_responses,
        })

    return leaderboard


def get_hospital_shortage_summary(db: Session) -> list:
    """Identify hospitals with frequent shortages — safe when tables are empty."""
    hospitals = db.query(Hospital).all()

    summary = []

    for hospital in hospitals:
        shortage_count = (
            db.query(func.count(Alert.id))
            .filter(
                Alert.target_id == hospital.id,
                Alert.alert_type == AlertType.shortage,
            )
            .scalar()
        ) or 0

        # Use func.count with distinct correctly
        donor_alerts_triggered = (
            db.query(func.count(func.distinct(Alert.id)))
            .join(DonorResponse, Alert.id == DonorResponse.alert_id)
            .filter(Alert.target_id == hospital.id)
            .scalar()
        ) or 0

        summary.append({
            "hospital_id": hospital.id,
            "hospital_name": hospital.name,
            "shortage_count": shortage_count,
            "donor_alerts_triggered": donor_alerts_triggered,
        })

    summary.sort(key=lambda x: x["shortage_count"], reverse=True)

    return summary


def get_donation_activity_heatmap(db: Session) -> list:
    """Generate daily donation activity for past 365 days — safe when tables are empty."""
    end_date = date.today()
    start_date = end_date - timedelta(days=364)

    accepted_donations = (
        db.query(
            func.date(DonorResponse.responded_at).label("date"),
            func.count(DonorResponse.id).label("count"),
        )
        .filter(
            DonorResponse.response_type == DonorResponseType.accepted,
            DonorResponse.responded_at.isnot(None),
            func.date(DonorResponse.responded_at) >= start_date,
        )
        .group_by(func.date(DonorResponse.responded_at))
        .all()
    )

    responses = (
        db.query(
            func.date(DonorResponse.responded_at).label("date"),
            func.count(DonorResponse.id).label("count"),
        )
        .filter(
            DonorResponse.response_type != DonorResponseType.no_response,
            DonorResponse.responded_at.isnot(None),
            func.date(DonorResponse.responded_at) >= start_date,
        )
        .group_by(func.date(DonorResponse.responded_at))
        .all()
    )

    alerts = (
        db.query(
            func.date(Alert.sent_at).label("date"),
            func.count(Alert.id).label("count"),
        )
        .filter(func.date(Alert.sent_at) >= start_date)
        .group_by(func.date(Alert.sent_at))
        .all()
    )

    accepted_dict = {row.date: row.count for row in accepted_donations}
    responses_dict = {row.date: row.count for row in responses}
    alerts_dict = {row.date: row.count for row in alerts}

    activity_data = []
    current_date = start_date

    for _ in range(365):
        activity_data.append({
            "date": current_date,
            "accepted_donations": accepted_dict.get(current_date, 0),
            "responses": responses_dict.get(current_date, 0),
            "alerts_triggered": alerts_dict.get(current_date, 0),
        })
        current_date += timedelta(days=1)

    return activity_data
