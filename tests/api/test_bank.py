"""SDD Phụ lục B #26 (read part): bank problems for the Ngân hàng bài tab."""

import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.api.test_sessions import poll
from tests.bankfix import P1, P2, add_bank
from tutor.db import repo, seed_dummy

W = {"X-Tutor": "1"}
ROOT = Path(__file__).resolve().parents[2]
MIX = ROOT / "tests" / "fixtures" / "bank" / "import-mix.tex"
ONE = (
    "% Hàm số ôn tập\n\\begin{problem}[8DS-ONE-001]\n% kc_du_kien: 8DS-HSBN-02\nTính $f(0)$.\n"
    "\\begin{solution}\nBước.\n\\end{solution}\n\\end{problem}\n"
)


def import_mix(paths, client) -> str:
    """Dummy bank seeded, mix.tex in the inbox, G2 started; returns the thread id."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
    shutil.copy(MIX, paths.inbox / "bank" / "mix.tex")
    r = client.post("/api/bank/imports", json={"file": "mix.tex"}, headers=W)
    assert r.status_code == 202
    return r.json()["thread_id"]


def test_search_by_ref_or_statement_and_detail(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    all_ = client.get("/api/bank/problems").json()
    assert [p["ref"] for p in all_] == ["8DS-PT1-001", "8DS-PT1-002", "9DS-PT2-001"]
    assert [p["ref"] for p in client.get("/api/bank/problems?q=pt1-002").json()] == [P2[0]]
    assert [p["ref"] for p in client.get("/api/bank/problems?q=nhận x = 3").json()] == [P2[0]]
    assert client.get("/api/bank/problems?q=pt1&limit=1").json()[0]["has_rubric"] == 1
    pid = all_[0]["id"]
    d = client.get(f"/api/bank/problems/{pid}").json()
    assert d["ref"] == P1[0] and d["rubric"]["items"][0]["item_id"] == "r1" and d["kcs"][0]["code"] == "8DS-PT1-01"
    assert client.get("/api/bank/problems/999").status_code == 404


def test_teacher_view_shape(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    got = client.get("/api/bank/problems?view=teacher&limit=2").json()
    assert set(got) == {"total", "topic_counts", "items"} and got["total"] == 3 and len(got["items"]) == 2
    assert all("delta" not in i for i in got["items"])
    assert [
        i["ref"] for i in client.get("/api/bank/problems?view=teacher&q=nhận x&grade=8&offset=0").json()["items"]
    ] == [P2[0]]
    assert client.get("/api/bank/problems?view=teacher&limit=0").json()["items"] != []
    assert client.get("/api/bank/problems?view=teacher&level=bogus").status_code == 422


def test_teacher_view_default_limit_is_12(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
        for n in range(20):
            repo.add_bank_problem(
                conn, ref=f"8DS-X-{n:03}", statement="s", solution="s", source="t", delta=None, tags=[],
                rubric_items=[{"item_id": "r1", "text": "t", "points": 1}],
            )  # fmt: skip
    got = client.get("/api/bank/problems?view=teacher").json()
    assert (got["total"], len(got["items"])) == (23, 12)
    assert len(client.get("/api/bank/problems?view=teacher&limit=500").json()["items"]) == 23
    assert len(client.get("/api/bank/problems").json()) == 23


def test_default_view_unchanged(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    assert isinstance(client.get("/api/bank/problems?topic=1&level=dễ").json(), list)


def test_patch_level_returns_word(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    pid = client.get("/api/bank/problems").json()[0]["id"]
    r = client.patch(f"/api/bank/problems/{pid}", json={"level": "khó"}, headers=W)
    assert r.status_code == 200
    got = r.json()
    assert got["level"] == "khó" and got["applies_from_now"] is True and "delta" not in got and "tech" not in got
    assert client.get(f"/api/bank/problems/{pid}").json()["level"] == "khó"
    tech = client.get(f"/api/bank/problems/{pid}?tech=1").json()["tech"]
    assert tech["delta"] == 0.6 and tech["difficulty_approved_at"] and tech["replay_hint"] == []


def test_patch_absent_vs_null(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    pid = client.get("/api/bank/problems").json()[0]["id"]
    url = f"/api/bank/problems/{pid}"
    assert client.patch(url, json={}, headers=W).json()["level"] == "vừa"
    assert client.patch(url, json={"level": None}, headers=W).json()["level"] is None


def test_patch_errors(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    pid = client.get("/api/bank/problems").json()[0]["id"]
    url = f"/api/bank/problems/{pid}"
    assert client.patch("/api/bank/problems/999", json={}, headers=W).status_code == 404
    for body in (
        {"kc_ids": []},
        {"kc_ids": [999]},
        {"level": "x"},
        {"rubric_items": []},
        {"rubric_items": [{"text": "t"}]},
    ):
        assert client.patch(url, json=body, headers=W).status_code == 422


def test_patch_needs_header(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    pid = client.get("/api/bank/problems").json()[0]["id"]
    assert client.patch(f"/api/bank/problems/{pid}", json={"level": "khó"}).status_code == 403
    assert client.get(f"/api/bank/problems/{pid}").json()["level"] == "vừa"


def test_inbox_status(paths, client):
    folder = paths.inbox / "bank"
    (folder / "a-one.tex").write_text(ONE, encoding="utf-8")
    (folder / "b-empty.tex").write_text("Không có bài nào\n", encoding="utf-8")
    (folder / "c-notes.txt").write_text("x", encoding="utf-8")
    with closing(repo.connect(paths.tutor_db)) as conn:
        seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
    shutil.copy(MIX, folder / "d-mix.tex")
    got = {f["file"]: f for f in client.get("/api/bank/inbox").json()}
    assert list(got) == ["a-one.tex", "b-empty.tex", "d-mix.tex"]
    assert got["a-one.tex"] == {
        "file": "a-one.tex",
        "title": "Hàm số ôn tập",
        "bytes": (folder / "a-one.tex").stat().st_size,
        "n_problems": 1,
        "n_new": 1,
        "status": "new",
        "imported_at": None,
    }
    assert (got["b-empty.tex"]["title"], got["b-empty.tex"]["status"], got["b-empty.tex"]["n_problems"]) == (
        None, "empty", 0)  # fmt: skip
    mix = got["d-mix.tex"]
    assert (mix["n_problems"], mix["n_new"], mix["status"]) == (5, 4, "partly")  # 3 broken problems are not counted
    assert mix["imported_at"] == f"{datetime.now(UTC):%Y-%m-%d}"
    tid = client.post("/api/bank/imports", json={"file": "a-one.tex"}, headers=W).json()["thread_id"]
    assert poll(client, tid, until=("awaiting_review", "failed"))["status"] == "awaiting_review"
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    assert poll(client, tid, until=("committed", "failed"))["status"] == "committed"
    one = next(f for f in client.get("/api/bank/inbox").json() if f["file"] == "a-one.tex")
    assert (one["n_new"], one["status"], one["imported_at"]) == (0, "imported", f"{datetime.now(UTC):%Y-%m-%d}")


@pytest.mark.parametrize("name", ["../tutor.db", "/etc/hosts", "notes.txt", "missing.tex", "empty.tex"])
def test_import_rejects_outside_inbox(paths, client, name):
    (paths.inbox / "bank" / "notes.txt").write_text("x", encoding="utf-8")
    (paths.inbox / "bank" / "empty.tex").write_text("Không có bài nào\n", encoding="utf-8")
    r = client.post("/api/bank/imports", json={"file": name}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    assert client.get("/api/threads?graph=G2").json() == []


def test_import_twice_returns_same_thread(paths, client):
    tid = import_mix(paths, client)
    r = client.post("/api/bank/imports", json={"file": "mix.tex"}, headers=W)
    assert r.status_code == 200 and r.json()["thread_id"] == tid and set(r.json()) == {"thread_id", "status"}
    assert len(client.get("/api/threads?graph=G2").json()) == 1


def test_import_needs_header(paths, client):
    shutil.copy(MIX, paths.inbox / "bank" / "mix.tex")
    assert client.post("/api/bank/imports", json={"file": "mix.tex"}).status_code == 403


def test_import_of_a_non_utf8_file_says_so_and_is_logged(paths, client):
    (paths.inbox / "bank" / "latin.tex").write_bytes("\\begin{problem}[X1] caf\xe9 \\end{problem}".encode("latin-1"))
    r = client.post("/api/bank/imports", json={"file": "latin.tex"}, headers=W)
    assert r.status_code == 422 and r.json()["error"]["message"] == "File phải lưu dạng UTF-8"
    assert "POST /api/bank/imports: File phải lưu dạng UTF-8" in (paths.logs / "app.log").read_text(encoding="utf-8")


def test_import_of_an_oversize_file_is_refused(paths, client):
    (paths.inbox / "bank" / "big.tex").write_text(ONE + "%" + "x" * 200_000, encoding="utf-8")
    r = client.post("/api/bank/imports", json={"file": "big.tex"}, headers=W)
    assert r.status_code == 422 and "200 KB" in r.json()["error"]["message"]
