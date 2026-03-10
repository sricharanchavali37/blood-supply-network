from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func
from app.core.base import Base as SQLAlchemyBase

class BaseModel(SQLAlchemyBase):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)