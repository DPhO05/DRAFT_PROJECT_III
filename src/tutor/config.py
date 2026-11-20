"""Settings (data/settings.json), data paths, fixed constants, student code."""

import copy
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Elo constants: fixed in code, read-only in the app (C-06).
K = 0.3
THETA0 = 0
RESOLVE_STREAK = 2
MAX_TEX_BYTES = 200_000

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
    "models": {f"{i:02d}": "openai:gpt-5.6-sol" for i in (*range(0, 5), 9)},
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
    "app": {"port": 8000},
    "runner": {"max_workers": 2},
    "assistant": {"max_tool_turns": 8},
}


ENV_FILE = Path(".env")  # cwd, like the default ./data


ENV_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def no_tracing() -> None:
    """Force LangSmith tracing off: it would send prompts and student work off the machine."""
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    for k in ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_ENDPOINT"):
        os.environ.pop(k, None)


def load_env(path: Path) -> None:
    """Put the API keys of a .env file into os.environ; a variable already set wins. Never prints values."""
    no_tracing()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    except UnicodeDecodeError:  # not OSError; the message would quote a byte of the file, so say our own words
        print("File khoá .env không đọc được (không phải UTF-8), bỏ qua.", file=sys.stderr)
        return
    for line in lines:
        line = line.strip().removeprefix("export ")
        key, eq, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not eq or key not in ENV_KEYS:
            continue
        if len(val) > 1 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


def save_env(path: Path, name: str, value: str) -> None:
    """Set NAME=value in a .env file, keep every other line; the file is 0600 from its first byte.

    The value, and what the file holds, never go into an exception message."""
    if "\n" in value or "\r" in value:
        raise ValueError("giá trị không được xuống dòng")
    lines = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    except UnicodeDecodeError:
        pass
    if lines is None:  # raised outside the except: the decode error names a byte of the file, and Starlette re-raises
        raise OSError(f"{path}: không đọc được (không phải UTF-8)")  # an exception's __context__ into app.log
    keep = [ln for ln in lines if ln.strip().removeprefix("export ").partition("=")[0].strip() != name]
    # mkstemp: a name nobody can guess, created O_EXCL (never follows a planted link), 0600
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write("".join(f"{ln}\n" for ln in [*keep, f"{name}={value}"]))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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


def patch(path: Path, changes: dict) -> dict:
    """Write `changes` over the file's own JSON, not over the defaults (later default changes still apply)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as e:
        raise SettingsError(f"{path}: {e}") from e
    if not isinstance(raw, dict):
        raise SettingsError(f"{path}: không phải object JSON")
    save(path, _merge(raw, changes))
    return load(path)


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
    def chat_db(self) -> Path:
        return self.root / "chat.db"

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
        for d in (self.root, self.inbox / "bank", self.out, self.logs, self.logs / "chat", self.backup):
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
