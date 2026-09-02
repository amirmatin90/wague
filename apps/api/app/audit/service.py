from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent


def write_audit(
    session: Session,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
) -> None:
    clean = dict(payload or {})
    clean.pop("cloid", None)
    clean.pop("oid", None)
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=clean,
        )
    )
