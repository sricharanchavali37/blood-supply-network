# app/main.py
#
# FIX — Requirement 7:
# GET /health now returns {"status": "ok"} (was {"status": "healthy"}).
# The integration test script checks for {"status": "ok"} in the pre-flight step.
#
# FIX — Requirement 6:
# app/events/models.py is imported at startup so Base.metadata includes the
# system_events table and create_all() creates it automatically.

import asyncio

from fastapi import FastAPI
from app.core.database import engine, Base
from app.core.redis import redis_client
from app.auth.routes import router as auth_router
from app.hospitals.routes import router as hospitals_router
from app.inventory.routes import router as inventory_router
from app.donors.routes import router as donors_router
from app.shortage.routes import router as shortage_router
from app.alerts.routes import router as alerts_router
from app.supply_intelligence.routes import router as supply_intelligence_router
from app.donor_fatigue_control.routes import router as donor_fatigue_router
from app.shortage_prediction.routes import router as shortage_prediction_router
from app.decision_engine.routes import router as decision_engine_router
from app.analytics.routes import router as analytics_router
from app.inventory.tasks import expiry_scan_loop
from app.donors.tasks import eligibility_recalc_loop
from app.alerts.tasks import alert_expiry_loop
import uvicorn

app = FastAPI(
    title="Smart Blood Network",
    description="AI-Driven Blood Supply Intelligence Platform",
    version="1.0.0"
)

app.include_router(auth_router)
app.include_router(hospitals_router)
app.include_router(inventory_router)
app.include_router(donors_router)
app.include_router(shortage_router)
app.include_router(alerts_router)
app.include_router(supply_intelligence_router)
app.include_router(donor_fatigue_router)
app.include_router(shortage_prediction_router)
app.include_router(decision_engine_router)
app.include_router(analytics_router)

_expiry_task     = None
_eligibility_task = None
_alert_expiry_task = None


@app.on_event("startup")
async def startup_event():
    global _expiry_task, _eligibility_task, _alert_expiry_task

    # Ensure all SQLAlchemy models are registered before create_all() runs.
    import app.core.models       # noqa: F401
    import app.auth.models       # noqa: F401
    import app.hospitals.models  # noqa: F401
    import app.donors.models     # noqa: F401
    import app.inventory.models  # noqa: F401
    import app.alerts.models     # noqa: F401
    import app.analytics.models  # noqa: F401
    import app.emergency.models  # noqa: F401
    import app.forecasting.models # noqa: F401
    import app.events.models     # noqa: F401  ← NEW: register SystemEvent table

    print("Database URL:", engine.url.render_as_string(hide_password=True))
    print("Registered tables:", list(Base.metadata.tables.keys()))
    Base.metadata.create_all(bind=engine)

    # Seed default roles
    from app.core.database import SessionLocal
    from app.auth.models import Role

    db = SessionLocal()
    try:
        existing_roles = db.query(Role).count()
        if existing_roles == 0:
            default_roles = [
                Role(name="Super Admin",      description="Full system access"),
                Role(name="Hospital Admin",   description="Hospital management access"),
                Role(name="Lab Technician",   description="Blood bank operations"),
                Role(name="Donor",            description="Donor portal access"),
            ]
            db.add_all(default_roles)
            db.commit()
            print("✓ Default roles seeded")
        else:
            print("✓ Roles already exist, skipping seed")
    finally:
        db.close()

    # Check Redis connection
    if redis_client is not None:
        try:
            await redis_client.ping()
            print("✓ Redis connection established")
        except Exception as e:
            print(f"⚠ Redis connection failed: {e}")
            print("⚠ Rate limiting will be disabled")
    else:
        print("⚠ Redis not configured; rate limiting will be disabled")

    _expiry_task      = asyncio.create_task(expiry_scan_loop())
    _eligibility_task = asyncio.create_task(eligibility_recalc_loop())
    _alert_expiry_task = asyncio.create_task(alert_expiry_loop())

    print("✓ Database tables created")
    print("✓ Expiry scan background task started (6-hour interval)")
    print("✓ Donor eligibility recalculation task started (24-hour interval)")
    print("✓ Alert expiry task started (6-hour interval)")


@app.on_event("shutdown")
async def shutdown_event():
    global _expiry_task, _eligibility_task, _alert_expiry_task
    for task in (_expiry_task, _eligibility_task, _alert_expiry_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    if redis_client is not None:
        await redis_client.close()
    print("✓ Background tasks stopped")
    print("✓ Redis connection closed")


@app.get("/")
async def root():
    return {
        "message": "Smart Blood Network API",
        "status": "active",
        "phase": "10 - Operational Intelligence Analytics"
    }


# FIX: return {"status": "ok"} so test_pipeline.py pre-flight check passes
@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
