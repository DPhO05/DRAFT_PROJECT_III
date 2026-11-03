"""/api/assistant: agent 00 over NDJSON, the conversation log, pending work (api-v3 §3.1-§3.3, MONO-P6-01).

No resume and no commit here (C-39): tutor.db is opened read-only for a reply; the only writes are what the
`start_*` wrappers start, the same functions as the matching routes (C-38), and data/logs/chat/ (C-42)."""

import itertools
import json
import logging
import re
import threading
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tutor.agents.a00_orchestrator import orchestrator
from tutor.agents.a00_orchestrator.tools import Starters, Toolbox
from tutor.api import errors
from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs import bank, report, session, threads, worksheet
from tutor.graphs.runner import Runner, ThreadBusy, ThreadNotFound
from tutor.mcp import client, server
from tutor.services import facts

router = APIRouter(prefix="/api/assistant")
log = logging.getLogger("tutor")
BUSY = "Trợ lý đang trả lời tin trước"
UNAVAILABLE = "Chưa trả lời được, thử lại"
INTERNAL = "Lỗi không lường trước, chi tiết ở data/logs/app.log"
_ID = re.compile(r"\d{4}-\d{2}-\d{2}-\d+")
_AT = re.compile(r"@HS-(\d+)", re.IGNORECASE)
# RLock: a dropped stream's `finally` runs in GC, possibly inside a section that already holds the lock
_lock = threading.RLock()  # every chat-log read / write and the busy set (R25)
_busy: set[Path] = set()  # log files of the conversations answering right now


class Attachment(BaseModel):
    path: str  # relative to data/inbox/


class Context(BaseModel):
    worksheet_thread_id: str | None = None


class Message(BaseModel):
    conversation_id: str | None = None
    text: str = ""
    mentions: list[int] = []
    attachment: Attachment | None = None
    held_on: date | None = None
    context: Context = Context()


def _dm(day: str) -> str:
    return f"{date.fromisoformat(day):%d/%m}"


def make_starters(paths: DataPaths, runner: Runner) -> Starters:
    """start_* wrappers around `runner.start`; a domain error becomes a ValueError with words for the tutor (R20)."""

    def start_grading(student_id: int, file: str, held_on: str) -> dict:
        try:
            return session.submit(paths, runner, student_id=student_id, held_on=held_on, rel_path=file)
        except repo.DuplicateSubmission as e:
            with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
                done = repo.session_detail(conn, e.session_id)["held_on"]
            raise ValueError(f"Bài này đã nộp cho {student_code(student_id)} rồi (buổi {_dm(done)}).") from e
        except repo.DateOrderLocked as e:
            raise ValueError(f"Ngày học sớm hơn buổi đã lưu {_dm(e.last_committed)}, không chấm được.") from e
        except repo.NotFound as e:
            raise ValueError(f"Không có học sinh {student_code(student_id)}") from e

    def propose_worksheet(
        student_id: int, for_date: str, items: list[dict], note: str | None, warnings: list[str]
    ) -> dict:
        try:
            return worksheet.propose(
                paths, runner, student_id=student_id, for_date=for_date, items=items, note=note, warnings=warnings
            )
        except repo.NotFound as e:
            raise ValueError(f"Không có học sinh {student_code(student_id)}") from e
        except ThreadBusy as e:  # propose deletes the old draft, which is being saved
            raise ValueError("Phiếu nháp đang được lưu, thử lại sau ít phút") from e

    def add_to_worksheet(thread_id: str, refs: list[str]) -> dict:
        try:
            return worksheet.add_refs(paths, runner, thread_id, refs)
        except ThreadNotFound as e:
            raise ValueError("Không có phiếu nháp để thêm bài") from e

    def start_report(student_id: int, period_kind: str, period_start: str) -> dict:
        try:
            return report.start(paths, runner, student_id=student_id, period_kind=period_kind,
                                period_start=period_start, today=date.today())  # fmt: skip
        except facts.NotReady as e:
            raise ValueError(
                f"Chưa làm được báo cáo cho {student_code(student_id)}: kỳ này chưa có buổi nào đã duyệt."
            ) from e
        except repo.ReportApproved as e:
            done = f"{date.fromisoformat(e.approved_at[:10]):%d/%m/%Y}"
            raise ValueError(f"Báo cáo kỳ này đã duyệt ngày {done}. Mỗi kỳ chỉ duyệt một lần.") from e

    return Starters(
        start_grading=start_grading,
        start_bank_import=lambda file: bank.start_import(paths, runner, file=file),
        propose_worksheet=propose_worksheet,
        add_to_worksheet=add_to_worksheet,
        start_report=start_report,
    )


def _file(paths: DataPaths, cid: str) -> Path:
    f = paths.logs / "chat" / f"{cid}.jsonl"
    if not _ID.fullmatch(cid) or not f.is_file():
        raise repo.NotFound(f"hội thoại {cid}")
    return f


def _read(f: Path) -> list[dict]:
    """Rows of a chat log; a line cut short by a crash or full disk is skipped, as `llm.iter_log` does."""
    rows = []
    for x in f.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(x))
        except ValueError:
            continue
    return rows


def _write(f: Path, row: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


def _open(paths: DataPaths, cid: str | None, user: dict) -> tuple[str, Path, list[dict]] | None:
    """Claim the conversation and log the tutor's row before any model call (R25); None = still answering.

    Returns (id, log file, rows before this one): history is read first so the model gets the message once (S12).
    A new id is the highest n of today + 1."""
    with _lock:
        if cid is None:
            day = date.today().isoformat()
            used = [int(f.stem.rsplit("-", 1)[1]) for f in (paths.logs / "chat").glob(f"{day}-*.jsonl")
                    if _ID.fullmatch(f.stem)]  # fmt: skip
            cid = f"{day}-{max(used, default=0) + 1}"
            f, rows = paths.logs / "chat" / f"{cid}.jsonl", []
        else:
            f = _file(paths, cid)
            if f in _busy:
                return None
            rows = _read(f)
        _write(f, {"id": f"m{len(rows) + 1}"} | user)
        _busy.add(f)
    return cid, f, rows


def _check(text: str, body: Message, everyone: dict[int, dict]) -> None:
    """422 before the stream starts (api-v3 §3.1)."""
    if not text.strip() and body.attachment is None:
        raise ValueError("Tin nhắn trống")
    for sid in body.mentions:
        if sid not in everyone or everyone[sid]["archived_at"]:
            raise ValueError(f"Không có học sinh {student_code(sid)}, hoặc học sinh đã lưu trữ")
    for n in _AT.findall(text):
        if int(n) not in body.mentions:
            raise ValueError(f"@HS-{n} chưa được chọn trong danh sách học sinh")


def _line(ev: dict) -> str:
    return json.dumps(ev, ensure_ascii=False) + "\n"


def _stream(f: Path, cid: str, mid: str, events: Iterator[dict], conn) -> Iterator[str]:
    """NDJSON lines. `finally` logs the answer so far and frees the conversation, also after an error or an abort."""
    said, kept, tools = [], [], []
    try:
        yield _line({"type": "start", "conversation_id": cid, "message_id": mid})
        err = None
        try:
            for ev in events:
                if ev["type"] == "text":
                    said.append(ev["delta"])
                else:
                    if "summary" in ev:  # S10: the summary may hold error codes; only the log keeps it
                        tools.append({"name": ev["name"], "summary": ev.pop("summary")})
                    kept.append(ev)
                yield _line(ev)
        except orchestrator.LLMUnavailable as e:
            log.warning("assistant %s: %s", cid, e)
            err = {"type": "error", "code": "llm_unavailable", "message": UNAVAILABLE}
        except Exception:
            log.exception("assistant %s", cid)
            err = {"type": "error", "code": "internal", "message": INTERNAL}
        if err:
            kept.append(err)
            yield _line(err)
    finally:
        conn.close()
        with _lock:
            _busy.discard(f)
            _write(f, {"id": mid, "role": "assistant", "ts": repo.now(), "text": "".join(said), "events": kept,
                       "tools": tools})  # fmt: skip


@router.post("/messages")
def message(body: Message, request: Request):
    """One tutor message → NDJSON events (C-51). Errors before the stream are plain JSON: 422, 404, 409."""
    paths, settings, today = request.app.state.paths, request.app.state.settings, date.today()
    conn = repo.connect(paths.tutor_db, readonly=True)  # the reply's only tutor.db connection (C-39)
    try:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}  # archived too; one-word names skipped (S24)
        text = orchestrator.mask(body.text, redact)
        _check(text, body, everyone)
        starters = make_starters(paths, request.app.state.runner)
        # this sync route runs in a worker thread, so the Session's anyio.run is safe here (design §11 M8, M10)
        s = client.connect("00", Toolbox(conn, settings=settings, today=today, text=text, starters=starters))
        fixed = orchestrator.fixed_parts(json.loads(s.resource(server.KCS)), json.loads(s.resource(server.ERROR_CODES)))
        tools = s.tools()
        attachment = body.attachment.model_dump() if body.attachment else None
        user = {"role": "user", "ts": repo.now(), "text": text, "mentions": body.mentions, "attachment": attachment}
        opened = _open(paths, body.conversation_id, user)
    except BaseException:
        conn.close()
        raise
    if opened is None:
        conn.close()
        return errors.error(409, "not_ready", BUSY, {"reason": BUSY})
    cid, f, rows = opened
    turn = orchestrator.Turn(
        text,
        body.mentions,
        attachment=body.attachment.path if body.attachment else None,
        held_on=body.held_on.isoformat() if body.held_on else None,
        worksheet_thread_id=body.context.worksheet_thread_id,
    )
    events = orchestrator.reply(
        turn,
        history=orchestrator.history_messages(rows),
        conn=conn,
        starters=starters,
        settings=settings,
        today=today,
        redact=redact,
        students=everyone,
        conversation_id=cid,
        fixed=fixed,
        tools=tools,
        call=s.call,
    )
    lines = _stream(f, cid, f"m{len(rows) + 2}", events, conn)
    first = next(lines)  # inside its try now: a response never read still runs `finally` when dropped
    return StreamingResponse(itertools.chain([first], lines), media_type="application/x-ndjson")


@router.get("/conversations")
def conversations(request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[dict]:
    """Newest first; title = the tutor's first message, names already masked (api-v3 §3.2)."""
    # shortcut: reads every log file per request; fine for one tutor, keep an index if it passes ~1000 conversations.
    with _lock:
        logs = [(f.stem, _read(f)) for f in (request.app.state.paths.logs / "chat").glob("*.jsonl")
                if _ID.fullmatch(f.stem)]  # fmt: skip
    out = [{"id": cid, "title": rows[0]["text"], "date": cid[:10], "updated_at": rows[-1]["ts"],
            "n_messages": len(rows)} for cid, rows in logs if rows]  # fmt: skip
    out.sort(key=lambda c: (c["updated_at"], c["date"], int(c["id"].rsplit("-", 1)[1])), reverse=True)
    return out[:limit]


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, request: Request) -> dict:
    """The log rows without `tools`: their summaries may hold error codes (S10)."""
    f = _file(request.app.state.paths, conversation_id)
    with _lock:
        rows = _read(f)
    return {"id": conversation_id, "messages": [{k: v for k, v in r.items() if k != "tools"} for r in rows]}


@router.get("/pending")
def pending(request: Request) -> dict:
    """G1 / G2 / G4 / G5 threads at a gate or failed (C-05); a running G1 is no work for the tutor yet."""
    paths, r = request.app.state.paths, request.app.state.runner
    items = []
    for row in threads.annotate(r.list_threads()):
        if row["status"] not in ("awaiting_review", "failed"):
            continue
        if row["graph"] == session.GRAPH:
            items.append(session.reminder(paths, row, r.state(row["thread_id"])))
        elif row["graph"] == bank.GRAPH:
            items.append(bank.reminder(paths, row, r.state(row["thread_id"])))
        elif row["graph"] == worksheet.GRAPH:
            items.append(worksheet.reminder(row, r.state(row["thread_id"])))
        elif row["graph"] == report.GRAPH:
            items.append(report.reminder(row, r.state(row["thread_id"])))
    assistant = sum(i["kind"] in ("grading", "worksheet") for i in items)
    return {"counts": {"assistant": assistant, "reports": sum(i["kind"] == "report" for i in items)}, "items": items}
