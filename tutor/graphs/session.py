"""G1 session graph (P1-T10, P2-T05, P3-T01, P3-T02).

① session row → 01 Ingest → prepare (02 drafts missing rubrics) → [DỪNG confirm_match while flags remain]
→ one 02 → 03 → 04 lane per problem (Send) → review queue → DỪNG review → commit ② (backup, one transaction).
05 Profiler + DỪNG confirm_commit go between review and commit in P4.
"""

import copy
import hashlib
from collections.abc import Callable
from contextlib import closing
from datetime import date

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from tutor import config
from tutor.agents import CallContext, diagnoser, grader, ingest, verifier
from tutor.config import DataPaths
from tutor.db import repo
from tutor.graphs.runner import Runner
from tutor.graphs.state import LaneState, SessionState

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
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
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


def _ctx(paths: DataPaths, student_id: int, session_id: int, config) -> CallContext:
    # The name is read here for masking only; it never enters graph state or checkpoints (SDD §8.6).
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        st = repo.get_student(conn, student_id)
    return CallContext(graph=GRAPH, thread_id=config["configurable"]["thread_id"], session_id=session_id,
                       student_code=st["code"], redact={st["name"]: st["code"]})  # fmt: skip


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
    return {a["seq"]: a for a in state["ingest"]["attempts"]}


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
    cards = review.get("cards") if isinstance(review, dict) else None
    cards = cards if isinstance(cards, dict) else {}
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


def _mistake_rows(state: SessionState, review: dict) -> dict[int, list[dict]]:
    """Decisions → mistake rows per attempt seq (contract §7): accept → confirmed, edit → edited, reject → rejected,
    add → added (llm_json, confidence, verifier NULL). llm_json = the proposal minus `verifier`."""
    props, out = {p["pid"]: p for p in state["proposals"]}, {}
    status = {"accept": "confirmed", "edit": "edited", "reject": "rejected", "add": "added"}
    for key, d in review["cards"].items():
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
        if node == "gate_review":
            with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
                codes = {c["code"] for c in repo.error_codes(conn, active_only=True)}
                kcs = {lane["seq"]: {k["id"] for k in repo.problem_detail(conn, lane["problem_id"])["kcs"]}
                       for lane in state["lanes"]}  # fmt: skip
            return _review_pending(state, decisions, codes, kcs)
        decisions = decisions if isinstance(decisions, dict) else {}
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            refs = {b["ref"] for b in repo.bank_problems(conn)}
        n = 0
        for f in _unresolved(state):
            d = decisions.get(str(f["seq"]))
            d = d if isinstance(d, dict) else {}
            ok = d.get("problem_ref") in refs if f["type"] == "low_match" else _rubric_ok(d.get("rubric_items"))
            n += not ok
        return n

    return count


def build(paths: DataPaths) -> StateGraph:
    def run_ingest(state: SessionState, config) -> dict:
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            st = repo.get_student(conn, state["student_id"])
            bank = repo.bank_problems(conn)
        tex = (paths.root / state["source_path"]).read_text(encoding="utf-8")
        ctx = _ctx(paths, state["student_id"], state["session_id"], config)
        res = ingest.run(tex, bank, grade=st["grade"], ctx=ctx)
        return {"transcript": tex, "ingest": res.model_dump(), "rubric_drafts": {}, "approved_rubrics": {}}

    def prepare(state: SessionState, config) -> dict:
        """Every matched problem needs a rubric: approved in the bank, or drafted by 02 for step 3."""
        res, drafts = copy.deepcopy(state["ingest"]), dict(state["rubric_drafts"])
        approved = state["approved_rubrics"]
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            for a in res["attempts"]:
                key = str(a["seq"])
                if a["problem_id"] is None or key in approved:
                    continue
                problem = repo.problem_detail(conn, a["problem_id"])
                if problem["rubric"]:
                    continue
                if not any(f["type"] == "no_rubric" and f["seq"] == a["seq"] and not f["resolved"]
                           for f in res["flags"]):  # fmt: skip
                    res["flags"].append({"type": "no_rubric", "seq": a["seq"], "resolved": False,
                                         "detail": f"Bài {a['seq']} ({a['ref']}) chưa có rubric đã duyệt"})  # fmt: skip
                if key not in drafts:
                    ctx = _ctx(paths, state["student_id"], state["session_id"], config)
                    drafts[key] = grader.generate_rubric(problem, ctx=ctx)
        return {"ingest": res, "rubric_drafts": drafts}

    def route(state: SessionState):
        if _unresolved(state):
            return "mark_waiting"
        return [Send("lane", {"lane": _lane_input(state, a)}) for a in state["ingest"]["attempts"]]

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
            if f["type"] == "low_match":
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
        for lane in sorted(state["lanes"], key=lambda x: x["seq"]):
            for m in lane["mistakes"]:
                cards.append({"pid": f"p{len(cards) + 1}", "kind": "mistake", "attempt_seq": lane["seq"]} | m)
        try:
            low = config.load(paths.settings)["review"]["low_confidence"]
        except config.SettingsError:
            low = config.defaults()["review"]["low_confidence"]
        return {"proposals": verifier.order_queue(cards, low)}

    def gate_review(state: SessionState) -> dict:
        return {"review": interrupt({"gate": "review", "n": len(state["proposals"])})["decisions"]}

    def commit(state: SessionState) -> dict:
        """② : backup first (C-29), then one transaction. A rerun after a failure runs only this node."""
        review, attempts = state["review"], _attempts(state)
        rows = _mistake_rows(state, review)
        flags = state["ingest"]["flags"]
        out = []
        for lane in sorted(state["lanes"], key=lambda x: x["seq"]):
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
        with closing(repo.connect(paths.tutor_db)) as conn:
            receipt = repo.commit_session(conn, state["session_id"], transcript=state["transcript"],
                                          review_seconds=secs, attempts=out)  # fmt: skip
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
    g.add_node("commit", commit)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "prepare")
    g.add_conditional_edges("prepare", route, ["mark_waiting", "lane"])
    g.add_edge("mark_waiting", "gate_confirm_match")
    g.add_edge("gate_confirm_match", "apply_match")
    g.add_edge("apply_match", "prepare")
    g.add_edge("lane", "queue")
    g.add_edge("queue", "mark_waiting_review")
    g.add_edge("mark_waiting_review", "gate_review")
    g.add_edge("gate_review", "commit")
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
        ctx = _ctx(paths, lane["student_id"], lane["session_id"], config)
        return {"lane_grade": grader.grade(lane["steps"], problem, rubric, ctx=ctx).model_dump()}

    def diagnose(state: LaneState, config) -> dict:
        lane, g = state["lane"], state["lane_grade"]
        problem, rubric = load(lane)
        failed = {i["item_id"] for i in g["items"] if not i["passed"]}
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            codes = repo.error_codes(conn, active_only=True)
            history = repo.recent_mistakes(conn, lane["student_id"])
        ctx = _ctx(paths, lane["student_id"], lane["session_id"], config)
        d = diagnoser.run(lane["steps"], problem, codes=codes, history=history, ctx=ctx,
                          failed_items=[i["text"] for i in rubric["items"] if i["item_id"] in failed])  # fmt: skip
        return {"lane_diag": d.model_dump() | {"context": history}}

    def verify(state: LaneState, config) -> dict:
        lane, d = state["lane"], state["lane_diag"]
        problem, rubric = load(lane)
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            codes = repo.error_codes(conn, active_only=True)
        ctx = _ctx(paths, lane["student_id"], lane["session_id"], config)
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
    """03's prompt_version for the current active taxonomy (Danh mục › Mã lỗi shows it after each edit)."""
    return diagnoser.prompt_version(repo.error_codes(conn, active_only=True))


def on_fail(paths: DataPaths) -> Callable[[dict], None]:
    def mark_failed(row: dict) -> None:
        if row["session_id"]:
            with closing(repo.connect(paths.tutor_db)) as conn:
                repo.commit_session_status(conn, row["session_id"], "failed")

    return mark_failed
