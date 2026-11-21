# a00 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3 (quyết định 1A). Mỗi run chạy mọi task theo thứ tự. Một trial là một task trong một run.
- Lỗi của một task được ghi vào `errors` và task đó trượt ở run đó. Run vẫn chạy tiếp.

## Trace

Thư mục `--traces`, mặc định `data/eval/traces/<stamp>_00/`:

| file | ghi bởi | nội dung |
|---|---|---|
| `run<k>.jsonl` | `agents.trials` | các dòng `llm.jsonl` của run: một dòng một lời gọi model |
| `run<k>-chat.json` | `agents.evaluate_00` | mỗi task: `events` của chat và `messages` của thread |

- Một dòng `llm.jsonl` do `llm._log` ghi: `agent`, `prompt_version`, `model`, token, `ms`, `result`, `output`. Phần `user` đã che tên.
- `messages` lấy từ `agent.get_state(cfg)` sau lượt cuối.

## Check "ổn định qua các lần"

- pass^k: tỉ lệ task đạt ở cả k run (`metrics.tally`).
- success: tỉ lệ trial đạt.
- Test: `tests/eval/test_agents.py::test_00_chat_trace_is_kept`.
