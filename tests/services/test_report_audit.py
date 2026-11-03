"""P7-T03: report sentence audit (C-41, C-44): flags in order percent, no_fact, number, tone. Pure, no DB."""

import unicodedata
from datetime import date

from tutor.services.audit import PRAISE, check_sentence

F01 = {"fact_id": "F01", "kind": "sessions", "value": 2, "text": "Số buổi học: 2."}
F02 = {"fact_id": "F02", "kind": "problems", "value": 6, "text": "Số bài đã làm: 6."}
F03 = {
    "fact_id": "F03",
    "kind": "session",
    "value": {"score": 4, "max_score": 6, "score_10": 6.7, "mistakes": 2},
    "text": "Buổi 20/10: đạt 4 trong 6 ý, điểm 6,7 trên 10, 2 lỗi.",
}
ALL = [F01, F02, F03]
# October 2026 report: period bounds and one session on 20/10 (no day looks like a score such as 7/10)
DATES = [date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 20)]


def check(text, cited, low=False, need_fact=True, dates=DATES):
    return check_sentence(text, cited, low=low, need_fact=need_fact, dates=dates)


def test_wrong_number():
    assert check("Em làm 7 bài.", [F02]) == {
        "flag": "number",
        "why": "Số “7” không có trong dữ liệu đã duyệt.",
        "detail": "số 7 không khớp F02 = 6",
    }


def test_number_must_be_in_a_cited_fact():
    assert check("Em làm 6 bài.", [F01])["detail"] == "số 6 không khớp F01 = 2"
    assert check("Em làm 6 bài.", [F01, F02]) is None


def test_number_is_read_from_value_not_text():
    assert check("Em học 20 buổi.", [F03])["flag"] == "number"  # 20 is only in the date of F03's text


def test_every_wrong_number_is_listed():
    out = check("Em làm 7 bài trong 9 buổi.", [F01, F02])
    assert out["why"] == "Số “7”, “9” không có trong dữ liệu đã duyệt."
    assert out["detail"] == "số 7, 9 không khớp F01 = 2, F02 = 6"


def test_no_fact():
    out = check("Em học chăm.", [])
    assert out["flag"] == "no_fact"
    assert out["why"] == "Câu chưa dựa vào số liệu đã duyệt."
    assert check("Em học chăm.", ALL, need_fact=False) is None
    assert check("Em học chăm.", [], need_fact=False) is None


def test_percent():
    for cited in ([F02], [{"fact_id": "F04", "kind": "x", "value": 40, "text": "40"}]):  # even when 40 is in a fact
        out = check("Em đúng 40% số bài.", cited)
        assert out["flag"] == "percent"
        assert out["why"] == "Báo cáo cho phụ huynh không dùng phần trăm."


def test_right_and_dates():
    assert check("Buổi 20/10 em làm 6 bài.", [F02]) is None
    assert check("Ngày 07/10/2026 em học 2 buổi.", [F01], dates=[*DATES, date(2026, 10, 7)]) is None
    assert check("Buổi 20/10 em đạt 4 trong 6 ý, điểm 6,7 trên 10.", [F03]) is None


def test_tone():
    out = check("Em học rất tốt.", [F01], low=True)
    assert out["flag"] == "tone"
    assert out["why"] == "Câu khen hơi quá so với kết quả kỳ này."
    assert check("Em học rất tốt.", [F01], low=False) is None
    assert check("Tuyệt vời, em làm 6 bài.", [F02], low=True)["flag"] == "tone"  # case does not matter
    assert check("Em học chăm.", [F01], low=True) is None


def test_every_praise_word():
    assert PRAISE == ("xuất sắc", "tuyệt vời", "hoàn hảo", "rất tốt", "rất giỏi")
    for word in PRAISE:
        assert check(f"Em làm {word}.", [F01], low=True)["flag"] == "tone", word


def test_percent_in_words():
    for text in ("Em đúng 6 phần trăm số bài.", "Em đúng 6 Phần Trăm số bài."):
        out = check(text, [F02])
        assert out["flag"] == "percent" and out["why"] == "Báo cáo cho phụ huynh không dùng phần trăm."


def test_number_in_words():
    out = check("Em học ba buổi và làm bảy bài.", [F01, F02])  # sessions = 2, problems = 6: still not checked
    assert out["flag"] == "number"
    assert out["why"] == "Số viết bằng chữ (“bảy”): viết bằng chữ số để kiểm được."
    both = check("Em học hai buổi, làm Sáu bài.", [F01, F02], need_fact=False)
    assert both["why"] == "Số viết bằng chữ (“hai”, “Sáu”): viết bằng chữ số để kiểm được."
    for word in ("hai", "bốn", "sáu", "bảy", "tám", "chín", "mười", "mươi", "trăm"):
        assert check(f"Em làm {word} bài.", [F02])["flag"] == "number", word
    assert check(unicodedata.normalize("NFD", "Em làm bảy bài."), [F02])["flag"] == "number"  # typed with marks apart
    assert check("Em làm 6 bài.", [F02]) is None


def test_everyday_words_are_not_numbers():
    for text in ("Em làm một bài.", "Em làm ba bước.", "Năm nay em học chăm.", "Em đọc haiku.", "Em có chai nước."):
        assert check(text, [F02]) is None, text


def test_flag_order():
    assert check("Em đúng 40% số bài.", [])["flag"] == "percent"  # before no_fact
    assert check("Em làm 7 bài.", [])["flag"] == "no_fact"  # before number
    assert check("Em làm rất tốt 7 bài.", [F02], low=True)["flag"] == "number"  # before tone
    assert check("Em đúng sáu phần trăm số bài.", [])["flag"] == "percent"
    assert check("Em làm sáu bài.", [])["flag"] == "no_fact"
    assert check("Em làm rất tốt sáu bài.", [F02], low=True)["flag"] == "number"


def test_invented_fractions_are_flagged():
    for text, cited, need_fact in (
        ("Em đạt 7/10 điểm.", [F03], True),
        ("Em đạt 7/10 điểm.", [F02], True),
        ("Em làm đúng 8/10 bài.", [F02], True),
        ("Em làm đúng 5/6 bài.", [F02], True),
        ("Em đạt 45/99 ý.", [F03], True),
        ("Em đạt 9/10 điểm.", ALL, False),  # a tutor edit
    ):
        out = check(text, cited, need_fact=need_fact)
        assert out and out["flag"] == "number", text


def test_only_padded_dates_are_dates():
    day7 = [*DATES, date(2026, 10, 7)]
    assert check("Buổi 07/10 em làm 6 bài.", [F02], dates=day7) is None
    assert check("Em đạt 7/10 điểm.", [F03], dates=day7)["flag"] == "number"  # looks like 7 Oct, is a score
    assert check("Buổi 7/10 em làm 6 bài.", [F02], dates=day7)["flag"] == "number"  # unpadded: a warning, not a pass
    sep7 = [*DATES, date(2026, 9, 7)]
    assert check("Buổi 07/9 em làm 6 bài.", [F02], dates=sep7)["flag"] == "number"  # the month is padded too


def test_real_fraction_passes():
    assert check("Em đạt 4/6 ý.", [F03]) is None  # both parts are in F03


def test_invented_date_is_flagged():
    assert check("Buổi 25/10 em làm 6 bài.", [F02])["flag"] == "number"
    assert check("Buổi 20/10 em làm 6 bài.", [F02], dates=[])["flag"] == "number"  # not a day of this report
    assert check("Ngày 07/10/2026 em học 2 buổi.", [F01], dates=[date(2026, 10, 8)])["flag"] == "number"


def test_month_and_year():
    assert check("Trong tháng 10/2026, em học 2 buổi.", [F01]) is None
    assert check("Trong tháng 9/2026, em học 2 buổi.", [F01])["flag"] == "number"  # not the month of this report
    assert check("Trong tháng 10/2026, em học 2 buổi.", [F01], dates=[date(2026, 9, 1)])["flag"] == "number"


def test_date_pattern_does_not_cut_into_numbers():
    dec = {"fact_id": "F04", "kind": "score", "value": {"score_10": 8.5}, "text": "Điểm 8,5 trên 10."}
    day5 = [*DATES, date(2026, 10, 5)]
    assert check("Em đạt 8,5/10 điểm.", [dec], dates=day5) is None
    zero5 = {"fact_id": "F06", "kind": "score", "value": {"score_10": 8.05}, "text": "Điểm 8,05 trên 10."}
    assert check("Em đạt 8,05/10 điểm.", [zero5], dates=day5) is None  # "05/10" is a day but belongs to 8,05
    big = {"fact_id": "F05", "kind": "x", "value": [20, 105], "text": "20 105"}
    assert check("Em đạt 20/105 điểm.", [big]) is None  # "20/10" is a day but "105" is one number


def test_number_words_and_codes():
    assert check("Em sai ở bài 9DS-PT2-002, $x^2 = 4$.", [F02]) is None
