# a00 · Bước 5: Scorecard

- File kết quả: thư mục `--out`, mặc định `data/eval/results/`. Tên file là `<created>_<prompt_version của 00>.json`.
- Khoá `per_run`: `metrics.score_00` của từng run: `n_questions`, `tools_ok`, `args_ok`, `unverified_pct`, `passed`, `approval_ok`.
- Khoá `pass_k`, `success`, `tally`: từ `metrics.tally` qua `agents.summarize`.
- Khoá `extra`: `name_leaks`, và `approval_ok` trung bình của các run.
- Khoá `calls`: `metrics.usage`: số lời gọi, USD, token, `ms_p50`, `ms_p95`, `error_rate`, theo agent.
- `tests/eval/scorecard.py` gộp file mới nhất của cặp (`00-dev`, backend) thành một dòng. Cột chỉ số chính của 00:
  `tools_ok`, `args_ok`, `name_leaks` (`scorecard.KEY`).
- Với `--backend fake`, USD chỉ là số của đường ống.

## Check "khớp production"

Chưa có:

- Task 21: tỉ lệ `unverified_rate` từ log chat production, ghi vào `production.json`.
- Task 22: `tests/eval/gate.py` so với baseline; sàn `pass_k` ≥ 0.85, `approval_ok` = 1.0 và `name_leaks` = 0 là sàn cứng.
- Task 23: cổng tầng 0 trong pytest.
