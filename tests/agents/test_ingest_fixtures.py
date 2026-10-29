"""P1-T07 + P1-T08 on tests/fixtures/submissions: P1 "xong khi", student-work part."""

import json
from pathlib import Path

from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents import CallContext, ingest
from tutor.db import repo, seed_dummy
from tutor.services import latex

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "submissions"
LABELS = json.loads((FIX / "labels.json").read_text(encoding="utf-8"))


def test_labels_use_known_codes_and_the_problems_kcs(conn):
    seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
    codes = {r[0] for r in conn.execute("SELECT code FROM error_code")}
    tags = {}
    for ref, kc in conn.execute(
        "SELECT p.ref, k.code FROM problem_kc pk JOIN problem p ON p.id = pk.problem_id JOIN kc k ON k.id = pk.kc_id"
    ):
        tags.setdefault(ref, set()).add(kc)
    for name, lab in LABELS.items():
        for p in lab["problems"]:
            for m in p["mistakes"]:
                assert m["code"] in codes, (name, m)
                assert m["kc"] is None or m["kc"] in tags[p["ref"]], (name, m)


def test_ingest_matches_every_fixture(conn, tmp_path):
    seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
    bank = repo.bank_problems(conn)
    llm.configure(tmp_path / "llm.jsonl", {})
    for name, lab in LABELS.items():
        truth = {p["seq"]: p for p in lab["problems"]}
        missing = [p["ref"] for p in lab["problems"] if not p["has_id"]]
        # FakeLLM: right answer ranked 2nd with a low score -> must be flagged, and kept in the top 3
        fake = FakeLLM({"01": ingest.MatchResult(candidates=[
            ingest.Candidate(ref="8DS-PT1-001", score=0.7), *(ingest.Candidate(ref=r, score=0.6) for r in missing)
        ])})  # fmt: skip
        llm.set_backend(fake)
        tex = (FIX / name).read_text(encoding="utf-8")
        assert len(latex.split_problems(tex)) == len(truth), name
        res = ingest.run(tex, bank, grade=lab["grade"], ctx=CallContext(graph="G1"))
        for a in res.attempts:
            t = truth[a.seq]
            assert len(a.steps) == t["n_steps"], (name, a.seq)
            if t["has_id"]:
                assert a.ref == t["ref"], (name, a.seq)
            else:
                assert a.ref is None and t["ref"] in [c.ref for c in a.candidates]
                assert ("low_match", a.seq) in [(f.type, f.seq) for f in res.flags]
        assert fake.count["01"] == len(missing), name
    llm.set_backend(None)
