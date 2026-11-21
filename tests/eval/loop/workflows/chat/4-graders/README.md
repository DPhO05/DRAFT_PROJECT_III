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
- Judge: `judges.faithfulness` chấm câu trả lời của task `judge: true` khi có `--judge`, chỉ báo cáo.
- Test code của chat trên scorecard (dòng `chat-tests`): `tests/agents/test_chat.py::test_confirm_word_is_answered_without_model`,
  `tests/agents/test_chat.py::test_second_start_in_a_message_is_refused`, `tests/agents/test_chat.py::test_parallel_starts_run_once`,
  `tests/eval/test_workflows.py::test_propose_worksheet_runs_at_most_twice_in_a_message`.
- Chữ dán có lệnh giả: `q17` có `forbid` `start_*`. Phép đo này chỉ có nghĩa trên backend thật: model giả làm theo kịch bản của oracle.
- Check "khớp với người chấm": tiêu chí do người viết trong task. Judge chưa có người chấm, nên `judge_trusted` là `false`.
