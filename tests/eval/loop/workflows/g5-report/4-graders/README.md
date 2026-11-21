# G5 · Bước 4: Graders

Một trial đạt khi cả ba đều đúng:

| kiểm | mức | ở đâu |
|---|---|---|
| `metrics.passed_09` của bản nháp | outcome, trajectory | `tests/eval/metrics.py` |
| `gate` là True: thread tới `gate_report` | outcome | `agents._draft_g5` |
| `report_rows` = 0: chưa ghi trước khi duyệt | trajectory | `agents.evaluate_g5` |

- Component: không có dòng riêng. Component của G5 là của 09: `metrics.score_09` trên bản nháp
  (`tests/eval/loop/a09-reporter/4-graders/README.md`).
- Phần sau cổng chỉ có test pytest: `tests/graphs/test_report.py`.
- Test code của G5 trên scorecard: câu báo cáo không có mã số liệu (`tests/agents/test_reporter.py::test_fact_ids_never_in_text`) và
  file `.md` đã lưu không có họ tên (`tests/eval/test_workflows.py::test_saved_report_md_holds_no_student_name`).
- File `.md` đã lưu có thẻ mã số liệu như `[F01]`: `report.text_md` ghi chúng, và `test_approve_writes_report_and_md` kiểm điều đó.
  Chủ dự án cần xác nhận file gửi phụ huynh được mang các thẻ này.

## Judge

- Judge faithfulness dùng chung với 09 (`judges.faithfulness`): xem `tests/eval/loop/a09-reporter/4-graders/README.md`.
- Check "khớp với người chấm": chưa có người chấm cho judge, nên `judge_trusted` là `false`.
