# a08 · Bước 5: Scorecard

- Dòng `08-dev` từ file kết quả của target 08: `scorecard.KEY` cho cột `p_at_n`, `recall_at_n`. Lần đo 2026-11-21: `p_at_n` = 0.300,
  `recall_at_n` = 0.180, 0 lời gọi, 0 USD.
- Dòng `08-tests` khi chạy `scorecard.py --with-tests`: test của luật chọn bài khai báo trong `tests/eval/workflows.json`
  (`tests/services/test_select.py`). Dòng này có `backend: code`.
- File kết quả ghi backend được yêu cầu, kể cả `real`, dù 08 không gọi model. Scorecard có thể hiện cùng một kết quả ở nhiều dòng backend.

## Cổng

- `tests/eval/baseline.json` không có sàn cho 08. Luật không tụt chỉ xét `passed` của 08, và chờ baseline thật.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 08 với `calls.logged` = 0.
- Chủ dự án quyết định nhãn trước khi đặt sàn: xem `tests/eval/loop/a08-recommender/README.md`.

## Check "khớp production"

Chưa có. Không có số production nào cho 08, và `harvest.py` không gom task cho 08.
