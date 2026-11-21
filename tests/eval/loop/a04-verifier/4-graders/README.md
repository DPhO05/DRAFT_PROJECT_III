# a04 · Bước 4: Graders

Chỉ có grader code, so khớp chính xác, trong `tests/eval/metrics.py`.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.passed_04` | outcome, trajectory | verdict bằng `expect`; mã gợi ý đúng khi `wrong_code`; `model_calls` = 1 |
| `metrics.score_04` | component | `accuracy`, `recall_disagree`, `empty`, `confusion` |

- Test grader: `tests/eval/test_metrics.py::test_score_04_accuracy_confusion_and_disagree_recall`.
- Agent luôn `agree` bỏ sót mọi kết luận sai: `tests/eval/test_components.py::test_04_always_agree_misses_every_wrong_conclusion`.
- Check "khớp với người chấm": verdict mong đợi do người viết. Không cần judge.
