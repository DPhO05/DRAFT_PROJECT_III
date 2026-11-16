"""POST /api/students/{id}/replay: rebuild one student's skill profile (the old `tutor replay`)."""

from contextlib import closing

import pytest

from tests.db.test_profile_repo import D1, D2, WRONG, bank, commit, mk, skill_rows, start  # noqa: F401
from tutor.db import repo
from tutor.graphs.runner import Runner

W = {"X-Tutor": "1"}


@pytest.fixture
def committed(conn, bank):  # noqa: F811
    """HS-01 with two committed sessions on KC 'Chuyển vế': right, then wrong."""
    sid = repo.add_student(conn, name="An")
    for day, work in ((D1, [(bank["p1"], [])]), (D2, [(bank["p1"], [mk(WRONG, bank["k1"])])])):
        commit(conn, start(conn, sid, day), work)
    return sid


def backups(paths):
    return list(paths.backup.glob("tutor-*.db"))


def test_replay_matches_the_function_the_old_command_called(client, paths, conn, committed):
    conn.execute("UPDATE problem SET delta = 0.6")
    ref = repo.backup(paths.tutor_db, paths.root / "ref")  # a WAL-safe copy: a plain file copy would miss rows
    with closing(repo.connect(ref)) as rc:
        want = repo.replay_student(rc, committed)
        want_rows = skill_rows(rc)
    n = len(backups(paths))
    r = client.post(f"/api/students/{committed}/replay", headers=W)
    assert r.status_code == 200, r.text
    assert r.json()["events"] == want["events"] == 2
    assert skill_rows(conn) == want_rows
    assert len(backups(paths)) == n + 1


def test_replay_lists_level_changes_by_kc_name(client, conn, committed):
    conn.execute("UPDATE skill_state SET theta = 5")  # the old command printed "Chuyển vế: vững → đang hình thành"
    r = client.post(f"/api/students/{committed}/replay", headers=W)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "events": 2,
        "level_changes": [{"kc": "Chuyển vế", "before": "vững", "after": "đang hình thành"}],
    }


@pytest.mark.parametrize("status", ["running", "awaiting_review", "failed"])
def test_replay_refused_while_g1_waiting(client, paths, conn, committed, status):
    conn.execute("UPDATE skill_state SET theta = 5")
    before, n = skill_rows(conn), len(backups(paths))
    rn = Runner(paths, {})
    rn._set("g1-hs01-20261110", create=True, graph="G1", status=status, student_id=committed)
    rn.close()
    r = client.post(f"/api/students/{committed}/replay", headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_ready"
    assert skill_rows(conn) == before and len(backups(paths)) == n


def test_replay_unknown_archived_and_missing_header(client, paths, conn, committed):
    assert client.post("/api/students/99/replay", headers=W).status_code == 404
    assert client.post(f"/api/students/{committed}/replay").status_code == 403
    repo.archive_student(conn, committed)
    assert client.post(f"/api/students/{committed}/replay", headers=W).status_code == 422
    assert not backups(paths)
