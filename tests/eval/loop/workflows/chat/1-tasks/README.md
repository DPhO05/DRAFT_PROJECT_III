# Chat · Bước 1: Tasks

Task của chat nằm trong `tests/eval/questions_00.json`, cùng tệp với 00.

| task | thử gì | trường chính |
|---|---|---|
| `q9` | `start_report` chạy, không cần duyệt | `expect_starts` |
| `q10` | `start_bank_import` hỏng: thử lại tối đa 1 lần | `fail_tools`, `allow_tool_error`, `max_calls` |
| `q11` | `start_grading` được duyệt | `expect_approval`, `approval`, `expect_starts` |
| `q12` | `start_grading` bị bỏ: không gọi lại | `approval`, `max_calls` |
| `q13` | `start_grading` được sửa | `approval` với `args` đã sửa |
| `q14` | thiếu học sinh và ngày: phải hỏi lại | `forbid`, `expect_any` |
| `q15`, `q16` | hai lượt trong một thread | `turns` |
| `q17` | lệnh giả trong đề bài | `forbid` |
| `q18` | "lưu đi": trả lời bằng code | `max_model_calls` = 0, `expect_text` |
| `q19` | mã bài: trả lời bằng thẻ, không cần model | `max_model_calls` = 0, `card_only` |
| `q20` | tin nhắn có họ tên | `masked`, `expect_args` |

- Người dùng giả là kịch bản: `turns` và `approval` (quyết định 7A). Không có model đóng vai gia sư.
- Check "bao phủ cách dùng thật": chưa đạt. Chưa có task nào từ log chat thật (Task 21).
