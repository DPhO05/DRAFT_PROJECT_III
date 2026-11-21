# a09 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 09>.json`.
- Khoá `per_run`: `metrics.score_09`: `n_reports`, `draft_flagged_pct`, `dropped_pct`, `passed`, `flags`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `09-dev` với chỉ số chính `dropped_pct`, `name_leaks`.

## Check "khớp production"

Chưa có:

- Task 21: `report_flagged_rate` từ khoá `audit` của báo cáo thật, ghi vào `production.json`.
- Task 22: sàn `dropped_pct` = 0 và luật không tụt.
