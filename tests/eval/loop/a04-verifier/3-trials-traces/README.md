# a04 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3. Mỗi run chạy 12 kết luận theo thứ tự.
- Trace: `run<k>.jsonl` trong thư mục `--traces`, mặc định `data/eval/traces/<stamp>_04/`. Một dòng một lời gọi 04.
- `components._verify_04` đếm `model_calls` bằng số dòng log mới của task.
- Check "ổn định qua các lần": pass^k qua `metrics.tally`. Kết luận trượt ở một run thì trượt pass^k.
