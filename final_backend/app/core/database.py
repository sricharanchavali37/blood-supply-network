from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.base import Base
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import all model modules so Base.metadata is populated before create_all() runs.
# Order: core.models first (BaseModel), then domain models that use it.
import app.core.models  # noqa: E402,F401
import app.auth.models  # noqa: E402,F401
import app.analytics.models  # noqa: E402,F401
import app.hospitals.models  # noqa: E402,F401
import app.inventory.models  # noqa: E402,F401
import app.donors.models  # noqa: E402,F401
import app.alerts.models  # noqa: E402,F401
import app.emergency.models   # noqa: E402,F401
import app.forecasting.models  # noqa: E402,F401
import app.events.models       # noqa: E402,F401  register system_events table

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
