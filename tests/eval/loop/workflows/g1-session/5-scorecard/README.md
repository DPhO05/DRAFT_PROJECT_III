# G1 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 02, 03, 04>.json`.
- Khoá `metrics`:
  - `per_run`: `metrics.score` của từng run.
  - `stability`, `pass_k`, `success`, `tally`.
  - `extra`: `flow_errors`, `items_changed_pct`.
- Khoá `calls`: `metrics.usage`, có `by_agent` cho 01, 02, 03, 04.
- `tests/eval/scorecard.py` in dòng `g1-dev` hoặc `g1-heldout` với chỉ số chính `recall`, `precision`. `name_leaks` in "-" vì G1 chưa
  ghi khoá này (Task 13).

## Check "khớp production"

Chưa có:

- Task 20: `production.json`: tỉ lệ đề xuất được giữ, bị sửa, bị bỏ, lỗi gia sư thêm tay.
- Design mục 8.4: so precision của G1 với tỉ lệ đề xuất được giữ; lệch quá 0.10 thì cảnh báo.
- Task 22: `tests/eval/gate.py` với sàn và luật không tụt.
