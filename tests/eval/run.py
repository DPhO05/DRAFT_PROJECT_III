"""G1 eval harness (P2-T10, NFR8): run G1 to the review gate on the labeled fixtures, score it, save by prompt_version.

uv run python tests/eval/run.py [--agent g1|00|09 | --set g1-dev] [--backend fake|dev|real] [--runs 3]
                                [--files s01.tex ... | --only q4 ...] [--out data/eval/results/]

fake = label oracle (checks the harness itself), dev = tutor.devfake, real = Anthropic API (costs money; manual only,
C-34). A prompt is fit for use only after it passes 3 runs (pass^3). --agent 00 and 09 use tests/eval/agents.py;
--files is for g1 only, --only for the others.
"""

# ruff: noqa: E402
import argparse
import json
import shutil
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

from tests.eval import agents, metrics
from tests.fakes import FakeLLM, lane_handlers
from tutor import config, devfake, llm
from tutor.agents.a01_ingest import ingest
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier
from tutor.db import repo, seed_dummy
from tutor.graphs import runner, session

FIX = ROOT / "tests" / "fixtures" / "submissions"
SETS = Path(__file__).with_name("sets.json")
LOCAL_SETS = ROOT / "data" / "eval" / "sets.json"  # sets built from real data: local, never in git
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


def load_sets() -> dict[str, dict]:
    """The committed sets, updated by the local file when it exists."""
    sets = json.loads(SETS.read_text(encoding="utf-8"))
    if LOCAL_SETS.exists():
        sets |= json.loads(LOCAL_SETS.read_text(encoding="utf-8"))
    return sets


def load_labels(files: list[str] | None = None, fix: Path = FIX) -> dict:
    """Labels of `files`; default every fixture except duplicate-check copies."""
    every = json.loads((fix / "labels.json").read_text(encoding="utf-8"))
    return {f: every[f] for f in files or [f for f, lab in every.items() if "duplicate_of" not in lab]}


def evaluate(make_backend, *, work: Path, files: list[str] | None = None, runs: int = 3, fix: Path = FIX,
             traces: Path | None = None) -> dict:  # fmt: skip
    """make_backend(conn, labels) -> (llm backend | None for the real API, models). Each run gets a new world in
    work/run<k>; the backend is built once, on run 1."""
    labels = load_labels(files, fix)
    files = list(labels)
    results, errors, rows = [], [], []
    for k in range(1, runs + 1):
        paths = config.paths(work / f"run{k}" / "data").ensure()
        repo.init_db(paths.tutor_db, paths.backup)
        with closing(repo.connect(paths.tutor_db)) as conn:
            seed_dummy.seed(conn, BANK)
            if k == 1:  # once: a stateful fake keeps its counters across runs
                backend, models = make_backend(conn, labels)
        for f in files:
            (paths.inbox / f).write_bytes((fix / f).read_bytes())
        log = paths.logs / "llm.jsonl"
        llm.configure(log, models)
        llm.set_backend(backend)
        r = runner.Runner(paths, {"G1": session.build(paths)})
        r.on_fail("G1", session.on_fail(paths))
        r.pending_fn("G1", session.pending(paths))
        got = {}
        try:
            for f in files:
                try:
                    got |= _one(paths, r, f, labels[f])
                except Exception as e:  # recorded; the problems count as missing in stability
                    errors.append({"run": k, "file": f, "error": f"{type(e).__name__}: {e}"})
        finally:
            r.close()
        results.append(got)
        rows += [r | {"run": k} for r in agents.read_log(log)]
        if traces is not None and log.exists():
            traces.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log, traces / f"run{k}.jsonl")
    seen: dict[str, dict[str, set]] = {"prompt_version": {}, "model": {}}
    for row in rows:
        for field, by_agent in seen.items():
            by_agent.setdefault(row["agent"], set()).add(row[field])
    stability = metrics.stability(results)
    # every label key starts False, so a problem that failed in all runs still counts
    every = {f"{f}#{p['seq']}": False for f, lab in labels.items() for p in lab["problems"]}
    tally = metrics.tally([every | metrics.g1_passed(g) for g in results])
    return {
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": runs,
        "files": files,
        "prompt_versions": {a: sorted(v) for a, v in sorted(seen["prompt_version"].items())},
        "models": {a: sorted(v) for a, v in sorted(seen["model"].items())},
        "metrics": {
            "per_run": [metrics.score(list(g.values())) for g in results],
            "stability": stability,
            "pass_k": tally["pass_k"],
            "success": tally["success"],
            "tally": tally,
            "extra": {"flow_errors": len(errors), "items_changed_pct": stability["items_changed_pct"]},
        },
        "errors": errors,
        "calls": metrics.usage(rows),
        "problems": results,
    }


TARGETS: dict[str, dict] = {  # --agent value -> how to run it; "g1" is handled by evaluate()
    "00": {"evaluate": agents.evaluate_00, "oracle": agents.oracle_00, "ids": ("00",)},
    "09": {"evaluate": agents.evaluate_09, "oracle": agents.oracle_09, "ids": ("09",)},
}


def meta(target: str, set_name: str | None, backend: str) -> dict:
    """The fields that say what a result is a result of."""
    if target == "g1":
        s = load_sets()[set_name]
        return {"backend": backend, "set": set_name, "target": target, "split": s["split"], "source": s["source"]}
    return {"backend": backend, "set": f"{target}-dev", "target": target, "split": "dev", "source": "synthetic"}


def _backend(name: str, fake=oracle):
    if name == "fake":
        return fake
    if name == "dev":
        return lambda *_: (devfake.DevFakeLLM(), devfake.models())
    return lambda *_: (None, config.load(config.paths().settings)["models"])


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agent", choices=["g1", *TARGETS])
    ap.add_argument("--set", help="bộ bài của g1, xem tests/eval/sets.json")
    ap.add_argument("--backend", choices=["fake", "dev", "real"], default="dev")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--files", nargs="+")
    ap.add_argument("--only", nargs="+", help="chỉ chạy các id này (không dùng cho g1)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "results")
    ap.add_argument("--traces", type=Path, help="mẹ của thư mục vết (mặc định <out>/../traces)")
    ap.add_argument("--yes", action="store_true", help="xác nhận chạy API thật (tốn tiền)")
    a = ap.parse_args(argv)
    if a.runs < 1:
        print("--runs phải từ 1 trở lên.")
        return 2
    target = a.agent or "g1"
    fix = FIX
    if target == "g1":
        if a.only:
            print("--only không dùng cho g1, dùng --files")
            return 2
        sets = load_sets()
        a.set = a.set or "g1-dev"
        if a.set not in sets:
            print(f"Không có bộ {a.set}. Có: {', '.join(sets)}")
            return 2
        fix = ROOT / sets[a.set]["dir"]
    elif a.set not in (None, f"{target}-dev"):
        print(f"Không có bộ {a.set} cho agent {target}.")
        return 2
    if a.backend == "real":
        if target == "g1":
            n = sum(len(lab["problems"]) for lab in load_labels(a.files, fix).values())
            what = f"{n} bài toán × ≥ 3 lượt gọi (02 · 03 · 04 mỗi lỗi; 01 khi thiếu mã bài)"
        elif target == "00":
            what = f"{len(agents.QUESTIONS)} câu × ≥ 2 lượt gọi"
        else:
            what = f"{len(agents.PERIODS)} kỳ × 1–2 lượt gọi"
        print(f"CẢNH BÁO: gọi API thật (Anthropic / OpenAI theo settings), tốn tiền: {a.runs} lần × {what}.")
        if not a.yes:
            print("Thêm --yes để chạy.")
            return 2
        config.load_env(config.ENV_FILE)  # no cli callback here; GPT settings need OPENAI_API_KEY
    with tempfile.TemporaryDirectory(prefix="tutor-eval-") as tmp:
        info = meta(target, a.set, a.backend)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        folder = (a.traces or a.out.parent / "traces") / f"{stamp}_{target}"
        if target == "g1":
            res = evaluate(_backend(a.backend), work=Path(tmp), files=a.files, runs=a.runs, fix=fix, traces=folder)
        else:
            t = TARGETS[target]
            try:
                res = t["evaluate"](_backend(a.backend, t["oracle"]), work=Path(tmp), runs=a.runs, only=a.only,
                                    traces=folder)  # fmt: skip
            except agents.UnknownTask as e:
                print(e)
                return 2
        res = info | res | {"traces": str(folder)}
    for k, s in enumerate(res["metrics"]["per_run"], 1):
        print(f"run {k}: " + "  ".join(f"{m}={_fmt(v)}" for m, v in s.items()))
    if target == "g1":
        print("stability: " + "  ".join(f"{m}={_fmt(v)}" for m, v in res["metrics"]["stability"].items()))
    else:
        print(f"pass_k={_fmt(res['metrics']['pass_k'])}")
    for e in res["errors"]:
        print(f"LỖI run {e['run']} {e.get('file') or e.get('id') or e.get('key')}: {e['error']}")
    print("prompt_version: " + "  ".join(v for vs in res["prompt_versions"].values() for v in vs))
    print(f"calls: logged={res['calls']['logged']}  usd={res['calls']['usd']:.3f}")
    ids = ("02", "03", "04") if target == "g1" else TARGETS[target]["ids"]
    key = "_".join(v for a_ in ids for v in res["prompt_versions"].get(a_, []))
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"{res['created'].replace(':', '').replace('-', '')}_{key}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
