from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.audit.service import write_audit
from app.deps import DbSession
from app.identity.service import authenticate, issue_token

router = APIRouter(prefix="/v1/auth", tags=["identity"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


@router.post("/login")
def login(payload: LoginRequest, session: DbSession) -> dict:
    user = authenticate(session, payload.email, payload.password)
    token = issue_token(user)
    write_audit(session, user.id, "auth.login", "user", str(user.id), {"email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "email": user.email,
    }
