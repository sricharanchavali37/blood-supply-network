from sqlalchemy import Column, Integer, Date, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.core.models import BaseModel

class SystemMetricsDaily(BaseModel):
    __tablename__ = "system_metrics_daily"
    
    date = Column(Date, nullable=False, unique=True, index=True)
    total_available_units = Column(Integer, default=0)
    total_expired_units = Column(Integer, default=0)
    total_wasted_units = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)
    fulfilled_requests = Column(Integer, default=0)
    fulfillment_rate = Column(Float, default=0.0)
    wastage_rate = Column(Float, default=0.0)
    availability_health_score = Column(Float, default=0.0)
    system_health_score = Column(Float, default=0.0)

class HospitalMetricsDaily(BaseModel):
    __tablename__ = "hospital_metrics_daily"
    
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    fulfillment_rate = Column(Float, default=0.0)
    wastage_rate = Column(Float, default=0.0)
    transfer_efficiency = Column(Float, default=0.0)
    alert_response_efficiency = Column(Float, default=0.0)
    
    hospital = relationship("Hospital", back_populates="metrics")