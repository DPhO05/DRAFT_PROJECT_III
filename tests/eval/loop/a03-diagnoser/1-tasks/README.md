# a03 · Bước 1: Tasks

03 dùng bài của G1 (`tests/eval/sets.json`). Nhãn nằm trong `labels.json` của mỗi bộ.

| set | `labels.json` | bài | lỗi gài |
|---|---|---|---|
| `g1-dev` | `tests/fixtures/submissions/labels.json` | 40 | 21 |
| `g1-heldout` | `tests/eval/tasks/g1-heldout/labels.json` | 20 | 12 |

Một lỗi gài trong `problems[].mistakes` có:

| trường | nghĩa |
|---|---|
| `step_idx` | bước sai |
| `code` | mã lỗi đúng |
| `kc` | kỹ năng |
| `propagates_to` | các bước sai kéo theo; 03 đề xuất ở đó không tính là thừa |

- Bài không có lỗi gài là bài sạch: 03 không được đề xuất gì.
- Check "bao phủ cách dùng thật": chưa đạt. Mọi bài là tự soạn có lỗi gài (`source: synthetic`).
- Bộ `g1-heldout` không dùng để sửa prompt (design mục 6.1).
