# G1 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Nhãn gài là verifier của từng bài.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.score` | outcome, component | `precision`, `recall`, `first_wrong_step_acc`, `kappa`, `drop_rate`, `add_rate` của một run |
| `metrics.g1_passed` | outcome | mỗi bài: bước sai đầu tiên đúng không; đầu vào của pass^k |
| `metrics.stability` | component | `pass_k`, `items_changed_pct` qua các run |
| `errors` trong `run.evaluate` | outcome | thread không tới cổng: `flow_errors` |
| `metrics.components` | component | bằng chứng nguyên văn, cờ, confusion matrix, `clean_full_marks`, `agree_on_right`, `agree_on_wrong` |
| `metrics.trajectory` | trajectory | `calls_max`, `over_budget`, `order_ok`, `retries`, `schema_errors`, `by_agent` |
| `confirm_ok` trong `run.evaluate` | trajectory | thread dừng ở `gate_confirm_match` đúng khi 01 gắn cờ |

- `over_budget` so số lời gọi mỗi thread với `max_calls` của nhãn. Một file hỏng vẫn có trần để so, nên không giấu thread vượt trần.
  Một file hỏng tính là không xác nhận trong `confirm_ok`.
- Bước kéo theo (`propagates_to`) không bắt buộc, nhưng đề xuất ở đó không tính là thừa.
- Test: `tests/eval/test_harness.py::test_label_oracle_scores_perfect_and_stable`, `tests/eval/test_harness.py::test_wrong_oracle_metrics_drop`,
  `tests/eval/test_harness.py::test_oracle_components_are_perfect`, `tests/eval/test_harness.py::test_heldout_trajectory_stays_in_budget`.
- Test pytest ngoài eval: `tests/graphs/test_session.py` (commit), `tests/graphs/test_no_write_before_review.py` (không ghi trước cổng).

## Check "khớp với người chấm"

- Nhãn do chủ dự án gài. Grader so khớp bằng code, không cần judge.
- Design mục 7.4: trước khi tin một scorecard thật, chủ dự án đọc mọi trial trượt và xem lại nhãn của bộ held-out.
  Chưa có công cụ cho việc này; `calibrate.py` chỉ dành cho judge.
