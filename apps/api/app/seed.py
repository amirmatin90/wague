from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.identity.service import hash_password
from app.ledger.service import ASSETS, CHAIN_PARTY_ID, DESK_PARTY_ID, ensure_account
from app.models import KillSwitch, User

SEED_USERS = (
    ("client@desk.local", "client-local", "client"),
    ("ops@desk.local", "ops-local", "ops"),
    ("cto@desk.local", "cto-local", "cto"),
)

CLIENT_PREFUND = {
    "BTC": Decimal("0"),
    "ETH": Decimal("0"),
    "USDC": Decimal("0"),
}

DESK_PREFUND = {
    "BTC": Decimal("100.00000000"),
    "ETH": Decimal("500.00000000"),
    "USDC": Decimal("20000000.00"),
}


def seed() -> None:
    session = SessionLocal()
    try:
        ks = session.get(KillSwitch, 1)
        if ks is None:
            session.add(KillSwitch(id=1, engaged=False))

        users_by_email: dict[str, User] = {}
        for email, password, role in SEED_USERS:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, password_hash=hash_password(password), role=role)
                session.add(user)
                session.flush()
            users_by_email[email] = user

        client = users_by_email["client@desk.local"]
        for asset in ASSETS:
            opening = CLIENT_PREFUND[asset]
            ensure_account(session, "client", client.id, asset, "available", opening)
            ensure_account(session, "client", client.id, asset, "reserved", Decimal("0"))
            ensure_account(session, "desk", DESK_PARTY_ID, asset, "available", DESK_PREFUND[asset])
            ensure_account(session, "desk", DESK_PARTY_ID, asset, "reserved", Decimal("0"))
            ensure_account(session, "chain", CHAIN_PARTY_ID, asset, "available", Decimal("0"))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
