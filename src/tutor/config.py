"""Settings (data/settings.json), data paths, fixed constants, student code."""

import copy
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Elo constants: fixed in code, read-only in the app (C-06).
K = 0.3
THETA0 = 0
RESOLVE_STREAK = 2

_DEFAULTS = {
    "reco": {
        "ratios": {"review": 0.4, "zpd": 0.5, "challenge": 0.1},
        "n_problems": 6,
        "no_repeat_days": 30,
        "min_kc_mix": 3,
        "zpd_window": [-0.5, 0.5],
    },
    "review": {"low_confidence": 0.6},
    "report": {"low_pass_rate": 0.5},
    "models": {f"{i:02d}": "claude-opus-5-5" for i in (*range(0, 5), 9)},
    "budget_usd_month": 30,
    # Assumed prices, not a price list (C-27); 5-min cache writes bill at 1.25x input.
    "price_assumption": {
        "input_per_mtok": 5,
        "output_per_mtok": 25,
        "cache_read_per_mtok": 0.5,
        "cache_write_per_mtok": 6.25,
    },
    # Keyed by the exact model string in settings["models"]; wins over price_assumption.
    # shortcut: Standard ≤ 272K input tokens only; longer calls bill higher, add a long-context price
    # if 00 ever sends that much.
    "price_by_model": {
        "openai:gpt-5.6-sol": {
            "input_per_mtok": 4,
            "output_per_mtok": 20,
            "cache_read_per_mtok": 0.4,
            "cache_write_per_mtok": 5,
        },
    },
    "privacy": {"send_code_only": True},
    "backup": {"keep_recent": 30, "keep_monthly": True},
    "app": {"port": 8000},
    "runner": {"max_workers": 2},
    "assistant": {"max_tool_turns": 8},
}


ENV_FILE = Path(".env")  # cwd, like the default ./data


def load_env(path: Path) -> None:
    """Put KEY=VALUE lines of a .env file into os.environ; a variable already set wins. Never prints values."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip().removeprefix("export ")
        key, eq, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not eq or not key or key.startswith("#"):
            continue
        if len(val) > 1 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


class SettingsError(Exception):
    """settings.json exists but cannot be read."""


def defaults() -> dict:
    return copy.deepcopy(_DEFAULTS)


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path: Path) -> dict:
    """Defaults overlaid with the file; missing file → defaults."""
    if not path.exists():
        return defaults()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SettingsError(f"{path}: {e}") from e
    if not isinstance(data, dict):
        raise SettingsError(f"{path}: không phải object JSON")
    return _merge(defaults(), data)


def save(path: Path, settings: dict) -> None:
    # Temp file + replace: a crash mid-write never leaves a half-written settings.json.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @property
    def tutor_db(self) -> Path:
        return self.root / "tutor.db"

    @property
    def checkpoints_db(self) -> Path:
        return self.root / "checkpoints.db"

    @property
    def settings(self) -> Path:
        return self.root / "settings.json"

    @property
    def runner_lock(self) -> Path:
        return self.root / "runner.lock"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def out(self) -> Path:
        return self.root / "out"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backup(self) -> Path:
        return self.root / "backup"

    def ensure(self) -> "DataPaths":
        for d in (self.root, self.inbox / "bank", self.out, self.logs, self.backup):
            d.mkdir(parents=True, exist_ok=True)
        return self


def paths(root: Path | str | None = None) -> DataPaths:
    """--data-dir > TUTOR_DATA > ./data."""
    return DataPaths(Path(root or os.environ.get("TUTOR_DATA") or "data"))


def student_code(student_id: int) -> str:
    """The only student identifier sent to the LLM API (C-11)."""
    return f"HS-{student_id:02d}"


def guess_submission(name: str) -> dict | None:
    """R26: "hs01-2026-10-21.tex" -> {student_id: 1, held_on: "2026-10-21"}; the caller checks the student exists."""
    m = re.match(r"hs(\d+)-(\d{4}-\d{2}-\d{2})(?!\d)", Path(name).name, re.IGNORECASE)
    try:
        return {"student_id": int(m[1]), "held_on": date.fromisoformat(m[2]).isoformat()} if m else None
    except ValueError:
        return None
