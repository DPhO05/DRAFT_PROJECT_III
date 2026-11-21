# a00 Orchestrator: vòng đánh giá

**TL;DR:** 00 là trợ lý chat của gia sư: một agent LangChain gọi công cụ. Eval hỏi 20 câu cố định, chạy k = 3 lần,
chấm bằng code: đúng công cụ, đúng đối số, giữ luật của app, không có số chưa kiểm.

- Code của agent: `src/tutor/agents/a00_orchestrator/chat.py`, `src/tutor/agents/a00_orchestrator/orchestrator.py`,
  `src/tutor/agents/a00_orchestrator/tools.py`.
- Code eval: `agents.evaluate_00`, `agents._ask_00`, `agents.oracle_00` trong `tests/eval/agents.py`.
- Test của eval: `tests/eval/test_agents.py`, các test tên `test_00_...`.

## Đánh giá cái gì

- Câu trả lời của 00 cho một tin nhắn của gia sư, có thể qua nhiều lượt.
- Công cụ 00 gọi, theo thứ tự, và đối số của chúng.
- Luật của app: không lộ họ tên, không hiện mã lỗi, không nói "đã lưu", `start_grading` phải chờ gia sư duyệt.
- Phần approval, nhiều lượt và `by_code` được đo trong cùng 20 task. Xem thêm `tests/eval/loop/workflows/chat/README.md`.

## Năm bước

| bước | với 00 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | 20 task `q1` đến `q20` trong `tests/eval/questions_00.json` | riêng |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run; DB chỉ đọc; `start_*` ghi âm | `agents.trials` chung |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl`, `run<k>-chat.json` | file chat riêng |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.passed_00` | riêng |
| [5 Scorecard](5-scorecard/README.md) | `metrics.score_00` mỗi run; pass^k, `name_leaks`, `approval_ok`, chi phí | `agents.summarize` chung |

## Ba mức grader

| mức | kiểm gì | hàm hoặc trường |
|---|---|---|
| Outcome | có câu trả lời, vòng không bị cắt, không số chưa kiểm | `metrics.passed_00` |
| Outcome | bản ghi âm nhận đúng lệnh `start_*` | trường `expect_starts`, trong `metrics.rules_ok` |
| Trajectory | đúng công cụ theo thứ tự, không gọi công cụ cấm, lỗi công cụ | `metrics._tools_ok` |
| Trajectory | approval có hay không, trần số lời gọi | `metrics.rules_ok`: `expect_approval`, `max_calls`, `max_model_calls` |
| Component | đối số của lời gọi đầu tiên mỗi công cụ | `metrics.args_ok` |
| Component | đối số hợp schema; không lộ tên; không hiện mã lỗi | `metrics.args_fit`, `agents.leak_count`, `codes_shown` |

- Trần 8 lượt công cụ (design mục 5.1) là của app: `max_tool_turns` trong `src/tutor/config.py`. Vòng chạm trần thì bị
  dừng, và `metrics.passed_00` đánh trượt vì `stopped`.

## Chưa có

- Task 16: recall@5 của công cụ `search_problems` trên 6 câu tìm có nhãn.
- Task 18: judge faithfulness cho câu có số liệu học sinh, cờ `--judge` và `--judge-model`.
- Task 19: hiệu chỉnh judge với người chấm.
- Task 21: câu có "số chưa kiểm" trong log chat production thành task nháp.
- Task 22 và 23: cổng với sàn `pass_k` ≥ 0.85 và `approval_ok` = 1.0.

## Chạy

```bash
uv run python tests/eval/run.py --agent 00 --backend fake --runs 3
```

- `--backend fake` dùng `agents.oracle_00`. Điểm luôn 1.0: chỉ chứng minh task giải được và grader đúng.
- `--only q4 q11` chỉ chạy các task đó.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 135 lời gọi, khoảng $0.55 cho 20 task × 3
  lần.
