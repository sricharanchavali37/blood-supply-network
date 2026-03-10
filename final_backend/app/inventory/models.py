from sqlalchemy import Column, Integer, String, ForeignKey, Date, Enum
from sqlalchemy.orm import relationship
from app.core.models import BaseModel
import enum

class BloodUnitStatus(enum.Enum):
    available = "available"
    reserved = "reserved"
    used = "used"
    expired = "expired"
    wasted = "wasted"

class BloodUnit(BaseModel):
    __tablename__ = "blood_units"
    
    blood_group = Column(String(5), nullable=False, index=True)
    quantity_ml = Column(Integer, nullable=False)
    collection_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)
    status = Column(Enum(BloodUnitStatus), default=BloodUnitStatus.available, nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    
    hospital = relationship("Hospital", back_populates="blood_units")