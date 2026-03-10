# app/inventory/tasks.py
#
# FIX: Added log_event() for UNIT_EXPIRED — wrapped in try/except per the
# requirement that event logging must never break the background task.

import asyncio
from datetime import date
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.inventory.models import BloodUnit, BloodUnitStatus


def mark_expired_units() -> dict:
    """
    Scans all available blood units. Any unit whose expiry_date is before
    today is marked as expired. Logs a UNIT_EXPIRED event for each.
    """
    db: Session = SessionLocal()
    today = date.today()
    expired_count = 0

    try:
        expired_units = (
            db.query(BloodUnit)
            .filter(
                BloodUnit.status == BloodUnitStatus.available,
                BloodUnit.expiry_date < today,
            )
            .all()
        )

        for unit in expired_units:
            unit.status = BloodUnitStatus.expired
            expired_count += 1

        db.commit()
        print(f"[Expiry Scan] Marked {expired_count} units as expired on {today}")

        # Log events after commit so unit.id is stable
        if expired_count > 0:
            try:
                from app.events.logger import log_event
                for unit in expired_units:
                    log_event(
                        db,
                        event_type="UNIT_EXPIRED",
                        entity_type="blood_unit",
                        entity_id=unit.id,
                        actor_user_id=None,
                        metadata={
                            "blood_group": unit.blood_group,
                            "hospital_id": unit.hospital_id,
                            "expiry_date": str(unit.expiry_date),
                        },
                    )
                db.commit()
            except Exception as e:
                # Roll back any partial event flushes so the session stays
                # clean for the next background cycle. Without this the
                # PostgreSQL transaction is left in an "aborted" state and
                # every subsequent statement on the same connection will fail
                # until the connection is recycled from the pool.
                db.rollback()
                print(f"[Expiry Scan] Event logging failed (non-fatal): {e}")

        return {"expired_count": expired_count, "scan_date": str(today)}

    except Exception as e:
        db.rollback()
        print(f"[Expiry Scan] Error during scan: {e}")
        raise
    finally:
        db.close()


async def expiry_scan_loop():
    """
    Background coroutine that runs mark_expired_units every 6 hours.
    Started once on application startup via asyncio.create_task().
    """
    INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
    while True:
        try:
            mark_expired_units()
        except Exception as e:
            print(f"[Expiry Scan Loop] Unhandled error: {e}")
        await asyncio.sleep(INTERVAL_SECONDS)
