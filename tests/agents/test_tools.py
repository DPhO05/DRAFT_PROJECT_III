"""P6-T03: read-only tools of agent 00."""

import json
import sqlite3
from contextlib import closing

import pytest

from tests.assistant_fix import world
from tutor import config
from tutor.agents.a00_orchestrator import tools
from tutor.agents.a00_orchestrator.tools import LABELS, TOOLS, Starters, Toolbox
from tutor.db import repo

REF = "9DS-BPT-001"
ORDER = [
    "find_problems", "search_problems", "list_students", "student_profile", "student_mistakes", "compare_students",
    "rank_problems", "start_grading", "start_bank_import", "propose_worksheet", "start_report",
]  # fmt: skip
CALLS = [
    ("find_problems", {"refs": [REF, "9ZZ-NOPE-999"]}),
    ("search_problems", {"text": "phương trình", "level_max": "vừa", "limit": 3}),
    ("list_students", {}),
    ("student_profile", {"code": "HS-01"}),
    ("student_mistakes", {"code": "HS-01", "since": "2026-10-01", "kind": "notational.operator_swap"}),
    ("compare_students", {"metric": "open_repeats"}),
    ("rank_problems", {"code": "HS-01"}),
]


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def box(ro, text="so sánh các học sinh", starters=None):
    c, w = ro
    return Toolbox(c, settings=config.defaults(), today=w["today"], text=text, starters=starters)


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
        text = json.dumps([out.content, out.card, out.summary, out.source], ensure_ascii=False)
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


BAD_ARGS = [
    ("find_problems", {}, "Thiếu tham số refs"),
    ("student_profile", {}, "Thiếu tham số code"),
    ("compare_students", {"kc": 1}, "Thiếu tham số metric"),
    ("search_problems", {"text": "x", "limit": "3"}, "không đúng"),
    ("student_mistakes", {"code": "HS-01", "since": 5}, "không đúng"),
    ("student_profile", {"code": 1}, "không đúng"),
    ("find_problems", {"refs": 5}, "không đúng"),
    ("rank_problems", {}, "Thiếu tham số code"),
    ("start_grading", {"code": "HS-01", "file": "a.tex"}, "Thiếu tham số held_on"),
    ("start_bank_import", {}, "Thiếu tham số file"),
    ("propose_worksheet", {"code": "HS-01", "for_date": "2026-10-24"}, "Thiếu tham số refs"),
    ("start_report", {"code": "HS-01", "period_kind": "week"}, "Thiếu tham số period_start"),
    ("rank_problems", {"code": "HS-01", "n": "3"}, "không đúng"),
    ("rank_problems", {"code": "HS-01", "ratios": {"review": "a", "zpd": 1, "challenge": 0}}, "không đúng"),
]


@pytest.mark.parametrize(("name", "args", "words"), BAD_ARGS)
def test_bad_arguments_are_errors_not_crashes(ro, caplog, name, args, words):
    tb = box(ro)
    out = tb.run(name, args)
    assert out.is_error and words in json.loads(out.content)["error"]
    assert out.card is None and tb.outcomes == [(name, out)]
    if "không đúng" in words:
        (rec,) = [r for r in caplog.records if r.name == "tutor"]
        assert (rec.levelname, rec.exc_info is not None, rec.getMessage()) == ("ERROR", True, f"tool {name}")


def test_tool_bug_is_logged_without_arguments(ro, caplog, monkeypatch):
    def broken(conn):
        return {}["students"]

    monkeypatch.setattr(tools.students, "list_students", broken)
    out = box(ro).run("list_students", {})
    assert out.is_error
    (rec,) = [r for r in caplog.records if r.name == "tutor"]
    assert rec.exc_info[0] is KeyError and "tool list_students" == rec.getMessage()


def test_busy_database_is_error(ro, caplog, monkeypatch):
    def locked(conn):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(tools.students, "list_students", locked)
    tb = box(ro)
    out = tb.run("list_students", {})
    assert out.is_error and "bận" in json.loads(out.content)["error"] and tb.outcomes == [("list_students", out)]
    (rec,) = [r for r in caplog.records if r.name == "tutor"]
    assert (rec.levelname, rec.exc_info is not None, rec.getMessage()) == (
        "WARNING",
        True,
        "tool list_students: DB busy",
    )


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
    report = defs[ORDER.index("start_report")]["input_schema"]
    assert report["required"] == ["code", "period_kind", "period_start"]
    assert report["properties"]["period_kind"]["enum"] == ["day", "week", "month"]
    levels = TOOLS[1]["input_schema"]["properties"]
    assert levels["level_min"]["enum"] == levels["level_max"]["enum"] == ["dễ", "vừa", "khó"]


def test_rank_problems_outcome(ro):
    tb = box(ro)
    out = tb.run("rank_problems", {"code": "HS-01"})
    assert not out.is_error and out.card is None
    assert (out.label, out.source) == ("chọn bài theo tiến bộ", "gợi ý bài theo tiến bộ của HS-01")
    body = json.loads(out.content)
    assert body["n"] == 6 and body["counts"] == {"review": 2, "zpd": 3, "challenge": 1} and body["warnings"] == []
    assert len(body["items"]) == 6 and all("statement_latex" not in i for i in body["items"])
    assert {"ref", "bucket", "reason", "kcs"} <= set(body["items"][0])
    assert [i["ref"] for i in tb.ranked] == [i["ref"] for i in body["items"]]
    assert all(i["statement_latex"] for i in tb.ranked)
    again = tb.run("rank_problems", {"code": "HS-01", "n": 2, "ratios": {"review": 1, "zpd": 0, "challenge": 0}})
    assert json.loads(again.content)["counts"] == {"review": 2, "zpd": 0, "challenge": 0}
    assert len(tb.ranked) == 2 and [n for n, _ in tb.outcomes] == ["rank_problems"] * 2


@pytest.mark.parametrize(
    ("args", "words"),
    [
        ({"code": "HS-99"}, "Không có học sinh HS-99"),
        ({"code": "HS-01", "n": 0}, "1 đến 12"),
        ({"code": "HS-01", "n": 13}, "1 đến 12"),
        ({"code": "HS-01", "ratios": {"review": 0, "zpd": 0, "challenge": 0}}, "Tỉ lệ"),
        ({"code": "HS-01", "ratios": {"review": 1.5, "zpd": 0, "challenge": 0}}, "Tỉ lệ"),
    ],
)
def test_rank_problems_bad_input_is_error(ro, args, words):
    tb = box(ro)
    out = tb.run("rank_problems", args)
    assert out.is_error and words in json.loads(out.content)["error"] and tb.ranked == []


def _walk(schema):
    yield schema
    for sub in (*schema.get("properties", {}).values(), *([schema["items"]] if "items" in schema else [])):
        yield from _walk(sub)


def test_strict_schema_limits():
    optional = 0
    for d in TOOLS:
        for node in _walk(d["input_schema"]):
            assert not {"minimum", "maximum", "maxItems", "exclusiveMinimum", "exclusiveMaximum"} & set(node), d["name"]
            assert node.get("minItems", 0) <= 1, d["name"]
            optional += len(node.get("properties", {})) - len(node.get("required", []))
    assert optional == 13
    rank = {d["name"]: d for d in TOOLS}["rank_problems"]["input_schema"]
    assert rank["required"] == ["code"] and set(rank["properties"]) == {"code", "n", "ratios"}
    assert rank["properties"]["ratios"]["required"] == ["review", "zpd", "challenge"]


GRADING = {"thread_id": "g1-hs01-20261021", "session_id": 7, "status": "running"}
IMPORT = {"thread_id": "g2-mix-20261021", "status": "running", "existing": False}
SHEET = {
    "thread_id": "g4-hs01-20261024",
    "existing": True,
    "added": ["9DS-BPT-001"],
    "invalid": [{"ref": "ZZ", "why": "không có trong ngân hàng"}],
}
REPORT = {"thread_id": "g5-hs01w-20261012", "status": "awaiting_review", "existing": True}


def recorder(calls, grading=GRADING):
    def rec(name, out):
        def f(*args):
            calls.append((name, *args))
            if isinstance(out, Exception):
                raise out
            return out

        return f

    return Starters(
        start_grading=rec("start_grading", grading),
        start_bank_import=rec("start_bank_import", IMPORT),
        propose_worksheet=rec("propose_worksheet", SHEET),
        add_to_worksheet=rec("add_to_worksheet", {}),
        start_report=rec("start_report", REPORT),
    )


def test_start_tools_outcomes(ro):
    calls = []
    tb = box(ro, starters=recorder(calls))
    g = tb.run("start_grading", {"code": "HS-01", "file": "a.tex", "held_on": "2026-10-21"})
    assert not g.is_error and calls == [("start_grading", 1, "a.tex", "2026-10-21")]
    assert g.card == {"kind": "grading", "thread_id": GRADING["thread_id"]}
    assert (g.label, g.source) == ("bắt đầu chấm bài", "chấm bài của HS-01")
    assert json.loads(g.content) == {"code": "HS-01", "held_on": "2026-10-21", "status": "running"}
    b = tb.run("start_bank_import", {"file": "mix.tex"})
    assert not b.is_error and calls[-1] == ("start_bank_import", "mix.tex")
    assert b.card == {
        "kind": "actions",
        "items": [{"label": "Mở Ngân hàng bài để chọn kỹ năng", "open": {"tab": "ngan-hang"}}],
    }
    assert b.label == "đọc file bài mới" and b.source
    assert json.loads(b.content) == {"file": "mix.tex", "status": "running", "existing": False}
    for out in (g, b):
        assert "thread" not in out.content and "g1-" not in out.content and "g2-" not in out.content
    assert [n for n, _ in tb.outcomes] == ["start_grading", "start_bank_import"]


def test_start_report_outcome(ro):
    calls = []
    tb = box(ro, starters=recorder(calls))
    r = tb.run("start_report", {"code": "HS-01", "period_kind": "week", "period_start": "2026-10-12"})
    assert not r.is_error and calls == [("start_report", 1, "week", "2026-10-12")]
    assert r.card == {"kind": "report", "thread_id": REPORT["thread_id"]}
    assert (r.label, r.source) == ("bắt đầu báo cáo", "báo cáo của HS-01")
    assert json.loads(r.content) == {"code": "HS-01", "period_kind": "week", "period_start": "2026-10-12",
                                     "status": "awaiting_review", "existing": True}  # fmt: skip
    assert "thread" not in r.content and "g5-" not in r.content


def test_propose_worksheet_outcome_and_rank_reasons(ro):
    calls = []
    tb = box(ro, starters=recorder(calls))
    rank = tb.run("rank_problems", {"code": "HS-01"})
    items = json.loads(rank.content)["items"]
    refs = [i["ref"] for i in items[:2]]
    assert "9DS-BPT-001" not in [i["ref"] for i in items]
    args = {"code": "HS-01", "for_date": "2026-10-24", "refs": [refs[0].lower(), refs[1], "9DS-BPT-001"], "note": "ôn"}
    out = tb.run("propose_worksheet", args)
    assert not out.is_error
    (_, sid, day, sent, note, warnings) = calls[0]
    assert (sid, day, note, warnings) == (1, "2026-10-24", "ôn", [])
    assert sent == [{"ref": r["ref"], "bucket": r["bucket"], "reason": r["reason"]} for r in items[:2]] + [
        {"ref": "9DS-BPT-001"}
    ]
    assert out.card == {
        "kind": "worksheet",
        "thread_id": SHEET["thread_id"],
        "added": SHEET["added"],
        "invalid": SHEET["invalid"],
    }
    assert (out.label, out.source) == ("soạn phiếu nháp", "phiếu nháp cho HS-01")
    body = json.loads(out.content)
    assert body == {"code": "HS-01", "for_date": "2026-10-24", "n": 1, "added": SHEET["added"],
                    "invalid": SHEET["invalid"], "replaced_draft": True}  # fmt: skip
    assert "thread" not in out.content and "g4-" not in out.content


def test_propose_passes_rank_warnings_and_skips_other_students_rank(ro, monkeypatch):
    real = tools.select.rank_problems
    warns = ["Chỉ tìm được 5 bài hợp"]
    monkeypatch.setattr(tools.select, "rank_problems", lambda *a, **k: real(*a, **k) | {"warnings": warns})
    calls = []
    tb = box(ro, starters=recorder(calls))
    tb.run("rank_problems", {"code": "HS-01"})
    ref = tb.ranked[0]["ref"]
    tb.run("propose_worksheet", {"code": "HS-01", "for_date": "2026-10-24", "refs": [ref]})
    assert calls[-1][5] == warns
    tb.run("propose_worksheet", {"code": "HS-02", "for_date": "2026-10-24", "refs": [ref]})
    assert calls[-1][1:] == (2, "2026-10-24", [{"ref": ref}], None, [])


@pytest.mark.parametrize(
    ("name", "args", "words"),
    [
        ("start_grading", {"code": "HS-99", "file": "a.tex", "held_on": "2026-10-21"}, "Không có học sinh HS-99"),
        ("start_grading", {"code": "HS-03", "file": "a.tex", "held_on": "2026-10-21"}, "Không có học sinh HS-03"),
        ("propose_worksheet", {"code": "HS-99", "for_date": "2026-10-24", "refs": ["X"]}, "Không có học sinh HS-99"),
        ("propose_worksheet", {"code": "HS-01", "for_date": "2026-10-24", "refs": []}, "ít nhất 1 mã bài"),
    ],
)
def test_start_tools_reject_before_starting(ro, name, args, words):
    calls = []
    tb = box(ro, starters=recorder(calls))
    out = tb.run(name, args)
    assert out.is_error and words in json.loads(out.content)["error"] and out.card is None and calls == []


@pytest.mark.parametrize("name", ["start_grading", "start_bank_import", "propose_worksheet"])
def test_starter_value_error_is_the_tool_error(ro, name):
    words = "Bài này đã nộp cho HS-01 rồi (buổi 07/10)."
    args = {
        "start_grading": {"code": "HS-01", "file": "a.tex", "held_on": "2026-10-21"},
        "start_bank_import": {"file": "mix.tex"},
        "propose_worksheet": {"code": "HS-01", "for_date": "2026-10-24", "refs": ["X"]},
    }[name]
    st = recorder([])
    setattr(st, name, lambda *a: (_ for _ in ()).throw(ValueError(words)))
    tb = box(ro, starters=st)
    out = tb.run(name, args)
    assert out.is_error and json.loads(out.content) == {"error": words} and out.card is None and out.source is None


def lc(ro, codes=("a.b", "c.d")):
    return {t.name: t for t in tools.lc_tools(box(ro), list(codes))}


def test_lc_tools_schema_to_model(ro):
    from langchain_core.utils.function_calling import convert_to_openai_tool

    by_name = lc(ro)
    assert list(by_name) == ORDER
    p = convert_to_openai_tool(by_name["student_mistakes"])["function"]["parameters"]
    assert p["required"] == ["code", "since", "kind", "kc"] and p["additionalProperties"] is False
    assert p["properties"]["since"]["type"] == ["string", "null"]
    assert p["properties"]["kind"]["enum"] == ["a.b", "c.d", None]
    assert p["properties"]["code"]["type"] == "string"


def test_lc_tools_artifact_not_in_model_content(ro):
    msg = lc(ro)["list_students"].invoke({"name": "list_students", "args": {}, "id": "t1", "type": "tool_call"})
    assert msg.tool_call_id == "t1" and "pick_student" not in msg.content
    assert msg.artifact["tutor/card"]["kind"] == "pick_student" and "tutor/source" in msg.artifact
    assert json.loads(msg.content)["students"]


def test_lc_tools_drop_none_args(ro):
    msg = lc(ro)["student_mistakes"].invoke(
        {
            "name": "student_mistakes",
            "args": {"code": "HS-01", "since": None, "kind": None, "kc": None},
            "id": "t2",
            "type": "tool_call",
        }  # fmt: skip
    )
    assert json.loads(msg.content)["code"] == "HS-01"


def test_lc_tools_error_flag_in_artifact(ro):
    msg = lc(ro)["student_profile"].invoke(
        {"name": "student_profile", "args": {"code": "HS-99"}, "id": "e1", "type": "tool_call"}
    )
    assert msg.artifact["tutor/error"] is True and "error" in json.loads(msg.content)
