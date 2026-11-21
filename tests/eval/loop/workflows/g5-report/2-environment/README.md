# G5 · Bước 2: Environment

## Dùng chung

- `agents.trials`: mỗi run một thư mục `work/run<k>`, `tutor.db` mới, `assistant_fix.world`.

## Riêng cho G5

`agents._draft_g5` chạy một kỳ:

- `Runner` thật từ `registry.make_runner`, như app. `report.start` mở thread G5 với ngày hôm nay của thế giới.
- Chờ thread tới cổng `gate_report`, rồi đọc bản nháp từ state (`runner.Runner.state`).
- Không có quyết định của gia sư. Cuối task, eval đếm dòng của bảng `report` bằng kết nối chỉ đọc.
- Phần "Lộ trình" của báo cáo do code viết, không gửi model.

## Check "sạch, không rò"

- Thread mới mỗi kỳ, thế giới mới mỗi run.
- Họ tên đếm bằng `agents.leak_count` trên log và trên câu, như 09.
