"""/api/settings: the tutor's three settings and the API keys (api-v3 §7.3, P8-T02).

A key goes to <data>/.env and the process env only: never into settings.json, a response or a log line."""

import os
import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, ConfigDict, Field

from tutor import config, llm
from tutor.api import errors

router = APIRouter(prefix="/api/settings")
KEY_FORMAT = re.compile(r"[A-Za-z0-9_-]{20,500}")


class Reco(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_problems: Annotated[int, Field(ge=3, le=12)] | None = None
    no_repeat_days: Annotated[int, Field(ge=0, le=120)] | None = None


class Changes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reco: Reco | None = None
    budget_usd_month: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


def _keys(settings: dict) -> dict[str, bool]:
    return {p: bool(os.environ.get(llm.KEY_ENV[p])) for p in llm.providers(settings["models"])}


def _view(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "reco": {k: s["reco"][k] for k in ("n_problems", "no_repeat_days")},
        "budget_usd_month": s["budget_usd_month"],
        "settings_error": "settings.json hỏng, nhờ người cài sửa." if request.app.state.settings_error else None,
        "keys": _keys(s),
    }


@router.get("")
def read(request: Request) -> dict:
    return _view(request)


@router.patch("", response_model=None)
def change(body: Changes, request: Request):
    state, changes = request.app.state, body.model_dump(exclude_none=True)
    try:
        if state.settings_error:  # started with defaults: writing now would bury the tutor's broken file
            raise config.SettingsError(state.settings_error)
        config.patch(state.paths.settings, changes)
    except config.SettingsError:
        return errors.error(409, "not_ready", "settings.json hỏng, sửa tay trước")
    config._merge(state.settings, changes)
    return _view(request)


@router.put("/key")
def put_key(body: Annotated[Any, Body()], request: Request) -> dict:
    """Not a pydantic model: its 422 would echo the body, and the body holds the key."""
    fields = body if isinstance(body, dict) else {}
    key, provider = fields.get("key"), fields.get("provider")
    key = key.strip() if isinstance(key, str) else ""
    state = request.app.state
    if not KEY_FORMAT.fullmatch(key):
        raise ValueError("Khoá không đúng dạng")
    if not isinstance(provider, str) or provider not in llm.providers(state.settings["models"]):
        raise ValueError("Không dùng provider này")
    config.save_env(state.paths.root / ".env", llm.KEY_ENV[provider], key)
    llm.use_key(provider, key)
    return {"keys": _keys(state.settings)}
