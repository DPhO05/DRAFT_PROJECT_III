# a08 · Bước 1: Tasks

## Hôm nay

- Task là các ca test trong `tests/services/test_select.py`. Mỗi ca dựng `assistant_fix.world`, chỉnh ngân hàng hoặc hồ sơ, rồi
  kiểm một luật: tỉ lệ nhóm, không lặp bài, đúng lớp, kỹ năng, ngân hàng thiếu bài.
- Công cụ `rank_problems` của 00 có ca test riêng: `tests/agents/test_tools.py::test_rank_problems_outcome`.
- Task `q5` và `q16` của 00 có gọi `rank_problems`, nhưng chỉ kiểm đối số, không kiểm bài được chọn.

## Chưa có

- Task 16: `tests/eval/tasks/reco_08.json`, 5 hồ sơ học sinh. Mỗi hồ sơ có danh sách bài liên quan và bài không được chọn.
- Nhãn bắt đầu với `status: draft`. CLI cảnh báo khi còn nhãn nháp, vì chủ dự án chưa duyệt.
- Check "bao phủ cách dùng thật": chưa đạt.
