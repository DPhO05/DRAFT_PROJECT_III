# a09 Reporter: vòng đánh giá

**TL;DR:** 09 viết phần "Nhận xét" của báo cáo phụ huynh. Mỗi câu phải trích ít nhất một mã số liệu; câu trượt
audit được viết lại một lần, trượt lần nữa thì bị bỏ. Eval chạy 6 kỳ báo cáo, k = 3 lần, chấm bằng code.

- Code của agent: `src/tutor/agents/a09_reporter/reporter.py` (`reporter.run`, `reporter.ReportOut`).
- Audit của app: `audit.check_sentence` trong `src/tutor/services/audit.py`. Số liệu của kỳ: `facts.report_facts` trong
  `src/tutor/services/facts.py`.
- Code eval: `agents.evaluate_09`, `agents._report_09`, `agents._report_row`, `agents.oracle_09` trong `tests/eval/agents.py`.
- Test của eval: `tests/eval/test_agents.py`, các test tên `test_09_...`.

## Đánh giá cái gì

- Báo cáo có giữ hết câu nháp không: không câu nào bị audit bỏ.
- Số câu đúng khoảng của loại kỳ: ngày 2 đến 3 câu, tuần và tháng 3 đến 5 câu (`metrics.SENTENCES`, theo
  `reporter.INSTRUCTIONS`).
- Chữ hiện cho phụ huynh không có mã số liệu, mã học sinh, mã bài, dấu %, họ tên.
- 09 không gọi quá 2 lần cho một kỳ.

## Năm bước

| bước | với 09 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | 6 kỳ trong `agents.PERIODS` | riêng |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run; DB chỉ đọc; tên đã che | `agents.trials` chung |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl`; bảng `audit` trong kết quả | chung |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.passed_09` | riêng |
| [5 Scorecard](5-scorecard/README.md) | `metrics.score_09`: `dropped_pct`, `draft_flagged_pct`, cờ theo loại | `agents.summarize` chung |

## Ba mức grader

| mức | kiểm gì | hàm hoặc trường |
|---|---|---|
| Outcome | không câu nào bị bỏ; số câu đúng khoảng của kỳ | `metrics.passed_09` |
| Outcome | chữ không có mã số liệu, mã học sinh, mã bài, dấu % | `metrics.text_ok_09` |
| Trajectory | 1 lời gọi, hoặc 2 khi có câu phải viết lại; không quá 2 | `model_calls` ≤ 2 trong `metrics.passed_09` |
| Component | mỗi câu trích mã số liệu có thật; số khớp số liệu | khoá `audit`, do `audit.check_sentence` của app |
| Component | % câu nháp bị cờ, % câu bị bỏ, số cờ theo loại | `metrics.score_09`, `metrics.FLAGS_09` |
| Component | không lộ họ tên trong log và trong câu | `agents.leak_count` |

- Audit bằng code chỉ so con số. Câu "em tiến bộ rõ" khi số liệu nói mức kỹ năng giảm thì code không bắt được.
  Judge faithfulness lo phần này (Task 18).

## Chưa có

- Task 18: judge faithfulness, cờ `--judge` và `--judge-model`. Mỗi báo cáo đã giữ sẵn `facts_block` cho judge.
- Task 19: hiệu chỉnh judge với người chấm trên 30 câu.
- Task 21: câu báo cáo bị cờ, bị sửa hay bị xoá ở production thành task nháp; tỉ lệ `report_flagged_rate`.
- Task 22: sàn `dropped_pct` = 0; sàn faithfulness ≥ 0.95 chỉ khi judge đã được tin.
- Design mục 5.9 muốn đếm riêng output hợp schema, hỏng schema, bị cắt. Build plan không có task cho việc này.

## Chạy

```bash
uv run python tests/eval/run.py --agent 09 --backend fake --runs 3
```

- `--backend fake` dùng `agents.oracle_09`: viết mỗi dòng số liệu thành một câu tự trích nó. Điểm luôn 1.0.
- `--only "HS-01 day 2026-10-14"` chỉ chạy kỳ đó. Khoá của kỳ là trường `key`.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 24 lời gọi, khoảng $0.39.
