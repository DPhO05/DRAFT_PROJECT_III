# a08 · Bước 3: Trials & traces

- k = 1: `run.TARGETS` đặt `runs` = 1 cho 08. Code tất định, chạy lại cho cùng kết quả, nên thêm trial không cho thêm thông tin.
- Không có trace `llm.jsonl`: 08 không gọi model. `calls.logged` là 0.
- File kết quả `<created>_08.json` trong `--out`. Mỗi task có `refs` (bài được chọn), `warnings`, `relevant`, `must_not`.
- Một câu tìm bị lỗi (`ValueError`, `KeyError`, `OperationalError` trong công cụ) được ghi vào `errors` và bị bỏ khỏi trung bình recall@5.
  Test: `tests/eval/test_components.py::test_08_failed_search_is_an_error_not_a_zero`.
- Check "ổn định qua các lần": đúng theo cấu tạo, vì không có phần ngẫu nhiên.
