from sqlalchemy import Column, Integer, Boolean, ForeignKey, Text, DateTime, Float
from app.core.models import BaseModel

class EmergencyState(BaseModel):
    __tablename__ = "emergency_state"
    
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    activated_at = Column(DateTime(timezone=True))
    activated_by = Column(Integer, ForeignKey("users.id"))
    reason = Column(Text)
    radius_multiplier = Column(Float, default=1.0)
    batch_size_multiplier = Column(Float, default=1.0)
    deactivated_at = Column(DateTime(timezone=True))