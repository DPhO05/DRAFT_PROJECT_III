"""G1 session graph (P1-T10, P2-T05, P3-T01, P3-T02).

① session row → 01 Ingest → prepare (02 drafts missing rubrics) → [DỪNG confirm_match while flags remain]
→ one 02 → 03 → 04 lane per problem (Send) → review queue → DỪNG review → 05 profile → DỪNG confirm_commit
→ commit ② (backup, one transaction). If another session of the student committed since 05 ran, commit ②
refuses (repo.StaleProfile) and the graph goes back to 05 instead of writing a stale profile.
"""

import copy
import hashlib
import json
import re
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from tutor import config
from tutor.agents import CallContext
from tutor.agents.a01_ingest import ingest
from tutor.agents.a02_grader import grader
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier
from tutor.config import DataPaths
from tutor.db import repo
from tutor.graphs.runner import Runner
from tutor.graphs.state import LaneState, SessionState
from tutor.services import elo, latex

GRAPH = "G1"


def _source(paths: DataPaths, rel_path: str):
    """Only .tex files inside data/inbox/ (SDD §9.1 #4)."""
    inbox = paths.inbox.resolve()
    p = (inbox / rel_path).resolve()
    if not p.is_relative_to(inbox) or not p.is_file():
        raise ValueError(f"Không có file trong data/inbox/: {rel_path}")
    if p.suffix.lower() == ".pdf":
        raise ValueError("Nhánh PDF chưa làm (P1-T09 chờ §11.1 câu 2); nộp file .tex")
    if p.suffix.lower() != ".tex":
        raise ValueError(f"Chỉ nhận .tex: {rel_path}")
    return p


def submit(paths: DataPaths, runner: Runner, *, student_id: int, held_on: str, rel_path: str) -> dict:
    """S1: duplicate check, date check and ① run synchronously; the graph then runs in the background."""
    src = _source(paths, rel_path)
    try:
        day = date.fromisoformat(held_on)
    except ValueError as e:
        raise ValueError(f"Ngày học phải dạng YYYY-MM-DD: {held_on}") from e
    held_on = day.isoformat()  # fromisoformat also takes "20261021"; a stored date must sort as text
    raw = src.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("File phải lưu dạng UTF-8") from e
    if not latex.split_problems(text):  # ingest would fail the same way later, after ① and a thread exist
        raise ValueError(
            "File không có \\begin{problem} nào: mỗi bài phải nằm giữa \\begin{problem}[mã bài] và \\end{problem}"
        )
    sha = hashlib.sha256(raw).hexdigest()
    rel = src.relative_to(paths.root.resolve()).as_posix()
    with closing(repo.connect(paths.tutor_db)) as conn:
        code = repo.get_student(conn, student_id)["code"]
        base = f"g1-{code.replace('-', '').lower()}-{day:%Y%m%d}"
        tid, k = base, 1
        while repo.thread_id_taken(conn, tid) or runner.exists(tid):  # C-05: -k suffix
            k += 1
            tid = f"{base}-{k}"
        session_id = repo.commit_session_start(
            conn, student_id=student_id, held_on=held_on, source_path=rel, source_kind="tex", sha256=sha, thread_id=tid
        )
    meta = {"subject": f"{code} · buổi {day:%d/%m/%Y}", "student_id": student_id, "session_id": session_id,
            "held_on": held_on}  # fmt: skip
    state = {"session_id": session_id, "student_id": student_id, "held_on": held_on, "source_path": rel,
             "source_kind": "tex"}  # fmt: skip
    try:
        runner.start(GRAPH, tid, state, meta)
    except Exception:
        # ① is already written: never leave a 'running' session with no thread behind it
        with closing(repo.connect(paths.tutor_db)) as conn:
            repo.commit_session_status(conn, session_id, "failed")
        raise
    return {"thread_id": tid, "session_id": session_id, "status": "running"}


def call_context(paths: DataPaths, student_id: int, session_id: int | None, config, graph: str = GRAPH) -> CallContext:
    # Names are read here for masking only; they never enter graph state or checkpoints (SDD §8.6).
    # Another student's name pasted into a .tex is masked too (NFR7); a one-word name would hit common words (S24).
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        st = repo.get_student(conn, student_id)
        everyone = repo.list_students(conn, include_archived=True)
    redact = {s["name"]: s["code"] for s in everyone if len(s["name"].split()) >= 2} | {st["name"]: st["code"]}
    return CallContext(graph=graph, thread_id=config["configurable"]["thread_id"], session_id=session_id,
                       student_code=st["code"], redact=redact)  # fmt: skip


def _unresolved(state: SessionState) -> list[dict]:
    return [f for f in state["ingest"]["flags"] if not f["resolved"]]


def _rubric_ok(items: object) -> bool:
    """Teacher-edited rubric from the API: non-empty, unique item ids, text, positive numeric points."""
    if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
        return False
    ids = [str(i.get("item_id") or "").strip() for i in items]
    pts = [i.get("points") for i in items]
    return (
        all(ids)
        and len(set(ids)) == len(ids)
        and all(str(i.get("text") or "").strip() for i in items)
        and all(isinstance(p, int | float) and not isinstance(p, bool) and p > 0 for p in pts)
    )


def _lane_input(state: SessionState, a: dict) -> dict:
    return {"seq": a["seq"], "problem_id": a["problem_id"], "steps": a["steps"],
            "rubric": state["approved_rubrics"].get(str(a["seq"])), "student_id": state["student_id"],
            "session_id": state["session_id"]}  # fmt: skip


EDIT_FIELDS = ("step_idx", "code", "kc_id", "description", "evidence_latex")


def _attempts(state: SessionState) -> dict[int, dict]:
    return {a["seq"]: a for a in state["ingest"]["attempts"] if not a.get("skipped")}


def _cards(review: object) -> dict:
    cards = review.get("cards") if isinstance(review, dict) else None
    return cards if isinstance(cards, dict) else {}


def _card(state: SessionState, key: str, d: dict) -> tuple[int, dict]:
    """(attempt seq, mistake fields) a decision stands for: proposal fields, an edit's own fields on top, or an add."""
    props = {p["pid"]: p for p in state["proposals"]}
    if key in props:
        p = props[key]
        f = {k: p[k] for k in EDIT_FIELDS}
        return p["attempt_seq"], f | ({k: d[k] for k in EDIT_FIELDS if k in d} if d["action"] == "edit" else {})
    seq, f = d.get("attempt_seq"), {k: d.get(k) for k in EDIT_FIELDS}
    steps = _attempts(state).get(seq, {}).get("steps", [])
    if not f["evidence_latex"] and isinstance(f["step_idx"], int) and 1 <= f["step_idx"] <= len(steps):
        f["evidence_latex"] = steps[f["step_idx"] - 1]["latex"]
    return seq, f


def _review_pending(state: SessionState, review: object, codes: set[str], kcs: dict[int, set[int]]) -> int:
    """Cards without a valid A / E / R + added mistakes that are not valid yet (SDD §5.4: no "approve all")."""
    cards = _cards(review)
    pids, attempts = {p["pid"] for p in state["proposals"]}, _attempts(state)

    def ok(key: str, d: object) -> bool:
        if not isinstance(d, dict) or d.get("action") not in ({"accept", "edit", "reject"} if key in pids else {"add"}):
            return False
        if d["action"] in ("accept", "reject"):
            return True
        seq, f = _card(state, key, d)
        n_steps = len(attempts[seq]["steps"]) if seq in attempts else 0
        return (
            f["code"] in codes
            and (f["kc_id"] is None or f["kc_id"] in kcs.get(seq, set()))
            and isinstance(f["step_idx"], int) and not isinstance(f["step_idx"], bool) and 1 <= f["step_idx"] <= n_steps
            and isinstance(f["description"], str) and bool(f["description"].strip())
            and isinstance(f["evidence_latex"], str)
        )  # fmt: skip

    return sum(not ok(p, cards.get(p)) for p in pids) + sum(not ok(k, d) for k, d in cards.items() if k not in pids)


def _review_inputs(conn, state: dict) -> tuple[set[str], dict[int, set[int]]]:
    """(active error codes, KC ids of each lane's problem by seq): what a review decision is checked against."""
    codes = {c["code"] for c in repo.error_codes(conn, active_only=True)}
    kcs = {lane["seq"]: {k["id"] for k in repo.problem_detail(conn, lane["problem_id"])["kcs"]}
           for lane in state.get("lanes", [])}  # fmt: skip
    return codes, kcs


def _low_confidence(paths: DataPaths) -> float:
    try:
        return config.load(paths.settings)["review"]["low_confidence"]
    except config.SettingsError:
        return config.defaults()["review"]["low_confidence"]


def _mistake_rows(state: SessionState, review: dict) -> dict[int, list[dict]]:
    """Decisions → mistake rows per attempt seq (contract §7): accept → confirmed, edit → edited, reject → rejected,
    add → added (llm_json, confidence, verifier NULL). llm_json = the proposal minus `verifier`."""
    props, out = {p["pid"]: p for p in state["proposals"]}, {}
    status = {"accept": "confirmed", "edit": "edited", "reject": "rejected", "add": "added"}
    for key, d in _cards(review).items():
        seq, f = _card(state, key, d)
        p = props.get(key)
        v = (p or {}).get("verifier") or {}
        note = d.get("teacher_note")
        out.setdefault(seq, []).append(f | {
            "confidence": p and p["confidence"], "verifier_verdict": v.get("verdict"),
            "verifier_reason": v.get("reason"),
            "status": status[d["action"]], "llm_json": p and {k: x for k, x in p.items() if k != "verifier"},
            "teacher_note": note if isinstance(note, str) and note.strip() else None,
        })  # fmt: skip
    return out


def pending(paths: DataPaths) -> Callable[[dict, object, str], int]:
    """Runner resume check: flags still unanswered at confirm_match, cards still undecided at review (SDD §5.4)."""

    def count(state: dict, decisions: object, node: str) -> int:
        if node == "gate_confirm_commit":
            return 0  # the decisions are final; resume only needs the tutor's go
        if node == "gate_review":
            with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
                codes, kcs = _review_inputs(conn, state)
            return _review_pending(state, decisions, codes, kcs)
        decisions = decisions if isinstance(decisions, dict) else {}
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            refs = {b["ref"] for b in repo.bank_problems(conn)}
        n = 0
        for f in _unresolved(state):
            d = decisions.get(str(f["seq"]))
            d = d if isinstance(d, dict) else {}
            ok = d.get("problem_ref") in refs if f["type"] == "low_match" else _rubric_ok(d.get("rubric_items"))
            n += not (ok or d.get("skip") is True)
        return n

    return count


def preview_of(paths: DataPaths, state: dict, review: dict) -> tuple[dict, dict, dict]:
    """(profile, prior, preview) of node 05 for these review decisions; reads only, so gate_review can show it too.
    `preview` = the same result in words for the teacher (no θ, δ or codes)."""
    rows = _mistake_rows(state, review)
    lanes = sorted(state.get("lanes", []), key=lambda x: x["seq"])
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        prior = repo.profile_prior(conn, state["student_id"])
        probs = repo.profile_problems(conn, [lane["problem_id"] for lane in lanes])
        kc_names = {k["id"]: k["name"] for k in repo.list_kc(conn)}
        code_words = {c["code"]: c["description"] for c in repo.error_codes(conn)}
    attempts = [{"seq": lane["seq"], **probs[lane["problem_id"]],
                 "mistakes": [{"code": m["code"], "kc_id": m["kc_id"]}
                              for m in rows.get(lane["seq"], []) if m["status"] != "rejected"]}
                for lane in lanes]  # fmt: skip
    result = elo.profile(prior, attempts, state["held_on"])
    no_rubric = {f["seq"] for f in state["ingest"]["flags"] if f["type"] == "no_rubric"}  # as repo._receipt
    miscon, codes = result["miscon_change"], result["codes"]
    preview = {
        "kcs": [{"kc": kc_names[k["kc_id"]], "before": k["level_before"], "after": k["level_after"],
                 "trend": k["trend"],
                 "n_mistakes": sum(m["kc_id"] == k["kc_id"] for a in attempts for m in a["mistakes"])}
                for k in result["kcs"]],
        "miscon": {n: [f"{code_words[c]} ({kc_names[kc]})" for c, kc in miscon[n]] for n in miscon},
        "codes": {n: [code_words[c] for c in codes[n]] for n in codes},
        "writes": {"attempt": len(lanes), "mistake": sum(map(len, rows.values())),
                   "rubric": len(no_rubric & {lane["seq"] for lane in lanes}),
                   "skill_event": len(result["events"]), "skill_state": len(result["skills"]),
                   "misconception_log": len(result["miscon"])},
    }  # fmt: skip
    return result, prior, preview


def sig(preview: dict) -> str:
    """preview_sig (api-v3 §3.4): the second resume of Lưu kết quả goes on only if the preview shown still holds."""
    body = json.dumps({k: v for k, v in preview.items() if k != "writes"}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


_RUNNING = {"prepare": "grading", "gate_confirm_match": "grading", "apply_match": "grading", "lane": "grading",
            "queue": "grading", "mark_waiting_review": "grading", "gate_review": "saving", "profile": "saving",
            "mark_waiting_confirm": "saving", "gate_confirm_commit": "saving", "commit": "saving"}  # fmt: skip
_AWAITING = {"gate_confirm_match": "confirm", "gate_review": "review", "gate_confirm_commit": "preview"}
_WHY = {"awaiting_review": "earlier_pending", "failed": "earlier_failed", "running": "earlier_running"}
_STEP = {"ingest": "đọc bài", "prepare": "đọc bài", "lane": "chấm bài", "profile": "tính tiến bộ",
         "commit": "lưu kết quả"}  # fmt: skip
_CODE = re.compile(rf"\b(?:{'|'.join(repo.ERROR_CATEGORIES)})\.\w+")


def _stage(row: dict, state: dict) -> str:
    """The runner's status + node as api-v3 §3.4 names it (a running node is the last one done), date lock aside."""
    status, node = row["status"], row["node"]
    if status == "running":
        if node == "prepare" and _unresolved(state):  # next is the confirm gate, not the lanes
            return "reading"
        return _RUNNING.get(node, "reading")
    if status == "awaiting_review":
        return _AWAITING[node]
    return "saved" if status == "committed" else "failed"


def _reason(error: str) -> str:
    if re.search(r"Khoá API bị từ chối|Thiếu OPENAI_API_KEY", error):  # before 429: no quota arrives as a 429
        return "Khoá API sai, hết hạn hoặc chưa có (mở ⚙ Cài đặt)"
    if "Tiến trình dừng giữa chừng" in error:
        return "App bị tắt"
    if re.search(r"\b(?:429|529)\b|overloaded|rate.?limit", error, re.I):
        return "Dịch vụ trợ lý đang quá tải"
    if re.search(r"connection|timed out|timeout", error, re.I):
        return "Mất kết nối"
    return "Gặp lỗi không lường trước"


def _plain(text: str, code_words: dict[str, str]) -> str:
    """Model text for the teacher: an error code `x.y` in it becomes the code's description."""
    return _CODE.sub(lambda m: code_words.get(m.group(), "một loại lỗi khác"), text)


def _check(p: dict, code_words: dict[str, str]) -> str | None:
    v = p.get("verifier") or {}
    if v.get("verdict") == "agree":
        return None
    if v.get("verdict") == "disagree":
        return f"Kiểm tra lại thấy có thể không phải lỗi: {_plain(v['reason'], code_words)}"
    if v.get("verdict") == "wrong_code" and v.get("suggested_code") in code_words:
        return f"Kiểm tra lại thấy có thể là loại “{code_words[v['suggested_code']]}”."
    return "Chưa kiểm tra lại được."


def _confirm(state: dict, statements: dict[str, str]) -> list[dict]:
    """The flags the teacher still answers at confirm_match; `statements` = bank ref → statement."""
    attempts, out = {a["seq"]: a for a in state["ingest"]["attempts"]}, []
    for f in _unresolved(state):
        a = attempts[f["seq"]]
        if f["type"] == "low_match":
            first = a["steps"][0]["latex"] if a["steps"] else ""
            out.append({"seq": a["seq"], "type": "low_match", "first_step_latex": first,
                        "candidates": [{"ref": c["ref"], "statement_latex": statements[c["ref"]], "best": i == 0}
                                       for i, c in enumerate(a["candidates"])]})  # fmt: skip
        else:
            draft = state["rubric_drafts"].get(str(f["seq"]))
            out.append({"seq": a["seq"], "type": "no_rubric", "ref": a["ref"],
                        "rubric_draft": [{k: i[k] for k in ("item_id", "text", "points")} for i in draft["items"]]
                        if draft else []})  # fmt: skip
    return out


def _mistake(p: dict, kc_names: dict[int, str], code_words: dict[str, str], low: float) -> dict:
    """One 03 proposal as the card shows it; `code` and `suggested_code` are only there to be sent back."""
    kc = None if p["kc_id"] is None else {"id": p["kc_id"], "name": kc_names[p["kc_id"]]}
    return {"pid": p["pid"], "step_idx": p["step_idx"], "code": p["code"], "kind": code_words[p["code"]], "kc": kc,
            "description": _plain(p["description"], code_words), "evidence_latex": p["evidence_latex"],
            "unsure": p["confidence"] < low, "suggested_code": (p.get("verifier") or {}).get("suggested_code"),
            "check": _check(p, code_words)}  # fmt: skip


def _error_words(row: dict, state: dict) -> str:
    """api-v3 §3.4: "<reason> khi đang <step>. ..." from the runner's error text and the node that failed."""
    step = _STEP.get(row["node"], "xử lý bài làm")
    if row["node"] == "lane":
        done = {lane["seq"] for lane in state.get("lanes", [])}
        left = [str(seq) for seq in _attempts(state) if seq not in done]
        step += f" {', '.join(left)}" if left else ""
    return f"{_reason(row['error'] or '')} khi đang {step}. Bài làm vẫn còn nguyên, chưa có gì được lưu."


def card(paths: DataPaths, row: dict, state: dict, progress: int | None) -> dict:
    """The teacher's view of a G1 thread (api-v3 §3.4): words only, no θ, δ, node names or error codes.
    `row` went through threads.annotate; `progress` = runner.done_count(thread, "lane")."""
    at = _stage(row, state)
    res = state.get("ingest") or {"attempts": [], "flags": []}
    lanes = {lane["seq"]: lane for lane in state.get("lanes", [])}
    proposals = state.get("proposals", [])
    stored = json.loads(row["decisions_json"]) if row.get("decisions_json") else None
    saved = state.get("review") if stored is None else stored
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        kc_names = {k["id"]: k["name"] for k in repo.list_kc(conn)}
        code_words = {c["code"]: c["description"] for c in repo.error_codes(conn)}
        problems = {a["problem_id"]: repo.problem_detail(conn, a["problem_id"]) for a in res["attempts"]
                    if a["problem_id"] is not None}  # fmt: skip
        statements = {b["ref"]: b["statement_latex"] for b in repo.bank_problems(conn)} if at == "confirm" else {}
        codes, kcs = _review_inputs(conn, state) if at == "review" else (set(), {})
    low, drafted = _low_confidence(paths), {f["seq"] for f in res["flags"] if f["type"] == "no_rubric"}
    attempts = []
    for a in res["attempts"]:
        pr, grade = problems.get(a["problem_id"]), (lanes.get(a["seq"]) or {}).get("grade")
        attempts.append({
            "seq": a["seq"], "ref": a["ref"], "statement_latex": pr and pr["statement_latex"],
            "score": grade and grade["score"], "max_score": grade and grade["max_score"],
            "skipped": bool(a.get("skipped")), "rubric_draft": a["seq"] in drafted,
            "kcs": [{"id": k["id"], "name": k["name"]} for k in pr["kcs"]] if pr else [],
            "steps": [{"idx": s["idx"], "latex": s["latex"]} for s in a["steps"]],
            "mistakes": [_mistake(p, kc_names, code_words, low) for p in proposals if p["attempt_seq"] == a["seq"]],
        })  # fmt: skip
    decided, shown = None, state.get("preview") if at == "preview" else None
    if at == "review":
        pids = {p["pid"] for p in proposals}
        mine = {"cards": {k: d for k, d in _cards(saved).items() if k in pids}}  # added mistakes are not counted
        decided = {"done": len(proposals) - _review_pending(state, mine, codes, kcs), "total": len(proposals)}
        if not _review_pending(state, saved, codes, kcs):
            shown = preview_of(paths, state, saved)[2]
    preview = shown and {k: v for k, v in shown.items() if k != "writes"}
    grades = [lane["grade"] for lane in lanes.values()]
    score, max_score = (
        (sum(g["score"] for g in grades), sum(g["max_score"] for g in grades)) if grades else (None, None)
    )
    total, rc = sum(not a.get("skipped") for a in res["attempts"]), state.get("receipt")
    return {
        "kind": "grading",
        "stage": "locked" if row["locked"] else at,
        "student_id": row["student_id"],
        "held_on": row["held_on"],
        "file": Path(state["source_path"]).name if state.get("source_path") else None,
        "progress": {"done": progress, "total": total}
        if progress is not None and at in ("reading", "confirm", "grading", "review") else None,
        "score": score,
        "max_score": max_score,
        "decided": decided,
        "saved": stored,
        "confirm": _confirm(state, statements) if at == "confirm" else [],
        "attempts": attempts,
        "preview": preview,
        "preview_sig": preview and sig(preview),
        "lock": {"blocked_by": {"thread_id": row["blocking_thread_id"], "held_on": row["blocking_held_on"]},
                 "why": _WHY[row["blocking_status"]]} if row["locked"] else None,
        "error_words": _error_words(row, state) if at == "failed" else None,
        "receipt": rc and {"score": score, "max_score": max_score, "backed_up": True,
                           "n_mistakes": rc["mistake"] - rc["by_status"]["rejected"]},
    }  # fmt: skip


def reminder(paths: DataPaths, row: dict, state: dict) -> dict:
    """One line of GET /api/assistant/pending (api-v3 §3.3) for a G1 thread."""
    at = "locked" if row["locked"] else _stage(row, state)
    if at == "confirm":
        words = f"cần xác nhận {len(_unresolved(state))} bài"
    elif at == "review":
        saved = json.loads(row["decisions_json"]) if row.get("decisions_json") else state.get("review")
        n = pending(paths)(state, saved, "gate_review")
        words = f"{n} lỗi cần xem" if n else "chờ lưu kết quả"
    elif at == "locked":
        words = f"chờ duyệt buổi {date.fromisoformat(row['blocking_held_on']):%d/%m} trước"
    else:
        words = "chấm chưa xong" if at == "failed" else "chờ lưu kết quả"
    return {
        "kind": "grading",
        "thread_id": row["thread_id"],
        "student_id": row["student_id"],
        "date": row["held_on"],
        "state": at,
        "words": words,
    }


def build(paths: DataPaths) -> StateGraph:
    def run_ingest(state: SessionState, config) -> dict:
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            st = repo.get_student(conn, state["student_id"])
            bank = repo.bank_problems(conn)
        tex = (paths.root / state["source_path"]).read_text(encoding="utf-8")
        ctx = call_context(paths, state["student_id"], state["session_id"], config)
        res = ingest.run(tex, bank, grade=st["grade"], ctx=ctx)
        return {"transcript": tex, "ingest": res.model_dump(), "rubric_drafts": {}, "approved_rubrics": {}}

    def prepare(state: SessionState, config) -> dict:
        """Every matched problem needs a rubric: approved in the bank, or drafted by 02 for step 3."""
        res, drafts = copy.deepcopy(state["ingest"]), dict(state["rubric_drafts"])
        approved = state["approved_rubrics"]
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            for a in res["attempts"]:
                key = str(a["seq"])
                if a.get("skipped") or a["problem_id"] is None or key in approved:
                    continue
                problem = repo.problem_detail(conn, a["problem_id"])
                if problem["rubric"]:
                    continue
                if not any(f["type"] == "no_rubric" and f["seq"] == a["seq"] and not f["resolved"]
                           for f in res["flags"]):  # fmt: skip
                    res["flags"].append({"type": "no_rubric", "seq": a["seq"], "resolved": False,
                                         "detail": f"Bài {a['seq']} ({a['ref']}) chưa có rubric đã duyệt"})  # fmt: skip
                if key not in drafts:
                    ctx = call_context(paths, state["student_id"], state["session_id"], config)
                    drafts[key] = grader.generate_rubric(problem, ctx=ctx)
        return {"ingest": res, "rubric_drafts": drafts}

    def route(state: SessionState):
        if _unresolved(state):
            return "mark_waiting"
        sends = [Send("lane", {"lane": _lane_input(state, a)}) for a in _attempts(state).values()]
        return sends or "queue"  # everything skipped: an empty Send list would end the graph

    def mark_waiting(state: SessionState) -> dict:
        # Own node before each gate: it is done once, so resuming the gate never writes again.
        with closing(repo.connect(paths.tutor_db)) as conn:
            repo.commit_session_status(conn, state["session_id"], "awaiting_review")
        return {}

    def gate_confirm_match(state: SessionState) -> dict:
        return {"match_decisions": interrupt({"gate": "confirm_match", "flags": _unresolved(state)})["decisions"]}

    def apply_match(state: SessionState) -> dict:
        """Fold the teacher's answers into the attempts; pending() already checked them before resume."""
        res, approved = copy.deepcopy(state["ingest"]), dict(state["approved_rubrics"])
        decisions = state["match_decisions"] or {}
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            by_ref = {b["ref"]: b for b in repo.bank_problems(conn)}
        attempts = {a["seq"]: a for a in res["attempts"]}
        for f in [f for f in res["flags"] if not f["resolved"]]:
            d = decisions[str(f["seq"])]
            if d.get("skip") is True:
                attempts[f["seq"]]["skipped"] = True
            elif f["type"] == "low_match":
                b = by_ref[d["problem_ref"]]
                attempts[f["seq"]] |= {"ref": b["ref"], "problem_id": b["id"]}
            else:
                items = d["rubric_items"]
                approved[str(f["seq"])] = {"items": items, "max_score": sum(i["points"] for i in items)}
            f |= {"resolved": True, "decision": d}
        with closing(repo.connect(paths.tutor_db)) as conn:
            repo.commit_session_status(conn, state["session_id"], "running")
        return {"ingest": res, "approved_rubrics": approved}

    def queue(state: SessionState) -> dict:
        cards = []
        for lane in sorted(state.get("lanes", []), key=lambda x: x["seq"]):
            for m in lane["mistakes"]:
                cards.append({"pid": f"p{len(cards) + 1}", "kind": "mistake", "attempt_seq": lane["seq"]} | m)
        return {"proposals": verifier.order_queue(cards, _low_confidence(paths))}

    def gate_review(state: SessionState) -> dict:
        # resume sends None when the teacher never saved a decision (0 mistakes): commit and the preview read a dict
        return {"review": interrupt({"gate": "review", "n": len(state["proposals"])})["decisions"] or {}}

    def profile(state: SessionState) -> dict:
        """05: replay this session over the stored prior. Reads only, no LLM; commit ② writes the result."""
        result, prior, preview = preview_of(paths, state, state["review"])
        return {"profile": result, "profile_prior": prior, "preview": preview}

    def gate_confirm_commit(state: SessionState) -> dict:
        interrupt({"gate": "confirm_commit"})
        return {}

    def commit(state: SessionState) -> dict | Command:
        """② : backup first (C-29), then one transaction. A rerun after a failure runs only this node.
        A prior that changed since 05 ran (another session committed) → back to 05, nothing written."""
        review, attempts = state["review"], _attempts(state)
        rows = _mistake_rows(state, review)
        flags = state["ingest"]["flags"]
        out = []
        for lane in sorted(state.get("lanes", []), key=lambda x: x["seq"]):
            a, g = attempts[lane["seq"]], lane["grade"]
            out.append({
                "seq": a["seq"], "problem_id": lane["problem_id"], "rubric_id": lane["rubric"].get("id"),
                "rubric": lane["rubric"], "solution_latex": state["transcript"][a["pos"]:a["pos_end"]],
                "steps": a["steps"], "grade_items": g["items"], "score": g["score"], "max_score": g["max_score"],
                "flags": [f for f in flags if f["seq"] == a["seq"]] + g["flags"] + lane["diagnosis"]["flags"],
                "mistakes": rows.get(a["seq"], []),
            })  # fmt: skip
        secs = review.get("review_seconds")
        secs = secs if isinstance(secs, int) and not isinstance(secs, bool) and secs >= 0 else None
        backup = repo.backup(paths.tutor_db, paths.backup)
        try:
            with closing(repo.connect(paths.tutor_db)) as conn:
                receipt = repo.commit_session(conn, state["session_id"], transcript=state["transcript"],
                                              review_seconds=secs, attempts=out, profile=state.get("profile"),
                                              prior=state.get("profile_prior"))  # fmt: skip
        except repo.StaleProfile:
            return Command(goto="profile")
        return {"receipt": receipt | {"backup": backup.name}, "committed": True}

    g = StateGraph(SessionState)
    g.add_node("ingest", run_ingest)
    g.add_node("prepare", prepare)
    g.add_node("mark_waiting", mark_waiting)
    g.add_node("gate_confirm_match", gate_confirm_match)
    g.add_node("apply_match", apply_match)
    g.add_node("lane", _lane(paths).compile())
    g.add_node("queue", queue)
    g.add_node("mark_waiting_review", mark_waiting)
    g.add_node("gate_review", gate_review)
    g.add_node("profile", profile)
    g.add_node("mark_waiting_confirm", mark_waiting)
    g.add_node("gate_confirm_commit", gate_confirm_commit)
    g.add_node("commit", commit)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "prepare")
    g.add_conditional_edges("prepare", route, ["mark_waiting", "lane", "queue"])
    g.add_edge("mark_waiting", "gate_confirm_match")
    g.add_edge("gate_confirm_match", "apply_match")
    g.add_edge("apply_match", "prepare")
    g.add_edge("lane", "queue")
    g.add_edge("queue", "mark_waiting_review")
    g.add_edge("mark_waiting_review", "gate_review")
    g.add_edge("gate_review", "profile")
    g.add_edge("profile", "mark_waiting_confirm")
    g.add_edge("mark_waiting_confirm", "gate_confirm_commit")
    g.add_edge("gate_confirm_commit", "commit")
    g.add_edge("commit", END)
    return g


def _lane(paths: DataPaths) -> StateGraph:
    """02 → 03 → 04 for one problem. A subgraph so a failed lane reruns only its own failed node and later ones."""

    def load(lane: dict) -> tuple[dict, dict]:
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            problem = repo.problem_detail(conn, lane["problem_id"])
        return problem, lane["rubric"] or problem["rubric"]

    def grade(state: LaneState, config) -> dict:
        lane = state["lane"]
        problem, rubric = load(lane)
        ctx = call_context(paths, lane["student_id"], lane["session_id"], config)
        return {"lane_grade": grader.grade(lane["steps"], problem, rubric, ctx=ctx).model_dump()}

    def diagnose(state: LaneState, config) -> dict:
        lane, g = state["lane"], state["lane_grade"]
        problem, rubric = load(lane)
        failed = {i["item_id"] for i in g["items"] if not i["passed"]}
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            codes = repo.error_codes(conn, active_only=True)
            history = repo.recent_mistakes(conn, lane["student_id"])
        ctx = call_context(paths, lane["student_id"], lane["session_id"], config)
        d = diagnoser.run(lane["steps"], problem, codes=codes, history=history, ctx=ctx,
                          failed_items=[i["text"] for i in rubric["items"] if i["item_id"] in failed])  # fmt: skip
        return {"lane_diag": d.model_dump() | {"context": history}}

    def verify(state: LaneState, config) -> dict:
        lane, d = state["lane"], state["lane_diag"]
        problem, rubric = load(lane)
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            codes = repo.error_codes(conn, active_only=True)
        ctx = call_context(paths, lane["student_id"], lane["session_id"], config)
        mistakes = [m | {"verifier": verifier.run(m, lane["steps"], problem, codes=codes, ctx=ctx).model_dump()}
                    for m in d["mistakes"]]  # fmt: skip
        return {"lanes": [{"seq": lane["seq"], "problem_id": lane["problem_id"], "rubric": rubric,
                           "grade": state["lane_grade"], "diagnosis": {"corrected_latex": d["corrected_latex"],
                           "flags": d["flags"], "context": d["context"]}, "mistakes": mistakes}]}  # fmt: skip

    g = StateGraph(LaneState)
    g.add_node("grade", grade)
    g.add_node("diagnose", diagnose)
    g.add_node("verify", verify)
    g.add_edge(START, "grade")
    g.add_edge("grade", "diagnose")
    g.add_edge("diagnose", "verify")
    g.add_edge("verify", END)
    return g


def diagnoser_prompt_version(conn) -> str:
    """03's prompt_version for the current active taxonomy."""
    return diagnoser.prompt_version(repo.error_codes(conn, active_only=True))


def on_fail(paths: DataPaths) -> Callable[[dict], None]:
    def mark_failed(row: dict) -> None:
        if row["session_id"]:
            with closing(repo.connect(paths.tutor_db)) as conn:
                repo.commit_session_status(conn, row["session_id"], "failed")

    return mark_failed
