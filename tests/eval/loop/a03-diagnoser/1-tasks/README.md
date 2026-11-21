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
- Task từ production: `harvest.sessions` (`tests/eval/harvest.py`) ghi `g1/<thread_id>.tex` (đã che tên) và `g1/labels.json` với
  `source: production`, `status: draft`, `signals`. Nhãn của task là quyết định của gia sư: mã lỗi bị bỏ (`rejected`) không thành nhãn.
  Chỉ buổi đã `committed` có ít nhất một đề xuất được sửa, bỏ hoặc thêm tay mới được gom. Chưa chạy trên dữ liệu thật.
