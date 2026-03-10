# app/inventory/routes.py
#
# FIXES applied:
# 1. log_event() added for UNIT_COLLECTED — wrapped in try/except so it never
#    breaks the blood unit creation pipeline.
# 2. All db.commit() calls already had rollback guards; verified correct.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import date, timedelta
from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.hospitals.models import Hospital
from app.inventory.models import BloodUnit, BloodUnitStatus
from app.inventory.schemas import (
    BloodUnitCreate,
    BloodUnitResponse,
    BloodUnitUse,
    AvailabilityResponse,
    AvailabilitySummaryResponse,
)

SHELF_LIFE_DAYS = 42

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def check_inventory_role(current_user: User = Depends(get_current_user)):
    allowed_roles = ["Hospital Admin", "Lab Technician"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Requires Hospital Admin or Lab Technician role"
        )
    return current_user


@router.post("/units", response_model=BloodUnitResponse, status_code=status.HTTP_201_CREATED)
def create_blood_unit(
    payload: BloodUnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_inventory_role),
):
    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    expiry_date = payload.collection_date + timedelta(days=SHELF_LIFE_DAYS)

    unit = BloodUnit(
        blood_group=payload.blood_group,
        quantity_ml=payload.quantity_ml,
        collection_date=payload.collection_date,
        expiry_date=expiry_date,
        status=BloodUnitStatus.available,
        hospital_id=payload.hospital_id,
    )
    db.add(unit)
    try:
        db.commit()
        db.refresh(unit)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate blood unit record"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create blood unit: {str(e)}"
        )

    # Log event — must never break the pipeline
    try:
        from app.events.logger import log_event
        log_event(
            db,
            event_type="UNIT_COLLECTED",
            entity_type="blood_unit",
            entity_id=unit.id,
            actor_user_id=current_user.id,
            metadata={
                "blood_group": unit.blood_group,
                "quantity_ml": unit.quantity_ml,
                "hospital_id": unit.hospital_id,
                "expiry_date": str(unit.expiry_date),
            },
        )
        db.commit()
    except Exception:
        pass  # logging failure must never surface to API caller

    return unit


@router.post("/units/use", response_model=list[BloodUnitResponse])
def use_blood_units(
    payload: BloodUnitUse,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_inventory_role),
):
    hospital = db.query(Hospital).filter(Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {payload.hospital_id} not found"
        )

    today = date.today()
    used_units = []

    try:
        with db.begin_nested():
            available_units = (
                db.query(BloodUnit)
                .filter(
                    BloodUnit.blood_group == payload.blood_group,
                    BloodUnit.hospital_id == payload.hospital_id,
                    BloodUnit.status == BloodUnitStatus.available,
                    BloodUnit.expiry_date >= today,
                )
                .order_by(BloodUnit.expiry_date.asc())
                .with_for_update()
                .all()
            )

            total_available_ml = sum(u.quantity_ml for u in available_units)
            if total_available_ml < payload.quantity_ml:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient blood supply. Available: {total_available_ml}ml, Requested: {payload.quantity_ml}ml",
                )

            ml_consumed = 0
            for unit in available_units:
                if ml_consumed >= payload.quantity_ml:
                    break
                unit.status = BloodUnitStatus.used
                ml_consumed += unit.quantity_ml
                used_units.append(unit)

        db.commit()
        for u in used_units:
            db.refresh(u)
        return used_units

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during blood unit consumption: {str(e)}"
        )


@router.get("/availability/{hospital_id}/{blood_group}", response_model=AvailabilityResponse)
def get_availability(
    hospital_id: int,
    blood_group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_inventory_role),
):
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {hospital_id} not found"
        )

    blood_group_upper = blood_group.upper()
    valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if blood_group_upper not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid blood_group. Must be one of {valid}"
        )

    today = date.today()
    seven_days = today + timedelta(days=7)

    available_units = (
        db.query(BloodUnit)
        .filter(
            BloodUnit.hospital_id == hospital_id,
            BloodUnit.blood_group == blood_group_upper,
            BloodUnit.status == BloodUnitStatus.available,
            BloodUnit.expiry_date >= today,
        )
        .all()
    )

    total_available_units = len(available_units)
    total_available_ml   = sum(u.quantity_ml for u in available_units)
    expiring_next_7      = sum(1 for u in available_units if u.expiry_date <= seven_days)
    expiry_risk_ratio    = (
        round(expiring_next_7 / total_available_units, 4)
        if total_available_units > 0 else 0.0
    )

    return AvailabilityResponse(
        hospital_id=hospital_id,
        blood_group=blood_group_upper,
        total_available_units=total_available_units,
        total_available_ml=total_available_ml,
        expiring_next_7_days=expiring_next_7,
        expiry_risk_ratio=expiry_risk_ratio,
    )


@router.get("/availability/{hospital_id}", response_model=AvailabilitySummaryResponse)
def get_availability_summary(
    hospital_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_inventory_role),
):
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {hospital_id} not found"
        )

    today       = date.today()
    seven_days  = today + timedelta(days=7)
    blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    summary = []

    for bg in blood_groups:
        units = (
            db.query(BloodUnit)
            .filter(
                BloodUnit.hospital_id == hospital_id,
                BloodUnit.blood_group == bg,
                BloodUnit.status == BloodUnitStatus.available,
                BloodUnit.expiry_date >= today,
            )
            .all()
        )
        total_units = len(units)
        total_ml    = sum(u.quantity_ml for u in units)
        expiring_7  = sum(1 for u in units if u.expiry_date <= seven_days)
        risk_ratio  = round(expiring_7 / total_units, 4) if total_units > 0 else 0.0

        summary.append(
            AvailabilityResponse(
                hospital_id=hospital_id,
                blood_group=bg,
                total_available_units=total_units,
                total_available_ml=total_ml,
                expiring_next_7_days=expiring_7,
                expiry_risk_ratio=risk_ratio,
            )
        )

    return AvailabilitySummaryResponse(hospital_id=hospital_id, summary=summary)


@router.get("/units/{hospital_id}", response_model=list[BloodUnitResponse])
def list_units(
    hospital_id: int,
    blood_group: str | None = None,
    unit_status: BloodUnitStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_inventory_role),
):
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with id {hospital_id} not found"
        )

    query = db.query(BloodUnit).filter(BloodUnit.hospital_id == hospital_id)

    if blood_group:
        blood_group_upper = blood_group.upper()
        valid = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if blood_group_upper not in valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid blood_group. Must be one of {valid}"
            )
        query = query.filter(BloodUnit.blood_group == blood_group_upper)

    if unit_status:
        query = query.filter(BloodUnit.status == unit_status)

    return query.order_by(BloodUnit.expiry_date.asc()).all()
