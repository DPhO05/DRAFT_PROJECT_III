# a04 Verifier: vòng đánh giá

**TL;DR:** 04 kiểm lại từng kết luận lỗi của 03 và trả `agree`, `wrong_code` hoặc `disagree`. Eval cho 04 chạy một mình
trên 12 kết luận cố định, k = 3 lần, chấm bằng code so khớp verdict.

- Code của agent: `src/tutor/agents/a04_verifier/verifier.py` (`verifier.run`, `verifier.VerdictOut`).
- Code eval: `components.evaluate_04`, `components._verify_04`, `components.oracle_04` trong `tests/eval/components.py`.
- Test của eval: `tests/eval/test_components.py`, các test tên `test_04_...`.

## Đánh giá cái gì

- Với kết luận đúng: 04 có `agree` không.
- Với kết luận sai bước: 04 có `disagree` không. Đây là việc chính của 04.
- Với kết luận đúng bước, sai mã: 04 có trả `wrong_code` và đúng mã gợi ý không.
- Trong G1, 04 chỉ thấy kết luận 03 đưa ra, nên G1 không thử được kết luận sai. Bộ 12 kết luận cố định lấp
  chỗ đó (design mục 5.5).

## Năm bước

| bước | với 04 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | 12 kết luận trong `tests/eval/tasks/verifier_04.json`: 6 đúng, 3 sai bước, 3 sai mã | riêng |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run; đề, bảng mã đọc từ DB | `agents.trials` chung |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl` | chung |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.passed_04` | riêng |
| [5 Scorecard](5-scorecard/README.md) | `metrics.score_04`: accuracy, `recall_disagree`, confusion 3 × 3 | `agents.summarize` chung |

## Ba mức grader

| mức | kiểm gì | hàm hoặc trường |
|---|---|---|
| Outcome | verdict bằng `expect` | `metrics.passed_04` |
| Trajectory | đúng 1 lời gọi mỗi kết luận; verdict rỗng đếm riêng | `model_calls` = 1; `empty` của `metrics.score_04` |
| Component | trong các kết luận sai, 04 bắt được bao nhiêu | `recall_disagree` |
| Component | với `wrong_code`, `suggested_code` bằng `expect_code` | `metrics.passed_04` |
| Component | confusion matrix verdict mong đợi và verdict 04 trả | khoá `confusion` |

## Trong G1 và cổng

- Trong trial của G1, `metrics.components` có `agree_on_right` và `agree_on_wrong`: tỉ lệ `agree` của 04 trên đề xuất đúng nhãn và
  trên đề xuất sai nhãn. Xem `tests/eval/loop/a03-diagnoser/4-graders/README.md`.
- Cổng: `tests/eval/gate.py` có sàn `04-dev` `recall_disagree` ≥ 0.80 và luật không tụt cho `accuracy`, `recall_disagree`.

## Chưa có

- Chạy thật: chưa có lần chạy `--backend real` của 04, nên chưa biết `recall_disagree` thật so với sàn 0.80.

## Chạy

```bash
uv run python tests/eval/run.py --agent 04 --backend fake --runs 3
```

- `--backend fake` dùng `components.oracle_04`: trả đúng verdict mong đợi. Điểm luôn 1.0.
- `--only v7 v10` chỉ chạy các task đó.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 36 lời gọi, khoảng $0.27.
