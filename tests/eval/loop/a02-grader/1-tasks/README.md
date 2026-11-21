# a02 · Bước 1: Tasks

02 không có bộ task riêng. Nó dùng bài của G1, khai báo trong `tests/eval/sets.json`:

| set | thư mục | bài |
|---|---|---|
| `g1-dev` | `tests/fixtures/submissions/` | 10 file, 40 bài; bản sao `s10-dup.tex` bị bỏ |
| `g1-heldout` | `tests/eval/tasks/g1-heldout/` | 10 file, 20 bài |

- Rubric của mỗi bài lấy từ ngân hàng mẫu. Khi bài thiếu rubric, G1 dừng ở `gate_confirm_match` và `run._answer` nhận
  rubric nháp của 02.
- `labels.json` hôm nay không có nhãn cho từng mục rubric. Chỉ có nhãn lỗi cho 03.
- Check "bao phủ cách dùng thật": chưa đạt. Mọi bài là synthetic.

## Task của rubric nháp

- File `tests/eval/tasks/rubric_02.json`, 4 task, đọc vào `components.TASKS_02R`. Mỗi task chỉ có `id`, là mã bài trong ngân hàng mẫu:
  `8DS-PTNT-003`, `8DS-PS-003`, `9DS-BPT-001`, `9DS-BPT-004`.
- Không có nhãn: tiêu chí là hình dạng của bản nháp (`metrics.passed_02r`), không phải nội dung rubric đúng.
- Mọi task là synthetic. Chưa có bài thật thiếu rubric.
