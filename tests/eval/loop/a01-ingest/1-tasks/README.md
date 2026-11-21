# a01 · Bước 1: Tasks

- File: `tests/eval/tasks/ingest_01.json`, 10 task, `m1` đến `m10`. Đọc vào `components.TASKS_01`.
- Mọi task là synthetic. `m1` đến `m8` chép từ bài mẫu trong `tests/fixtures/submissions/`. `m9`, `m10` là bài viết thêm (hình
  tròn, xác suất).

| trường | nghĩa |
|---|---|
| `tex` | một bài nguyên văn, không có mã bài |
| `grade` | lớp của bài, gửi kèm cho 01 |
| `expect_ref` | mã đúng trong ngân hàng; `null` khi bài không có trong ngân hàng |

| task | nội dung |
|---|---|
| `m1` đến `m8` | bài có trong ngân hàng, đã bỏ mã; cả lớp 8 và lớp 9 |
| `m9`, `m10` | bài không có trong ngân hàng: phải có cờ `low_match` |

- Test: `tests/eval/test_components.py::test_01_tasks_are_wellformed`.
- Check "bao phủ cách dùng thật": chưa đạt. Bài thật của học sinh chưa có trong repo.
