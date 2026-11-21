# a00 · Bước 1: Tasks

- File: `tests/eval/questions_00.json`, 20 task, `q1` đến `q20`. Đọc vào `agents.QUESTIONS`.
- Mọi task là synthetic: chủ dự án tự soạn, không lấy từ dữ liệu thật.
- Input là trường `text`. Task nhiều lượt có thêm `turns`.

## Tiêu chí đạt nằm trong task

| trường | nghĩa |
|---|---|
| `expect` | công cụ phải gọi, theo thứ tự; công cụ khác được xen giữa |
| `forbid` | công cụ không được gọi; `*` là mọi công cụ |
| `expect_args` | cặp đối số mà lời gọi đầu tiên của công cụ đó phải có |
| `expect_last_args` | cặp đối số mà lời gọi cuối cùng của công cụ đó phải có |
| `expect_approval`, `approval` | lượt có phải chờ duyệt không; quyết định của kịch bản |
| `expect_starts` | lệnh mà bản ghi âm `start_*` phải nhận |
| `max_calls`, `max_model_calls` | trần số lần gọi một công cụ; trần số lời gọi model |
| `expect_text`, `expect_any`, `card_only` | yêu cầu về chữ trả lời; chỉ cần thẻ |
| `fail_tools`, `allow_tool_error` | công cụ hỏng có chủ đích; lỗi công cụ được phép |

- `script` và `say` là lời của oracle (fake model), không phải tiêu chí.
- `masked` là chữ sau khi chat che tên, để oracle tìm đúng task.

## Nhóm task

| task | thử gì |
|---|---|
| `q1` đến `q8` | tra cứu: học sinh, hồ sơ, lỗi, so sánh, chọn bài, tìm bài, đề bài, câu ngoài phạm vi |
| `q9`, `q10` | bắt đầu báo cáo; nhập ngân hàng với công cụ hỏng |
| `q11`, `q12`, `q13` | `start_grading` được duyệt, bị bỏ, được sửa |
| `q14` | thiếu học sinh và ngày: phải hỏi lại, không gọi `start_*` |
| `q15`, `q16` | hai lượt trong một thread |
| `q17` | lệnh giả chèn trong đề bài |
| `q18`, `q19` | trả lời bằng code (`by_code`), 0 lời gọi model |
| `q20` | tin nhắn có họ tên học sinh |

- Trường `judge: true` đánh dấu task có câu trả lời mang số liệu học sinh; chỉ các task này được judge chấm khi có `--judge`
  (`q1` đến `q5`, `q9`, `q11`, `q15`, `q16`, `q20`).
- Test: `tests/eval/test_agents.py::test_00_tasks_are_wellformed`.
- Check "bao phủ cách dùng thật": chưa đạt. Chưa có task nào lấy từ log chat thật. `harvest.chats` (`tests/eval/harvest.py`) gom
  câu có cảnh báo `unverified_number` và approval bị bỏ thành task nháp ở `00/tasks.json`. Nó chưa chạy trên log thật.
