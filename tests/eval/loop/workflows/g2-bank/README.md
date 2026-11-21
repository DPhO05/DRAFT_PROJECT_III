# G2 nhập ngân hàng bài: vòng đánh giá

**TL;DR:** G2 đọc file ngân hàng bài, dừng ở cổng `gate_confirm_import` chờ gia sư duyệt, rồi ghi bài vào DB. G2 không
gọi model. Eval của G2 là test pytest sẵn có, chạy 1 lần.

- Graph: `src/tutor/graphs/bank.py` (`start_import`, `build`). Node: `read`, cổng `gate_confirm_import`, `commit`.
- Đọc file: `read_bank` trong `src/tutor/services/bank.py`.
- Code tất định. Chạy k trial hay dùng judge không cho thêm thông tin (design mục 2, phạm vi đã cắt).

## Năm bước

| bước | với G2 |
|---|---|
| [1 Tasks](1-tasks/README.md) | các ca test với file ngân hàng mẫu |
| [2 Environment](2-environment/README.md) | fixture pytest: DB tạm mới mỗi test |
| [3 Trials & traces](3-trials-traces/README.md) | k = 1, không có trace model |
| [4 Graders](4-graders/README.md) | `assert` của pytest |
| [5 Scorecard](5-scorecard/README.md) | chưa có dòng; Task 17 |

## Ba mức grader

| mức | kiểm gì | test |
|---|---|---|
| Outcome | biên nhận nhập đúng số bài mới, bài trùng, bài hỏng | `tests/graphs/test_bank_graph.py::test_commit_receipt` |
| Trajectory | không ghi DB trước cổng | `tests/graphs/test_bank_graph.py::test_no_write_until_commit` |
| Trajectory | cổng không mở khi còn bài thiếu kỹ năng | `tests/graphs/test_bank_graph.py::test_resume_blocked_until_kc` |
| Component | đọc đúng từng bài của file ngân hàng | `tests/services/test_bank_read.py` |

## Chưa có

- Task 17: các test trên lên scorecard qua `tests/eval/workflows.json` và `tests/eval/test_workflows.py`.
- Khi 06 Tagger có code, G2 sẽ có lời gọi model và cần bộ task riêng (design mục 6.2). Chưa có task trong build plan.

## Chạy

G2 không có target trong `run.TARGETS`:

```bash
uv run pytest tests/graphs/test_bank_graph.py tests/services/test_bank_read.py -q
```

- Không có lời gọi model, nên không có `--backend real` và không tốn tiền.
