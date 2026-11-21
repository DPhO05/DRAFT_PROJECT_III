# a00 · Bước 5: Scorecard

- File kết quả: thư mục `--out`, mặc định `data/eval/results/`. Tên file là `<created>_<prompt_version của 00>.json`.
- Khoá `per_run`: `metrics.score_00` của từng run: `n_questions`, `tools_ok`, `args_ok`, `unverified_pct`, `passed`, `approval_ok`.
- Khoá `pass_k`, `success`, `tally`: từ `metrics.tally` qua `agents.summarize`.
- Khoá `extra`: `name_leaks`, và `approval_ok` trung bình của các run. Với `--judge`: `faithfulness`, `judge_unknown`, `judge_errors`.
- Khoá `calls`: `metrics.usage`: số lời gọi, USD, token, `ms_p50`, `ms_p95`, `error_rate`, theo agent.
- `tests/eval/scorecard.py` gộp file mới nhất của cặp (`00-dev`, backend) thành một dòng. Cột chỉ số chính của 00:
  `tools_ok`, `args_ok`, `name_leaks` (`scorecard.KEY`).
- Với `--backend fake`, USD chỉ là số của đường ống.

## Cổng

- `tests/eval/gate.py` xét dòng `00-dev`: `pass_k` ≥ 0.85; `approval_ok` = 1.0 và `name_leaks` = 0 là sàn cứng; `faithfulness` ≥ 0.95 chờ
  `judge_trusted`. Luật không tụt cho `tools_ok`, `args_ok` và `passed` chờ baseline thật.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 00 với oracle và judge giả, rồi cho `gate.check`.
- Chạy với `--only` (suite `compact`: 14 trong 20 task) ghi khoá `subset` vào file kết quả. Dòng một phần nằm cạnh dòng đầy đủ, bảng đánh dấu `*` sau số task (ví dụ `9*`). Sàn vẫn áp cho mọi dòng. `no_drop` chỉ so dòng cùng `set` và cùng `subset` với dòng baseline; không có thì in `BỎ QUA` với giới hạn `khác tập task`.

## Check "khớp production"

- `harvest.chats` tính `unverified_rate` từ log chat production và ghi vào `production.json`. Chưa chạy trên dữ liệu thật, nên chưa có số.
- Không có số thật để so với `00-dev`.
