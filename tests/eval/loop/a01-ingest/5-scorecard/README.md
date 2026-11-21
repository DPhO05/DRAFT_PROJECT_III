# a01 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 01>.json`.
- Khoá `per_run`: `metrics.score_01`: `n_tasks`, `hit_at_1`, `hit_at_3`, `mrr`, `low_match_precision`, `passed`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: như mọi target, qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `01-dev` với chỉ số chính `hit_at_1`, `mrr`, `name_leaks`.

## Check "khớp production"

Chưa có. Task 22 thêm sàn `hit_at_1` ≥ 0.90 và luật không tụt cho `hit_at_1`, `hit_at_3`, `mrr`.
