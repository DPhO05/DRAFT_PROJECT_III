# Chat · Bước 5: Scorecard

- Chat không có dòng riêng. Số của nó nằm trong dòng `00-dev`:
  - Khoá `extra.approval_ok`: trung bình `approval_ok` của các run.
  - Khoá `extra.name_leaks`: số chuỗi còn họ tên trong log và message.
- Xem `tests/eval/loop/a00-orchestrator/5-scorecard/README.md`.

## Check "khớp production"

Chưa có:

- Task 21: `unverified_rate` từ log chat thật.
- Task 22: `approval_ok` = 1.0 và `name_leaks` = 0 là sàn cứng; trượt là chặn.
