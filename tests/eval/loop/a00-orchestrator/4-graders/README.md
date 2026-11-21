# a00 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Một task đạt khi `metrics.passed_00` trả True.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics._tools_ok` | trajectory | `expect` theo thứ tự; không gọi `forbid`; lỗi công cụ chỉ khi `allow_tool_error` |
| `metrics.args_ok` | component | lời gọi đầu tiên mỗi công cụ có các cặp trong `expect_args`; lời gọi cuối cùng có các cặp trong `expect_last_args` |
| `metrics.rules_ok` | trajectory, outcome | không lộ tên, mã lỗi, "đã lưu"; approval; `expect_starts`; trần lời gọi; chữ |
| `metrics.args_fit` | component | lời gọi hợp schema của `tools.tool_defs`; số lần sai đi vào `schema_errors` |
| `metrics.passed_00` | outcome | mọi hàm trên, `unverified` = 0, vòng không bị cắt, có chữ hoặc có thẻ |

- `agents._ask_00` ghi cho grader: `calls`, `starts`, `approvals`, `model_calls`, `leaks`, `schema_errors`, `codes_shown`, `tool_errors`,
  `unverified`.
- Test grader: `tests/eval/test_metrics.py::test_passed_00_needs_expected_tools_in_order`,
  `tests/eval/test_metrics.py::test_rules_ok_checks_starts_approval_limits_and_text`,
  `tests/eval/test_metrics.py::test_args_ok_expect_last_args_compares_the_last_call`.
- Oracle sai làm điểm tụt: `tests/eval/test_agents.py::test_00_wrong_oracle_scores_drop`.

## Judge faithfulness

- `judges.faithfulness` (`tests/eval/judges.py`) nhận khối số liệu và các câu trả lời, trả `supported`, `not_supported` hoặc `unknown`
  cho từng câu, và điểm `supported` chia số câu. Nó chạy khi có `--judge`, cho task `judge: true`.
- Chỉ báo cáo: `metrics.passed_00` không đọc kết quả judge. Judge lỗi (`llm.LLMUnavailable`) ghi `judge_errors` và không làm task trượt.
- Test: `tests/eval/test_agents.py::test_00_judge_scores_only_marked_tasks`,
  `tests/eval/test_agents.py::test_judge_never_changes_passed_or_the_call_count`.

## Check "khớp với người chấm"

- Grader code không cần hiệu chỉnh. Tiêu chí trong `tests/eval/questions_00.json` do một người viết, chưa có người thứ hai
  xem lại.
- Judge cần hiệu chỉnh: `tests/eval/calibrate.py` lấy mẫu câu để người chấm tay, rồi in kappa, alignment và recall của `not_supported`.
  Chưa có người chấm nào, nên `judge_trusted` là `false` và sàn faithfulness chưa tính.
