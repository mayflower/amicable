from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

app = FastAPI(title="Amicable FastAPI Template", version="1.0.0")


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=302)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


class EchoRequest(BaseModel):
    input: dict | list | str | int | float | bool | None = None


@app.post("/actions/echo")
async def action_echo(req: EchoRequest) -> dict:
    # Hasura Actions typically send JSON; adapt this handler as needed.
    return {"ok": True, "echo": req.input}


class EventTriggerPayload(BaseModel):
    event: dict


@app.post("/events/log")
async def event_log(payload: EventTriggerPayload) -> dict:
    # Hasura Event Triggers post a structured payload.
    # In real code you would validate shape and act accordingly.
    return {"ok": True}
