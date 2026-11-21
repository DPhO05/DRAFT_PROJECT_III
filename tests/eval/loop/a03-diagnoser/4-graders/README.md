# a03 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Nhãn gài là verifier của từng bài.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.first_wrong_step` | outcome | bước nhỏ nhất 03 đề xuất bằng bước nhỏ nhất của nhãn; bài sạch: 0 |
| `metrics.score` | component | `precision`, `recall` trên tập bước sai; `drop_rate`, `add_rate`; `first_wrong_step_acc` |
| `metrics.cohen_kappa` | component | kappa giữa mã của nhãn và mã 03 chọn ở cùng bước |
| `metrics.components` | component | `evidence_03`: share đề xuất có `evidence_latex` là chuỗi con của bước; `confusion`: mã nhãn và mã 03 chọn |
| `metrics.components` | component | `clean_flagged`: share bài sạch bị đề xuất; `flags`: cờ của `Diagnosis` theo loại |
| `metrics.components` | component | `agree_on_right`, `agree_on_wrong`: share `agree` của 04 trên đề xuất ở bước nhãn; ở bước ngoài nhãn |
| `metrics.trajectory` | trajectory | `calls_max`, `over_budget`, `retries`, `schema_errors`, `order_ok` (02 trước 03 trước 04) |

- `over_budget` so số lời gọi của mỗi thread với `max_calls` trong `labels.json`. Chỉ `g1-heldout` có trường này; `g1-dev` cho `None`.
- Test grader: `tests/eval/test_metrics.py::test_score_hand_example`, `tests/eval/test_metrics.py::test_kappa_matches_hand_computed_3x3`,
  `tests/eval/test_metrics.py::test_components_hand_example`, `tests/eval/test_metrics.py::test_trajectory_groups_lanes_and_counts_budget`.
- Held-out nằm trong trần lời gọi: `tests/eval/test_harness.py::test_heldout_trajectory_stays_in_budget`.
- Oracle sai làm điểm tụt: `tests/eval/test_harness.py::test_wrong_oracle_metrics_drop`.

## Check "khớp với người chấm"

- Nhãn là "người": chủ dự án gài lỗi và ghi nhãn. Kappa đo 03 khớp với nhãn đó tới đâu.
- Chưa có người thứ hai xem lại nhãn. Design mục 7.4 muốn chủ dự án đọc lại nhãn của bộ held-out.
