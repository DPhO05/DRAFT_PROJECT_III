# a09 · Bước 1: Tasks

- Task là 6 kỳ báo cáo trong `agents.PERIODS` (`tests/eval/agents.py`). Không có file JSON riêng.
- Input của 09 là số liệu của kỳ: `facts.report_facts` tính từ DB của thế giới. Tiêu chí đạt là luật chung của
  `metrics.passed_09`, không ghi trong từng task.

| `key` | học sinh | kỳ | thử gì |
|---|---|---|---|
| `HS-01 month 2026-10-01` | HS-01 | tháng | kỳ tháng có 2 buổi |
| `HS-01 week 2026-10-12` | HS-01 | tuần | có số liệu tuần trước |
| `HS-02 day 2026-10-14` | HS-02 | ngày | học sinh chỉ có 1 buổi |
| `HS-01 day 2026-10-14` | HS-01 | ngày | có số liệu ngày trước |
| `HS-01 week 2026-10-05` | HS-01 | tuần | không có tuần trước |
| `HS-02 week 2026-10-12 low` | HS-02 | tuần | kết quả thấp: `low_pass_rate` = 0.6 |

- Không kỳ nào của thế giới là "thấp" ở ngưỡng mặc định 0.5, nên kỳ cuối nâng ngưỡng (build plan, sửa lỗi
  số 7).
- Test: `tests/eval/test_agents.py::test_09_periods_cover_low_previous_and_no_previous`.
- Check "bao phủ cách dùng thật": chưa đạt. Thế giới là dữ liệu test, không phải buổi học thật.
