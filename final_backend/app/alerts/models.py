from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from app.core.models import BaseModel
import enum

class AlertType(enum.Enum):
    shortage = "shortage"
    donor_request = "donor_request"
    transfer_suggestion = "transfer_suggestion"

class AlertSeverity(enum.Enum):
    low = "low"
    critical = "critical"
    emergency = "emergency"

class AlertStatus(enum.Enum):
    active = "active"
    fulfilled = "fulfilled"
    expired = "expired"

class TargetType(enum.Enum):
    donor = "donor"
    hospital = "hospital"

class Alert(BaseModel):
    __tablename__ = "alerts"

    alert_type = Column(Enum(AlertType), nullable=False, index=True)
    blood_group = Column(String(5), nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False, index=True)
    target_type = Column(Enum(TargetType), nullable=False)
    target_id = Column(Integer, nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(Enum(AlertStatus), default=AlertStatus.active, nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True))

    # Use back_populates instead of backref to avoid conflicts with donors.models
    donor_responses = relationship(
        "DonorResponse",
        back_populates="alert",
        foreign_keys="DonorResponse.alert_id",
    )
