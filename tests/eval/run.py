"""G1 eval harness (P2-T10, NFR8): run G1 to the review gate on the labeled fixtures, score it, save by prompt_version.

uv run python tests/eval/run.py [--agent g1|00|09 | --set g1-dev] [--backend fake|dev|real] [--runs 3]
                                [--files s01.tex ... | --only q4 ...] [--out data/eval/results/]
uv run python tests/eval/run.py --suite full|compact [--backend ... --runs ... --yes --out ... --judge-model ...]

fake = label oracle (checks the harness itself), dev = tutor.devfake, real = Anthropic API (costs money; manual only,
C-34). A prompt is fit for use only after it passes 3 runs (pass^3). --agent 00 and 09 use tests/eval/agents.py;
--files is for g1 only, --only for the others. --judge [--judge-model provider:name] adds an LLM faithfulness score
(00, 09, g5; report-only).
"""

# ruff: noqa: E402
import argparse
import json
import re
import shutil
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

from tests.eval import agents, components, judges, metrics
from tests.fakes import FakeLLM, lane_handlers
from tutor import config, devfake, llm
from tutor.agents.a00_orchestrator import orchestrator
from tutor.agents.a01_ingest import ingest
from tutor.agents.a02_grader import grader
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier
from tutor.db import repo, seed_dummy
from tutor.graphs import runner, session

FIX = ROOT / "tests" / "fixtures" / "submissions"
SETS = Path(__file__).with_name("sets.json")
SUITES = Path(__file__).with_name("suites.json")
LOCAL_SETS = ROOT / "data" / "eval" / "sets.json"  # sets built from real data: local, never in git
BANK = ROOT / "data" / "dummy" / "bank"
HELD_ON = "2026-10-20"
TIMEOUT = 900  # seconds per graph leg; real API lanes are slow


def oracle(conn, labels: dict):
    """FakeLLM answering exactly the labels: 03 finds its problem by the statement in the prompt."""
    by_ref = {p["ref"]: p for lab in labels.values() for p in lab["problems"]}
    ref_of = {b["statement_latex"]: b["ref"] for b in repo.bank_problems(conn)}
    kc_id = {k["code"]: k["id"] for k in repo.list_kc(conn)}

    def lines(user):
        """The framed work as {step idx: line}, the way the agent sees it (masked)."""
        return {
            int(i): t
            for i, t in re.findall(r"^\[(\d+)\] (.*)$", user.split(llm.OPEN, 1)[1].split(llm.CLOSE, 1)[0], re.M)
        }

    def h03(user, system):
        statement = user.split("Đề:\n", 1)[1].split("\n\nLời giải mẫu:\n", 1)[0]
        steps = lines(user)
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[
            diagnoser.MistakeOut(step_idx=m["step_idx"], code=m["code"], kc_id=kc_id.get(m["kc"]),
                                 description=m["note"], evidence_latex=steps.get(m["step_idx"], ""), confidence=0.9)
            for m in by_ref[ref_of[statement]]["mistakes"]
        ])  # fmt: skip

    base02 = lane_handlers()["02"]

    def h02(user, system):
        out = base02(user=user, system=system)
        if not isinstance(out, grader.GradeOut):
            return out
        first = next(iter(lines(user).values()), "")
        return out.model_copy(update={"items": [i.model_copy(update={"evidence_latex": first}) for i in out.items]})

    handlers = {"01": ingest.MatchResult(candidates=[]), "02": h02, "03": h03,
                "04": verifier.VerdictOut(verdict="agree", reason="oracle")}  # fmt: skip
    return FakeLLM(handlers), {}


def _answer(flag: dict, state: dict, refs: dict) -> dict:
    """confirm_match from the labels; no_rubric takes 02's draft as is."""
    seq = str(flag["seq"])
    if flag["type"] == "low_match":
        return {"problem_ref": refs[seq]}
    draft = state["rubric_drafts"].get(seq) or {"items": [{"item_id": "r1", "text": "Đáp số", "points": 1}]}
    return {"rubric_items": draft["items"]}


def _one(paths, r, name: str, lab: dict, budgets: dict[str, int], k: int) -> tuple[dict, bool]:
    """Submit one fixture, pass confirm_match; return ({"<file>#<seq>": problem} at the review gate, whether the
    thread stopped at confirm_match exactly when ingest raised a flag). The budget is set right after submit so a
    thread that crashes later is still compared."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        sid = repo.add_student(conn, name=lab["student_name"] or f"Eval {name}", grade=lab["grade"])
    tid = session.submit(paths, r, student_id=sid, held_on=HELD_ON, rel_path=name)["thread_id"]
    if "max_calls" in lab:
        budgets[f"{k}:{tid}"] = lab["max_calls"]
    row = r.wait(tid, TIMEOUT)
    refs = {str(p["seq"]): p["ref"] for p in lab["problems"]}
    stopped = False
    while (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_match"):
        stopped = True
        st = r.state(tid)
        r.save_decisions(tid, {str(f["seq"]): _answer(f, st, refs) for f in st["ingest"]["flags"] if not f["resolved"]})
        r.resume(tid)
        row = r.wait(tid, TIMEOUT)
    if (row["status"], row["node"]) != ("awaiting_review", "gate_review"):
        raise RuntimeError(f"{row['status']} ở {row['node']}: {row['error']}")
    st = r.state(tid)
    confirm_ok = bool(st["ingest"]["flags"]) == stopped
    lanes = {lane["seq"]: lane for lane in st["lanes"]}
    attempts = {a["seq"]: a for a in st["ingest"]["attempts"]}
    redact = session.call_context(paths, sid, None, {"configurable": {"thread_id": tid}}).redact  # as the agents saw
    out = {}
    for p in lab["problems"]:
        lane = lanes.get(p["seq"])
        grade = lane["grade"] if lane else {"items": [], "flags": [], "score": None, "max_score": None}
        out[f"{name}#{p['seq']}"] = {
            "labels": [{k: m[k] for k in ("step_idx", "code", "propagates_to")} for m in p["mistakes"]],
            "proposals": [
                {"step_idx": x["step_idx"], "code": x["code"], "verdict": x["verifier"]["verdict"],
                 "evidence_latex": x["evidence_latex"]}
                for x in st["proposals"]
                if x["attempt_seq"] == p["seq"]
            ],
            "items": {i["item_id"]: i["passed"] for i in grade["items"]},
            "steps": {s["idx"]: llm.mask(s["latex"], redact) for s in attempts[p["seq"]]["steps"]},
            "score": grade["score"],
            "max_score": grade["max_score"],
            "evidence": {i["item_id"]: i["evidence_latex"] for i in grade["items"] if i["passed"]},
            "flags": [f["type"] for f in [*grade["flags"], *(lane["diagnosis"]["flags"] if lane else [])]],
        }  # fmt: skip
    return out, confirm_ok


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
    names = {lab["student_name"]: "X" for lab in labels.values() if lab["student_name"]}
    results, errors, rows, confirms = [], [], [], []
    budgets: dict[str, int] = {}
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
                    out, ok = _one(paths, r, f, labels[f], budgets, k)
                    got |= out
                    confirms.append(ok)
                except Exception as e:  # recorded; the problems count as missing in stability
                    confirms.append(False)  # a file that never reached the review gate is not confirmed
                    errors.append({"run": k, "file": f, "error": orchestrator.mask(f"{type(e).__name__}: {e}", names)})
        finally:
            r.close()
        results.append(got)
        rows += [row | {"run": k} for row in agents.read_log(log)]
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
    trajectory = metrics.trajectory(rows, budgets or None)
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
            "components": [metrics.components(list(g.values())) for g in results],
            "trajectory": trajectory,
            "extra": {
                "flow_errors": len(errors),
                "items_changed_pct": stability["items_changed_pct"],
                "name_leaks": agents.leak_count(agents._strings([results, errors]), names),
                "over_budget": trajectory["over_budget"],
                "order_ok": trajectory["order_ok"],
                "confirm_ok": sum(confirms) / len(confirms) if confirms else None,
            },
        },
        "errors": errors,
        "calls": metrics.usage(rows),
        "problems": results,
    }


TARGETS: dict[str, dict] = {  # --agent value -> how to run it; "g1" is handled by evaluate()
    "00": {"evaluate": agents.evaluate_00, "oracle": agents.oracle_00, "ids": ("00",), "judge": True},
    "09": {"evaluate": agents.evaluate_09, "oracle": agents.oracle_09, "ids": ("09",), "judge": True},
    "g5": {
        "evaluate": agents.evaluate_g5,
        "oracle": agents.oracle_09,
        "ids": ("09",),
        "judge": True,
        "tasks": agents.G5_PERIODS,
    },
    "01": {
        "evaluate": components.evaluate_01,
        "oracle": components.oracle_01,
        "ids": ("01",),
        "judge": False,
        "tasks": components.TASKS_01,
    },
    "04": {
        "evaluate": components.evaluate_04,
        "oracle": components.oracle_04,
        "ids": ("04",),
        "judge": False,
        "tasks": components.TASKS_04,
    },
    "02r": {
        "evaluate": components.evaluate_02r,
        "oracle": components.oracle_02r,
        "ids": ("02",),
        "judge": False,
        "tasks": components.TASKS_02R,
    },
    "08": {  # code only: no model call, so no cost warning and no --yes
        "evaluate": components.evaluate_08,
        "oracle": None,
        "ids": (),
        "judge": False,
        "model": False,
        "runs": 1,
        "tasks": components.TASKS_08,
    },
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


def _judge_refusal(target: str, a) -> str | None:
    """Why --judge cannot run with these arguments, in Vietnamese; None when it can."""
    if not TARGETS.get(target, {}).get("judge", False):
        return f"--judge không dùng cho agent {target}."
    if a.backend == "dev":
        return "--judge không chạy với --backend dev: devfake không có judge."
    if a.backend == "real" and not a.judge_model:
        return "--backend real cần --judge-model <provider:tên>: judge không được dùng ngầm model đang chấm."
    try:
        _judge_provider(a.judge_model)
    except ValueError as e:
        return f"--judge-model sai: {e}"
    return None


def _judge_provider(judge_model: str | None) -> str | None:
    return llm.split_model(judge_model)[0] if judge_model else None


def _judged_models(target: str) -> dict[str, str]:
    """The models setting of the agents the target runs."""
    models = config.load(config.paths().settings)["models"]
    return {i: models[i] for i in TARGETS[target]["ids"] if i in models}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agent", choices=["g1", *TARGETS])
    ap.add_argument("--set", help="bộ bài của g1, xem tests/eval/sets.json")
    ap.add_argument("--backend", choices=["fake", "dev", "real"], default="dev")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--files", nargs="+")
    ap.add_argument("--only", nargs="+", help="chỉ chạy các id này (không dùng cho g1)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "results")
    ap.add_argument("--traces", type=Path, help="mẹ của thư mục vết (mặc định <out>/../traces)")
    ap.add_argument("--judge", action="store_true", help="chấm thêm độ trung thực bằng LLM (chỉ 00, 09, g5)")
    ap.add_argument("--judge-model", help="model của judge, dạng provider:tên; bắt buộc với --backend real")
    ap.add_argument(
        "--suite", help="chạy một dãy bước trong tests/eval/suites.json (không kèm --agent --set --files --only)"
    )
    ap.add_argument("--yes", action="store_true", help="xác nhận chạy API thật (tốn tiền)")
    return ap


def _step(a) -> tuple[int, dict | None]:
    """One target: its exit code and its result (None when it refused or did not run)."""
    target = a.agent or "g1"
    fix = FIX
    if target == "g1":
        if a.only:
            print("--only không dùng cho g1, dùng --files")
            return 2, None
        sets = load_sets()
        a.set = a.set or "g1-dev"
        if a.set not in sets:
            print(f"Không có bộ {a.set}. Có: {', '.join(sets)}")
            return 2, None
        fix = ROOT / sets[a.set]["dir"]
    elif a.set not in (None, f"{target}-dev"):
        print(f"Không có bộ {a.set} cho agent {target}.")
        return 2, None
    if a.judge:
        if msg := _judge_refusal(target, a):
            print(msg)
            return 2, None
    model = TARGETS.get(target, {}).get("model", True)
    if a.backend == "real" and model:
        if target == "g1":
            n = sum(len(lab["problems"]) for lab in load_labels(a.files, fix).values())
            what = f"{n} bài toán × ≥ 3 lượt gọi (02 · 03 · 04 mỗi lỗi; 01 khi thiếu mã bài)"
        elif target == "00":
            what = f"{len(agents.QUESTIONS)} câu × ≥ 2 lượt gọi"
        elif target == "09":
            what = f"{len(agents.PERIODS)} kỳ × 1–2 lượt gọi"
        else:
            what = f"{len(TARGETS[target]['tasks'])} task × ≥ 1 lượt gọi"
        print(f"CẢNH BÁO: gọi API thật (Anthropic / OpenAI theo settings), tốn tiền: {a.runs} lần × {what}.")
        if not a.yes:
            print("Thêm --yes để chạy.")
            return 2, None
        config.load_env(config.ENV_FILE)  # no cli callback here; GPT settings need OPENAI_API_KEY
        if a.judge and _judge_provider(a.judge_model) in llm.providers(_judged_models(target)):
            print("CẢNH BÁO: judge cùng nhà cung cấp với model được chấm")  # decision 2B stays possible
    with tempfile.TemporaryDirectory(prefix="tutor-eval-") as tmp:
        info = meta(target, a.set, a.backend) | {"subset": sorted(a.files or a.only or []) or None}
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        folder = _free((a.traces or a.out.parent / "traces") / f"{stamp}_{a.set or target}")
        if target == "g1":
            res = evaluate(_backend(a.backend), work=Path(tmp), files=a.files, runs=a.runs, fix=fix, traces=folder)
        else:
            t = TARGETS[target]
            try:
                runs = a.runs if model else t["runs"]
                fake = judges.with_oracle(t["oracle"]) if a.judge and a.backend == "fake" else t["oracle"]
                kw = {"judge": a.judge, "judge_model": a.judge_model} if t.get("judge") else {}
                res = t["evaluate"](_backend(a.backend, fake), work=Path(tmp), runs=runs, only=a.only,
                                    traces=folder, **kw)  # fmt: skip
            except agents.UnknownTask as e:
                print(e)
                return 2, None
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
    extra = res["metrics"]["extra"]
    if extra.get("search_recall_at_5") is not None:
        print(f"search recall@5={extra['search_recall_at_5']:.3f}")
    if extra.get("draft_labels"):
        print(f"CẢNH BÁO: {extra['draft_labels']} nhãn nháp, chủ dự án chưa duyệt")
    if a.judge:
        print(f"faithfulness={_fmt(extra.get('faithfulness'))}  unknown={_fmt(extra.get('judge_unknown'))}")
    ids = ("02", "03", "04") if target == "g1" else TARGETS[target]["ids"]
    key = "_".join(v for a_ in ids for v in res["prompt_versions"].get(a_, [])) if model else target
    a.out.mkdir(parents=True, exist_ok=True)
    out = _free(a.out / f"{res['created'].replace(':', '').replace('-', '')}_{key}.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")
    return (1 if res["errors"] else 0), res


def _free(path: Path) -> Path:
    """`path`, or `<stem>-2`, `-3`, ... when taken: two suite steps can end in the same second."""
    n = 1
    while (cand := path if n == 1 else path.with_name(f"{path.stem}-{n}{path.suffix}")).exists():
        n += 1
    return cand


def over_budget(*, logged: int, expected: int, runs: int) -> bool:
    """More than 30 % above the expected calls; expected_calls in suites.json is for k = 3."""
    return logged > 1.3 * expected * runs / 3


def _suite(a) -> int:
    """Run the steps of a suite in turn with the common flags; stop (3) when a real step overruns."""
    if any((a.agent, a.set, a.files, a.only, a.judge)):
        print("--suite không dùng cùng --agent, --set, --files, --only, --judge.")
        return 2
    suites = json.loads(SUITES.read_text(encoding="utf-8"))
    if a.suite not in suites:
        print(f"Không có suite {a.suite}. Có: {', '.join(suites)}")
        return 2
    steps = suites[a.suite]
    common = ["--backend", a.backend, "--runs", str(a.runs), "--out", str(a.out)]
    common += [x for flag, v in (("--traces", a.traces), ("--judge-model", a.judge_model)) if v for x in (flag, str(v))]
    common += ["--yes"] if a.yes else []
    parsed = [parser().parse_args([*s["argv"], *common]) for s in steps]
    if a.backend == "real":
        total = round(sum(s["expected_calls"] for s in steps) * a.runs / 3)
        print(
            f"CẢNH BÁO: gọi API thật, tốn tiền: suite {a.suite} dự kiến {total} lần gọi ({a.runs} lần chạy mỗi bước)."
        )
        if not a.yes:
            print("Thêm --yes để chạy.")
            return 2
    for p in parsed:
        if p.judge and (msg := _judge_refusal(p.agent or "g1", p)):  # before any step spends money
            print(msg)
            return 2
    worst = 0
    for s, p in zip(steps, parsed, strict=True):
        code, res = _step(p)
        worst = max(worst, code)
        if (
            a.backend == "real"
            and res
            and over_budget(logged=res["calls"]["logged"], expected=s["expected_calls"], runs=res["runs"])
        ):
            scaled = round(s["expected_calls"] * res["runs"] / 3)
            print(f"DỪNG: {' '.join(s['argv'])} gọi {res['calls']['logged']} lần, dự kiến {scaled}")
            return 3
    return worst


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.runs < 1:
        print("--runs phải từ 1 trở lên.")
        return 2
    return _suite(a) if a.suite else _step(a)[0]


if __name__ == "__main__":
    sys.exit(main())
