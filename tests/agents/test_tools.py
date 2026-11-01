"""P6-T03: read-only tools of agent 00."""

import json
import sqlite3
from contextlib import closing

import pytest

from tests.assistant_fix import world
from tutor.agents import tools
from tutor.agents.tools import LABELS, TOOLS, Toolbox
from tutor.db import repo

REF = "9DS-BPT-001"
ORDER = [
    "find_problems", "search_problems", "list_students", "student_profile", "student_mistakes", "compare_students",
]  # fmt: skip
CALLS = [
    ("find_problems", {"refs": [REF, "9ZZ-NOPE-999"]}),
    ("search_problems", {"text": "phương trình", "level_max": "vừa", "limit": 3}),
    ("list_students", {}),
    ("student_profile", {"code": "HS-01"}),
    ("student_mistakes", {"code": "HS-01", "since": "2026-10-01", "kind": "notational.operator_swap"}),
    ("compare_students", {"metric": "open_repeats"}),
]


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def box(ro, text="so sánh các học sinh"):
    c, w = ro
    return Toolbox(c, settings={}, today=w["today"], text=text)


def test_readonly_connection(conn, paths):
    world(conn)
    with (
        closing(repo.connect(paths.tutor_db, readonly=True)) as c,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        c.execute("DELETE FROM student")


def test_no_names_in_outcomes(conn, ro):
    names = [s["name"] for s in repo.list_students(conn, include_archived=True)]
    assert len(names) == 3
    tb = box(ro)
    for name, args in CALLS:
        out = tb.run(name, args)
        assert not out.is_error, (name, out.content)
        text = json.dumps([out.content, out.data, out.card, out.summary, out.source], ensure_ascii=False)
        assert not [n for n in names if n in text], name
    assert [n for n, _ in tb.outcomes] == [n for n, _ in CALLS]


def test_search_bad_level_is_error(ro):
    out = box(ro).run("search_problems", {"text": "x", "level_min": "trung bình"})
    assert out.is_error and "dễ / vừa / khó" in out.content and out.card is None


def test_unknown_tool_and_code_are_errors(ro):
    tb = box(ro)
    gone = tb.run("delete_everything", {})
    assert gone.is_error and "delete_everything" in gone.content
    missing = tb.run("student_profile", {"code": "HS-99"})
    assert missing.is_error and "Không có học sinh HS-99" in missing.content
    archived = tb.run("student_mistakes", {"code": "HS-03"})
    assert archived.is_error
    assert [n for n, _ in tb.outcomes] == ["delete_everything", "student_profile", "student_mistakes"]


def test_content_capped(conn, ro):
    tb = box(ro)
    for name, args in CALLS:
        out = tb.run(name, args)
        assert len(out.content) <= tools.MAX_CONTENT
        json.loads(out.content)
    err = tb.run("student_profile", {"code": "HS-99"})
    assert isinstance(json.loads(err.content), dict)


def test_long_list_is_trimmed_not_cut(conn, ro):
    for i in range(150):
        repo.add_student(conn, name=f"Học Sinh {i}", grade=7)
    out = box(ro).run("list_students", {})
    body = json.loads(out.content)
    assert len(out.content) <= tools.MAX_CONTENT
    assert body["omitted"]["students"] == 152 - len(body["students"]) > 0
    assert len(out.data["students"]) == 152


def test_find_problems_outcome(ro):
    out = box(ro).run("find_problems", {"refs": [REF.lower(), "9ZZ-NOPE-999"]})
    body = json.loads(out.content)
    assert body["missing"] == ["9ZZ-NOPE-999"]
    (p,) = body["problems"]
    assert set(p) == {"ref", "grade", "level", "kcs", "has_rubric", "statement_latex"}
    assert p["ref"] == REF and p["grade"] == 9 and all(isinstance(k, str) for k in p["kcs"])
    c, _ = ro
    pid = c.execute("SELECT id FROM problem WHERE ref = ?", (REF,)).fetchone()[0]
    assert out.card["kind"] == "problem" and out.card["missing"] == ["9ZZ-NOPE-999"] and out.card["added_to"] is None
    assert out.card["problems"][0]["id"] == pid
    assert out.card["problems"][0]["solution_steps"] == repo.problem_view(c, pid)["solution_steps"] != []
    assert (out.label, out.source) == ("tìm bài theo mã", "ngân hàng bài (theo mã)")
    assert out.summary == "find_problems: 1 bài, không thấy 1"


def test_find_problems_needs_one_to_ten_refs(ro):
    tb = box(ro)
    assert tb.run("find_problems", {"refs": []}).is_error
    assert tb.run("find_problems", {"refs": [REF] * 11}).is_error


def test_search_problems_outcome(ro):
    c, _ = ro
    out = box(ro).run("search_problems", {"text": "phương trình", "limit": 2})
    body = json.loads(out.content)
    assert body["n"] == len(body["problems"]) == 2 == len(out.card["problems"])
    assert out.card["missing"] == []
    total = c.execute("SELECT count(*) FROM problem").fetchone()[0]
    assert out.source == f"tìm trong ngân hàng bài ({total} bài)"
    assert (out.label, out.summary) == ("tìm trong ngân hàng bài", "search_problems: 2 bài")


def test_list_students_card_only_without_mention(ro):
    plain = box(ro, text="bạn nào hay sai dấu?").run("list_students", {})
    assert plain.card == {"kind": "pick_student", "text": "bạn nào hay sai dấu?"}
    assert [s["code"] for s in json.loads(plain.content)["students"]] == ["HS-01", "HS-02"]
    assert box(ro, text="hồ sơ @HS-01").run("list_students", {}).card is None
    assert (plain.label, plain.source, plain.summary) == (
        "danh sách học sinh", "danh sách học sinh", "list_students: 2 học sinh"
    )  # fmt: skip


def test_student_outcomes_words(ro):
    tb = box(ro)
    prof = tb.run("student_profile", {"code": "HS-01"})
    assert (prof.label, prof.source, prof.card) == ("hồ sơ học sinh", "hồ sơ của HS-01", None)
    assert prof.summary == "student_profile HS-01: 0 vững, 1 đang hình thành, 0 chưa vững; 1 lỗi lặp"
    since = tb.run("student_mistakes", {"code": "HS-01", "since": "2026-10-10"})
    assert since.source == "lỗi đã duyệt của HS-01 từ 10/10/2026" and since.label == "lỗi đã duyệt"
    assert tb.run("student_mistakes", {"code": "HS-01"}).source == "lỗi đã duyệt của HS-01"
    assert json.loads(since.content)["total"] == 1
    cmp = tb.run("compare_students", {"metric": "mistakes"})
    assert (cmp.label, cmp.source) == ("so sánh học sinh", "so sánh lỗi đã duyệt của 2 học sinh")
    assert tb.run("compare_students", {"metric": "level"}).is_error


def test_tool_defs_strict(conn):
    codes = [e["code"] for e in repo.error_codes(conn, active_only=True)]
    conn.execute("UPDATE error_code SET active = 0 WHERE code = ?", (codes[0],))
    active = [e["code"] for e in repo.error_codes(conn, active_only=True)]
    assert active == codes[1:]
    defs = tools.tool_defs(active)
    assert [d["name"] for d in defs] == ORDER == list(LABELS)[: len(ORDER)]
    assert [d["name"] for d in TOOLS] == ORDER
    for d in defs:
        assert d["strict"] is True and d["description"]
        schema = d["input_schema"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
    kinds = [d["input_schema"]["properties"]["kind"] for d in defs if "kind" in d["input_schema"]["properties"]]
    assert len(kinds) == 2 and all(k["enum"] == active for k in kinds)
    assert "enum" not in TOOLS[4]["input_schema"]["properties"]["kind"]
    levels = TOOLS[1]["input_schema"]["properties"]
    assert levels["level_min"]["enum"] == levels["level_max"]["enum"] == ["dễ", "vừa", "khó"]
