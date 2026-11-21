# a00 · Bước 2: Environment

## Dùng chung

- `agents.trials` gọi `agents._world` mỗi run: thư mục `work/run<k>`, `tutor.db` mới, rồi `assistant_fix.world`.
- `assistant_fix.world` (`tests/assistant_fix.py`) seed ngân hàng `data/dummy/bank`, thêm HS-01, HS-02, HS-03 (đã lưu trữ) và vài
  buổi học. Hôm nay của thế giới là 2026-10-21.
- Backend dựng một lần ở run 1. Mỗi run có `llm.jsonl` riêng.

## Riêng cho 00

`agents._ask_00` dựng từng task:

- DB mở chỉ đọc. Một task không đổi được dữ liệu của task sau.
- Mỗi task một thread mới (`InMemorySaver`). Mọi lượt của task nằm trong thread đó, như trong app.
- Prompt hệ thống và danh sách công cụ lấy từ `orchestrator.fixed_parts` và `tools.tool_defs`, như `src/tutor/api/assistant.py`.
- Công cụ `start_*` không chạy graph thật. `recorder` của `tests/agents/test_tools.py` ghi lại lệnh. `fail_tools` thay công cụ
  bằng hàm luôn lỗi.
- Người dùng giả là kịch bản cố định: `turns` và `approval` (quyết định 7A). Không có model đóng vai gia sư.
- Lời gọi model đi qua `chat.scope` với bản đồ che tên. `llm.Guard` che tên và từ chối gửi nếu còn họ tên.

## Check "sạch, không rò"

- `tests/eval/test_agents.py::test_00_each_run_starts_from_a_new_world`.
- `tests/eval/test_agents.py::test_00_full_name_never_reaches_the_model`.
- `tests/eval/test_agents.py::test_00_two_turn_tasks_share_one_thread`.
- Giới hạn: các task trong một run dùng chung một DB. DB chỉ đọc nên không rò dữ liệu, nhưng thế giới mới theo run,
  không theo từng trial.
  Khác design mục 5.1 ("mỗi trial"). Code làm theo build Task 4.
