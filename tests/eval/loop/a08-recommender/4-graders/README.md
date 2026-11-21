# a08 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.passed_08` | outcome | đủ n bài hoặc có cảnh báo; không bài nào trong `must_not` |
| `metrics.score_08` | component | `p_at_n`, `recall_at_n`, `must_not_hits`, `passed` |

- Dùng P@n và recall@n vì phiếu là một tập bài. Thứ tự trên phiếu là thứ tự nhóm, nên MRR không hợp (design mục 5.8).
- Recall@5 của `search_problems` tính trong `components.evaluate_08`, không qua `metrics.score_08`.
- Test: `tests/eval/test_metrics.py::test_score_08_precision_recall_and_must_not`.
- Luật chọn bài vẫn do `assert` trong `tests/services/test_select.py` kiểm.
- Trajectory không áp dụng: một hàm, không có bước trung gian.

## Check "khớp với người chấm"

- Chưa đạt. Nhãn `relevant` còn nháp, chủ dự án chưa duyệt. Nhãn suy từ chính luật của `select.py` thì chỉ số là vòng tròn (design mục 5.8).
- Ba hồ sơ có 0/6 bài khớp nhãn. Xem "Việc của chủ dự án" trong `tests/eval/loop/a08-recommender/README.md`. Chưa tin được `p_at_n` và
  `recall_at_n` cho tới khi chủ dự án quyết định nhãn hay bộ xếp hạng.
