"""P5-T01: FTS5 problem search and the teacher's problem grid."""

import shutil
from contextlib import closing
from pathlib import Path

import pytest

from tutor.db import repo, seed_dummy
from tutor.services import search

BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"
MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "tutor" / "db" / "migrations"


@pytest.fixture
def bank(conn):
    seed_dummy.seed(conn, BANK)
    return conn


def refs(items):
    return [i["ref"] for i in items]


def count(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def test_migration_002_keeps_data(tmp_path):
    db, mig, bk = tmp_path / "t.db", tmp_path / "mig", tmp_path / "bk"
    mig.mkdir()
    shutil.copy(MIGRATIONS / "001.sql", mig)
    assert repo.init_db(db, bk, mig) == 1
    with closing(repo.connect(db)) as c:
        c.execute(
            "INSERT INTO problem (ref, statement_latex, solution_latex) VALUES ('8DS-X-001', 'Tính hình thoi', 's')"
        )
    assert repo.migrate(db, bk) == 2
    with closing(repo.connect(db)) as c:
        assert count(c, "SELECT count(*) FROM problem") == 1
        assert refs(search.search_problems(c, "hinh thoi")) == ["8DS-X-001"]


def test_search_unaccented_top5(bank):
    top = search.search_problems(bank, "phuong trinh chua an o mau")[:5]
    code = "9DS-PT2-08"
    assert any(code in {k["code"] for k in repo.problem_detail(bank, i["id"])["kcs"]} for i in top)


def test_search_d_stroke(bank):
    plain, accented = search.search_problems(bank, "do thi"), search.search_problems(bank, "đồ thị")
    assert refs(plain) == refs(accented)
    assert any(i["ref"].startswith("8DS-HSBN-") and "đồ thị" in i["statement_latex"] for i in plain)


def test_search_follows_edits(bank):
    bank.execute("UPDATE problem SET statement_latex = 'Tính diện tích hình thoi' WHERE ref = '8DS-PT1-001'")
    assert refs(search.search_problems(bank, "hinh thoi"))[0] == "8DS-PT1-001"
    kc_id = count(bank, "SELECT kc_id FROM problem_kc GROUP BY kc_id HAVING count(*) <= 3 ORDER BY kc_id LIMIT 1")
    pids = {r[0] for r in bank.execute("SELECT problem_id FROM problem_kc WHERE kc_id = ?", (kc_id,))}
    repo.update_kc(bank, kc_id, name="Đường tròn nội tiếp")
    assert pids <= {i["id"] for i in search.search_problems(bank, "duong tron noi tiep")}


def test_search_follows_tags_and_deletes(bank):
    a, b = (r[0] for r in bank.execute("SELECT id FROM problem ORDER BY id LIMIT 2"))
    kc_id = bank.execute("INSERT INTO kc (code, name, description) VALUES ('ZZ-1', 'Quaternion', 'd')").lastrowid
    found = lambda: [i["id"] for i in search.search_problems(bank, "quaternion")]  # noqa: E731
    bank.execute("INSERT INTO problem_kc (problem_id, kc_id, approved_at) VALUES (?, ?, 't')", (a, kc_id))
    assert found() == [a]
    bank.execute("UPDATE problem_kc SET problem_id = ? WHERE kc_id = ?", (b, kc_id))
    assert found() == [b]
    bank.execute("DELETE FROM problem_kc WHERE kc_id = ?", (kc_id,))
    assert found() == []
    bank.execute("DELETE FROM problem_kc WHERE problem_id = ?", (a,))
    bank.execute("DELETE FROM rubric WHERE problem_id = ?", (a,))
    bank.execute("DELETE FROM problem WHERE id = ?", (a,))
    assert count(bank, "SELECT count(*) FROM problem_fts") == 309
    assert count(bank, "SELECT count(*) FROM problem_fts WHERE rowid = ?", a) == 0


def test_search_hostile_text(bank):
    for text in ['"', "*", "AND (", "?", "NEAR(a b)", "a OR", "'; DROP TABLE problem; --"]:
        search.search_problems(bank, text)
        search.browse(bank, q=text)
    assert search.browse(bank, q="$$") == search.browse(bank, q="")


def test_search_levels_and_limit(bank):
    assert len(search.search_problems(bank, "phuong trinh", limit=50)) == 10
    assert {i["level"] for i in search.search_problems(bank, "phuong trinh", level_min="khó")} == {"khó"}
    mid = search.search_problems(bank, "phuong trinh", level_min="vừa", level_max="vừa")
    assert mid and {i["level"] for i in mid} == {"vừa"}
    bank.execute("UPDATE problem SET delta = NULL, difficulty_approved_at = NULL")
    assert search.search_problems(bank, "phuong trinh", level_min="dễ") == []
    assert search.search_problems(bank, "phuong trinh")


def test_items_by_id_shape_and_order(bank):
    ids = [
        r[0]
        for r in bank.execute("SELECT id FROM problem WHERE ref IN ('9DS-PT2-001', '8DS-HSBN-001') ORDER BY ref DESC")
    ]
    got = search.items_by_id(bank, ids + [999999])
    assert [i["id"] for i in got] == ids
    one = got[1]
    assert set(one) == {"id", "ref", "grade", "topic", "kcs", "level", "has_rubric", "is_new", "statement_latex"}
    assert (one["ref"], one["grade"], one["has_rubric"], one["is_new"]) == ("8DS-HSBN-001", 8, True, True)
    assert one["topic"]["name"] and one["kcs"] and set(one["kcs"][0]) == {"id", "name"}
    bank.execute("UPDATE problem SET delta = 0.31 WHERE id = ?", (ids[1],))
    bank.execute("UPDATE problem SET delta = -0.3, difficulty_approved_at = NULL WHERE id = ?", (ids[0],))
    assert [i["level"] for i in search.items_by_id(bank, ids)] == [None, "khó"]


def test_items_by_id_topic_is_root_of_smallest_kc(bank):
    row = bank.execute(
        "SELECT pk.problem_id, MIN(pk.kc_id) FROM problem_kc pk GROUP BY pk.problem_id HAVING count(*) > 1 LIMIT 1"
    ).fetchone()
    root = count(bank, "SELECT COALESCE(parent_id, id) FROM kc WHERE id = ?", row[1])
    assert search.items_by_id(bank, [row[0]])[0]["topic"]["id"] == root


def test_browse_filters(bank):
    bank.execute("UPDATE problem SET delta = NULL, difficulty_approved_at = NULL WHERE ref LIKE '8DS-PT1-00%'")
    root = count(bank, "SELECT id FROM kc WHERE parent_id IS NULL ORDER BY id LIMIT 1")
    kc_id = count(bank, "SELECT kc_id FROM problem_kc GROUP BY kc_id ORDER BY count(*) DESC, kc_id LIMIT 1")
    cases = [
        ({}, "SELECT count(*) FROM problem"),
        (
            {"topic": root},
            "SELECT count(DISTINCT problem_id) FROM problem_kc"
            f" WHERE kc_id IN (SELECT id FROM kc WHERE id = {root} OR parent_id = {root})",
        ),
        ({"grade": 9}, "SELECT count(*) FROM problem WHERE ref LIKE '9%'"),
        ({"level": "dễ"}, "SELECT count(*) FROM problem WHERE difficulty_approved_at IS NOT NULL AND delta < -0.3"),
        (
            {"level": "vừa"},
            "SELECT count(*) FROM problem WHERE difficulty_approved_at IS NOT NULL AND delta BETWEEN -0.3 AND 0.3",
        ),
        ({"level": "khó"}, "SELECT count(*) FROM problem WHERE difficulty_approved_at IS NOT NULL AND delta > 0.3"),
        ({"level": "none"}, "SELECT count(*) FROM problem WHERE difficulty_approved_at IS NULL"),
        ({"kc": kc_id}, f"SELECT count(*) FROM problem_kc WHERE kc_id = {kc_id}"),
    ]
    for kw, sql in cases:
        got = search.browse(bank, **kw)
        assert got["total"] == count(bank, sql) > 0, kw
        assert len(got["items"]) == min(12, got["total"])
    assert {i["level"] for i in search.browse(bank, level="none", limit=100)["items"]} == {None}
    assert {i["grade"] for i in search.browse(bank, grade=9, limit=100)["items"]} == {9}
    both = search.browse(bank, grade=8, level="khó")["total"]
    assert both == count(bank, "SELECT count(*) FROM problem WHERE ref LIKE '8%' AND delta > 0.3")


def test_browse_pages_and_topic_counts(bank):
    first, second = search.browse(bank)["items"], search.browse(bank, offset=12)["items"]
    assert len(first) == len(second) == 12 and not set(refs(first)) & set(refs(second))
    assert refs(first) == sorted(refs(first))
    roots = {str(r[0]) for r in bank.execute("SELECT id FROM kc WHERE parent_id IS NULL")}
    got = search.browse(bank, topic=int(next(iter(roots))), limit=1)
    assert set(got["topic_counts"]) == roots and len(roots) == 10
    assert got["topic_counts"] == search.browse(bank)["topic_counts"]


def test_ref_prefix_first(bank):
    assert search.browse(bank, q="8ds-hsbn-00")["items"][0]["ref"].startswith("8DS-HSBN-00")
    assert search.search_problems(bank, "8DS-PT1-003")[0]["ref"] == "8DS-PT1-003"


def test_find_problems(bank):
    got = search.find_problems(bank, ["8ds-pt1-001", "KHONG-CO", "9DS-PT2-001"])
    assert refs(got) == ["8DS-PT1-001", "9DS-PT2-001"]
