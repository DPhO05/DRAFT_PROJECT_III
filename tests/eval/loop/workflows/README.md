# Workflow: vòng đánh giá

**TL;DR:** Năm workflow của app. Hai workflow có LLM chạy được bằng `run.py` hôm nay: G1 (`--agent g1`) và G5 (`--agent g5`). Chat
được đo trong 20 task của 00. G2 và G4 không gọi model, chỉ có test pytest.

| thư mục | graph | gọi LLM | eval hôm nay | lệnh với fake model |
|---|---|---|---|---|
| `g1-session/` | `src/tutor/graphs/session.py` | 01 đến 04 | `run.evaluate`, tới `gate_review` | `run.py --agent g1 --backend fake` |
| `g2-bank/` | `src/tutor/graphs/bank.py` | không | test pytest, dòng `G2-tests` | `pytest tests/graphs/test_bank_graph.py` |
| `g4-worksheet/` | `src/tutor/graphs/worksheet.py` | không | test pytest, dòng `G4-tests` | `pytest tests/graphs/test_worksheet.py` |
| `g5-report/` | `src/tutor/graphs/report.py` | 09, judge | `agents.evaluate_g5`, tới `gate_report` | `run.py --agent g5 --backend fake` |
| `chat/` | `src/tutor/agents/a00_orchestrator/chat.py` | 00 | 12 trong 20 task của 00 | `run.py --agent 00 --backend fake` |

- Lệnh trong bảng là bản rút gọn. Lệnh đủ nằm ở README của từng workflow.
- Test code của mọi workflow lên scorecard bằng `scorecard.py --with-tests`: khai báo trong `tests/eval/workflows.json`, một dòng
  `<target>-tests` mỗi target (G1, G2, G4, G5, chat, và 05, 08). Dòng có `backend: code` và 0 lời gọi.
- Mọi lệnh chạy từ gốc repo với `uv run python tests/eval/...` hoặc `uv run pytest ...`.
- G3 không có trong app hôm nay, nên không có thư mục.
- Eval của workflow có LLM dừng ở cổng duyệt của gia sư. Bước ghi DB sau cổng (`commit`) chỉ được kiểm bằng test
  pytest.

## Ba mức grader cho workflow

| mức | với workflow |
|---|---|
| Outcome | luồng tới được cổng duyệt; trạng thái cuối đúng; không ghi DB trước khi duyệt |
| Trajectory | các node và agent chạy đúng thứ tự; số lời gọi trong trần; dừng ở cổng đúng lúc |
| Component | eval của từng agent bên trong: xem thư mục agent tương ứng trong `tests/eval/loop/` |

## Đã có

- Trajectory của G1 từ `llm.jsonl`: `metrics.trajectory` (xem `tests/eval/loop/workflows/g1-session/README.md`).
- Test pytest của G1, G2, G4, G5 và chat trên scorecard qua `tests/eval/workflows.json`.
- Cổng: `tests/eval/gate.py` xét dòng của `g1-*`, 00, 01, 04 và 09. Dòng `-tests` không có sàn riêng. Test tầng 0: `tests/eval/test_gate.py`.

## Chưa có

- Chạy thật: chưa có lần chạy `--backend real` của G1, G5 hay chat sau 2026-11-04. Chưa có baseline thật.
- GitHub Actions: chưa có workflow chạy cổng.
