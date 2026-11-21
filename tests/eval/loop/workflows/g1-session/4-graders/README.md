# G1 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Nhãn gài là verifier của từng bài.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.score` | outcome, component | `precision`, `recall`, `first_wrong_step_acc`, `kappa`, `drop_rate`, `add_rate` của một run |
| `metrics.g1_passed` | outcome | mỗi bài: bước sai đầu tiên đúng không; đầu vào của pass^k |
| `metrics.stability` | component | `pass_k`, `items_changed_pct` qua các run |
| `errors` trong `run.evaluate` | outcome | thread không tới cổng: `flow_errors` |

- Trajectory: chưa có. Task 15 thêm thứ tự 02, 03, 04 và số lời gọi mỗi file, đọc từ `llm.jsonl`.
- Bước kéo theo (`propagates_to`) không bắt buộc, nhưng đề xuất ở đó không tính là thừa.
- Test: `tests/eval/test_harness.py::test_label_oracle_scores_perfect_and_stable`, `tests/eval/test_harness.py::test_wrong_oracle_metrics_drop`.
- Test pytest ngoài eval: `tests/graphs/test_session.py` (commit), `tests/graphs/test_no_write_before_review.py` (không ghi trước cổng).

## Check "khớp với người chấm"

- Nhãn do chủ dự án gài. Grader so khớp bằng code, không cần judge.
- Design mục 7.4: trước khi tin một scorecard thật, chủ dự án đọc mọi trial trượt và xem lại nhãn của bộ held-out.
  Chưa có công cụ cho việc này.
