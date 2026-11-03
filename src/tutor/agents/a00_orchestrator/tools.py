"""Tools agent 00 can call (P6): API definitions and the runner. Students go by code only.

Writes are limited to what `Starters` does: G1's session row (①) and drafts that wait for a button (C-39)."""

import copy
import json
import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from tutor.agents.a08_recommender import select
from tutor.config import student_code
from tutor.services import facts, search, students

log = logging.getLogger("tutor")
MAX_CONTENT = 6000  # chars of tool result sent to the model


@dataclass
class Outcome:
    content: str  # JSON for the model, at most MAX_CONTENT chars
    is_error: bool = False
    label: str = ""
    source: str | None = None
    summary: str = ""
    card: dict | None = None


@dataclass
class Starters:
    """Writes the tools may start; each calls the same function as the matching API route (C-38)."""

    start_grading: Callable[[int, str, str], dict]
    start_bank_import: Callable[[str], dict]
    propose_worksheet: Callable[[int, str, list[dict], str | None, list[str]], dict]
    add_to_worksheet: Callable[[str, list[str]], dict]
    start_report: Callable[[int, str, str], dict] | None = None


def _tool(name: str, description: str, props: dict | None = None, required: tuple[str, ...] = ()) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": props or {},
            "required": list(required),
            "additionalProperties": False,
        },
    }


_CODE = {"type": "string", "description": "Mã học sinh, vd HS-01"}
_KIND = {"type": "string", "description": "Loại lỗi, chọn trong danh mục"}
_KC = {"type": "integer", "description": "Số thứ tự kỹ năng (kc_id) trong danh mục"}
_LEVEL = {"type": "string", "enum": list(search.LEVELS)}
_DAY = "dạng yyyy-mm-dd"

TOOLS: list[dict] = [
    _tool(
        "find_problems",
        "Tìm bài trong ngân hàng theo mã bài. Cho 1 đến 10 mã.",
        {"refs": {"type": "array", "items": {"type": "string"}, "description": "Mã bài, vd 9DS-PT2-001"}},
        ("refs",),
    ),
    _tool(
        "search_problems",
        "Tìm bài trong ngân hàng theo chữ trong đề, có thể lọc theo kỹ năng, lớp, mức bài.",
        {
            "text": {"type": "string", "description": "Chữ cần tìm trong đề hoặc mã bài"},
            "kc": _KC,
            "grade": {"type": "integer", "description": "Lớp"},
            "level_min": {**_LEVEL, "description": "Mức thấp nhất"},
            "level_max": {**_LEVEL, "description": "Mức cao nhất"},
            "limit": {"type": "integer", "description": "Số bài tối đa, từ 1 đến 10"},
        },
        ("text",),
    ),
    _tool("list_students", "Danh sách học sinh chưa lưu trữ, kèm số buổi và buổi gần nhất."),
    _tool(
        "student_profile",
        "Hồ sơ một học sinh: số kỹ năng theo mức, từng kỹ năng, lỗi lặp chưa hết, 5 buổi gần nhất.",
        {"code": _CODE},
        ("code",),
    ),
    _tool(
        "student_mistakes",
        "Lỗi thầy/cô đã duyệt của một học sinh: tổng, theo loại, và danh sách. Lọc theo ngày, loại lỗi, kỹ năng.",
        {
            "code": _CODE,
            "since": {"type": "string", "description": "Từ ngày (gồm cả ngày này), dạng yyyy-mm-dd"},
            "kind": _KIND,
            "kc": _KC,
        },
        ("code",),
    ),
    _tool(
        "compare_students",
        "So sánh các học sinh chưa lưu trữ theo số lỗi đã duyệt (mistakes), số lần lỗi lặp chưa hết"
        " (open_repeats), hoặc mức một kỹ năng (level, cần kc). Xếp từ nhiều nhất / giỏi nhất.",
        {
            "metric": {"type": "string", "enum": list(students.METRICS)},
            "kc": _KC,
            "kind": _KIND,
        },
        ("metric",),
    ),
    _tool(
        "rank_problems",
        "Chọn bài cho phiếu của một học sinh theo tiến bộ: ôn lỗi lặp, vừa sức, thử thách."
        " Chỉ xếp hạng, không lưu gì. Bỏ trống n và ratios thì theo cài đặt.",
        {
            "code": _CODE,
            "n": {"type": "integer", "description": "Số bài, từ 1 đến 12"},
            "ratios": {
                "type": "object",
                "description": "Tỉ lệ ôn / vừa sức / thử thách, mỗi số từ 0 đến 1",
                "properties": {k: {"type": "number"} for k in select.BUCKETS},
                "required": list(select.BUCKETS),
                "additionalProperties": False,
            },
        },
        ("code",),
    ),
    _tool(
        "start_grading",
        "Bắt đầu chấm bài của một học sinh từ file .tex thầy/cô đã gửi. Chỉ bắt đầu, chưa lưu kết quả:"
        " thầy/cô xem thẻ chấm bài rồi bấm Lưu kết quả.",
        {
            "code": _CODE,
            "file": {"type": "string", "description": "Tên file .tex đã gửi"},
            "held_on": {"type": "string", "description": f"Ngày học, {_DAY}"},
        },
        ("code", "file", "held_on"),
    ),
    _tool(
        "start_bank_import",
        "Đọc một file .tex bài mới để thêm vào ngân hàng bài. Chỉ đọc, chưa lưu bài nào:"
        " thầy/cô chọn kỹ năng và lưu ở tab Ngân hàng bài.",
        {"file": {"type": "string", "description": "Tên file .tex bài mới"}},
        ("file",),
    ),
    _tool(
        "propose_worksheet",
        "Soạn phiếu bài nháp cho một học sinh từ các mã bài đã chọn, thay phiếu nháp cũ của học sinh đó."
        " Chỉ là nháp: thầy/cô bấm Tạo phiếu để lưu.",
        {
            "code": _CODE,
            "for_date": {"type": "string", "description": f"Ngày của phiếu, {_DAY}"},
            "refs": {"type": "array", "items": {"type": "string"}, "description": "Mã bài theo thứ tự trên phiếu"},
            "note": {"type": "string", "description": "Ghi chú cho phiếu"},
        },
        ("code", "for_date", "refs"),
    ),
    _tool(
        "start_report",
        "Bắt đầu làm báo cáo cho phụ huynh về một học sinh trong một kỳ, từ các buổi đã duyệt."
        " Chỉ bắt đầu, chưa lưu: thầy/cô sửa câu và bấm Duyệt báo cáo ở tab Báo cáo."
        " period_start: ngày học (day), thứ Hai (week), ngày 1 (month), dạng yyyy-mm-dd.",
        {
            "code": _CODE,
            "period_kind": {"type": "string", "enum": list(facts.KINDS)},
            "period_start": {"type": "string", "description": f"Ngày bắt đầu kỳ, {_DAY}"},
        },
        ("code", "period_kind", "period_start"),
    ),
]

LABELS = {
    "find_problems": "tìm bài theo mã",
    "search_problems": "tìm trong ngân hàng bài",
    "list_students": "danh sách học sinh",
    "student_profile": "hồ sơ học sinh",
    "student_mistakes": "lỗi đã duyệt",
    "compare_students": "so sánh học sinh",
    "rank_problems": "chọn bài theo tiến bộ",
    "start_grading": "bắt đầu chấm bài",
    "start_bank_import": "đọc file bài mới",
    "propose_worksheet": "soạn phiếu nháp",
    "start_report": "bắt đầu báo cáo",
}


_REQUIRED = {t["name"]: t["input_schema"]["required"] for t in TOOLS}


def tool_defs(codes: list[str]) -> list[dict]:
    """TOOLS with the `kind` enum filled from the error codes in use."""
    defs = copy.deepcopy(TOOLS)
    for d in defs:
        if kind := d["input_schema"]["properties"].get("kind"):
            kind["enum"] = list(codes)
    return defs


def meta(out: Outcome) -> dict:
    """UI fields of an outcome as MCP `_meta` (R6), empty ones left out."""
    m = {"tutor/source": out.source, "tutor/summary": out.summary, "tutor/card": out.card}
    return {k: v for k, v in m.items() if v}


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _content(result: dict, trim: tuple[str, ...] = ()) -> str:
    """JSON for the model; over the cap, the `trim` lists lose their last items and `omitted` counts them."""
    out = {k: list(v) if k in trim else v for k, v in result.items()}
    omitted: dict[str, int] = {}
    text = _dumps(out)
    for key in trim:
        while len(text) > MAX_CONTENT and out[key]:
            out[key].pop()
            omitted[key] = omitted.get(key, 0) + 1
            out["omitted"] = omitted
            text = _dumps(out)
    return text


def _problem_row(p: dict) -> dict:
    return {
        "ref": p["ref"],
        "grade": p["grade"],
        "level": p["level"],
        "kcs": [k["name"] for k in p["kcs"]],
        "has_rubric": p["has_rubric"],
        "statement_latex": p["statement_latex"],
    }


class Toolbox:
    def __init__(self, conn, *, settings: dict, today: date, text: str, starters: Starters | None = None):
        self.conn, self.settings, self.today, self.text, self.starters = conn, settings, today, text, starters
        self.outcomes: list[tuple[str, Outcome]] = []
        self.ranked: list[dict] = []  # items of the latest rank_problems, for propose_worksheet (R18)
        self.rank_student, self.rank_warnings = 0, []  # whose sheet that was, and its warnings

    def run(self, name: str, args: dict) -> Outcome:
        """Strict schema makes bad input rare, not impossible: any bad call becomes a tool error the model can retry."""
        try:
            if name not in LABELS:
                raise ValueError(f"Không có công cụ {name}")
            if missing := [k for k in _REQUIRED[name] if k not in args]:
                raise ValueError(f"Thiếu tham số {missing[0]}")
            out = getattr(self, f"tool_{name}")(args)
        except ValueError as e:
            out = self._error(name, str(e))
        except (KeyError, TypeError):
            log.exception("tool %s", name)  # name only: arguments can hold student text (C-40)
            out = self._error(name, "Tham số công cụ không đúng")
        except sqlite3.OperationalError:
            log.warning("tool %s: DB busy", name, exc_info=True)
            out = self._error(name, "Cơ sở dữ liệu đang bận, thử lại sau")
        self.outcomes.append((name, out))
        return out

    @staticmethod
    def _error(name: str, message: str) -> Outcome:
        return Outcome(_dumps({"error": message}), is_error=True, label=LABELS.get(name, ""))

    def _out(self, name: str, result: dict, *, source: str, summary: str, card=None, trim=()) -> Outcome:
        return Outcome(_content(result, trim), label=LABELS[name], source=source, summary=summary, card=card)

    def _problem_card(self, items: list[dict], missing: list[str]) -> dict:
        steps = search.solution_steps(self.conn, [p["id"] for p in items])
        return {
            "kind": "problem",
            "problems": [p | {"solution_steps": steps[p["id"]]} for p in items],
            "missing": missing,
            "added_to": None,
        }

    def tool_find_problems(self, a: dict) -> Outcome:
        refs = a["refs"]
        if not 1 <= len(refs) <= 10:
            raise ValueError("Cho 1 đến 10 mã bài")
        items = search.find_problems(self.conn, refs)
        found = {p["ref"].lower() for p in items}
        missing = [r for r in refs if r.lower() not in found]
        return self._out(
            "find_problems",
            {"problems": [_problem_row(p) for p in items], "missing": missing},
            source="ngân hàng bài (theo mã)",
            summary=f"find_problems: {len(items)} bài" + (f", không thấy {len(missing)}" if missing else ""),
            card=self._problem_card(items, missing),
            trim=("problems",),
        )

    def tool_search_problems(self, a: dict) -> Outcome:
        lo, hi, limit = a.get("level_min"), a.get("level_max"), a.get("limit")
        if {lo, hi} - {None, *search.LEVELS}:
            raise ValueError("Mức bài chỉ có dễ / vừa / khó")
        if limit is not None and not 1 <= limit <= 10:
            raise ValueError("Số bài tối đa từ 1 đến 10")
        items = search.search_problems(
            self.conn, a["text"], kc=a.get("kc"), grade=a.get("grade"), level_min=lo, level_max=hi, limit=limit or 10
        )
        bank = search.browse(self.conn, limit=0)["total"]
        return self._out(
            "search_problems",
            {"n": len(items), "problems": [_problem_row(p) for p in items]},
            source=f"tìm trong ngân hàng bài ({bank} bài)",
            summary=f"search_problems: {len(items)} bài",
            card=self._problem_card(items, []),
            trim=("problems",),
        )

    def tool_list_students(self, a: dict) -> Outcome:
        rows = students.list_students(self.conn)
        picked = re.search(r"@HS-\d+", self.text, re.IGNORECASE)
        return self._out(
            "list_students",
            {"students": rows},
            source="danh sách học sinh",
            summary=f"list_students: {len(rows)} học sinh",
            card=None if picked else {"kind": "pick_student", "text": self.text},
            trim=("students",),
        )

    def tool_student_profile(self, a: dict) -> Outcome:
        p = students.profile(self.conn, students.student_id(self.conn, a["code"]))
        counts = ", ".join(f"{n} {level}" for level, n in p["counts"].items())
        return self._out(
            "student_profile",
            p,
            source=f"hồ sơ của {p['code']}",
            summary=f"student_profile {p['code']}: {counts}; {len(p['repeats'])} lỗi lặp",
            trim=("skills", "repeats", "sessions"),
        )

    def tool_student_mistakes(self, a: dict) -> Outcome:
        m = students.mistakes(
            self.conn,
            students.student_id(self.conn, a["code"]),
            since=a.get("since"),
            kind=a.get("kind"),
            kc=a.get("kc"),
        )
        since = f" từ {date.fromisoformat(m['since']):%d/%m/%Y}" if m["since"] else ""
        return self._out(
            "student_mistakes",
            m,
            source=f"lỗi đã duyệt của {m['code']}{since}",
            summary=f"student_mistakes {m['code']}: {m['total']} lỗi",
            trim=("items", "by_kind"),
        )

    def tool_compare_students(self, a: dict) -> Outcome:
        c = students.compare(self.conn, a["metric"], kc=a.get("kc"), kind=a.get("kind"))
        return self._out(
            "compare_students",
            c,
            source=f"so sánh lỗi đã duyệt của {c['n_students']} học sinh",
            summary=f"compare_students {c['metric']}: {c['n_students']} học sinh, {len(c['rows'])} có số liệu",
            trim=("rows",),
        )

    def tool_rank_problems(self, a: dict) -> Outcome:
        reco = self.settings["reco"]
        n = reco["n_problems"] if a.get("n") is None else a["n"]
        if not 1 <= n <= 12:
            raise ValueError("Số bài từ 1 đến 12")
        sid = students.student_id(self.conn, a["code"])
        r = select.rank_problems(self.conn, sid, n, reco=reco, today=self.today, ratios=a.get("ratios"))
        self.ranked, self.rank_student, self.rank_warnings = r["items"], sid, r["warnings"]
        items = [{k: v for k, v in i.items() if k != "statement_latex"} for i in r["items"]]
        c = r["counts"]
        return self._out(
            "rank_problems",
            {"n": len(items), "items": items, "counts": c, "warnings": r["warnings"]},
            source=f"gợi ý bài theo tiến bộ của {student_code(sid)}",
            summary=f"rank_problems {student_code(sid)}: {len(items)} bài ({c['review']} ôn, {c['zpd']} vừa sức,"
            f" {c['challenge']} thử thách)",
            trim=("items",),
        )

    def tool_start_grading(self, a: dict) -> Outcome:
        sid = students.student_id(self.conn, a["code"])
        code = student_code(sid)
        started = self.starters.start_grading(sid, a["file"], a["held_on"])
        day = date.fromisoformat(a["held_on"])
        return self._out(
            "start_grading",
            {"code": code, "held_on": a["held_on"], "status": started["status"]},
            source=f"chấm bài của {code}",
            summary=f"start_grading {code}: buổi {day:%d/%m/%Y}",
            card={"kind": "grading", "thread_id": started["thread_id"]},
        )

    def tool_start_bank_import(self, a: dict) -> Outcome:
        started = self.starters.start_bank_import(a["file"])
        return self._out(
            "start_bank_import",
            {"file": a["file"], "status": started["status"], "existing": started["existing"]},
            source=f"file bài mới {a['file']}",
            summary=f"start_bank_import: {a['file']}",
            card={
                "kind": "actions",
                "items": [{"label": "Mở Ngân hàng bài để chọn kỹ năng", "open": {"tab": "ngan-hang"}}],
            },
        )

    def tool_propose_worksheet(self, a: dict) -> Outcome:
        if not a["refs"]:
            raise ValueError("Cho ít nhất 1 mã bài")
        sid = students.student_id(self.conn, a["code"])
        code = student_code(sid)
        # reasons are the student's own: keep them only when the latest rank was for this student (R18)
        same = self.rank_student == sid
        ranked = {i["ref"].upper(): i for i in self.ranked} if same else {}
        items = []
        for ref in a["refs"]:
            ref = str(ref).strip().upper()
            hit = ranked.get(ref)
            items.append({"ref": ref, "bucket": hit["bucket"], "reason": hit["reason"]} if hit else {"ref": ref})
        made = self.starters.propose_worksheet(
            sid, a["for_date"], items, a.get("note"), self.rank_warnings if same else []
        )
        day = date.fromisoformat(a["for_date"])
        return self._out(
            "propose_worksheet",
            {
                "code": code,
                "for_date": a["for_date"],
                "n": len(made["added"]),
                "added": made["added"],
                "invalid": made["invalid"],
                "replaced_draft": made["existing"],
            },
            source=f"phiếu nháp cho {code}",
            summary=f"propose_worksheet {code}: {len(made['added'])} bài cho {day:%d/%m/%Y}",
            card={
                "kind": "worksheet",
                "thread_id": made["thread_id"],
                "added": made["added"],
                "invalid": made["invalid"],
            },
        )

    def tool_start_report(self, a: dict) -> Outcome:
        sid = students.student_id(self.conn, a["code"])
        code = student_code(sid)
        started = self.starters.start_report(sid, a["period_kind"], a["period_start"])
        return self._out(
            "start_report",
            {
                "code": code,
                "period_kind": a["period_kind"],
                "period_start": a["period_start"],
                "status": started["status"],
                "existing": started["existing"],
            },
            source=f"báo cáo của {code}",
            summary=f"start_report {code}: {a['period_kind']} {a['period_start']}",
            card={"kind": "report", "thread_id": started["thread_id"]},
        )
