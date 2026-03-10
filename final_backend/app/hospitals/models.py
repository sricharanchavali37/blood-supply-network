from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, DateTime, Enum
from sqlalchemy.orm import relationship
from app.core.models import BaseModel
import enum

class RequestUrgency(enum.Enum):
    routine = "routine"
    urgent = "urgent"
    critical = "critical"
    emergency = "emergency"

class RequestStatus(enum.Enum):
    pending = "pending"
    reserved = "reserved"
    fulfilled = "fulfilled"
    cancelled = "cancelled"

class TransferStatus(enum.Enum):
    proposed = "proposed"
    accepted = "accepted"
    in_transit = "in_transit"
    completed = "completed"
    cancelled = "cancelled"

class Hospital(BaseModel):
    __tablename__ = "hospitals"
    
    name = Column(String(255), nullable=False, unique=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    contact_email = Column(String(255), nullable=False)
    contact_phone = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    blood_units = relationship("BloodUnit", back_populates="hospital")
    blood_requests = relationship("BloodRequest", back_populates="hospital")
    metrics = relationship("HospitalMetricsDaily", back_populates="hospital")
    outgoing_transfers = relationship("Transfer", foreign_keys="Transfer.from_hospital_id", back_populates="from_hospital")
    incoming_transfers = relationship("Transfer", foreign_keys="Transfer.to_hospital_id", back_populates="to_hospital")
    

class BloodRequest(BaseModel):
    __tablename__ = "blood_requests"
    
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    blood_group = Column(String(5), nullable=False, index=True)
    quantity_required = Column(Integer, nullable=False)
    urgency = Column(Enum(RequestUrgency), default=RequestUrgency.routine, nullable=False)
    status = Column(Enum(RequestStatus), default=RequestStatus.pending, nullable=False, index=True)
    requested_at = Column(DateTime(timezone=True), nullable=False)
    fulfilled_at = Column(DateTime(timezone=True))
    
    hospital = relationship("Hospital", back_populates="blood_requests")

class Transfer(BaseModel):
    __tablename__ = "transfers"
    
    from_hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    to_hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    blood_group = Column(String(5), nullable=False)
    quantity_ml = Column(Integer, nullable=False)
    status = Column(Enum(TransferStatus), default=TransferStatus.proposed, nullable=False, index=True)
    initiated_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    
    from_hospital = relationship("Hospital", foreign_keys=[from_hospital_id], back_populates="outgoing_transfers")
    to_hospital = relationship("Hospital", foreign_keys=[to_hospital_id], back_populates="incoming_transfers")
