# a02 · Bước 4: Graders

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.stability` | component | `items_changed_pct`: % mục rubric đổi kết quả giữa các run |
| `metrics.components` | component | `evidence_02`: share bằng chứng là chuỗi con nguyên văn của bài (`metrics.quoted`) |
| `metrics.components` | outcome | `clean_full_marks`: share bài sạch được điểm tối đa; `flags`: số cờ theo loại |
| `metrics.trajectory` | trajectory | `retries`, `schema_errors`, `by_agent`, `order_ok` (02 trước 03 trước 04) |
| `metrics.passed_02r` | outcome, trajectory | mục `r1`, `r2`, ... theo thứ tự; mỗi mục điểm > 0; `max_score` bằng tổng; `model_calls` = 1 |
| `metrics.score_02r` | component | `n_tasks`, `passed` |

- `metrics.components` trả một dict mỗi run, nằm ở khoá `metrics.components` của file kết quả G1.
- Test grader: `tests/eval/test_metrics.py::test_stability_items_changed_and_pass_k`, `tests/eval/test_metrics.py::test_components_hand_example`,
  `tests/eval/test_metrics.py::test_passed_02r_checks_ids_points_and_total`.
- Rubric nháp hỏng schema thì task trượt: `tests/eval/test_components.py::test_02r_schema_failure_fails_the_task`.

## Check "khớp với người chấm"

- Chưa đo được. Không có nhãn của người cho từng mục rubric. `metrics.components` chỉ kiểm bằng chứng có nằm trong bài, không kiểm
  mục đó đạt đúng hay sai.
- Số `items_changed_pct` chỉ nói 02 ổn định hay không, không nói 02 đúng hay sai.
