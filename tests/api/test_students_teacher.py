"""P7-T08: Học sinh tab routes (api-v3 §4): ?view=teacher, unarchive, profile, progress."""

import json
import re
from contextlib import closing

import pytest

from tests.api.test_review_api import submit
from tests.api.test_sessions import TEX, W, add_student
from tests.assistant_fix import world
from tests.services.test_student_views import LEVELS
from tutor.db import repo
from tutor.services import students

# tests/ui/check_v3.py FORBIDDEN, copied: that module needs playwright
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b|\b\d[A-Z]{2}-[A-Z0-9]+-\d\d\b"
)
OLD_STUDENT = {"id", "name", "grade", "note", "created_at", "archived_at", "code"}
NEW_STUDENT = {"since", "last_session", "level_counts", "pending_grading"}
OLD_SESSION = {"id", "student_id", "held_on", "source_path", "source_kind", "source_sha256", "thread_id", "status",
               "created_at", "committed_at", "student_code"}  # fmt: skip
TEACHER_SESSION = {"id", "student_id", "held_on", "n_attempts", "score", "max_score", "n_mistakes"}
ZEROS = [{"level": lv, "n": 0} for lv in LEVELS]


@pytest.fixture
def env(paths, client):
    """(client, the dummy world's ids): An 2 sessions, Bình 1, Cường archived."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        w = world(conn)
    return client, w


def conn_of(client):
    return closing(repo.connect(client.app.state.paths.tutor_db))


def test_teacher_list(client):
    sid = add_student(client)
    idle = client.post("/api/students", json={"name": "Trần Bình", "grade": 8}, headers=W).json()["id"]
    tid, _, t = submit(client, sid)
    assert t["status"] == "awaiting_review"

    def got():
        return {s["id"]: s for s in client.get("/api/students?view=teacher").json()}

    a = got()[sid]
    assert set(a) == OLD_STUDENT | NEW_STUDENT
    assert (a["pending_grading"], got()[idle]["pending_grading"]) == (1, 0)
    assert a["since"] == a["created_at"][:10] and a["last_session"] is None and a["level_counts"] == ZEROS
    r = client.app.state.runner
    r._set(tid, status="failed")
    assert got()[sid]["pending_grading"] == 1  # failed grading is work for the tutor too
    r._set(tid, status="running")
    assert got()[sid]["pending_grading"] == 0  # still running: nothing to do yet
    r._set(tid, status="awaiting_review")
    earlier, _, _ = submit(client, sid, day="2026-10-13", name="b.tex", tex=TEX + "% b\n")
    r._set(earlier, created_at="2099-01-01T00:00:00Z")  # queued later, but the day comes first
    assert got()[sid]["pending_grading"] == 2
    p = client.get(f"/api/students/{sid}/profile").json()["pending"]
    assert p == [{"thread_id": earlier, "held_on": "2026-10-13"}, {"thread_id": tid, "held_on": "2026-10-20"}]
    assert client.get(f"/api/students/{idle}/profile").json()["pending"] == []


def test_teacher_list_world(env):
    client, w = env
    got = client.get("/api/students?view=teacher").json()
    assert [s["id"] for s in got] == [w["an"], w["binh"]]  # archived stay out unless asked
    an = got[0]
    assert an["last_session"] == {"session_id": 2, "held_on": "2026-10-14", "score": 1.0, "max_score": 2.0}
    assert an["level_counts"] == [{"level": lv, "n": int(lv == "đang hình thành")} for lv in LEVELS]
    assert an["pending_grading"] == 0
    both = client.get("/api/students?view=teacher&archived=true").json()
    cuong = next(s for s in both if s["id"] == w["cuong"])
    assert cuong["archived_at"] and cuong["last_session"] is None and cuong["level_counts"] == ZEROS


def test_unarchive(env):
    client, w = env
    sid = w["cuong"]
    assert sid not in [s["id"] for s in client.get("/api/students").json()]
    assert client.post(f"/api/students/{sid}/unarchive", headers=W).json() == {"archived_at": None}
    assert sid in [s["id"] for s in client.get("/api/students").json()]
    assert client.post(f"/api/students/{sid}/archive", headers=W).json()["archived_at"]
    assert client.post(f"/api/students/{sid}/unarchive", headers=W).json() == {"archived_at": None}
    assert client.post(f"/api/students/{sid}/unarchive", headers=W).json() == {"archived_at": None}  # twice: same
    r = client.post("/api/students/99/unarchive", headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_profile_and_progress_routes(env):
    client, w = env
    an = w["an"]
    p = client.get(f"/api/students/{an}/profile").json()
    assert list(p) == ["student", "skills", "recurring", "pending"]
    assert list(p["student"]) == ["id", "name", "grade", "note", "since", "archived_at"]
    assert (p["student"]["id"], p["student"]["name"], p["student"]["archived_at"]) == (an, "Nguyễn Văn An", None)
    with conn_of(client) as conn:
        assert p["student"]["since"] == students.overview(conn)[an]["since"]
        assert p["skills"] == students.skills(conn, an) and p["recurring"] == students.recurring(conn, an)
        assert client.get(f"/api/students/{an}/progress").json() == json.loads(json.dumps(students.progress(conn, an)))
    [s] = p["skills"]
    assert (s["level"], s["trend"], s["n_attempts"], s["last_seen"]) == ("đang hình thành", "cần ôn", 2, "2026-10-14")
    assert p["recurring"][0]["count"] == 2 and "code" not in p["recurring"][0] and p["pending"] == []
    prog = client.get(f"/api/students/{an}/progress").json()
    assert prog["dates"] == ["2026-10-07", "2026-10-14"] and set(prog["skills"]) == {str(s["kc_id"])}
    assert client.get(f"/api/students/{w['cuong']}/profile").json()["student"][
        "archived_at"
    ]  # archived: still readable
    assert client.get(f"/api/students/{w['cuong']}/progress").json() == {"dates": [], "all": [], "skills": {}}
    for tail in ("profile", "progress"):
        r = client.get(f"/api/students/99/{tail}")
        assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_sessions_teacher_view(env):
    client, w = env
    an = w["an"]
    rows = client.get(f"/api/sessions?student={an}&status=committed&view=teacher").json()
    assert [(r["held_on"], r["n_attempts"], r["score"], r["max_score"], r["n_mistakes"]) for r in rows] == [
        ("2026-10-14", 1, 1.0, 2.0, 1),
        ("2026-10-07", 1, 1.0, 2.0, 1),
    ]
    assert all(set(r) == TEACHER_SESSION for r in rows)
    assert len(client.get("/api/sessions?month=2026-10&view=teacher").json()) == 3
    assert client.get("/api/sessions?month=2026-09&view=teacher").json() == []
    d = client.get(f"/api/sessions/{rows[0]['id']}?view=teacher").json()
    assert (d["id"], d["student_id"], d["n_mistakes"]) == (rows[0]["id"], an, 1)
    [m] = d["attempts"][0]["mistakes"]
    assert m["kind"] == "Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)" and m["kc"]["id"] == w["kc_swap"]
    r = client.get("/api/sessions/999?view=teacher")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_no_view_unchanged(env):
    client, w = env
    [first, *_] = client.get("/api/students").json()
    assert set(first) == OLD_STUDENT
    assert all(set(s) == OLD_STUDENT for s in client.get("/api/students?archived=true").json())
    [row, *_] = client.get("/api/sessions?student=1").json()
    assert set(row) == OLD_SESSION
    d = client.get(f"/api/sessions/{row['id']}").json()
    assert "transcript_latex" in d and {"rubric", "grade", "flags"} <= set(d["attempts"][0])
    assert "llm_json" in d["attempts"][0]["mistakes"][0]
    assert client.get("/api/sessions/1?view=other").json() == client.get("/api/sessions/1").json()


def test_no_tech_text(env):
    client, w = env
    an = w["an"]
    urls = [
        "/api/students?view=teacher&archived=true",
        f"/api/students/{an}/profile",
        f"/api/students/{an}/progress",
        f"/api/students/{w['binh']}/profile",
        "/api/sessions?view=teacher",
        "/api/sessions/1?view=teacher",
        "/api/sessions/3?view=teacher",
    ]

    def scrub(node):
        """Without the values the app only sends back: codes, thread ids."""
        if isinstance(node, dict):
            return {k: scrub(v) for k, v in node.items() if k not in ("code", "thread_id")}
        return [scrub(v) for v in node] if isinstance(node, list) else node

    for url in urls:
        got = client.get(url)
        assert got.status_code == 200, url
        assert not FORBIDDEN.search(json.dumps(scrub(got.json()), ensure_ascii=False)), url
