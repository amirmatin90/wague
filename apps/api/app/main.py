from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.admin.router import router as admin_router
from app.config import assert_local_stub, get_settings
from app.db import SessionLocal
from app.errors import ApiError, api_error_handler
from app.identity.router import router as identity_router
from app.realtime.router import router as realtime_router
from app.rfq.router import router as rfq_router
from app.seed import seed
from app.trade.router import router as trade_router
from app.trade.service import kill_switch_row
from app.workers import start_workers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    assert_local_stub()
    seed()
    start_workers()
    yield


app = FastAPI(title="WAGUE OTC Desk", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)


@app.exception_handler(RequestValidationError)
def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "Request failed validation")
    if loc:
        message = f"{loc}: {message}"
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": message})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8472", "http://localhost:8472"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(identity_router)
app.include_router(rfq_router)
app.include_router(trade_router)
app.include_router(admin_router)
app.include_router(realtime_router)


@app.middleware("http")
async def cache_request_body(request: Request, call_next):
    request.state.body = await request.body()
    return await call_next(request)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    settings = get_settings()
    if settings.hl_network != "stub":
        return JSONResponse({"status": "not_ready", "reason": "hl_network"}, status_code=503)
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        row = kill_switch_row(session, for_update=False)
        if row is None:
            return JSONResponse({"status": "halted", "reason": "kill_switch_missing"}, status_code=503)
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "not_ready", "reason": "database"}, status_code=503)
    finally:
        session.close()


def run() -> None:
    import uvicorn

    assert_local_stub()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    run()
