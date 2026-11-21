# a04 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 04>.json`.
- Khoá `per_run`: `metrics.score_04`: `n_tasks`, `accuracy`, `recall_disagree`, `empty`, `confusion`, `passed`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `04-dev` với chỉ số chính `accuracy`, `recall_disagree`, `name_leaks`. Khoá `confusion` là dict
  nên không vào cột số.

## Cổng

- `tests/eval/gate.py`: sàn `recall_disagree` ≥ 0.80 và luật không tụt cho `accuracy`, `recall_disagree`, `passed`. Luật không tụt
  chờ baseline thật.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 04 với oracle.
- Suite `full` và `compact` đều chạy cả 12 kết luận của 04, nên dòng `04-dev` luôn là dòng đầy đủ.

## Check "khớp production"

Chưa có. `harvest.py` không gom kết luận cho 04, và không có số production để so với `04-dev`.
