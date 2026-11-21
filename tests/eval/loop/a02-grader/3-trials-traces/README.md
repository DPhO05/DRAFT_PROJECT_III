# a02 · Bước 3: Trials & traces

- k = `--runs` của G1, mặc định 3.
- Trace: `run<k>.jsonl` của G1. Các dòng của 02 có `agent` = `02`, cùng `thread_id` với cả buổi chấm.
- Kết quả đạt hay không của từng mục nằm trong khoá `items` của mỗi bài trong file kết quả (`run._one` đọc
  `lane["grade"]["items"]`).
- Check "ổn định qua các lần": `items_changed_pct` là % mục rubric có kết quả khác nhau giữa các run. Bài thiếu ở một
  run tính là đổi.
- Giới hạn: một dòng log không có trường lane. Task 15 sẽ nhóm dòng theo khối `Đề:` của phần `user`.
- Trạng thái check: chưa đạt. Chưa đo với model thật; model giả (`--backend fake`) luôn cho pass^k = 1.000.
  Chạy thật là design T18 đến T21, ngoài build plan.
- Số thật duy nhất của 02: lần chạy thật 2026-11-04 trên `s01.tex` và `s04.tex` cho 48.9 % mục rubric đổi điểm (design mục 1.3).
