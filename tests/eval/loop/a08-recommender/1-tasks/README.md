# a08 · Bước 1: Tasks

## Hồ sơ xếp hạng

- File: `tests/eval/tasks/reco_08.json`, 5 task, đọc vào `components.TASKS_08`. Mọi task là synthetic.

| trường | nghĩa |
|---|---|
| `id` | tên hồ sơ: `new`, `repeat`, `solid`, `used-up`, `grade8` |
| `status` | `draft`: nhãn chưa được chủ dự án duyệt |
| `grade`, `n` | lớp của học sinh; số bài trên phiếu (6) |
| `theta` | mức thạo từng kỹ năng của hồ sơ |
| `repeats`, `done` | lỗi lặp; bài đã làm và cách đây mấy ngày |
| `relevant` | bài mà chủ dự án muốn thấy trên phiếu |
| `must_not` | bài không được chọn |

## Câu tìm

- File: `tests/eval/tasks/search_00.json`, 6 câu `s1` đến `s6`, đọc vào `components.SEARCH_00`. Mỗi câu có `text`, `relevant` và `status: draft`.
- Công cụ `search_problems` của 00 trả tối đa 5 bài cho mỗi câu.

## Cũng có

- Các ca test trong `tests/services/test_select.py` kiểm luật chọn bài. Công cụ `rank_problems` của 00 có test riêng:
  `tests/agents/test_tools.py::test_rank_problems_outcome`.
- Task `q5` và `q16` của 00 có gọi `rank_problems`, nhưng chỉ kiểm đối số, không kiểm bài được chọn.
- Test: `tests/eval/test_components.py::test_08_tasks_name_bank_problems`.
- Check "bao phủ cách dùng thật": chưa đạt. Hồ sơ là bản tự soạn, và nhãn còn nháp: xem `tests/eval/loop/a08-recommender/README.md`.
