# a00 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`. Một task đạt khi `metrics.passed_00` trả True.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics._tools_ok` | trajectory | `expect` theo thứ tự; không gọi `forbid`; lỗi công cụ chỉ khi `allow_tool_error` |
| `metrics.args_ok` | component | lời gọi đầu tiên mỗi công cụ có các cặp trong `expect_args` |
| `metrics.rules_ok` | trajectory, outcome | không lộ tên, mã lỗi, "đã lưu"; approval; `expect_starts`; trần lời gọi; chữ |
| `metrics.args_fit` | component | lời gọi hợp schema của `tools.tool_defs`; số lần sai đi vào `schema_errors` |
| `metrics.passed_00` | outcome | mọi hàm trên, `unverified` = 0, vòng không bị cắt, có chữ hoặc có thẻ |

- `agents._ask_00` ghi cho grader: `calls`, `starts`, `approvals`, `model_calls`, `leaks`, `schema_errors`, `codes_shown`, `tool_errors`,
  `unverified`.
- Test grader: `tests/eval/test_metrics.py::test_passed_00_needs_expected_tools_in_order`,
  `tests/eval/test_metrics.py::test_rules_ok_checks_starts_approval_limits_and_text`.
- Oracle sai làm điểm tụt: `tests/eval/test_agents.py::test_00_wrong_oracle_scores_drop`.

## Check "khớp với người chấm"

- Grader code không cần hiệu chỉnh. Tiêu chí trong `tests/eval/questions_00.json` do một người viết, chưa có người thứ hai
  xem lại.
- Chưa có: Task 18 thêm judge faithfulness (`tests/eval/judges.py`). Task 19 đo judge với người chấm bằng kappa và alignment.
