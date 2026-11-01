"""Tools agent 00 can call (P6): API definitions and the runner. Read-only; students go by code only."""

import copy
import json
import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from tutor.services import search, students

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
    data: object = None  # the full result, for the number check


@dataclass
class Starters:
    """Writes the tools may start; each calls the same function as the matching API route (C-38)."""

    start_grading: Callable[[int, str, str], dict]
    start_bank_import: Callable[[str], dict]
    propose_worksheet: Callable[[int, str, list[dict], str | None, list[str]], dict]
    add_to_worksheet: Callable[[str, list[str]], dict]


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
]

LABELS = {
    "find_problems": "tìm bài theo mã",
    "search_problems": "tìm trong ngân hàng bài",
    "list_students": "danh sách học sinh",
    "student_profile": "hồ sơ học sinh",
    "student_mistakes": "lỗi đã duyệt",
    "compare_students": "so sánh học sinh",
}


_REQUIRED = {t["name"]: t["input_schema"]["required"] for t in TOOLS}


def tool_defs(codes: list[str]) -> list[dict]:
    """TOOLS with the `kind` enum filled from the error codes in use."""
    defs = copy.deepcopy(TOOLS)
    for d in defs:
        if kind := d["input_schema"]["properties"].get("kind"):
            kind["enum"] = list(codes)
    return defs


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
        return Outcome(
            _content(result, trim), label=LABELS[name], source=source, summary=summary, card=card, data=result
        )

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
