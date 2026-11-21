# a01 · Bước 2: Environment

## Dùng chung

- `agents.trials`: mỗi run một thư mục `work/run<k>`, `tutor.db` mới, `assistant_fix.world` seed ngân hàng `data/dummy/bank`.
- Backend dựng một lần ở run 1. Mỗi run có `llm.jsonl` riêng.

## Riêng cho 01

`components._match_01` chạy một task:

- Đọc ngân hàng bằng kết nối chỉ đọc (`repo.bank_problems`).
- Gọi `ingest.run` với chữ của bài, ngân hàng và lớp. Không chạy G1 quanh nó.
- `CallContext` có `graph` là G1 và `thread_id` là `eval-<id>`, cộng bản đồ che tên của `components._redact`.

## Check "sạch, không rò"

- Nhãn `expect_ref` không đi vào prompt: oracle tìm task bằng chữ của bài (`components.body`), không bằng nhãn.
- `name_leaks` của `agents.summarize` đếm họ tên trong các dòng log.
- Giới hạn: thế giới mới theo run, không theo từng trial. 01 không ghi DB nên không có gì rò giữa các task.
