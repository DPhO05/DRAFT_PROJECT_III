# Chat · Bước 2: Environment

Như 00: xem `tests/eval/loop/a00-orchestrator/2-environment/README.md`.

Phần riêng cho chat trong `agents._ask_00`:

- Mỗi task một `InMemorySaver` và một thread. Mỗi lượt dựng lại `Toolbox`, `ChatContext` và agent, như app làm cho mỗi tin
  nhắn.
- Khi một lượt dừng ở sự kiện `approval`, eval tạo `assistant.Decision` từ trường `approval` của task (mặc định
  `reject`) và chạy tiếp thread.
- Bản ghi âm `recorder` thay cho graph thật, nên lệnh `start_grading` được duyệt không chạy G1.

## Check "sạch, không rò"

- `tests/eval/test_agents.py::test_00_full_name_never_reaches_the_model`.
- `tests/eval/test_agents.py::test_00_approval_decisions_reach_the_starter`.
- Test pytest: `tests/agents/test_chat.py::test_names_never_enter_state`.
