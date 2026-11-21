# Chat · Bước 4: Graders

Grader code của 00, trong `tests/eval/metrics.py`:

| hàm | mức | kiểm gì cho chat |
|---|---|---|
| `metrics.rules_ok` | outcome, trajectory | `expect_approval`; `starts` = `expect_starts`; trần lời gọi; `expect_text`, `expect_any` |
| `metrics._tools_ok` | trajectory | không gọi công cụ trong `forbid`; lỗi công cụ chỉ khi `allow_tool_error` |
| `metrics.passed_00` | outcome | có chữ, hoặc có thẻ khi `card_only` |
| `metrics.args_ok` | component | lời gọi đầu tiên của công cụ có các cặp trong `expect_args` (`q20`) |
| `metrics.score_00` | outcome | `approval_ok`: tỉ lệ đạt trên các task có `approval` |

- Kiểm tra approval là luật nhị phân của dự án. Nguồn không có chỉ số cho bước người duyệt (design mục 6.5).
- Test: `tests/eval/test_agents.py::test_00_calling_again_after_a_reject_fails`,
  `tests/eval/test_metrics.py::test_score_00_approval_ok_counts_only_answers_with_an_approval`.
- Check "khớp với người chấm": tiêu chí do người viết trong task. Không có judge.
