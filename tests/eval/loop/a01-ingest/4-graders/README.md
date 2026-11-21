# a01 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.passed_01` | outcome, trajectory | `ref` = `expect_ref`; bài ngoài có `low_match`; `model_calls` = 1; `bad_candidates` = 0 |
| `metrics.score_01` | component | `hit_at_1`, `hit_at_3`, `mrr` trên bài có trong ngân hàng; `low_match_precision` |

- Test grader: `tests/eval/test_metrics.py::test_score_01_hit_mrr_and_flag_precision`.
- Ứng viên đầu sai thì chỉ hit@1 tụt: `tests/eval/test_components.py::test_01_wrong_first_candidate_drops_hit_at_1_only`.
- Check "khớp với người chấm": nhãn là mã bài, so khớp chính xác. Không cần judge. Nhãn của `m1` đến `m8` lấy từ
  `tests/fixtures/submissions/labels.json`.
