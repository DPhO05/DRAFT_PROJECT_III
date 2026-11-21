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

## Judge faithfulness

- `judges.faithfulness` (`tests/eval/judges.py`) nhận `facts_block` và các câu của báo cáo, trả `supported`, `not_supported` hoặc `unknown`
  cho từng câu, kèm lý do. `score` là số câu `supported` chia số câu. Judge không chấm giọng văn hay độ dài.
- Chạy khi có `--judge`. Với `real` cần thêm `--judge-model`; cùng nhà cung cấp với model được chấm thì có cảnh báo.
- Judge lỗi (`llm.LLMUnavailable`) ghi `error` và `judge_errors`, task không trượt. Câu hỏng schema thành `unknown`.
- Test: `tests/eval/test_agents.py::test_09_judge_scores_every_report`, `tests/eval/test_agents.py::test_09_judge_error_changes_nothing_else`,
  `tests/eval/test_judges.py`.

## Check "khớp với người chấm"

- `tests/eval/calibrate.py` đo judge với người chấm trong ba lệnh:
  - `sample --from RESULT.json --n 30`: lấy 30 câu từ file kết quả có judge, nửa `supported`, nửa `not_supported`. Thiếu câu
    `not_supported` thì làm thêm bằng cách sửa sai một câu đúng (`calibrate.wrong`). Ghi `<ngày>-human.csv` và
    `<ngày>-judge.json`. Id mờ (`s01`, ...) để người chấm không biết câu nào bị sửa. Không ghi đè file đã chấm.
  - `judge HUMAN.csv JUDGE.json`: judge chấm các câu trong CSV. `--backend real` cần `--yes` và `--judge-model`.
  - `score --human FILE JUDGE.json`: in `alignment`, `kappa`, bảng 2x2, `recall(not_supported)` và `TIN` hay `CHƯA TIN`.
- Ngưỡng mặc định: kappa ≥ 0.61, alignment ≥ 0.85, recall `not_supported` ≥ 0.80. Đổi bằng `--kappa`, `--alignment`, `--recall`.
  Ngưỡng tin judge là quyết định 5, chưa chốt.
- Tên học sinh gõ vào CSV bị che trước khi tới judge: `tests/eval/test_calibrate.py::test_judge_masks_a_student_name_typed_in_the_csv`.
- Chưa có người chấm nào. `calibrate.py score` chỉ in kết quả, không ghi `judge_trusted`: chủ dự án tự đặt giá trị này trong
  `tests/eval/baseline.json` sau khi đọc kết quả.
