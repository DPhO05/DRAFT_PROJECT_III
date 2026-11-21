# G5 báo cáo phụ huynh: vòng đánh giá

**TL;DR:** G5 gọi 09 viết bản nháp, dừng ở cổng `gate_report` chờ gia sư duyệt, rồi ghi báo cáo và file `.md`. Eval chạy
graph G5 thật tới cổng trên 1 kỳ, k = 3 lần. Nó xác nhận đường nối graph giống production. Chất lượng câu chữ đo
ở 09.

- Graph: `src/tutor/graphs/report.py` (`report.start`, `report.build`). Node: `write` (gọi 09), cổng `gate_report`, `commit`.
- Code eval: `agents.evaluate_g5`, `agents._draft_g5`, `agents.G5_PERIODS` trong `tests/eval/agents.py`. Target `g5` trong `run.TARGETS`.
- Test của eval: `tests/eval/test_agents.py::test_g5_draft_reaches_the_gate_and_writes_no_report`,
  `tests/eval/test_agents.py::test_g5_failed_thread_is_an_error`.

## Đánh giá cái gì

- Thread có tới cổng `gate_report` không.
- Chưa có quyết định của gia sư thì không có dòng `report` nào trong DB.
- Bản nháp ở cổng đạt cùng luật như 09 (`metrics.passed_09`).

## Năm bước

| bước | với G5 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | 1 kỳ: `HS-01 week 2026-10-12` | dùng lại kỳ của 09 |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run; `Runner` thật với mọi graph | `agents.trials` chung |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl`; bản nháp ở cổng | chung |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.passed_09`, `gate`, `report_rows` = 0 | phần 09 chung |
| [5 Scorecard](5-scorecard/README.md) | `metrics.score_09` mỗi run; pass^k; chi phí | `agents.summarize` chung |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | thread tới cổng `gate_report` | có: trường `gate` |
| Outcome | sau khi duyệt mẫu: dòng `report`, file `.md` đúng | `tests/graphs/test_report.py::test_approve_writes_report_and_md` |
| Trajectory | không ghi trước khi duyệt | có: `report_rows` = 0; test `tests/graphs/test_report.py::test_no_write_until_approve` |
| Trajectory | 1 đến 2 lời gọi 09 cho mỗi bản nháp | có: `model_calls` ≤ 2 trong `metrics.passed_09` |
| Component | 09: xem `tests/eval/loop/a09-reporter/README.md` | có |

## Chưa có

- Task 17: hai test pytest của G5 lên scorecard.
- Task 18: judge faithfulness cho bản nháp. `run.TARGETS` đã đánh dấu `judge` cho g5, nhưng chưa có cờ `--judge`.
- Task 22: cổng so với baseline.

## Chạy

```bash
uv run python tests/eval/run.py --agent g5 --backend fake --runs 3
```

- `--backend fake` dùng `agents.oracle_09`. Điểm luôn 1.0.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 6 lời gọi, khoảng $0.10.
