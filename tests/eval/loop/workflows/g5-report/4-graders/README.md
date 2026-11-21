# G5 · Bước 4: Graders

Một trial đạt khi cả ba đều đúng:

| kiểm | mức | ở đâu |
|---|---|---|
| `metrics.passed_09` của bản nháp | outcome, trajectory | `tests/eval/metrics.py` |
| `gate` là True: thread tới `gate_report` | outcome | `agents._draft_g5` |
| `report_rows` = 0: chưa ghi trước khi duyệt | trajectory | `agents.evaluate_g5` |

- Phần sau cổng chỉ có test pytest: `tests/graphs/test_report.py`.
- Check "khớp với người chấm": chưa có. Judge faithfulness là Task 18, dùng chung với 09.
