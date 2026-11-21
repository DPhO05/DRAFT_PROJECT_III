# a04 · Bước 1: Tasks

- File: `tests/eval/tasks/verifier_04.json`, 12 task, `v1` đến `v12`. Đọc vào `components.TASKS_04`.
- Mọi task là synthetic. Mỗi kết luận trỏ vào một bài mẫu trong `tests/fixtures/submissions/`.

| trường | nghĩa |
|---|---|
| `file`, `seq` | bài mẫu và số thứ tự bài trong file |
| `claim` | kết luận cần kiểm: `step_idx`, `code`, `description` |
| `expect` | verdict đúng: `agree`, `disagree` hoặc `wrong_code` |
| `expect_code` | mã đúng khi `expect` là `wrong_code` |

| task | `expect` |
|---|---|
| `v1` đến `v6` | `agree` |
| `v7` đến `v9` | `disagree`: sai bước |
| `v10` đến `v12` | `wrong_code`: đúng bước, sai mã |

- Bộ cân bằng giữa kết luận đúng và sai, theo lời khuyên của nguồn (design mục 5.5).
- Test: `tests/eval/test_components.py::test_04_tasks_are_balanced_and_unique`.
- Check "bao phủ cách dùng thật": chưa đạt. Kết luận do người viết, chưa lấy từ đề xuất thật bị gia sư bỏ.
