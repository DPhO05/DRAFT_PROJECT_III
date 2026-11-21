# a09 · Bước 2: Environment

## Dùng chung

- `agents.trials`: mỗi run một thư mục `work/run<k>`, `tutor.db` mới, `assistant_fix.world`.
- Backend dựng một lần ở run 1. Mỗi run có `llm.jsonl` riêng.

## Riêng cho 09

`agents._report_09` dựng từng kỳ:

- DB mở chỉ đọc. `facts.report_facts` tính số liệu của kỳ, với `low_pass_rate` của task hoặc của settings.
- `CallContext` lấy từ `session.call_context` với `graph` là G5, như app. Bản đồ che tên có mọi học sinh.
- Gọi `reporter.run` một mình, không chạy graph G5. G5 có target riêng: `tests/eval/loop/workflows/g5-report/README.md`.

## Check "sạch, không rò"

- `tests/eval/test_agents.py::test_09_masks_every_full_name`.
- `tests/eval/test_agents.py::test_09_a_failed_period_keeps_its_leak_rows`: kỳ hỏng vẫn được đếm rò tên.
- 09 không ghi DB, nên các kỳ trong một run không ảnh hưởng nhau.
