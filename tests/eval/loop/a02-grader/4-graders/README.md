# a02 · Bước 4: Graders

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.stability` | component | `items_changed_pct`: % mục rubric đổi kết quả giữa các run |

- Test grader: `tests/eval/test_metrics.py::test_stability_items_changed_and_pass_k`.
- Chưa có grader outcome và trajectory cho 02. Xem mục "Chưa có" của `tests/eval/loop/a02-grader/README.md`.

## Check "khớp với người chấm"

- Chưa đo được. Không có nhãn của người cho từng mục rubric.
- Số `items_changed_pct` chỉ nói 02 ổn định hay không, không nói 02 đúng hay sai.
