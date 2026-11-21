# a03 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Nhãn gài là verifier của từng bài.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.first_wrong_step` | outcome | bước nhỏ nhất 03 đề xuất bằng bước nhỏ nhất của nhãn; bài sạch: 0 |
| `metrics.score` | component | `precision`, `recall` trên tập bước sai; `drop_rate`, `add_rate`; `first_wrong_step_acc` |
| `metrics.cohen_kappa` | component | kappa giữa mã của nhãn và mã 03 chọn ở cùng bước |

- Trajectory: chưa có. Task 15 thêm thứ tự 02, 03, 04 và số lời gọi mỗi file, đọc từ `llm.jsonl`.
- Test grader: `tests/eval/test_metrics.py::test_score_hand_example`, `tests/eval/test_metrics.py::test_kappa_matches_hand_computed_3x3`.
- Oracle sai làm điểm tụt: `tests/eval/test_harness.py::test_wrong_oracle_metrics_drop`.

## Check "khớp với người chấm"

- Nhãn là "người": chủ dự án gài lỗi và ghi nhãn. Kappa đo 03 khớp với nhãn đó tới đâu.
- Chưa có người thứ hai xem lại nhãn. Design mục 7.4 muốn chủ dự án đọc lại nhãn của bộ held-out.
