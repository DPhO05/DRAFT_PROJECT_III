"""G4 teacher card, /api/worksheets and the .tex download (P6-T11, api-v3 §3.5-§3.7)."""

import json
import re
from contextlib import closing

import pytest

from tests.api.test_bank import import_mix
from tests.api.test_sessions import W, poll
from tests.assistant_fix import world
from tutor import config
from tutor.db import repo
from tutor.graphs import bank, worksheet
from tutor.services import latex, select

DAY = "2026-10-24"
LATER = "2026-10-31"
FORBIDDEN = re.compile(r"θ|δ|kc_id|g4-hs|computational\.|conceptual\.|notational\.")


@pytest.fixture
def env(paths, client):
    """(client, An's id, rank_problems for An, refs outside that ranking); the dummy world is in tutor.db."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        w = world(conn)
        ranked = select.rank_problems(conn, w["an"], 6, reco=config.defaults()["reco"], today=w["today"])
        used = {i["ref"] for i in ranked["items"]}
        spare = [r for (r,) in conn.execute("SELECT ref FROM problem ORDER BY ref") if r not in used]
    return client, w["an"], ranked, spare


def draft(client, sid, ranked, day=DAY):
    items = [{k: i[k] for k in ("ref", "bucket", "reason")} for i in ranked["items"]]
    out = worksheet.propose(client.app.state.paths, client.app.state.runner, student_id=sid, for_date=day,
                            items=items, warnings=ranked["warnings"])  # fmt: skip
    return out["thread_id"]


def card(client, tid):
    return client.get(f"/api/threads/{tid}?view=teacher").json()["card"]


def save(client, tid, refs, day=DAY, replace=False):
    body = {"for_date": day, "refs": refs, "replace": replace}
    return client.put(f"/api/threads/{tid}/decisions", json=body, headers=W).json()["pending"]


def create(client, tid, refs, day=DAY, replace=False):
    assert save(client, tid, refs, day, replace) == 0
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    return poll(client, tid)


def refs_of(ranked):
    return [i["ref"] for i in ranked["items"]]


def test_card_draft_counts(env):
    client, sid, ranked, _ = env
    got = card(client, draft(client, sid, ranked))
    assert set(got) == {"kind", "stage", "student_id", "for_date", "items", "counts", "warnings", "invalid",
                        "existing_for_date", "saved"}  # fmt: skip
    assert (got["kind"], got["stage"], got["student_id"], got["for_date"]) == ("worksheet", "draft", sid, DAY)
    assert got["counts"] == {"review": 2, "zpd": 3, "challenge": 1, "added": 0}
    assert [i["ref"] for i in got["items"]] == refs_of(ranked)
    assert set(got["items"][0]) == {"ref", "problem_id", "level", "kcs", "bucket", "reason", "statement_latex"}
    assert got["items"][0]["reason"] == ranked["items"][0]["reason"] and got["items"][0]["kcs"]
    assert (got["warnings"], got["invalid"], got["existing_for_date"], got["saved"]) == (
        ranked["warnings"],
        [],
        None,
        None,
    )
    assert not FORBIDDEN.search(json.dumps(got, ensure_ascii=False))


def test_card_follows_saved_decisions(env):
    client, sid, ranked, spare = env
    tid = draft(client, sid, ranked)
    refs = refs_of(ranked)
    assert save(client, tid, [spare[0], refs[1], refs[0], "9ZZ-XXX-999"], LATER) == 1
    got = card(client, tid)
    assert got["for_date"] == LATER
    assert [i["ref"] for i in got["items"]] == [spare[0], refs[1], refs[0]]
    assert [i["bucket"] for i in got["items"]] == [None, ranked["items"][1]["bucket"], ranked["items"][0]["bucket"]]
    assert got["items"][0]["reason"] == worksheet.SELF_ADDED
    want = {b: sum(i["bucket"] == b for i in ranked["items"][:2]) for b in select.BUCKETS}
    assert got["counts"] == want | {"added": 1}
    assert got["invalid"] == [{"ref": "9ZZ-XXX-999", "why": "không có trong ngân hàng"}]


def test_card_existing_for_date(env):
    client, sid, ranked, _ = env
    refs = refs_of(ranked)
    assert create(client, draft(client, sid, ranked), refs)["status"] == "committed"
    second = draft(client, sid, ranked)
    assert card(client, second)["existing_for_date"] == {"n_problems": 6}
    save(client, second, refs, LATER)
    assert card(client, second)["existing_for_date"] is None


def test_list_and_tex(env, paths):
    client, sid, ranked, _ = env
    refs = refs_of(ranked)
    assert create(client, draft(client, sid, ranked), refs)["status"] == "committed"
    [ws] = client.get(f"/api/worksheets?student={sid}").json()
    assert (ws["student_id"], ws["for_date"], ws["n_problems"], ws["tex"]) == (
        sid,
        DAY,
        6,
        f"/api/worksheets/{sid}/{DAY}.tex",
    )
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ws["created_at"])
    assert [(i["position"], i["ref"]) for i in ws["items"]] == list(enumerate(refs, 1))
    assert set(ws["items"][0]) == {"position", "ref", "problem_id", "level", "kcs", "reason", "statement_latex"}
    assert ws["items"][0]["reason"] == ranked["items"][0]["reason"] and ws["items"][0]["kcs"]
    r = client.get(ws["tex"])
    assert (r.status_code, r.headers["content-type"]) == (200, "text/x-tex; charset=utf-8")
    assert (
        r.headers["content-disposition"].startswith("attachment")
        and f"phieu-HS-01-{DAY}.tex" in r.headers["content-disposition"]
    )
    assert [p.ref for p in latex.split_problems(r.text)] == refs
    assert r.content == (paths.out / f"phieu-HS-01-{DAY}.tex").read_bytes()
    base = f"/api/worksheets/{sid}"
    for url, code in [
        (f"{base}/2026-13-40.tex", 422),
        (f"{base}/20261024.tex", 422),
        (f"{base}/...tex", 422),  # for_date ".."
        (f"{base}/../x.tex", 404),  # httpx drops the dot segments: /api/worksheets/x.tex matches no route
        (f"{base}/2026-10-25.tex", 404),
        (f"/api/worksheets/99/{DAY}.tex", 404),
        ("/api/worksheets", 422),
        ("/api/worksheets?student=99", 404),
    ]:
        assert client.get(url).status_code == code, url


def test_list_newest_first_without_rejected(env, paths):
    client, sid, ranked, _ = env
    its = ranked["items"]

    def commit(day, items, replace=False):
        rows = [{k: i[k] for k in ("problem_id", "kc_id", "bucket", "reason")} for i in items]
        with closing(repo.connect(paths.tutor_db)) as conn:
            repo.commit_worksheet(conn, student_id=sid, for_date=day, items=rows, replace=replace)

    commit(DAY, its[:3])
    commit(LATER, its[3:5])
    commit(DAY, its[4:6], replace=True)
    got = client.get(f"/api/worksheets?student={sid}").json()
    assert [(w["for_date"], w["n_problems"], [i["ref"] for i in w["items"]]) for w in got] == [
        (LATER, 2, [i["ref"] for i in its[3:5]]),
        (DAY, 2, [i["ref"] for i in its[4:6]]),
    ]
    binh = client.get("/api/students").json()[1]["id"]
    assert client.get(f"/api/worksheets?student={binh}").json() == []


def test_saved_card(env):
    client, sid, ranked, _ = env
    refs = refs_of(ranked)
    tid = draft(client, sid, ranked)
    assert create(client, tid, refs)["status"] == "committed"
    got = card(client, tid)
    assert got["stage"] == "saved"
    assert got["saved"] == {"for_date": DAY, "n_problems": 6, "tex": f"/api/worksheets/{sid}/{DAY}.tex"}
    assert (got["existing_for_date"], [i["ref"] for i in got["items"]]) == (None, refs)
    assert client.get(got["saved"]["tex"]).status_code == 200


def test_failed_card_then_retry(env, paths):
    client, sid, ranked, _ = env
    tid = draft(client, sid, ranked)
    paths.out.rmdir()
    paths.out.write_text("not a folder")  # the file write fails after the rows landed
    assert create(client, tid, refs_of(ranked))["status"] == "failed"
    got = card(client, tid)
    assert (got["stage"], got["saved"], got["existing_for_date"]) == ("failed", None, None)
    assert len(got["items"]) == 6
    paths.out.unlink()
    paths.out.mkdir()
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    assert poll(client, tid)["status"] == "committed"
    assert card(client, tid)["stage"] == "saved" and (paths.out / f"phieu-HS-01-{DAY}.tex").is_file()


def test_card_stage_while_running(env, paths):
    client, sid, ranked, _ = env
    r = client.app.state.runner
    tid = draft(client, sid, ranked)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        assert worksheet.card(r.get(tid) | {"status": "running"}, r.state(tid), conn)["stage"] == "saving"


def test_worksheet_reminder(env):
    client, sid, ranked, _ = env
    r = client.app.state.runner
    tid = draft(client, sid, ranked)
    state = r.state(tid)
    want = {"kind": "worksheet", "thread_id": tid, "student_id": sid, "date": DAY, "words": "6 bài"}
    assert worksheet.reminder(r.get(tid), state) == want
    save(client, tid, refs_of(ranked)[:2], LATER)
    assert worksheet.reminder(r.get(tid), state) == want | {"date": LATER, "words": "2 bài"}


def test_bank_reminder(paths, client):
    tid = import_mix(paths, client)
    poll(client, tid, until=("awaiting_review", "failed"))
    r = client.app.state.runner
    want = {"kind": "bank_import", "thread_id": tid, "file": "mix.tex", "words": "2 bài cần chọn kỹ năng"}
    assert bank.reminder(paths, r.get(tid), r.state(tid)) == want
    kc = {k["code"]: k["id"] for k in client.get("/api/catalog/kc").json()}
    r.save_decisions(tid, {"items": {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]},
                                     "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]]}}})  # fmt: skip
    assert bank.reminder(paths, r.get(tid), r.state(tid))["words"] == "chờ lưu kết quả"
    assert bank.reminder(paths, r.get(tid) | {"status": "failed"}, r.state(tid))["words"] == "nạp chưa xong"
