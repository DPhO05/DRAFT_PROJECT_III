# Chat · Bước 3: Trials & traces

- k = `--runs`, mặc định 3, chung với 00.
- `run<k>-chat.json`: với mỗi task, `events` (chữ, công cụ, thẻ, nguồn, `approval`, `warning`, `done`) và `messages` của thread
  sau lượt cuối.
- `run<k>.jsonl`: các lời gọi model của 00. Task `by_code` không có dòng nào.
- Kết quả mỗi task giữ `approvals` (tên và đối số chờ duyệt) và `starts` (lệnh bản ghi âm nhận).
- Check "ổn định qua các lần": pass^k của 00. Chưa tách pass^k theo nhóm task chat.
- Trạng thái check: chưa đạt. Chưa đo với model thật; model giả (`--backend fake`) luôn cho pass^k = 1.000.
  Chạy thật là `--backend real --yes` hoặc `--suite`; chưa có lần chạy nào.
