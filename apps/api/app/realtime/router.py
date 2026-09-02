from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.deps import CurrentUser
from app.realtime.hub import hub
from app.schemas import assert_no_venue_ids

router = APIRouter(tags=["realtime"])


@router.get("/v1/stream")
async def stream(user: CurrentUser) -> StreamingResponse:
    admin = user.role in {"ops", "cto"}
    queue = await hub.subscribe(user.id, admin=admin)

    async def events():
        try:
            hello = {"type": "hello", "role": user.role}
            assert_no_venue_ids(hello)
            yield f"data: {json.dumps(hello)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    assert_no_venue_ids(event)
                    yield f"data: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ":\n\n"
        finally:
            await hub.unsubscribe(user.id, queue, admin=admin)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
