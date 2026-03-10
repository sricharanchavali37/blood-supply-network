# app/events/logger.py
#
# Single public function: log_event()
#
# Design contract:
#   • NEVER raises. All exceptions are caught and printed to stderr.
#   • Uses its own db.flush() rather than db.commit() so it participates in the
#     caller's transaction when convenient, but failures are isolated.
#   • Callers wrap calls in try/except if they want belt-and-suspenders safety.

import traceback
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.events.models import SystemEvent


def log_event(
    db: Session,
    event_type: str,
    entity_type: str,
    entity_id: Optional[int],
    actor_user_id: Optional[int],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a SystemEvent row to the database.

    This function is intentionally fault-tolerant: it must never propagate
    exceptions to callers. If the INSERT fails for any reason the failure is
    logged to stderr and execution continues normally.

    Args:
        db:             Active SQLAlchemy session.
        event_type:     Short SCREAMING_SNAKE_CASE label, e.g. "UNIT_COLLECTED".
        entity_type:    Domain noun in snake_case, e.g. "blood_unit".
        entity_id:      PK of the affected row (can be None for pre-insert events).
        actor_user_id:  ID of the authenticated user who triggered the action.
        metadata:       Arbitrary JSON-serialisable dict for context.
    """
    try:
        event = SystemEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            metadata_json=metadata or {},
        )
        db.add(event)
        db.flush()          # Write to DB inside the current transaction.
                            # Caller's db.commit() persists it; caller's
                            # db.rollback() rolls it back too — which is correct
                            # because we don't want orphaned events for failed ops.
    except Exception:       # noqa: BLE001
        # Log to stderr but DO NOT re-raise — logging must never kill the pipeline.
        traceback.print_exc()
