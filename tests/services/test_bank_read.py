"""P5-T02: read labels and rubric v1 from a bank .tex."""

from pathlib import Path

import pytest

from tutor.services import bank

TEX = (Path(__file__).resolve().parents[1] / "fixtures" / "bank" / "import-mix.tex").read_text("utf-8")
KC = {"8DS-HSBN-01": 1, "8DS-HSBN-02": 2, "8DS-HSBN-03": 3, "8DS-PT1-01": 4}
P1 = "Thay $x = x_0$ vào công thức $f(x) = 4x - 1$ rồi thực hiện phép tính."


def test_read_bank_labels():
    items = bank.read_bank(TEX, KC)
    assert len(items) == 8
    a = items[0]
    assert (a.ref, a.invalid, a.unknown_label) == ("8DS-NEW-001", None, False)
    assert a.tags == [(2, 1, P1)]
    assert (a.delta, a.needs) == (-0.6, [])
    assert [r["item_id"] for r in a.rubric_items] == ["r1", "r2"]
    assert a.rubric_items[0]["text"] == P1
    assert "Đáp số" in a.rubric_items[1]["text"]
    assert a.statement.startswith("Cho hàm số") and a.solution.startswith(P1)


def test_read_bank_missing_labels():
    items = bank.read_bank(TEX, KC)
    b = items[1]
    assert (b.needs, b.tags, b.delta) == (["kc", "level"], [], None)
    assert "đồ thị" in b.statement and "đèn lồng" in b.statement
    d = items[3]
    assert d.needs == ["level"] and d.delta is None
    assert [(k, i) for k, i, _ in d.tags] == [(1, 1), (3, 1)]
    assert len(d.rubric_items) == 1 and d.rubric_items[0]["text"] == d.tags[0][2]


def test_read_bank_unknown_label():
    c = bank.read_bank(TEX, KC)[2]
    assert (c.unknown_label, c.needs, c.delta, c.tags) == (True, ["kc"], 0.6, [])


def test_read_bank_invalid():
    items = bank.read_bank(TEX, KC)
    assert [i.invalid for i in items] == [None] * 5 + ["thiếu mã bài", "thiếu lời giải", "trùng mã trong file"]
    assert items[6].solution == "" and items[6].rubric_items == [] and items[6].tags == []


def test_read_bank_empty_ref():
    one = "\\begin{problem}%s\nĐề.\n\\begin{solution}\nGiải.\n\\end{solution}\n\\end{problem}\n"
    items = bank.read_bank((one % "[]") + (one % "[ ]"), KC)
    assert [i.invalid for i in items] == ["thiếu mã bài"] * 2


@pytest.mark.parametrize("bad", ["7", "abc", "0", ""])
def test_read_bank_bad_level_label(bad):
    tex = TEX.replace("% do_kho_du_kien: 2", f"% do_kho_du_kien: {bad}")
    a = bank.read_bank(tex, KC)[0]
    assert a.delta is None and "level" in a.needs


def test_level_delta():
    assert [bank.level_delta(w) for w in ("dễ", "vừa", "khó")] == [-0.6, 0.0, 0.6]
    assert bank.level_delta(None) is None
    with pytest.raises(ValueError):
        bank.level_delta("rất khó")


def test_rubric_items():
    got = bank.rubric_items([{"text": "a", "points": 2}, {"text": "b", "points": 0.5}])
    assert got == [{"item_id": "r1", "text": "a", "points": 2}, {"item_id": "r2", "text": "b", "points": 0.5}]
    for bad in (
        [],
        None,
        "x",
        ["x"],
        [{"text": " ", "points": 1}],
        [{"points": 1}],
        [{"text": "a"}],
        [{"text": "a", "points": 0}],
        [{"text": "a", "points": -1}],
        [{"text": "a", "points": "1"}],
        [{"text": "a", "points": True}],
    ):
        with pytest.raises(ValueError):
            bank.rubric_items(bad)


def test_rubric_v1():
    assert bank.rubric_v1(["a"]) == [{"item_id": "r1", "text": "a", "points": 1}]
    assert [r["text"] for r in bank.rubric_v1(["a", "b", "c"])] == ["a", "b\n\nc"]
