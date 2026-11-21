# G1 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 02, 03, 04>.json`.
- Khoá `metrics`:
  - `per_run`: `metrics.score` của từng run.
  - `stability`, `pass_k`, `success`, `tally`.
  - `components`: một dict mỗi run. `trajectory`: một dict cho cả file.
  - `extra`: `flow_errors`, `items_changed_pct`, `name_leaks`, `over_budget`, `order_ok`, `confirm_ok`.
- Khoá `calls`: `metrics.usage`, có `by_agent` cho 01, 02, 03, 04.
- `tests/eval/scorecard.py` in dòng `g1-dev` hoặc `g1-heldout` với chỉ số chính `recall`, `precision`, `name_leaks`.
- `scorecard.py --with-tests` thêm dòng `G1-tests`: test của `tests/graphs/test_session.py`, `tests/graphs/test_session_lanes.py` và
  `tests/graphs/test_no_write_before_review.py`, theo ba mức.

## Cổng

- `tests/eval/gate.py`: sàn `flow_errors` = 0, `recall` ≥ 0.90, `precision` ≥ 0.75 cho `g1-*`; `name_leaks` = 0 là sàn cứng.
  Luật không tụt cho `recall`, `precision`, `first_wrong_step_acc`: chờ baseline thật.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy `g1-dev` và `g1-heldout` với oracle, và so `g1-dev` trên backend `dev` với ảnh chụp
  trong `baseline.json` (`dev`).
- Chạy với `--files` (cả hai suite chạy `g1-dev` với `s01.tex` và `s04.tex`: 9 bài thay vì 40; `compact` chạy `g1-heldout` với 5 file: 10 bài thay vì 20) ghi khoá `subset` vào file kết quả. Dòng một phần nằm cạnh dòng đầy đủ, bảng đánh dấu `*` sau số task (ví dụ `9*`). Sàn vẫn áp cho mọi dòng. `no_drop` chỉ so dòng cùng `set` và cùng `subset` với dòng baseline; không có thì in `BỎ QUA` với giới hạn `khác tập task`.

## Check "khớp production"

- `harvest.sessions` ghi `production.json`: `proposals` và `rates` (`kept`, `edited`, `rejected`, `added`) từ quyết định của gia sư.
  Chưa chạy trên dữ liệu thật, nên chưa có số.
- Design mục 8.4: so `precision` của G1 với `rates.kept`; lệch quá 0.10 thì cảnh báo. Code chưa so hai số này.
