# a09 · Bước 4: Graders

Chỉ có grader code, trong `tests/eval/metrics.py`.

| hàm | mức | kiểm gì |
|---|---|---|
| `metrics.passed_09` | outcome, trajectory | không câu `dropped`; số câu theo `metrics.SENTENCES`; chữ sạch; `leaks` = 0; `model_calls` ≤ 2 |
| `metrics.text_ok_09` | outcome | không câu nào có mã số liệu `F01`, mã học sinh, mã bài, dấu % |
| `metrics.score_09` | component | `draft_flagged_pct`, `dropped_pct`, `passed`, `flags` theo loại |

- Phần "câu trích số liệu có thật, số khớp số liệu" do audit của app làm (`audit.check_sentence`). Eval không chấm
  lại, chỉ đọc kết quả audit.
- Test grader: `tests/eval/test_metrics.py::test_passed_09_needs_no_drop_and_the_sentence_range`,
  `tests/eval/test_metrics.py::test_text_ok_09_refuses_ids_codes_refs_and_percent`.
- Câu sai số bị viết lại rồi bị bỏ: `tests/eval/test_agents.py::test_09_bad_number_is_dropped_after_one_rewrite`.

## Check "khớp với người chấm"

- Chưa có. Task 18 thêm judge faithfulness. Task 19 so judge với người chấm.
- Ngưỡng tin judge là quyết định 5, chưa chốt. Build plan mặc định kappa ≥ 0.61, alignment ≥ 0.85, recall `not_supported`
  ≥ 0.80.
