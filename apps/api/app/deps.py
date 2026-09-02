from __future__ import annotations

import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.identity.service import decode_token, get_user
from app.models import IdempotencyKey, User

DbSession = Annotated[Session, Depends(get_db)]


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def current_user(
    request: Request,
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = None
    if authorization:
        token = _bearer(authorization)
    elif request.query_params.get("token"):
        token = request.query_params["token"]
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "Missing bearer token")
    payload = decode_token(token)
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise ApiError(401, "UNAUTHORIZED", "Invalid session") from exc
    user = get_user(session, user_id)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Unknown principal")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: str):
    def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "This route is not available for your role")
        return user

    return _check


AdminUser = Annotated[User, Depends(require_roles("ops", "cto"))]
ClientUser = Annotated[User, Depends(require_roles("client"))]


class Idempotency:
    def __init__(self, session: Session, user: User, key: str, route: str, digest: str) -> None:
        self.session = session
        self.user = user
        self.key = key
        self.route = route
        self.digest = digest
        self.cached: dict | None = None
        self.cached_status: int | None = None
        existing = session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id, IdempotencyKey.key == key
            )
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise ApiError(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency-Key was reused with a different request",
                )
            self.cached = existing.response_json
            self.cached_status = existing.status_code

    def store(self, status_code: int, body: dict) -> None:
        if self.cached is not None:
            return
        self.session.add(
            IdempotencyKey(
                user_id=self.user.id,
                key=self.key,
                route=self.route,
                request_digest=self.digest,
                status_code=status_code,
                response_json=body,
            )
        )


def require_idempotency(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Idempotency:
    if not idempotency_key or not idempotency_key.strip():
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required on this POST")
    body = request.state.body if hasattr(request.state, "body") else b""
    digest = hashlib.sha256(
        (request.method + "\n" + request.url.path + "\n").encode("utf-8") + body
    ).hexdigest()
    return Idempotency(session, user, idempotency_key.strip(), request.url.path, digest)


def body_digest_from_obj(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
