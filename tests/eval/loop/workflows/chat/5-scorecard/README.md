# Chat · Bước 5: Scorecard

- Chat không có dòng riêng. Số của nó nằm trong dòng `00-dev`:
  - Khoá `extra.approval_ok`: trung bình `approval_ok` của các run.
  - Khoá `extra.name_leaks`: số chuỗi còn họ tên trong log và message.
- Xem `tests/eval/loop/a00-orchestrator/5-scorecard/README.md`.

- Với `--judge`, khoá `extra`: `faithfulness`, `judge_unknown`, `judge_errors`.
- Với `--with-tests`: dòng `chat-tests`, `backend: code`, 0 lời gọi.

## Cổng

- `approval_ok` = 1.0 và `name_leaks` = 0 là sàn cứng của `00-dev` (`tests/eval/gate.py`); thiếu số cũng là `TRƯỢT`.
- Chạy `00` với `--only` (suite `compact`) tạo dòng `00-dev` một phần, thay dòng đầy đủ, và gate không phân biệt được. Đang sửa trong
  review cuối.

## Check "khớp production"

- `harvest.chats` tính `unverified_rate` từ log chat thật và ghi vào `production.json`. Chưa chạy trên dữ liệu thật, nên chưa có số.
