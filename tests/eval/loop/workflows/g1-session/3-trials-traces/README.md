# G1 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3. Mỗi run nộp mọi file của bộ, theo thứ tự.
- Một file hỏng (thread `failed`, hết thời gian) được ghi vào `errors`. Các bài của file đó tính là thiếu ở run đó.

## Trace

| ở đâu | nội dung |
|---|---|
| `run<k>.jsonl` trong `--traces`, mặc định `data/eval/traces/<stamp>_g1/` | mọi lời gọi 01, 02, 03, 04 của run |
| khoá `problems` của file kết quả | mỗi run, mỗi `<file>#<seq>`: `labels`, `proposals` ở cổng, `items` của 02 |

- `proposals` lấy từ state ở cổng `gate_review` (`runner.Runner.state`): bước, mã lỗi và verdict của 04.
- Test: `tests/eval/test_harness.py::test_traces_are_kept_per_run`.

## Check "ổn định qua các lần"

- `metrics.stability`: `pass_k` theo bước sai đầu tiên, `items_changed_pct` cho 02.
- File kết quả có hai `pass_k`. `metrics.stability.pass_k` chia cho bài xuất hiện ở ít nhất một run. `metrics.pass_k` lấy từ
  `metrics.tally`, có mọi khoá của nhãn. Scorecard đọc `metrics.pass_k`. Hai số khác nhau khi một file hỏng ở mọi run.
- Lần chạy thật 2026-11-04 trên `s01.tex` và `s04.tex` cho pass^3 = 0.333 và 48.9 % mục rubric đổi điểm (design mục 1.3).
  Chưa có lần chạy thật nào sau đó.
