# G5 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 09>.json`.
- Khoá `per_run`: `metrics.score_09` của bản nháp. Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls` qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `g5-dev` với chỉ số chính `dropped_pct`, `name_leaks`.

## Check "khớp production"

Chưa có. Task 21 đọc khoá `audit` của báo cáo thật: `writer` là bản nháp của 09, `approved` là bản gia sư duyệt.
