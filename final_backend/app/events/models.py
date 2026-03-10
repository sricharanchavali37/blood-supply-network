# app/events/models.py
#
# Lightweight, append-only event log. Every domain action that matters for
# observability (blood unit lifecycle, alert creation, donor responses,
# decision engine runs) records a row here. The table is intentionally
# decoupled from all business logic: failures in this module NEVER surface
# to API callers.

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.base import Base


class SystemEvent(Base):
    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # What happened — e.g. UNIT_COLLECTED, ALERT_CREATED, DONOR_ACCEPTED
    event_type = Column(String(80), nullable=False, index=True)

    # Which domain object this event is about — e.g. "blood_unit", "alert", "donor"
    entity_type = Column(String(60), nullable=False, index=True)

    # The DB id of that object (nullable so we can log pre-insert events)
    entity_id = Column(Integer, nullable=True, index=True)

    # Which authenticated user triggered the action (nullable for background tasks)
    actor_user_id = Column(Integer, nullable=True, index=True)

    # Wall-clock time (UTC, with timezone) — default set in the DB for accuracy
    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Arbitrary context — blood group, hospital name, response type, etc.
    # Using PostgreSQL JSONB for efficient storage and querying.
    metadata_json = Column(JSONB, nullable=True)
