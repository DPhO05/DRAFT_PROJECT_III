# a02 · Bước 2: Environment

Môi trường của G1, dựng trong `run.evaluate`. Xem `tests/eval/loop/workflows/g1-session/2-environment/README.md`.

- Mỗi run: thư mục `work/run<k>/data`, `tutor.db` mới, seed ngân hàng `data/dummy/bank`, file bài chép vào `inbox`.
- 02 nhận bước, đề và rubric làm đối số của `grader.grade` (node `grade` trong `session._lane`), tên đã che.
- `CallContext` (`session.call_context`) chỉ mang graph, thread, buổi, mã học sinh và bản đồ che tên.
- Riêng cho việc chấm: không có. Không có môi trường gọi `grader.grade` một mình.

## Riêng cho `02r`

`components._draft_02r` dựng một task:

- `agents.trials`: mỗi run một thế giới mới `work/run<k>`, ngân hàng mẫu seed sẵn.
- Đề lấy từ DB bằng kết nối chỉ đọc (`repo.problem_detail`), qua mã bài của task.
- Gọi `grader.generate_rubric` một mình, không chạy G1. `CallContext` có `graph` là G1, `thread_id` là `eval-<id>` và bản đồ che tên
  của `components._redact`.

## Check "sạch, không rò"

- Dùng check của G1: `tests/eval/test_harness.py::test_each_run_starts_from_a_new_world` và
  `tests/eval/test_harness.py::test_labels_never_enter_the_trial_data`.
