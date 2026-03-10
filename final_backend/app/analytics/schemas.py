from pydantic import BaseModel
from datetime import date
from typing import List


class SystemOverviewResponse(BaseModel):
    total_hospitals: int
    total_donors: int
    total_blood_units: int
    active_alerts: int
    alerts_last_24h: int
    accepted_donations_last_24h: int


class AlertPerformanceResponse(BaseModel):
    alerts_created: int
    donors_notified: int
    responses_received: int
    accepted_responses: int
    success_rate: float
    avg_response_time_minutes: float


class BloodGroupStability(BaseModel):
    blood_group: str
    shortage_count_30_days: int
    avg_inventory_units: float


class BloodGroupStabilityResponse(BaseModel):
    stability_data: List[BloodGroupStability]


class DonorLeaderboardEntry(BaseModel):
    donor_id: int
    reliability_score: float
    total_alerts_received: int
    total_responses: int
    accepted_responses: int


class DonorLeaderboardResponse(BaseModel):
    leaderboard: List[DonorLeaderboardEntry]


class HospitalShortageSummary(BaseModel):
    hospital_id: int
    hospital_name: str
    shortage_count: int
    donor_alerts_triggered: int


class HospitalShortageSummaryResponse(BaseModel):
    hospitals: List[HospitalShortageSummary]


class DonationActivityEntry(BaseModel):
    date: date
    accepted_donations: int
    responses: int
    alerts_triggered: int


class DonationActivityHeatmapResponse(BaseModel):
    activity_data: List[DonationActivityEntry]