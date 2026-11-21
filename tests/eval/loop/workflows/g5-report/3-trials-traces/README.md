# G5 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3.
- Trace: `run<k>.jsonl` trong `--traces`, mặc định `data/eval/traces/<stamp>_g5/`. Dòng của 09 có `graph` là G5.
- Khoá `reports` của file kết quả giữ bản nháp ở cổng, cùng dạng với 09 (`agents._report_row`), thêm `gate` và
  `report_rows`.
- Thread hỏng được ghi vào `errors`: `tests/eval/test_agents.py::test_g5_failed_thread_is_an_error`.
- Check "ổn định qua các lần": pass^k qua `metrics.tally`.
