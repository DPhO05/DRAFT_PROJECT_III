# a04 · Bước 2: Environment

## Dùng chung

- `agents.trials`: mỗi run một thư mục `work/run<k>`, `tutor.db` mới, `assistant_fix.world` seed ngân hàng `data/dummy/bank`.

## Riêng cho 04

`components._verify_04` dựng đầu vào của một kết luận:

- Chữ bài lấy từ `tests/fixtures/submissions/`, cắt bước bằng `latex.split_steps`.
- Mã bài lấy từ `labels.json`, rồi đề bài lấy từ DB (`repo.problem_detail`). Bảng mã lỗi lấy từ `repo.error_codes`.
  Kết nối chỉ đọc.
- `evidence_latex` của kết luận là chữ của bước mà kết luận chỉ ra.
- Gọi `verifier.run` một mình, không chạy G1.

## Check "sạch, không rò"

- `expect` và `expect_code` không vào prompt. Oracle tìm task bằng `description` của kết luận.
- `name_leaks` của `agents.summarize` đếm họ tên trong các dòng log.
- 04 không ghi DB, nên các task trong một run không ảnh hưởng nhau.
