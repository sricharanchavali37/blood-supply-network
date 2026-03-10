import asyncio
from datetime import date
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.donors.models import Donor


def recalculate_donor_eligibility() -> dict:
    """
    Scans all donors. Sets is_eligible = True when next_eligible_date <= today.
    Returns count of donors updated.
    """
    db: Session = SessionLocal()
    today = date.today()
    updated_count = 0

    try:
        ineligible_donors = (
            db.query(Donor)
            .filter(
                Donor.is_eligible == False,
                Donor.next_eligible_date <= today
            )
            .all()
        )

        for donor in ineligible_donors:
            donor.is_eligible = True
            updated_count += 1

        db.commit()
        print(f"[Eligibility Recalculation] Updated {updated_count} donors to eligible on {today}")
        return {"updated_count": updated_count, "recalc_date": str(today)}

    except Exception as e:
        db.rollback()
        print(f"[Eligibility Recalculation] Error during recalculation: {e}")
        raise
    finally:
        db.close()


async def eligibility_recalc_loop():
    """
    Background coroutine that runs recalculate_donor_eligibility once per day.
    Started once on application startup via asyncio.create_task().
    """
    INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours

    while True:
        try:
            recalculate_donor_eligibility()
        except Exception as e:
            print(f"[Eligibility Recalc Loop] Unhandled error: {e}")
        await asyncio.sleep(INTERVAL_SECONDS)