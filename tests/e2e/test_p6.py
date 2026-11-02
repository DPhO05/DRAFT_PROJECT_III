"""P6-T13: the assistant end to end over HTTP, FakeLLM scripts only (C-34, C-39, C-40, C-41)."""

import json
import time
from contextlib import closing
from datetime import date, timedelta

import pytest

from tests.agents.test_orchestrator import text, tool
from tests.api.test_assistant import lines, send
from tests.api.test_sessions import W, poll
from tests.assistant_fix import SWAP, world
from tests.fakes import FakeLLM, lane_handlers
from tests.graphs.g1 import prob
from tutor import llm
from tutor.agents.orchestrator import SAVED_NOTHING
from tutor.db import repo
from tutor.services import latex

NAMES = ("Nguyễn Văn An", "Trần Thị Bình", "Lê Văn Cường")
FILE = "hs01-2026-10-21.tex"
SATURDAY = (date.today() + timedelta(days=(5 - date.today().weekday()) % 7 or 7)).isoformat()


@pytest.fixture
def w(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        return world(conn)


def backend(*turns, **lanes) -> FakeLLM:
    llm.set_backend(fake := FakeLLM(lane_handlers() | {"00": list(turns)} | lanes))
    return fake


def total(client) -> int:
    return client.get("/api/backup").json()["total"]


def counts(paths) -> dict:
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        return repo.row_counts(conn)


def card_at(client, tid, *stages) -> dict:
    for _ in range(100):
        card = client.get(f"/api/threads/{tid}?view=teacher").json()["card"]
        if card["stage"] in stages:
            return card
        time.sleep(0.05)
    raise AssertionError(card)


def cards(evs) -> list[dict]:
    return [e["card"] for e in evs if e["type"] == "card"]


def fold(s: str) -> str:
    return "".join(llm._fold(c) for c in s)


def no_names(paths, fake, seen: str = "hs-01") -> None:
    """C-40: not one student's full name, in any case or spelling, in llm.jsonl, the chat logs or a payload."""
    assert (paths.logs / "chat").is_dir()
    files = [paths.logs / "llm.jsonl", *(paths.logs / "chat").glob("*.jsonl")]
    logged = fold("".join(f.read_text(encoding="utf-8") for f in files))
    assert seen in logged  # the logs themselves hold it, else the scan below passes on empty logs
    got = logged + fold(json.dumps(fake.calls, ensure_ascii=False))
    for name in NAMES:
        assert fold(name) not in got


def test_search_by_description(paths, client, w):
    fake = backend(
        [tool("search_problems", text="phuong trinh chua an o mau", level_min="vừa", level_max="vừa", limit=3)],
        [text("Có 3 bài mức vừa.")],
    )
    before = total(client)
    evs = lines(send(client, "Tìm 3 bài phương trình chứa ẩn ở mẫu mức vừa"))
    [card] = cards(evs)
    assert card["kind"] == "problem" and len(card["problems"]) == 3
    assert {p["level"] for p in card["problems"]} == {"vừa"}
    assert [e["type"] for e in evs if e["type"] in ("warning", "source", "done")] == ["source", "done"]
    assert total(client) == before
    no_names(paths, fake, seen="search_problems")


def test_worksheet_flow(paths, client, w):
    def propose(messages):
        ranked = json.loads(messages[-1]["content"][0]["content"])["items"]
        return [tool("propose_worksheet", code="HS-01", for_date=SATURDAY, refs=[i["ref"] for i in ranked])]

    fake = backend(
        [tool("rank_problems", code="HS-01", n=6)],
        propose,
        [text("Mình soạn xong phiếu 6 bài, thầy/cô xem thẻ rồi bấm Tạo phiếu.")],
    )
    runner = client.app.state.runner
    before = total(client)
    evs = lines(send(client, "Gợi ý 6 bài cho @HS-01 buổi thứ Bảy", [w["an"]]))
    cid = evs[0]["conversation_id"]
    [sheet] = cards(evs)
    tid = sheet["thread_id"]
    assert sheet["kind"] == "worksheet" and len(sheet["added"]) == 6 and not sheet["invalid"]
    assert not [e for e in evs if e["type"] == "warning"]
    draft = card_at(client, tid, "draft")
    assert draft["counts"] == {"review": 2, "zpd": 3, "challenge": 1, "added": 0}
    refs = [i["ref"] for i in draft["items"]]
    assert "9DS-PT2-001" not in refs  # S23: else the typed ref would be dropped as a repeat
    assert total(client) == before

    kept = [refs[3], refs[0], refs[5], refs[1], refs[2]]  # new order, refs[4] dropped
    body = {"for_date": SATURDAY, "refs": kept, "replace": False}
    assert client.put(f"/api/threads/{tid}/decisions", json=body, headers=W).json() == {"saved": True, "pending": 0}
    typed = lines(send(client, "9DS-PT2-001", [], cid=cid, context={"worksheet_thread_id": tid}))
    assert fake.count["00"] == 3  # the typed code cost no API call
    [added] = cards(typed)
    assert (added["thread_id"], added["added"], added["invalid"]) == (tid, ["9DS-PT2-001"], [])
    final = [*kept, "9DS-PT2-001"]
    draft = card_at(client, tid, "draft")
    assert [i["ref"] for i in draft["items"]] == final and draft["counts"]["added"] == 1
    assert total(client) == before

    rows, saved = counts(paths), {t["thread_id"]: t["decisions_json"] for t in runner.list_threads()}
    evs = lines(send(client, "ok, lưu đi", cid=cid, context={"worksheet_thread_id": tid}))  # Review Focus 2, S21
    assert fake.count["00"] == 3
    assert "".join(e["delta"] for e in evs if e["type"] == "text") == SAVED_NOTHING
    assert not cards(evs) and evs[-1] == {"type": "done", "stopped": None}
    assert counts(paths) == rows and total(client) == before
    assert {t["thread_id"]: t["decisions_json"] for t in runner.list_threads()} == saved
    assert card_at(client, tid, "draft")["stage"] == "draft"

    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    done = card_at(client, tid, "saved", "failed")
    assert done["stage"] == "saved" and done["saved"]["n_problems"] == 6
    assert total(client) == before + 6
    [sheet] = client.get(f"/api/worksheets?student={w['an']}").json()
    assert [(i["position"], i["ref"]) for i in sheet["items"]] == list(enumerate(final, 1))
    r = client.get(sheet["tex"])
    assert [p.ref for p in latex.split_problems(r.text)] == final
    no_names(paths, fake)


def test_grading_in_chat(paths, client, w):
    (paths.inbox / FILE).write_text(prob("9DS-PT2-003", "$x^2 = 1$"), encoding="utf-8")
    fake = backend()
    before = counts(paths)
    evs = lines(send(client, "Chấm bài này @HS-01", [w["an"]], attachment={"path": FILE}, held_on="2026-10-21"))
    assert fake.count["00"] == 0
    [grading] = cards(evs)
    tid = grading["thread_id"]
    assert grading["kind"] == "grading"
    review = card_at(client, tid, "review", "failed")
    assert (review["stage"], review["file"], review["held_on"]) == ("review", FILE, "2026-10-21")
    only_session = {t: n - before[t] for t, n in counts(paths).items() if n != before[t]}
    assert only_session == {"session": 1}  # ① only

    pid = review["attempts"][0]["mistakes"][0]["pid"]
    body = {"cards": {pid: {"action": "accept"}}, "review_seconds": 9}
    assert client.put(f"/api/threads/{tid}/decisions", json=body, headers=W).json()["pending"] == 0
    sig = card_at(client, tid, "review")["preview_sig"]
    assert sig
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    preview = card_at(client, tid, "preview", "failed")
    assert (preview["stage"], preview["preview_sig"]) == ("preview", sig)
    assert counts(paths) == {t: n + (t == "session") for t, n in before.items()}  # nothing but ① before the last resume

    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    saved = card_at(client, tid, "saved", "failed")
    assert saved["stage"] == "saved" and saved["receipt"]["backed_up"] is True
    after = counts(paths)
    assert after["attempt"] == before["attempt"] + 1 and after["mistake"] > before["mistake"]
    assert fake.count["00"] == 0
    no_names(paths, fake)


def test_compare_students(paths, client, w):
    ask = [tool("compare_students", metric="open_repeats", kind=SWAP)]
    fake = backend(ask, [text("HS-01 còn 2 lần.")], ask, [text("HS-01 còn 4 lần.")])
    before = total(client)
    evs = lines(send(client, "Ai còn sai dấu khi chuyển vế?"))
    assert "".join(e["delta"] for e in evs if e["type"] == "text") == "HS-01 còn 2 lần."
    assert [e["type"] for e in evs if e["type"] in ("warning", "source")] == ["source"]
    [source] = [e for e in evs if e["type"] == "source"]
    assert source["items"] and "no_student_data" not in source

    evs = lines(send(client, "Ai còn sai dấu khi chuyển vế?", cid=evs[0]["conversation_id"]))
    [warning] = [e for e in evs if e["type"] == "warning"]
    assert (warning["kind"], warning["numbers"]) == ("unverified_number", ["4"])
    assert evs[-1] == {"type": "done", "stopped": None} and total(client) == before
    no_names(paths, fake)


def test_no_names_anywhere(paths, client, w):
    body = "Bài làm của NGUYỄN VĂN AN, tức nguyen van an, cạnh Trần Thị Bình. $x^2 = 1$"
    (paths.inbox / FILE).write_text(prob("9DS-PT2-003", body), encoding="utf-8")
    fake = backend([tool("student_profile", code="HS-01")], [text("Đã xem hồ sơ.")])
    ask = "Nguyễn Văn An với LÊ VĂN CƯỜNG và tran thi binh hay sai gì?"
    evs = lines(send(client, ask))
    assert "HS-01 với HS-03 và HS-02" in fake.calls[0]["messages"][-1]["content"]
    lines(send(client, "", [w["an"]], cid=evs[0]["conversation_id"], attachment={"path": FILE}, held_on="2026-10-21"))
    tid = client.get("/api/threads").json()[0]["thread_id"]
    assert poll(client, tid)["status"] == "awaiting_review"
    assert any(c["agent"] != "00" for c in fake.calls)  # the lanes ran on the text that held the name
    no_names(paths, fake)
