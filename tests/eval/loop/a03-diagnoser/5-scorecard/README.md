# a03 · Bước 5: Scorecard

- 03 không có dòng scorecard riêng. Số của nó nằm trong file kết quả của G1:
  - Khoá `per_run`: `metrics.score` của từng run.
  - Khoá `stability`: `pass_k` theo bước sai đầu tiên.
  - `calls.by_agent["03"]`: số lời gọi và USD của 03.
- `tests/eval/scorecard.py` in dòng `g1-dev` hoặc `g1-heldout` với chỉ số chính `recall`, `precision`.

## Check "khớp production"

Chưa có:

- Task 20: đề xuất bị gia sư bỏ, sửa, hay thêm tay trong dữ liệu thật thành task G1 nháp.
- Task 22: sàn `recall` ≥ 0.90, `precision` ≥ 0.75, luật không tụt cho `first_wrong_step_acc`.
