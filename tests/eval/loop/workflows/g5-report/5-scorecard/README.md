# G5 · Bước 5: Scorecard

- File kết quả trong `--out`, mặc định `data/eval/results/`, tên `<created>_<prompt_version của 09>.json`.
- Khoá `per_run`: `metrics.score_09` của bản nháp. Khoá `pass_k`, `success`, `tally`, `extra.name_leaks`, `calls` qua `agents.summarize`.
- Với `--judge`, khoá `extra`: `faithfulness`, `judge_unknown`, `judge_errors`.
- `tests/eval/scorecard.py` in dòng `g5-dev` với chỉ số chính `dropped_pct`, `name_leaks`. Với `--with-tests` có thêm dòng `G5-tests`.

## Cổng

- `name_leaks` = 0 là sàn cứng cho mọi dòng. Không có sàn `dropped_pct` hay faithfulness cho `g5-dev` (chúng gắn với `09-dev`).
- Cổng tầng 0: `tests/eval/test_gate.py` chạy g5 với oracle và judge giả.

## Check "khớp production"

- `harvest.reports` đọc khoá `audit` của báo cáo thật: `writer` là bản nháp của 09, `approved` là bản gia sư duyệt. Chưa chạy trên
  dữ liệu thật.
