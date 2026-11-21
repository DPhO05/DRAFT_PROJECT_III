# a02 · Bước 5: Scorecard

- 02 không có dòng scorecard riêng. Số của nó nằm trong file kết quả của G1:
  - `metrics.stability.items_changed_pct` và `metrics.extra.items_changed_pct`.
  - `calls.by_agent["02"]`: số lời gọi và USD của 02.
- `tests/eval/scorecard.py` đưa `items_changed_pct` vào khoá `metrics` của dòng `g1-dev` hoặc `g1-heldout`.

## Check "khớp production"

Chưa có. Task 22 thêm luật không tụt cho cả lần chạy G1. Task 14 thêm dòng `02r-dev` cho rubric nháp.
