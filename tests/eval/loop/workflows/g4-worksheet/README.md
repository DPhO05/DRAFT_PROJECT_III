# G4 phiếu bài tập: vòng đánh giá

**TL;DR:** G4 giữ phiếu bài tập ở cổng `gate_worksheet` chờ gia sư duyệt, rồi ghi file `.tex` của phiếu và các dòng
`recommendation`. G4 không gọi model. Bài trên phiếu do 08 chọn. Eval của G4 là test pytest sẵn có, chạy 1 lần.

- Graph: `src/tutor/graphs/worksheet.py` (`build`, `propose`). Node: cổng `gate_worksheet`, `commit`.
- Bài thường đến từ `select.rank_problems` (agent 08) qua công cụ `rank_problems` của 00. Công cụ `propose_worksheet` mở
  phiếu nháp với các mã bài đó.
- Code tất định. Chạy k trial hay dùng judge không cho thêm thông tin.

## Năm bước

| bước | với G4 |
|---|---|
| [1 Tasks](1-tasks/README.md) | các ca test trong `tests/graphs/test_worksheet.py` |
| [2 Environment](2-environment/README.md) | fixture pytest: DB tạm mới mỗi test |
| [3 Trials & traces](3-trials-traces/README.md) | k = 1, không có trace model |
| [4 Graders](4-graders/README.md) | `assert` của pytest |
| [5 Scorecard](5-scorecard/README.md) | chưa có dòng; Task 17 |

## Ba mức grader

| mức | kiểm gì | test |
|---|---|---|
| Outcome | file `.tex` và dòng `recommendation` đúng quyết định | `tests/graphs/test_worksheet.py::test_commit_order_and_file` |
| Trajectory | không ghi DB trước cổng | `tests/graphs/test_worksheet.py::test_no_write_until_commit` |
| Component | 08 chọn bài | xem `tests/eval/loop/a08-recommender/README.md` |

## Chưa có

- Task 16: chỉ số xếp hạng của 08 (P@n, recall@n).
- Task 17: các test trên lên scorecard qua `tests/eval/workflows.json`.

## Chạy

G4 không có target trong `run.TARGETS`:

```bash
uv run pytest tests/graphs/test_worksheet.py -q
```

- Không có lời gọi model, nên không có `--backend real` và không tốn tiền.
