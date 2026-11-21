"""Judge calibration (design 7.2, 7.3): sample sentences to grade by hand, let the judge grade them, score the match.

calibrate.py sample --from RESULT.json [--n 30] [--seed 0] [--out DIR]
calibrate.py judge HUMAN.csv JUDGE.json [--backend fake|real] [--judge-model M] [--yes]
calibrate.py score --human FILE [--human FILE2] JUDGE.json [--kappa 0.61] [--alignment 0.85] [--recall 0.80]
"""

# ruff: noqa: E402
import argparse
import csv
import json
import random
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

from tests.eval import agents, judges, metrics
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.db import repo

TREND = {"tiến bộ": "sa sút", "tăng": "giảm", "giảm": "tăng", "vững": "chưa vững", "tốt hơn": "kém hơn",
         "ít hơn": "nhiều hơn", "nhiều hơn": "ít hơn"}  # fmt: skip
PREFIX = "Em sa sút rõ: "
COLUMNS = ["id", "context", "sentence", "human"]
N = "not_supported"
LABELS = ("supported", N)


def wrong(sentence: str) -> str:
    """The sentence with one trend word flipped; without one, a claim of decline in front."""
    for word, opposite in TREND.items():
        if word in sentence:
            return sentence.replace(word, opposite, 1)
    return PREFIX + sentence


def judged_sentences(result: dict):
    """(id, context, sentence, verdict) of each judged sentence of a result; failed judge calls are skipped."""
    for run, items in enumerate(result.get("answers") or result.get("reports") or [], 1):
        for item in items:
            j = item.get("judge")
            if not j or j.get("error"):
                continue
            context = item["judge_context"] if "judge_context" in item else item["facts_block"]
            sentences = item["judge_sentences"] if "judge_sentences" in item else item["sentences"]
            by_i = {v["i"]: v["verdict"] for v in j["verdicts"]}
            for i, s in enumerate(sentences, 1):
                if i in by_i:
                    yield f"r{run}-{item.get('id') or item['key']}-{i}", context, s, by_i[i]


def sample(a) -> int:
    pool = list(judged_sentences(json.loads(a.src.read_text(encoding="utf-8"))))
    rng = random.Random(a.seed)
    good = [x for x in pool if x[3] == "supported"]
    bad = [x for x in pool if x[3] != "supported"]
    want_good = a.n // 2
    picked_good = rng.sample(good, min(want_good, len(good)))
    picked_bad = rng.sample(bad, min(a.n - want_good, len(bad)))
    rest = [x for x in good if x not in picked_good]
    made = [(c, wrong(s)) for _, c, s, _ in rng.sample(rest, min(a.n - want_good - len(picked_bad), len(rest)))]
    rows = [(c, s, v, None) for _, c, s, v in picked_good + picked_bad] + [(c, s, None, N) for c, s in made]
    rng.shuffle(rows)
    rows = [(f"s{k:02d}", *row) for k, row in enumerate(rows, 1)]  # opaque ids: the rater must not see which are made
    day = datetime.now(UTC).date().isoformat()
    human, judge = a.out / f"{day}-human.csv", a.out / f"{day}-judge.json"
    if human.exists() or judge.exists():
        print(f"Đã có {human.name} hoặc {judge.name} trong {a.out}: không ghi đè nhãn đã chấm. Dùng --out khác.")
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    with human.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows({"id": i, "context": c, "sentence": s, "human": ""} for i, c, s, *_ in rows)
    verdicts = {i: {"verdict": v, "truth": t} for i, _, _, v, t in rows}
    judge.write_text(json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {human}\n→ {judge}")
    return 0


def student_names() -> dict[str, str]:
    """name -> code of the eval world's students, so the Guard masks a name the rater typed into the CSV."""
    with tempfile.TemporaryDirectory() as d:
        paths, _ = agents._world(Path(d))
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            return {s["name"]: s["code"] for s in repo.list_students(conn, include_archived=True)}


def judge(a) -> int:
    if a.backend == "real":
        if not a.yes or not a.judge_model:
            print("--backend real cần --yes và --judge-model <provider:tên>: mỗi câu một lượt gọi API thật, tốn tiền.")
            return 2
    verdicts = json.loads(a.judge_file.read_text(encoding="utf-8"))
    with a.human.open(newline="", encoding="utf-8") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    todo = [i for i, v in verdicts.items() if v["verdict"] is None and i in rows]
    log = a.judge_file.with_suffix(".llm.jsonl")
    if a.backend == "fake":
        llm.configure(log, {})
        llm.set_backend(FakeLLM({"judge": judges.oracle}))
    else:
        print(f"CẢNH BÁO: gọi API thật, tốn tiền: {len(todo)} lượt gọi, model {a.judge_model}.")
        config.load_env(config.ENV_FILE)
        llm.configure(log, {"judge": a.judge_model})
        llm.set_backend(None)
    ctx = llm.CallContext(graph=None, redact=student_names())
    try:
        for i in todo:
            out = judges.faithfulness(rows[i]["context"], [rows[i]["sentence"]], ctx)
            verdicts[i]["verdict"] = out["verdicts"][0]["verdict"]
    finally:
        a.judge_file.write_text(json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"judge đã chấm {len(todo)} câu → {a.judge_file}")
    return 0


def read_human(path: Path) -> dict[str, str] | None:
    with path.open(newline="", encoding="utf-8") as f:
        got = {r["id"]: r["human"].strip() for r in csv.DictReader(f)}
    bad = [i for i, h in got.items() if h not in LABELS]
    if bad:
        print(f"{path}: ô human trống hoặc sai ở {', '.join(bad[:5])}; chỉ nhận supported hoặc not_supported.")
        return None
    return got


def score(a) -> int:
    humans = [read_human(p) for p in a.human]
    if None in humans:
        return 2
    verdicts = json.loads(a.judge_file.read_text(encoding="utf-8"))
    first = humans[0]
    if any(set(h) != set(first) for h in humans):
        print("Các file human không cùng danh sách id.")
        return 2
    if missing := [i for i in first if (verdicts.get(i) or {}).get("verdict") is None]:
        print(f"Judge chưa chấm {len(missing)} câu: chạy judge trước.")
        return 2
    unknown = sum(verdicts[i]["verdict"] == "unknown" for i in first)
    pairs = [(first[i], N if verdicts[i]["verdict"] == "unknown" else verdicts[i]["verdict"]) for i in first]
    alignment = sum(h == j for h, j in pairs) / len(pairs)
    kappa = metrics.cohen_kappa(pairs)
    cell = {(h, j): sum(p == (h, j) for p in pairs) for h in LABELS for j in LABELS}
    not_ok = [j for h, j in pairs if h == N]
    recall = not_ok.count(N) / len(not_ok) if not_ok else None
    f = lambda x: "—" if x is None else f"{x:.3f}"  # noqa: E731
    print(f"n={len(pairs)}\nunknown={unknown}\nalignment={f(alignment)}\nkappa={f(kappa)}")
    print("bảng 2x2 (hàng: người, cột: judge)")
    print(f"{'':15}{'supported':>14}{N:>14}")
    for h in LABELS:
        print(f"{h:15}{cell[h, 'supported']:>14}{cell[h, N]:>14}")
    print(f"recall(not_supported)={f(recall)}")
    for i, (h, j) in zip(first, pairs, strict=True):
        if h != j:
            print(f"lệch {i} người={h} judge={verdicts[i]['verdict']}")
    if len(humans) > 1:
        print(f"kappa người-người={f(metrics.cohen_kappa([(first[i], humans[1][i]) for i in first]))}")
    else:
        print("1 người chấm: không đo được đồng thuận người với người")
    trusted = None not in (kappa, recall) and kappa >= a.kappa and alignment >= a.alignment and recall >= a.recall
    print("TIN" if trusted else "CHƯA TIN")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--from", dest="src", type=Path, required=True, help="file kết quả có judge")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "calibration")
    j = sub.add_parser("judge")
    j.add_argument("human", type=Path)
    j.add_argument("judge_file", type=Path)
    j.add_argument("--backend", choices=["fake", "real"], default="fake")
    j.add_argument("--judge-model", help="provider:tên; bắt buộc với --backend real")
    j.add_argument("--yes", action="store_true", help="xác nhận chạy API thật (tốn tiền)")
    c = sub.add_parser("score")
    c.add_argument("--human", type=Path, action="append", required=True, help="một hoặc hai file")
    c.add_argument("judge_file", type=Path)
    c.add_argument("--kappa", type=float, default=0.61)
    c.add_argument("--alignment", type=float, default=0.85)
    c.add_argument("--recall", type=float, default=0.80)
    a = ap.parse_args(argv)
    return {"sample": sample, "judge": judge, "score": score}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
