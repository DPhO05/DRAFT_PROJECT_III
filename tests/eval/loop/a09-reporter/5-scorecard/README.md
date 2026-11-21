# a09 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 09>.json`.
- Khoá `per_run`: `metrics.score_09`: `n_reports`, `draft_flagged_pct`, `dropped_pct`, `passed`, `flags`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: qua `agents.summarize`.
- Với `--judge`, khoá `extra`: `faithfulness`, `judge_unknown`, `judge_errors`.
- `tests/eval/scorecard.py` in dòng `09-dev` với chỉ số chính `dropped_pct`, `name_leaks`.

## Cổng

- `tests/eval/gate.py`: `09-dev` `dropped_pct` = 0; `faithfulness` ≥ 0.95 chờ `judge_trusted`. Luật không tụt cho `passed`.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 09 với oracle và judge giả.
- Lỗi cần sửa: chạy với `--only` (suite `compact`: 3 trong 6 kỳ) tạo dòng `09-dev` một phần, thay dòng đầy đủ, và gate không phân biệt
  được. Đang sửa trong review cuối.

## Check "khớp production"

- `harvest.reports` đọc khoá `audit` của báo cáo thật (`writer` là bản nháp của 09, `approved` là bản gia sư duyệt) và ghi
  `report_flagged_rate` vào `production.json`. Chưa chạy trên dữ liệu thật, nên chưa có số.
