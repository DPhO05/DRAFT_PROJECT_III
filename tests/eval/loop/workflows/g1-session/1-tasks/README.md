# G1 · Bước 1: Tasks

Bộ bài khai báo trong `tests/eval/sets.json`. `run.load_sets` đọc file này, rồi đọc thêm `data/eval/sets.json` nếu có (bộ từ
dữ liệu thật, chỉ ở máy).

| set | thư mục | file | bài | lỗi gài | `split` |
|---|---|---|---|---|---|
| `g1-dev` | `tests/fixtures/submissions/` | 10, bỏ `s10-dup.tex` | 40 | 21 | `dev` |
| `g1-heldout` | `tests/eval/tasks/g1-heldout/` | 10 | 20 | 12 | `heldout` |

- Cả hai bộ có `source: synthetic`: bài tự soạn có lỗi gài. Bộ held-out chép từ kịch bản demo15, đã bỏ tên.
- Input là file `.tex`. Tiêu chí đạt là nhãn trong `labels.json` của mỗi thư mục.

| trường của một file | nghĩa |
|---|---|
| `problems[].seq`, `ref` | số thứ tự bài và mã bài đúng |
| `problems[].mistakes` | lỗi gài: `step_idx`, `code`, `kc`, `propagates_to` |
| `grade`, `student_name` | lớp; tên học sinh (held-out để `null`) |
| `expected_calls`, `max_calls` | chỉ ở held-out; `max_calls`: trần lời gọi mỗi thread, `metrics.trajectory` đọc; `expected_calls`: chưa ai đọc |

- `run.load_labels` bỏ các file có `duplicate_of`.
- Khác design mục 6.1: design ghi bộ dev là `s01.tex`, `s04.tex` (9 bài) và held-out có 10 lỗi gài. Code làm theo build Task 2:
  `g1-dev` trỏ cả thư mục (40 bài), held-out có 12 lỗi gài. Cỡ 9 bài là của lần chạy thật với `--files s01.tex s04.tex`.
- Test: `tests/eval/test_harness.py::test_committed_task_files_are_not_production_data`.
- Bộ `g1-heldout` không dùng để sửa prompt (design mục 6.1).
- Check "bao phủ cách dùng thật": chưa đạt. Repo chưa có bài làm thật. `harvest.sessions` (`tests/eval/harvest.py`) đưa buổi chấm đã duyệt
  về thành task nháp trong `data/eval/tasks/inbox/<ngày>/g1/`: file `.tex` đã che tên và `labels.json` (`source: production`, `status: draft`).
  Muốn chạy chúng, thêm bộ vào `data/eval/sets.json`: `run.load_sets` đọc file này (chỉ ở máy, không vào git)
  (`tests/eval/test_harvest.py::test_harvested_drafts_run_as_a_local_set`). Chưa chạy trên dữ liệu thật.
