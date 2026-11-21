# a03 · Bước 3: Trials & traces

- k = `--runs` của G1, mặc định 3.
- Trace: `run<k>.jsonl` của G1. Dòng của 03 có `agent` = `03`.
- Đề xuất của 03 ở cổng `gate_review` nằm trong khoá `proposals` của mỗi bài trong file kết quả: `step_idx`, `code`, và
  `verdict` của 04.
- Check "ổn định qua các lần": `metrics.stability.pass_k`: tỉ lệ bài có bước sai đầu tiên đúng ở mọi run. Bài
  thiếu ở một run (luồng hỏng) tính là trượt. Scorecard đọc `metrics.pass_k` từ `metrics.tally`: xem
  `tests/eval/loop/workflows/g1-session/3-trials-traces/README.md`.
- Trạng thái check: chưa đạt. Chưa đo với model thật; model giả (`--backend fake`) luôn cho pass^k = 1.000.
  Chạy thật là `--backend real --yes` hoặc `--suite`; chưa có lần chạy nào.
- Số thật duy nhất của 03: lần chạy thật 2026-11-04 trên `s01.tex` và `s04.tex` cho pass^3 = 0.333 (design mục 1.3).
