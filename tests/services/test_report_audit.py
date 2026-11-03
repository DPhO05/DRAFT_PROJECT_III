"""P7-T03: report sentence audit (C-41, C-44): flags in order percent, no_fact, number, tone. Pure, no DB."""

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


def check(text, cited, low=False, need_fact=True):
    return check_sentence(text, cited, low=low, need_fact=need_fact)


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
    assert check("Ngày 07/10/2026 em học 2 buổi.", [F01]) is None
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


def test_flag_order():
    assert check("Em đúng 40% số bài.", [])["flag"] == "percent"  # before no_fact
    assert check("Em làm 7 bài.", [])["flag"] == "no_fact"  # before number
    assert check("Em làm rất tốt 7 bài.", [F02], low=True)["flag"] == "number"  # before tone


def test_number_words_and_codes():
    assert check("Em sai ở bài 9DS-PT2-002, $x^2 = 4$.", [F02]) is None
