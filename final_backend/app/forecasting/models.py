from sqlalchemy import Column, Integer, String, Date, Float
from app.core.models import BaseModel

class ForecastResult(BaseModel):
    __tablename__ = "forecast_results"
    
    blood_group = Column(String(5), nullable=False, index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    predicted_demand = Column(Float, nullable=False)
    confidence_score = Column(Float)
    model_version = Column(String(50))