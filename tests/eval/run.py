"""G1 eval harness (P2-T10, NFR8): run G1 to the review gate on the labeled fixtures, score it, save by prompt_version.

uv run python tests/eval/run.py [--backend fake|dev|real] [--runs 3] [--files s01.tex ...] [--out data/eval/results/]

fake = label oracle (checks the harness itself), dev = tutor.devfake, real = Anthropic API (costs money; manual only,
C-34). A prompt is fit for use only after it passes 3 runs (pass^3).
"""

# ruff: noqa: E402
import argparse
import json
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

from tests.eval import metrics
from tests.fakes import FakeLLM, lane_handlers
from tutor import config, devfake, llm
from tutor.agents.a01_ingest import ingest
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier
from tutor.db import repo, seed_dummy
from tutor.graphs import runner, session

FIX = ROOT / "tests" / "fixtures" / "submissions"
BANK = ROOT / "data" / "dummy" / "bank"
HELD_ON = "2026-10-20"
TIMEOUT = 900  # seconds per graph leg; real API lanes are slow


def oracle(conn, labels: dict):
    """FakeLLM answering exactly the labels: 03 finds its problem by the statement in the prompt."""
    by_ref = {p["ref"]: p for lab in labels.values() for p in lab["problems"]}
    ref_of = {b["statement_latex"]: b["ref"] for b in repo.bank_problems(conn)}
    kc_id = {k["code"]: k["id"] for k in repo.list_kc(conn)}

    def h03(user, system):
        statement = user.split("Đề:\n", 1)[1].split("\n\nLời giải mẫu:\n", 1)[0]
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[
            diagnoser.MistakeOut(step_idx=m["step_idx"], code=m["code"], kc_id=kc_id.get(m["kc"]),
                                 description=m["note"], evidence_latex="x", confidence=0.9)
            for m in by_ref[ref_of[statement]]["mistakes"]
        ])  # fmt: skip

    handlers = {"01": ingest.MatchResult(candidates=[]), "02": lane_handlers()["02"], "03": h03,
                "04": verifier.VerdictOut(verdict="agree", reason="oracle")}  # fmt: skip
    return FakeLLM(handlers), {}


def _answer(flag: dict, state: dict, refs: dict) -> dict:
    """confirm_match from the labels; no_rubric takes 02's draft as is."""
    seq = str(flag["seq"])
    if flag["type"] == "low_match":
        return {"problem_ref": refs[seq]}
    draft = state["rubric_drafts"].get(seq) or {"items": [{"item_id": "r1", "text": "Đáp số", "points": 1}]}
    return {"rubric_items": draft["items"]}


def _one(paths, r, name: str, lab: dict) -> dict:
    """Submit one fixture, pass confirm_match, return {"<file>#<seq>": problem} at the review gate."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        sid = repo.add_student(conn, name=lab["student_name"] or f"Eval {name}", grade=lab["grade"])
    tid = session.submit(paths, r, student_id=sid, held_on=HELD_ON, rel_path=name)["thread_id"]
    row = r.wait(tid, TIMEOUT)
    refs = {str(p["seq"]): p["ref"] for p in lab["problems"]}
    while (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_match"):
        st = r.state(tid)
        r.save_decisions(tid, {str(f["seq"]): _answer(f, st, refs) for f in st["ingest"]["flags"] if not f["resolved"]})
        r.resume(tid)
        row = r.wait(tid, TIMEOUT)
    if (row["status"], row["node"]) != ("awaiting_review", "gate_review"):
        raise RuntimeError(f"{row['status']} ở {row['node']}: {row['error']}")
    st = r.state(tid)
    lanes = {lane["seq"]: lane for lane in st["lanes"]}
    out = {}
    for p in lab["problems"]:
        lane = lanes.get(p["seq"])
        out[f"{name}#{p['seq']}"] = {
            "labels": [{k: m[k] for k in ("step_idx", "code", "propagates_to")} for m in p["mistakes"]],
            "proposals": [
                {"step_idx": x["step_idx"], "code": x["code"], "verdict": x["verifier"]["verdict"]}
                for x in st["proposals"]
                if x["attempt_seq"] == p["seq"]
            ],
            "items": {i["item_id"]: i["passed"] for i in lane["grade"]["items"]} if lane else {},
        }
    return out


def load_labels(files: list[str] | None = None) -> dict:
    """Labels of `files`; default every fixture except duplicate-check copies."""
    every = json.loads((FIX / "labels.json").read_text(encoding="utf-8"))
    return {f: every[f] for f in files or [f for f, lab in every.items() if "duplicate_of" not in lab]}


def evaluate(make_backend, *, work: Path, files: list[str] | None = None, runs: int = 3) -> dict:
    """make_backend(conn, labels) -> (llm backend | None for the real API, models). Runs and files go in order."""
    labels = load_labels(files)
    files = list(labels)
    paths = config.paths(work / "data").ensure()
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        seed_dummy.seed(conn, BANK)
        backend, models = make_backend(conn, labels)
    for f in files:
        (paths.inbox / f).write_bytes((FIX / f).read_bytes())
    log = paths.logs / "llm.jsonl"
    llm.configure(log, models)
    llm.set_backend(backend)
    r = runner.Runner(paths, {"G1": session.build(paths)})
    r.on_fail("G1", session.on_fail(paths))
    r.pending_fn("G1", session.pending(paths))
    results, errors = [], []
    try:
        for k in range(runs):
            got = {}
            for f in files:
                try:
                    got |= _one(paths, r, f, labels[f])
                except Exception as e:  # recorded; the problems count as missing in stability
                    errors.append({"run": k + 1, "file": f, "error": f"{type(e).__name__}: {e}"})
            results.append(got)
    finally:
        r.close()
    versions: dict[str, set] = {}
    for row in llm.iter_log(log):
        versions.setdefault(row["agent"], set()).add(row["prompt_version"])
    return {
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": runs,
        "files": files,
        "prompt_versions": {a: sorted(v) for a, v in sorted(versions.items())},
        "metrics": {
            "per_run": [metrics.score(list(g.values())) for g in results],
            "stability": metrics.stability(results),
        },
        "errors": errors,
        "problems": results,
    }


def _backend(name: str):
    if name == "fake":
        return oracle
    if name == "dev":
        return lambda conn, labels: (devfake.DevFakeLLM(), devfake.models())
    return lambda conn, labels: (None, config.load(config.paths().settings)["models"])


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend", choices=["fake", "dev", "real"], default="dev")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--files", nargs="+")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "results")
    ap.add_argument("--yes", action="store_true", help="xác nhận chạy API thật (tốn tiền)")
    a = ap.parse_args(argv)
    if a.backend == "real":
        n = sum(len(lab["problems"]) for lab in load_labels(a.files).values())
        print(f"CẢNH BÁO: gọi Anthropic API thật, tốn tiền: {a.runs} lần × {n} bài toán × ≥ 3 lượt gọi "
              "(02 · 03 · 04 mỗi lỗi; 01 khi thiếu mã bài).")  # fmt: skip
        if not a.yes:
            print("Thêm --yes để chạy.")
            return 2
    with tempfile.TemporaryDirectory(prefix="tutor-eval-") as tmp:
        res = {"backend": a.backend} | evaluate(_backend(a.backend), work=Path(tmp), files=a.files, runs=a.runs)
    for k, s in enumerate(res["metrics"]["per_run"], 1):
        print(f"run {k}: " + "  ".join(f"{m}={_fmt(v)}" for m, v in s.items()))
    print("stability: " + "  ".join(f"{m}={_fmt(v)}" for m, v in res["metrics"]["stability"].items()))
    for e in res["errors"]:
        print(f"LỖI run {e['run']} {e['file']}: {e['error']}")
    print("prompt_version: " + "  ".join(v for vs in res["prompt_versions"].values() for v in vs))
    key = "_".join(v for a_ in ("02", "03", "04") for v in res["prompt_versions"].get(a_, []))
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"{res['created'].replace(':', '').replace('-', '')}_{key}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
