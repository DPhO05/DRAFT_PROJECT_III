# a03 · Bước 5: Scorecard

- 03 không có dòng scorecard riêng. Số của nó nằm trong file kết quả của G1:
  - Khoá `per_run`: `metrics.score` của từng run.
  - Khoá `stability.pass_k` và `pass_k` (từ `metrics.tally`): cùng ý, khác mẫu số. Scorecard đọc `pass_k`.
  - `calls.by_agent["03"]`: số lời gọi và USD của 03.
- `tests/eval/scorecard.py` in dòng `g1-dev` hoặc `g1-heldout` với chỉ số chính `recall`, `precision`.

## Check "khớp production"

- `harvest.sessions` (`tests/eval/harvest.py`) đếm đề xuất của 03 theo quyết định của gia sư và ghi `production.json`:
  `proposals` (số `confirmed`, `edited`, `rejected`, `added`) và `rates` (`kept`, `edited`, `rejected`, `added`).
- Design mục 8.4: so `precision` của G1 với `rates.kept`; lệch quá 0.10 thì cảnh báo. Code chưa so hai số này.
- Chưa chạy `harvest.py` trên dữ liệu thật, nên chưa có số production.

## Cổng

- `tests/eval/gate.py`: sàn `recall` ≥ 0.90 và `precision` ≥ 0.75 cho `g1-*`, `flow_errors` = 0; luật không tụt cho `first_wrong_step_acc`.
  Luật không tụt chờ baseline thật.
- Chạy với `--files` ghi khoá `subset` vào file kết quả. Dòng một phần nằm cạnh dòng đầy đủ, bảng đánh dấu `*` sau số task (ví dụ `9*`). Sàn vẫn áp cho mọi dòng. `no_drop` chỉ so dòng cùng `set` và cùng `subset` với dòng baseline; không có thì in `BỎ QUA` với giới hạn `khác tập task`.
