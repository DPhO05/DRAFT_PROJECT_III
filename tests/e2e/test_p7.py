"""P7a-T09: period reports end to end over HTTP, FakeLLM only (C-34, C-39, C-40, C-41, C-44)."""

import json
import re
from contextlib import closing
from datetime import date

import pytest

from tests.agents.test_orchestrator import text, tool
from tests.api.test_assistant import lines, send
from tests.api.test_sessions import W
from tests.assistant_fix import world
from tests.e2e.test_p6 import NAMES, card_at, cards, counts, fold, no_names, total
from tests.fakes import FakeLLM
from tests.graphs.test_report import writer
from tutor import llm
from tutor.api import assistant, reports
from tutor.db import repo
from tutor.graphs import report

TODAY = date(2026, 10, 21)  # the dummy world's day; An has sessions on 07/10 and 14/10, Bình on 14/10
PERIODS = (("day", "2026-10-14"), ("week", "2026-10-12"), ("month", "2026-10-01"))
WEEK = {"period_kind": "week", "period_start": "2026-10-12"}
# 97 is never a day or month, so neither the "Hôm nay" line nor a session date can make it a known number.
INVENTED = "Em làm 97 bài."
SKILL = f"Ôn cho {NAMES[0]}"  # a skill named after a student: the name rides inside the facts 09 reads
FACT_ID = re.compile(r"\bF\d\d\b")


class Pinned(date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    """Both routes that start G5 read the day from `date.today()`; neither may depend on the real one."""
    monkeypatch.setattr(reports, "date", Pinned)
    monkeypatch.setattr(assistant, "date", Pinned)


@pytest.fixture
def w(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        w = world(conn)
        repo.update_kc(conn, w["kc_swap"], name=SKILL)
        return w


def backend(*turns) -> FakeLLM:
    """09 writes from the fact lines; 00 follows `turns`."""
    llm.set_backend(fake := FakeLLM({"09": writer, "00": list(turns)}))
    return fake


def thread_id(kind: str, start: str) -> str:
    return f"g5-hs01{kind[0]}-{start.replace('-', '')}"


def post(client, sid, kind, start):
    body = {"student_id": sid, "period_kind": kind, "period_start": start}
    return client.post("/api/reports", json=body, headers=W)


def approve(client, tid):
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    done = card_at(client, tid, "saved", "failed")
    assert done["stage"] == "saved"
    return done


def md_file(paths, kind, start):
    return paths.out / f"baocao-HS-01-{kind}-{start}.md"


TAIL = re.compile(r" (\[F\d\d\])+$")  # R17: "câu [F01][F03]", one space, adjacent brackets


def only_ids_in_tail(md: str) -> None:
    """R17: a fact id sits after the sentence, never inside its words (C-44, H9)."""
    for line in md.splitlines():
        assert not FACT_ID.search(TAIL.sub("", line)), line


def no_ids(card: dict) -> None:
    """C-44: no sentence `text` or `why` on the teacher card shows a fact id; its `facts` hold bare ids by design."""
    for s in card["sentences"]:
        for words in (s["text"], s["why"] or ""):
            assert "[F" not in words and not FACT_ID.search(words), words


def test_three_periods(paths, client, w):
    backend()
    rows, base = counts(paths), total(client)
    for kind, start in PERIODS:
        r = post(client, w["an"], kind, start)
        tid = r.json()["thread_id"]
        assert (r.status_code, r.json()) == (202, {"thread_id": thread_id(kind, start), "status": "running"})
        fresh = card_at(client, tid, "draft")
        shown = fresh["sentences"]
        assert len(shown) >= 2 and all(s["flag"] is None for s in shown)
        no_ids(fresh)
        assert counts(paths) == rows and total(client) == base  # C-39: a draft writes nothing
        assert not md_file(paths, kind, start).exists()  # the .md is written once, after the commit

        edited = [{"text": s["text"], "facts": s["facts"]} for s in shown]
        edited[0] = {"text": INVENTED, "facts": []}
        edited[1]["text"] += " [F07]"  # H9: a typed id never reaches the card, text_md or the app
        got = client.put(f"/api/threads/{tid}/decisions", json={"sentences": edited}, headers=W).json()
        flagged = {"i": 0, "flag": "number", "why": "Số “97” không có trong dữ liệu đã duyệt."}
        clean = [{"i": i, "flag": None, "why": None} for i in range(1, len(shown))]
        plan = [{"i": i, "flag": None, "why": None} for i in range(len(fresh["plan"]))]  # the draft's, untouched
        assert fresh["sessions"] and plan
        assert got == {"saved": True, "pending": 0, "audit": [flagged, *clean], "audit_plan": plan}
        edited_card = card_at(client, tid, "draft")
        assert edited_card["n_flagged"] == 1  # Review Focus 1: a warning, approval still allowed
        assert [s["text"] for s in edited_card["sentences"]] == [INVENTED, *(s["text"] for s in shown[1:])]
        no_ids(edited_card)
        assert counts(paths) == rows and total(client) == base

        done = approve(client, tid)
        after = counts(paths)
        assert {t: n - rows[t] for t, n in after.items() if n != rows[t]} == {"report": 1}  # one row per resume
        rows, base = after, base + 1
        assert total(client) == base
        assert done["sentences"] == [] and done["n_flagged"] == 0

        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            text_md, audit = conn.execute("SELECT text_md, audit_json FROM report WHERE id = ?",
                                          (done["report_id"],)).fetchone()  # fmt: skip
        assert json.loads(audit)["approved"][0] == {"i": 0, "flag": "number", "why": flagged["why"]}
        assert md_file(paths, kind, start).read_text(encoding="utf-8") == text_md
        review = {s["title"]: s["lines"] for s in report.sections(text_md)}["Nhận xét"]
        assert len(review) == len(shown) and review[0] == INVENTED
        body = text_md.split("## Nhận xét\n")[1].split("## ")[0].splitlines()  # the part's raw lines, tails on
        assert body[0] == INVENTED  # the tutor's sentence cites nothing: no tail
        assert all(TAIL.search(line) for line in body[1:])  # 09's sentences all end in their [Fxx] tail
        assert body[1] == shown[1]["text"] + " " + "".join(f"[{f}]" for f in shown[1]["facts"])
        assert "F07" not in text_md
        only_ids_in_tail(text_md)

    got = client.get(f"/api/reports?student={w['an']}").json()
    assert got["drafts"] == []
    assert sorted((a["period_kind"], a["period_start"]) for a in got["approved"]) == sorted(PERIODS)
    for a in got["approved"]:
        r = client.get(f"/api/reports/{a['id']}")
        assert "[F" not in r.text and not FACT_ID.search(r.text)  # C-44: the app never sees a fact id
        body = r.json()
        assert body["file"] == md_file(paths, a["period_kind"], a["period_start"]).name
        assert INVENTED in body["sentences"] and body["sections"][1]["lines"][0] == INVENTED and "F07" not in r.text


def test_chat_then_tab_once(paths, client, w):
    """Review Focus 3: one period, two doors (chat tool, then the tab), one approval."""
    fake = backend([tool("start_report", code="HS-01", **WEEK)], [text("Mình đã bắt đầu.")])
    kind, start = WEEK["period_kind"], WEEK["period_start"]
    tid = thread_id(kind, start)
    rows, base = counts(paths), total(client)
    evs = lines(send(client, "Làm báo cáo tuần cho @HS-01", [w["an"]]))
    assert cards(evs) == [{"kind": "report", "thread_id": tid}]
    assert not [e for e in evs if e["type"] == "warning"]
    card_at(client, tid, "draft")
    assert counts(paths) == rows and total(client) == base  # C-39: the chat tool writes nothing

    again = post(client, w["an"], kind, start)
    assert (again.status_code, again.json()) == (200, {"thread_id": tid, "status": "awaiting_review",
                                                       "existing": True})  # fmt: skip
    assert [t["thread_id"] for t in client.app.state.runner.list_threads(graph="G5")] == [tid]
    assert counts(paths) == rows and total(client) == base

    done = approve(client, tid)
    assert {t: n - rows[t] for t, n in counts(paths).items() if n != rows[t]} == {"report": 1}
    assert total(client) == base + 1
    md = md_file(paths, kind, start)
    written, stamp = md.read_bytes(), md.stat().st_mtime_ns

    r = post(client, w["an"], kind, start)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "already_committed"
    assert err["detail"]["report_id"] == done["report_id"] and err["detail"]["approved_at"]
    r = client.post(f"/api/threads/{tid}/resume", headers=W)  # the same draft, a second click
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "already_committed"
    assert total(client) == base + 1  # no second row
    assert (md.read_bytes(), md.stat().st_mtime_ns) == (written, stamp)  # nor a second file write
    assert len(client.get(f"/api/reports?student={w['an']}").json()["approved"]) == 1
    no_names(paths, fake)


def test_no_names_in_09_logs(paths, client, w):
    """Review Focus 5 (C-40): a student's full name inside the facts is masked before 09 sees it."""
    fake = backend()
    tid = post(client, w["an"], *WEEK.values()).json()["thread_id"]
    card_at(client, tid, "draft")
    approve(client, tid)

    rows = [x for x in llm.iter_log(paths.logs / "llm.jsonl") if x["agent"] == "09"]
    assert rows and {x["student_code"] for x in rows} == {"HS-01"} and all(x["name_masked"] for x in rows)
    logged = fold(json.dumps(rows, ensure_ascii=False))
    assert "on cho hs-01" in logged  # the log holds the masked line, so the scan below is not scanning nothing
    seen = [c["user"] for c in fake.calls if c["agent"] == "09"]
    assert seen and all(fold(SKILL) not in fold(u) and "on cho hs-01" in fold(u) for u in seen)  # masked, not dropped
    for name in NAMES:
        assert fold(name) not in logged
        assert not any(fold(name) in fold(json.dumps(c, ensure_ascii=False)) for c in fake.calls)
