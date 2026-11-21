# a01 · Bước 3: Trials & traces

- k = `--runs`, mặc định 3. Mỗi run chạy 10 task theo thứ tự.
- Trace: `run<k>.jsonl` trong thư mục `--traces`, mặc định `data/eval/traces/<stamp>_01/`. Một dòng một lời gọi 01.
- `components._match_01` đọc trường `output` của dòng log để đếm ứng viên ngoài ngân hàng (`bad_candidates`).
- Check "ổn định qua các lần": pass^k qua `metrics.tally`; task thiếu ở một run tính là trượt.
- Trạng thái check: chưa đạt. Chưa đo với model thật; model giả (`--backend fake`) luôn cho pass^k = 1.000.
  Chạy thật là design T18 đến T21, ngoài build plan.
