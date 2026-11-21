# a04 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 04>.json`.
- Khoá `per_run`: `metrics.score_04`: `n_tasks`, `accuracy`, `recall_disagree`, `empty`, `confusion`, `passed`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `04-dev` với chỉ số chính `accuracy`, `recall_disagree`, `name_leaks`. Khoá `confusion` là dict
  nên không vào cột số.

## Check "khớp production"

Chưa có. Task 22 thêm sàn `recall_disagree` ≥ 0.80 và luật không tụt cho `accuracy`.
