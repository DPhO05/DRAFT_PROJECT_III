# a02 · Bước 5: Scorecard

- 02 không có dòng scorecard riêng. Số của nó nằm trong file kết quả của G1:
  - `metrics.stability.items_changed_pct` và `metrics.extra.items_changed_pct`.
  - `calls.by_agent["02"]`: số lời gọi và USD của 02.
  - `metrics.components` và `metrics.trajectory`: chi tiết của 02 và 03 trong G1. Scorecard chưa đưa chúng vào cột.
- `tests/eval/scorecard.py` đưa `items_changed_pct` vào khoá `metrics` của dòng `g1-dev` hoặc `g1-heldout`.
- `02r` có dòng `02r-dev`. `scorecard.KEY` của `02r` rỗng, nên cột chỉ số chính chỉ có `name_leaks`.

## Cổng

- `tests/eval/gate.py` xét dòng G1 (`g1-*`): `flow_errors` = 0, `recall` ≥ 0.90, `precision` ≥ 0.75. 02 chưa có sàn riêng.
- Luật không tụt cho G1 xét các chỉ số trong `no_drop` (`recall`, `precision`, `first_wrong_step_acc`). Luật này chờ baseline thật.
- Lỗi cần sửa: chạy với `--files` (cả hai suite chạy `g1-dev` với `s01.tex` và `s04.tex`) tạo dòng một phần, thay dòng đầy đủ, và gate
  không phân biệt được. Đang sửa trong review cuối.

## Check "khớp production"

Chưa có. `harvest.py` gom buổi chấm đã duyệt thành task G1 nháp (xem `tests/eval/loop/a03-diagnoser/5-scorecard/README.md`). Chưa chạy
trên dữ liệu thật, và không có số production riêng cho 02.
