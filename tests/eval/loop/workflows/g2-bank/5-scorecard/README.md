# G2 · Bước 5: Scorecard

- G2 không có file kết quả của `run.py`. Có một dòng khi chạy `scorecard.py --with-tests`: `G2-tests`, `backend: code`, 0 lời gọi.
- Các test của G2 khai báo trong `tests/eval/workflows.json`, theo ba mức. `scorecard.code_rows` chạy pytest và ghi số test đạt mỗi mức
  vào `metrics`, tổng vào `pass_k`.
- Gate không có sàn cho dòng `-tests`.
- Check "khớp production": chưa có.
