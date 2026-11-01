"""SDD Phụ lục B #26 (read part): bank problems for Buổi học bước 3 › Chọn bài khác."""

from contextlib import closing

from tests.bankfix import P1, P2, add_bank
from tutor.db import repo


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


def test_default_view_unchanged(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    assert isinstance(client.get("/api/bank/problems?topic=1&level=dễ").json(), list)
