"""/api/assistant: agent 00 over NDJSON, the conversation log, pending work (api-v3 §3.1-§3.3, MONO-P6-01).

No resume and no commit here (C-39): tutor.db is opened read-only for a reply; the only writes are what the
`start_*` wrappers start, the same functions as the matching routes (C-38), data/logs/chat/ (C-42) and the chat
thread in data/chat.db."""

import itertools
import json
import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from tutor import llm
from tutor.agents.a00_orchestrator import chat, orchestrator
from tutor.agents.a00_orchestrator.tools import Starters, Toolbox, lc_tools, tool_defs
from tutor.api import errors
from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs import bank, report, session, threads, worksheet
from tutor.graphs.runner import Runner, ThreadBusy, ThreadNotFound
from tutor.services import facts

router = APIRouter(prefix="/api/assistant")
log = logging.getLogger("tutor")
BUSY = "Trợ lý đang trả lời tin trước"
WAITING = "Có việc đang chờ thầy/cô duyệt. Bấm Duyệt, Sửa hoặc Bỏ trước khi nhắn tiếp."
NOT_WAITING = "Không có việc nào đang chờ duyệt."
UNAVAILABLE = "Chưa trả lời được, thử lại"
BAD_KEY = "Khoá API sai, hết hạn, chưa có hoặc tài khoản hết hạn mức. Mở ⚙ Cài đặt để kiểm tra khoá."
INTERNAL = "Lỗi không lường trước, chi tiết ở data/logs/app.log"
_ID = re.compile(r"\d{4}-\d{2}-\d{2}-\d+")
_AT = re.compile(r"@HS-(\d+)", re.IGNORECASE)
# RLock: a dropped stream's `finally` runs in GC, possibly inside a section that already holds the lock
_lock = threading.RLock()  # every chat-log read / write and the busy set (R25)
_busy: set[Path] = set()  # log files of the conversations answering right now
HISTORY_MESSAGES = 20


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


class NotReady(Exception):
    """A message while a call waits for approval, or a decision with nothing waiting: 409."""


class Decision(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    args: dict | None = None  # edit only: code, file, held_on


class ChatStore:
    """data/chat.db: one LangGraph thread per conversation (id = conversation id), one shared connection."""

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # takes effect with the VACUUM below
        self.conn.execute("VACUUM")  # prune frees pages but never shrinks the file; once per start is enough
        self.saver = SqliteSaver(self.conn)
        self.saver.setup()

    def prune(self, cid: str) -> None:
        """Keep the newest checkpoint of the thread. `SqliteSaver.prune` is not implemented (K28)."""
        with self.saver.cursor() as cur:
            for sql in (
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id !="
                " (SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id = ?)",
                "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id !="
                " (SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id = ?)",
            ):
                cur.execute(sql, (cid, cid))
        with self.saver.lock:  # give the freed pages and the WAL back, or the files stay at the turn's peak
            self.conn.execute("PRAGMA incremental_vacuum").fetchall()  # it frees one page per row fetched
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def head(self, cid: str) -> str | None:
        t = self.saver.get_tuple({"configurable": {"thread_id": cid}})
        return t.config["configurable"]["checkpoint_id"] if t else None

    def answered(self, cid: str) -> bool:
        """True when no call of the thread's newest AI message is left without a tool answer, so nothing waits."""
        t = self.saver.get_tuple({"configurable": {"thread_id": cid}})
        msgs = t.checkpoint["channel_values"].get("messages", []) if t else []
        calls = next((m.tool_calls for m in reversed(msgs) if isinstance(m, AIMessage) and m.tool_calls), [])
        done = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
        return all(c["id"] in done for c in calls)

    def reset_pause(self, cid: str, checkpoint_id: str) -> None:
        """A retried decision starts from the paused checkpoint: its finished writes would replay the first answer."""
        with self.saver.cursor() as cur:
            cur.execute(
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id = ? AND channel != '__interrupt__'",
                (cid, checkpoint_id),
            )

    def close(self) -> None:
        self.conn.close()


def _dm(day: str) -> str:
    return f"{date.fromisoformat(day):%d/%m}"


def _not_ready(detail: dict) -> str:
    """Words for a period with no approved session: the model gets what to tell the tutor, no chat buttons (H11)."""
    words = ["Kỳ này chưa có buổi nào đã duyệt."]
    words += [f"Buổi {_dm(day)} còn chờ duyệt." for day in sorted(p["held_on"] for p in detail.get("pending", []))[:3]]
    if detail.get("previous_start"):
        words.append(f"Kỳ gần nhất có dữ liệu bắt đầu {_dm(detail['previous_start'])}.")
    return " ".join(words)


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
        except TimeoutError as e:  # both workers busy: the queued draft still lands later
            raise ValueError(
                "Máy đang bận chấm bài khác nên phiếu chưa hiện kịp. Phiếu nháp sẽ có ở mục Phiếu nháp sau ít phút."
            ) from e

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
            raise ValueError(_not_ready(e.detail)) from e
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


def _resume(rows: list[dict], answered: bool = False) -> tuple[str | None] | None:
    """(checkpoint id,) the next turn must run from when the last turn never finished, else None.

    A turn is unfinished when its user row has no assistant row (the process died) or an incomplete one.
    A decision whose tool already ran is final: the thread moves on from its newest checkpoint (P4-14)."""
    i = len(rows) - 1
    if i >= 0 and rows[i]["role"] == "assistant":
        if not rows[i].get("incomplete"):
            return None
        i -= 1
    if i < 0 or rows[i]["role"] != "user" or "from" not in rows[i] or (rows[i].get("decision") and answered):
        return None
    return (rows[i]["from"],)


def _waiting(rows: list[dict]) -> dict | None:
    """The approval event the log says the conversation waits on, else None.

    A decision that never finished (no answer row, or an incomplete one) leaves it open; whether its tool ran is
    the thread's word (`ChatStore.answered`): the conversation waits only when this is set and that is False."""
    i = len(rows) - 1
    while i >= 0 and (rows[i].get("decision") or rows[i].get("incomplete")):
        i -= 1
    if i < 0 or rows[i]["role"] != "assistant":
        return None
    last = (rows[i].get("events") or [{}])[-1]
    return last if last.get("type") == "approval" else None


def _open(
    paths: DataPaths, cid: str | None, user: dict, store: ChatStore
) -> tuple[str, Path, list[dict], tuple[str | None] | None] | None:
    """Claim the conversation and log the tutor's row before any model call (R25); None = still answering.

    The row carries `from`: the checkpoint this turn runs from (None = empty thread), written now so a killed
    process still leaves the way back (P4-11).

    Returns (id, log file, rows before this one, checkpoint to run from): history is read first so the model
    gets the message once (S12).
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
            ask = _waiting(rows)
            answered = store.answered(cid) if ask else False
            if bool(ask and not answered) != (
                "decision" in user
            ):  # a message waits for the decision; a decision needs one
                if "decision" in user:
                    raise NotReady(NOT_WAITING)
                raise NotReady(WAITING)
        resume = _resume(rows, answered) if rows else None
        start = resume[0] if resume else (store.head(cid) if rows else None)
        _write(f, {"id": f"m{len(rows) + 1}"} | user | {"from": start})
        _busy.add(f)
    return cid, f, rows, resume


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


def _history(rows: list[dict], redact: dict[str, str]) -> list:
    """The thread's start when it has none: the last 20 text messages of the log, an incomplete turn left out.

    An old answer = its text + one "(đã tra: …)" line per tool. The user row before an incomplete answer goes too,
    so the log and a thread resumed before that turn agree."""
    kept: list[tuple[str, str]] = []
    if rows and rows[-1]["role"] == "user":
        rows = rows[:-1]  # its turn never got an answer row: the process died
    for r in rows:
        if r["role"] == "assistant" and r.get("incomplete"):
            if kept and kept[-1][0] == "user":
                kept.pop()
            continue
        if not r.get("text"):
            continue  # attachment only or a turn that said nothing: the API rejects empty content (S13)
        tried = "\n".join(f"(đã tra: {t['summary']})" for t in r.get("tools") or [])
        kept.append((r["role"], f"{r['text']}\n\n{tried}" if tried else r["text"]))
    kept = kept[-HISTORY_MESSAGES:]
    while kept and kept[0][0] != "user":
        kept.pop(0)
    # the log may predate a student, so its text is masked again with today's names (C-40)
    return [(HumanMessage if role == "user" else AIMessage)(orchestrator.mask(text, redact)) for role, text in kept]


def _resaved(runner: Runner, rows: list[dict]) -> bool:
    """A G1 thread this conversation started was saved since the last answer (rows = the log before this message)."""
    last = max((r["ts"] for r in rows if r["role"] == "assistant"), default="")
    ids = {e["card"]["thread_id"] for r in rows for e in r.get("events", [])
           if e["type"] == "card" and e["card"].get("kind") == "grading"}  # fmt: skip
    for tid in ids:
        try:
            t = runner.get(tid)
        except ThreadNotFound:
            continue
        if t["status"] == "committed" and t["updated_at"] >= last:
            return True
    return False


def _scoped(scope: Callable, events: Iterator[dict]) -> Iterator[dict]:
    """`llm.scope` is a ContextVar: each `next` may run in another worker thread, so it is opened per event."""
    try:
        while True:
            with scope():
                try:
                    ev = next(events)
                except StopIteration:
                    return
            yield ev
    finally:
        with scope():
            events.close()


def _stream(f: Path, cid: str, mid: str, events: Iterator[dict], conn, *, stop: threading.Event,
            done: Callable[[], None]) -> Iterator[str]:  # fmt: skip
    """NDJSON lines. `finally` logs the answer so far and frees the conversation, also after an error or an abort.

    done: after a turn that ended cleanly."""
    said, kept, tools = [], [], []
    finished = False
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
            finished = True
            done()
        except orchestrator.KeyRejected as e:
            log.warning("assistant %s: %s", cid, e)
            err = {"type": "error", "code": "bad_key", "message": BAD_KEY}
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
        if not finished:
            stop.set()  # K11: the model call keeps going until it sees this
        try:
            events.close()
        finally:
            conn.close()
            row = {"id": mid, "role": "assistant", "ts": repo.now(), "text": "".join(said), "events": kept,
                   "tools": tools}  # fmt: skip
            if not finished:
                row["incomplete"] = True
            with _lock:
                _busy.discard(f)
                _write(f, row)


def _respond(app, conn, cid: str, f: Path, rows: list[dict], resume, ctx: chat.ChatContext, codes: list[dict],
             fixed: list[str], *, decision: Decision | None = None) -> StreamingResponse:  # fmt: skip
    """The NDJSON stream of one turn: a new message, or `decision` on the call the thread waits on."""
    store, settings = app.state.chat, app.state.settings

    def run() -> Iterator[dict]:  # inside `_stream`'s try: an error here becomes an error event and a log row
        ctx.resaved = _resaved(app.state.runner, rows)
        agent = chat.build(
            llm.model("00"),
            lc_tools(ctx.box, [c["code"] for c in codes]),
            store.saver,
            max_tool_turns=settings["assistant"]["max_tool_turns"],
            system=fixed,
        )
        cfg = {"configurable": {"thread_id": cid}, "recursion_limit": 200}
        if resume:  # K12: run from before the unfinished turn
            if resume[0] is None:
                store.saver.delete_thread(cid)
            else:
                cfg["configurable"]["checkpoint_id"] = resume[0]
                if decision:
                    store.reset_pause(cid, resume[0])
        snap = agent.get_state(cfg)
        defs = tool_defs([c["code"] for c in codes])
        cc = llm.CallContext(graph=None, conversation_id=cid, redact=orchestrator._names(ctx.redact))
        history = [] if snap.values else _history(rows, ctx.redact)
        answers = _decisions(decision, chat.waiting(agent, cfg)) if decision else None
        yield from _scoped(lambda: chat.scope(cc, fixed, defs, stop=ctx.stop),
                           chat.events(agent, ctx, cfg, history, answers))  # fmt: skip

    lines = _stream(f, cid, f"m{len(rows) + 2}", run(), conn, stop=ctx.stop,
                    done=lambda: store.prune(cid))  # fmt: skip
    first = next(lines)  # inside its try now: a response never read still runs `finally` when dropped
    return StreamingResponse(itertools.chain([first], lines), media_type="application/x-ndjson")


def _decisions(d: Decision, asks: list[dict]) -> list[dict]:
    """K30: one decision per waiting call. A second call in the same message is rejected: only one start runs."""
    if not asks:
        raise NotReady(NOT_WAITING)
    reject = {"type": "reject", "message": chat.REJECTED}
    edited = {"type": "edit", "edited_action": {"name": asks[0]["name"], "args": d.args}}
    first = {"approve": {"type": "approve"}, "edit": edited, "reject": reject}[d.decision]
    return [first] + [reject] * (len(asks) - 1)


@router.post("/messages")
def message(body: Message, request: Request):
    """One tutor message → NDJSON events (C-51). Errors before the stream are plain JSON: 422, 404, 409."""
    app = request.app
    paths, settings, today, store = app.state.paths, app.state.settings, date.today(), app.state.chat
    conn = repo.connect(paths.tutor_db, readonly=True)  # the reply's only tutor.db connection (C-39)
    try:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}  # archived too; one-word names skipped (S24)
        text = orchestrator.mask(body.text, redact)
        _check(text, body, everyone)
        starters = make_starters(paths, app.state.runner)
        box = Toolbox(conn, settings=settings, today=today, text=text, starters=starters)
        codes = repo.error_codes(conn, active_only=True)
        fixed = orchestrator.fixed_parts(repo.list_kc(conn), codes)
        attachment = body.attachment.model_dump() if body.attachment else None
        user = {"role": "user", "ts": repo.now(), "text": text, "mentions": body.mentions, "attachment": attachment}
        opened = _open(paths, body.conversation_id, user, store)
    except NotReady as e:
        conn.close()
        return errors.error(409, "not_ready", str(e), {"reason": str(e)})
    except BaseException:
        conn.close()
        raise
    if opened is None:
        conn.close()
        return errors.error(409, "not_ready", BUSY, {"reason": BUSY})
    cid, f, rows, resume = opened
    turn = orchestrator.Turn(
        text,
        body.mentions,
        attachment=body.attachment.path if body.attachment else None,
        held_on=body.held_on.isoformat() if body.held_on else None,
        worksheet_thread_id=body.context.worksheet_thread_id,
    )
    return _respond(app, conn, cid, f, rows, resume, chat.ChatContext(turn, box, everyone, redact), codes, fixed)


@router.post("/conversations/{conversation_id}/decide")
def decide(conversation_id: str, body: Decision, request: Request):
    """The tutor's answer to the call the conversation waits on (api-v3 §3.1): NDJSON like `/messages`."""
    app = request.app
    paths, settings, store = app.state.paths, app.state.settings, app.state.chat
    conn = repo.connect(paths.tutor_db, readonly=True)
    try:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}
        if body.decision != "edit":
            body.args = None
        else:  # the same name masking as a typed message (C-40), the same date rule as the form
            a = chat._mask_deep(body.args or {}, redact)
            if not all(isinstance(a.get(k), str) and a[k].strip() for k in ("code", "file", "held_on")):
                raise ValueError("Thiếu học sinh, file hoặc ngày học")
            session.held_day(a["held_on"])
            body.args = {k: a[k] for k in ("code", "file", "held_on")}
        last = next((r for r in reversed(_read(_file(paths, conversation_id))) if r["role"] == "user"
                     and not r.get("decision")), {})  # fmt: skip
        text = last.get("text", "")
        box = Toolbox(conn, settings=settings, today=date.today(), text=text,
                      starters=make_starters(paths, app.state.runner))  # fmt: skip
        codes = repo.error_codes(conn, active_only=True)
        fixed = orchestrator.fixed_parts(repo.list_kc(conn), codes)
        label = {"approve": "Duyệt", "edit": "Sửa", "reject": "Bỏ"}[body.decision]
        user = {"role": "user", "ts": repo.now(), "text": "", "mentions": [], "attachment": None,
                "decision": body.decision, "label": label, "args": body.args}  # fmt: skip
        opened = _open(paths, conversation_id, user, store)
    except NotReady as e:
        conn.close()
        return errors.error(409, "not_ready", str(e), {"reason": str(e)})
    except BaseException:
        conn.close()
        raise
    if opened is None:
        conn.close()
        return errors.error(409, "not_ready", BUSY, {"reason": BUSY})
    cid, f, rows, resume = opened
    turn = orchestrator.Turn(text, last.get("mentions", []))
    ctx = chat.ChatContext(turn, box, everyone, redact)
    return _respond(app, conn, cid, f, rows, resume, ctx, codes, fixed, decision=body)


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
    """The log rows without `tools` (their summaries may hold error codes, S10) and `from` (a checkpoint id),
    and whether a call waits for the tutor's decision."""
    f = _file(request.app.state.paths, conversation_id)
    with _lock:
        rows = _read(f)
    return {
        "id": conversation_id,
        "waiting": bool(_waiting(rows)) and not request.app.state.chat.answered(conversation_id),
        "messages": [{k: v for k, v in r.items() if k not in ("tools", "from")} for r in rows],
    }


@router.get("/pending")
def pending(request: Request) -> dict:
    """G1 / G2 / G4 / G5 threads at a gate or failed (C-05), running G1 so a reload shows its card, and
    conversations waiting for an approval."""
    paths, r = request.app.state.paths, request.app.state.runner
    items = []
    for row in threads.annotate(r.list_threads()):
        if row["status"] not in ("awaiting_review", "failed") and not (
            row["status"] == "running" and row["graph"] == session.GRAPH
        ):
            continue
        if row["graph"] == session.GRAPH:
            items.append(session.reminder(paths, row, r.state(row["thread_id"])))
        elif row["graph"] == bank.GRAPH:
            items.append(bank.reminder(paths, row, r.state(row["thread_id"])))
        elif row["graph"] == worksheet.GRAPH:
            items.append(worksheet.reminder(row, r.state(row["thread_id"])))
        elif row["graph"] == report.GRAPH:
            items.append(report.reminder(row, r.state(row["thread_id"])))
    with _lock:
        logs = [(f.stem, _read(f)) for f in (paths.logs / "chat").glob("*.jsonl") if _ID.fullmatch(f.stem)]
    items += [{"kind": "approval", "conversation_id": cid, **ask} for cid, rows in sorted(logs)
              if (ask := _waiting(rows)) and not request.app.state.chat.answered(cid)]  # fmt: skip
    assistant = sum(
        i["kind"] in ("grading", "worksheet")
        and i.get("state") not in ("reading", "grading", "saving")
        or i["kind"] == "approval"
        for i in items
    )
    return {"counts": {"assistant": assistant, "reports": sum(i["kind"] == "report" for i in items)}, "items": items}
