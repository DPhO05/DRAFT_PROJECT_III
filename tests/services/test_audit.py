"""P6-T06: number check — a number in the answer that no tool result holds is flagged (pure, no DB)."""

import json

from tutor.services.audit import known_numbers, unverified, values


def test_values():
    assert values("0,5") == {0.5}
    assert values("0.5") == {0.5}
    assert values("1.000") == {1000.0}
    assert values("1.000,5") == {1000.5}
    assert values("40%") == {40.0, 0.4}


def test_known_numbers_from_tool_json_and_dates():
    blob = json.dumps({"day": "2026-10-07", "ratio": 0.125, "ids": [3, 4], "pct": "40%"}, separators=(",", ":"))
    assert known_numbers([blob]) >= {2026.0, 10.0, 7.0, 0.125, 3.0, 4.0, 40.0, 0.4}


def test_count_matches():
    assert unverified("An sai 3 lần.", {3.0}) == []
    assert unverified("An sai 3 lần.", {2.0}) == [{"sentence": "An sai 3 lần.", "numbers": ["3"]}]


def test_invented_count():
    flagged = unverified("An sai 5 lần.", known_numbers(['{"count":3}']))
    assert flagged == [{"sentence": "An sai 5 lần.", "numbers": ["5"]}]


def test_comma_decimal():
    assert unverified("Điểm 0,5 ý.", {0.5}) == []
    assert unverified("Điểm 1.000 ý.", {1000.0}) == []


def test_percent():
    assert unverified("Đúng 40% số bài.", {0.4}) == []
    assert unverified("Đúng 40% số bài.", {40.0}) == []
    assert unverified("Đúng 40% số bài.", {3.0})[0]["numbers"] == ["40%"]


def test_fraction_parts():
    assert unverified("Khoảng 3/4 số bài.", {3.0}) == [{"sentence": "Khoảng 3/4 số bài.", "numbers": ["3/4"]}]
    assert unverified("Được 6,5/10 điểm.", {6.5, 10.0}) == []


def test_ignored_spans():
    known = known_numbers(["2026-10-07"])
    for text in (
        "Buổi ngày 07/10.",
        "Làm bài 9DS-PT2-002 trước.",
        "Gửi HS-01 nhé.",
        "Giải $x^2 - 5x + 6 = 0$ xem.",
        "1. Bài đầu",
        "Cho $$a. 12 b$$ thử.",
    ):
        assert unverified(text, known) == [], text


def test_list_marker_only_at_line_start():
    assert unverified("1. Bài đầu\n2) Bài hai", set()) == []
    assert unverified("Làm 2. bài", set())[0]["numbers"] == ["2"]


def test_sentence_split():
    text = "An sai 3 lần. Minh sai 9 lần!\n\nCòn lại ổn."
    assert unverified(text, {3.0}) == [{"sentence": "Minh sai 9 lần!", "numbers": ["9"]}]


def test_joined_api_calls_split_on_blank_line():
    text = "Đã tra HS-01.\n\nAn sai 7 lần."
    assert unverified(text, set()) == [{"sentence": "An sai 7 lần.", "numbers": ["7"]}]


def test_repeated_number_listed_once():
    assert unverified("Sai 5 rồi lại 5.", set())[0]["numbers"] == ["5"]


def test_codes_in_tool_text_do_not_launder_counts():
    known = known_numbers(['{"code":"HS-05","count":3,"ref":"9DS-PT2-012","kc2":1}'])
    assert known == {3.0, 1.0}
    assert unverified("HS-05 sai 5 lần.", known) == [{"sentence": "HS-05 sai 5 lần.", "numbers": ["5"]}]
    assert unverified("Làm 12 bài.", known)[0]["numbers"] == ["12"]


def test_iso_timestamp_and_class_name_keep_their_numbers():
    known = known_numbers(['{"created_at":"2026-10-07T14:30:00Z","class":"10-A"}'])
    assert {2026.0, 10.0, 7.0, 14.0, 30.0} <= known
    assert unverified("Ngày 7/10/2026 lúc 14:30.", known) == []


def test_scale_in_key_name_is_known():
    known = known_numbers(['{"score_10":6.5}'])
    assert known == {6.5, 10.0}
    assert unverified("Được 6,5/10 điểm.", known) == []
