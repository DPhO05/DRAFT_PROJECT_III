# a03 · Bước 3: Trials & traces

- k = `--runs` của G1, mặc định 3.
- Trace: `run<k>.jsonl` của G1. Dòng của 03 có `agent` = `03`.
- Đề xuất của 03 ở cổng `gate_review` nằm trong khoá `proposals` của mỗi bài trong file kết quả: `step_idx`, `code`, và
  `verdict` của 04.
- Check "ổn định qua các lần": `metrics.stability` cho `pass_k`: tỉ lệ bài có bước sai đầu tiên đúng ở mọi run. Bài
  thiếu ở một run (luồng hỏng) tính là trượt.
