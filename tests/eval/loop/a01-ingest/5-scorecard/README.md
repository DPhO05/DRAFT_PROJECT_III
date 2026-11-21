# a01 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 01>.json`, một bản mỗi lớp.
  Phần cố định của prompt chứa đề của một lớp (`ingest.run`), bộ task có lớp 8 và lớp 9, nên tên có hai `prompt_version` của 01.
- Khoá `per_run`: `metrics.score_01`: `n_tasks`, `hit_at_1`, `hit_at_3`, `mrr`, `low_match_precision`, `passed`.
- Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls`: như mọi target, qua `agents.summarize`.
- `tests/eval/scorecard.py` in dòng `01-dev` với chỉ số chính `hit_at_1`, `mrr`, `name_leaks`.

## Cổng

- `tests/eval/gate.py`: sàn `hit_at_1` ≥ 0.90 và luật không tụt cho `hit_at_1`, `hit_at_3`, `mrr`, `passed`. Luật không tụt chờ baseline thật.
- Chạy với `--only` (suite `compact`: 6 trong 10 task) ghi khoá `subset` vào file kết quả. Dòng một phần nằm cạnh dòng đầy đủ, bảng đánh dấu `*` sau số task (ví dụ `9*`). Sàn vẫn áp cho mọi dòng. `no_drop` chỉ so dòng cùng `set` và cùng `subset` với dòng baseline; không có thì in `BỎ QUA` với giới hạn `khác tập task`.

## Check "khớp production"

Chưa có. `harvest.py` không gom task cho 01, và không có số production nào để so với `01-dev`.
