from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.analytics.schemas import (
    SystemOverviewResponse,
    AlertPerformanceResponse,
    BloodGroupStabilityResponse,
    BloodGroupStability,
    DonorLeaderboardResponse,
    DonorLeaderboardEntry,
    HospitalShortageSummaryResponse,
    HospitalShortageSummary,
    DonationActivityHeatmapResponse,
    DonationActivityEntry,
)
from app.analytics.queries import (
    get_system_overview,
    get_alert_performance,
    get_blood_group_stability,
    get_donor_leaderboard,
    get_hospital_shortage_summary,
    get_donation_activity_heatmap,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/system-overview", response_model=SystemOverviewResponse)
def system_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_system_overview(db)
    return SystemOverviewResponse(**data)


@router.get("/alert-performance", response_model=AlertPerformanceResponse)
def alert_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_alert_performance(db)
    return AlertPerformanceResponse(**data)


@router.get("/blood-group-stability", response_model=BloodGroupStabilityResponse)
def blood_group_stability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_blood_group_stability(db)
    stability_data = [BloodGroupStability(**item) for item in data]
    return BloodGroupStabilityResponse(stability_data=stability_data)


@router.get("/donor-leaderboard", response_model=DonorLeaderboardResponse)
def donor_leaderboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_donor_leaderboard(db)
    leaderboard = [DonorLeaderboardEntry(**item) for item in data]
    return DonorLeaderboardResponse(leaderboard=leaderboard)


@router.get("/hospital-shortage-summary", response_model=HospitalShortageSummaryResponse)
def hospital_shortage_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_hospital_shortage_summary(db)
    hospitals = [HospitalShortageSummary(**item) for item in data]
    return HospitalShortageSummaryResponse(hospitals=hospitals)


@router.get("/donation-activity", response_model=DonationActivityHeatmapResponse)
def donation_activity_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_donation_activity_heatmap(db)
    activity_data = [DonationActivityEntry(**item) for item in data]
    return DonationActivityHeatmapResponse(activity_data=activity_data)