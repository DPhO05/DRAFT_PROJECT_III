# a09 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3. Mỗi run chạy 6 kỳ theo thứ tự.
- Trace: `run<k>.jsonl` trong thư mục `--traces`, mặc định `data/eval/traces/<stamp>_09/`. Một dòng một lời gọi 09.
- Mỗi báo cáo trong khoá `reports` của file kết quả giữ phần trace của app:

| khoá | nội dung |
|---|---|
| `audit` | mỗi câu nháp: chữ, mã số liệu, `status` (`ok`, `rewritten`, `dropped`), cờ |
| `sentences` | các câu còn lại sau audit |
| `facts_block` | khối số liệu đã gửi cho 09 |
| `model_calls`, `leaks` | số lời gọi; số chuỗi còn họ tên |

- Số lời gọi đếm trước mọi lời gọi judge sau này, nên judge không đổi kết quả đạt.
- Check "ổn định qua các lần": pass^k qua `metrics.tally`.
