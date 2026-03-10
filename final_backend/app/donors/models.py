from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, Float, DateTime, Enum, func
from sqlalchemy.orm import relationship
from app.core.base import Base
import enum


class DonorResponseType(str, enum.Enum):
    accepted = "accepted"
    declined = "declined"
    no_response = "no_response"


class Donor(Base):
    __tablename__ = "donors"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    blood_group = Column(String(5), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_eligible = Column(Boolean, default=True, nullable=False)
    last_donation_date = Column(Date)
    next_eligible_date = Column(Date)
    reliability_score = Column(Float, default=0.0)
    total_donations = Column(Integer, default=0)
    total_alerts_received = Column(Integer, default=0)
    total_responses = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    responses = relationship("DonorResponse", back_populates="donor")


class DonorResponse(Base):
    __tablename__ = "donor_responses"

    id = Column(Integer, primary_key=True, index=True)

    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)

    response_type = Column(Enum(DonorResponseType), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    donor = relationship("Donor", back_populates="responses")
    alert = relationship("Alert", back_populates="donor_responses")
