import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.alerts.models import Alert, AlertStatus


def expire_old_alerts() -> dict:
    """
    Scans all active alerts. Marks alerts older than 24 hours as expired.
    Returns count of expired alerts.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    expiry_threshold = now - timedelta(hours=24)
    expired_count = 0

    try:
        active_alerts = (
            db.query(Alert)
            .filter(
                Alert.status == AlertStatus.active,
                Alert.sent_at < expiry_threshold,
            )
            .all()
        )

        for alert in active_alerts:
            alert.status = AlertStatus.expired
            expired_count += 1

        db.commit()
        print(f"[Alert Expiry] Marked {expired_count} alerts as expired at {now}")
        return {"expired_count": expired_count, "scan_time": str(now)}

    except Exception as e:
        db.rollback()
        print(f"[Alert Expiry] Error during scan: {e}")
        raise
    finally:
        db.close()


async def alert_expiry_loop():
    """
    Background coroutine that runs expire_old_alerts every 6 hours.
    Started once on application startup via asyncio.create_task().
    """
    INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours

    while True:
        try:
            expire_old_alerts()
        except Exception as e:
            print(f"[Alert Expiry Loop] Unhandled error: {e}")
        await asyncio.sleep(INTERVAL_SECONDS)