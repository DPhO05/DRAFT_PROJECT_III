# a09 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 09>.json`.
- Khoá `per_run`: `metrics.score_09`: `n_reports`, `draft_flagged_pct`, `dropped_pct`, `passed`, `flags`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: qua `agents.summarize`.
- Với `--judge`, khoá `extra`: `faithfulness`, `judge_unknown`, `judge_errors`.
- `tests/eval/scorecard.py` in dòng `09-dev` với chỉ số chính `dropped_pct`, `name_leaks`.

## Cổng

- `tests/eval/gate.py`: `09-dev` `dropped_pct` = 0; `faithfulness` ≥ 0.95 chờ `judge_trusted`. Luật không tụt cho `passed`.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 09 với oracle và judge giả.
- Chạy với `--only` (suite `compact`: 3 trong 6 kỳ) ghi khoá `subset` vào file kết quả. Dòng một phần nằm cạnh dòng đầy đủ, bảng đánh dấu `*` sau số task (ví dụ `9*`). Sàn vẫn áp cho mọi dòng. `no_drop` chỉ so dòng cùng `set` và cùng `subset` với dòng baseline; không có thì in `BỎ QUA` với giới hạn `khác tập task`.

## Check "khớp production"

- `harvest.reports` đọc khoá `audit` của báo cáo thật (`writer` là bản nháp của 09, `approved` là bản gia sư duyệt) và ghi
  `report_flagged_rate` vào `production.json`. Chưa chạy trên dữ liệu thật, nên chưa có số.
