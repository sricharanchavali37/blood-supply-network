from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.hospitals.models import Hospital
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])

# Roles allowed to create/update hospitals
HOSPITAL_ADMIN_ROLES = ["Super Admin", "Hospital Admin"]


def check_hospital_admin_role(current_user: User = Depends(get_current_user)) -> User:
    """Require Super Admin or Hospital Admin for create/update hospital."""
    if current_user.role.name not in HOSPITAL_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Requires Super Admin or Hospital Admin role",
        )
    return current_user


class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    latitude: float = Field(..., ge=-90, le=90, description="Latitude -90 to 90")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude -180 to 180")
    contact_email: EmailStr
    contact_phone: str = Field(..., min_length=1, max_length=20)

    class Config:
        from_attributes = True


class HospitalResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    contact_email: str
    contact_phone: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED)
def create_hospital(
    payload: HospitalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_hospital_admin_role),
):
    existing = db.query(Hospital).filter(Hospital.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hospital with this name already exists",
        )
    hospital = Hospital(
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        is_active=True,
    )
    db.add(hospital)
    try:
        db.commit()
        db.refresh(hospital)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hospital with this name already exists",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create hospital",
        )
    return hospital


@router.get("", response_model=List[HospitalResponse])
def list_hospitals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Hospital).all()


@router.get("/{hospital_id}", response_model=HospitalResponse)
def get_hospital(
    hospital_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {hospital_id} not found"
        )
    return hospital

