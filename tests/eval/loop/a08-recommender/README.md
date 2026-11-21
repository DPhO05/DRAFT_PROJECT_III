# a08 Recommender: vòng đánh giá

**TL;DR:** 08 không gọi LLM. `select.rank_problems` chọn bài cho phiếu theo ba nhóm: ôn, vừa sức, thử thách. Hôm nay 08 chưa
có target eval. Nó chỉ có test pytest cho các luật chọn bài. Target `--agent 08` với chỉ số xếp hạng là Task 16.

- Code của agent: `src/tutor/agents/a08_recommender/select.py` (`select.rank_problems`, `select.BUCKETS`).
- Ai gọi 08: công cụ `rank_problems` của 00 (`tools.Toolbox`). G4 kiểm nhóm của từng bài (`src/tutor/graphs/worksheet.py`).
- Code tất định: chạy k lần cho cùng kết quả, không cần judge (design mục 2, phạm vi đã cắt).

## Đánh giá cái gì

- Luật chọn bài: không lặp bài gần đây, đúng lớp, đúng tỉ lệ nhóm, đủ kỹ năng.
- Sau Task 16: phiếu có chứa các bài mà chủ dự án đánh dấu là liên quan không (P@n, recall@n).

## Năm bước

| bước | với 08 hôm nay | sau build plan |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | các ca test trong `tests/services/test_select.py` | Task 16: 5 hồ sơ học sinh |
| [2 Environment](2-environment/README.md) | fixture pytest | Task 16: `agents.trials` với fake không trả lời gì |
| [3 Trials & traces](3-trials-traces/README.md) | k = 1, không có trace | Task 16: k = 1, 0 lời gọi |
| [4 Graders](4-graders/README.md) | `assert` của pytest | Task 16: `passed_08`, `score_08` |
| [5 Scorecard](5-scorecard/README.md) | không có dòng | Task 16, 17: dòng `08-dev` và dòng test code |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | phiếu có đủ n bài, hoặc có cảnh báo khi ngân hàng thiếu bài hợp | test pytest; Task 16 thêm `passed_08` |
| Trajectory | không áp dụng: một hàm, không có bước trung gian | không có |
| Component | luật chọn bài | có: `tests/services/test_select.py` |
| Component | P@n và recall@n so với danh sách bài liên quan | chưa có: Task 16 |

## Chưa có

- Task 16: `tests/eval/tasks/reco_08.json`, `components.evaluate_08`, `--agent 08`, chỉ số `p_at_n`, `recall_at_n`, `must_not_hits`.
- Task 17: dòng scorecard cho test code của 08, khai báo trong `tests/eval/workflows.json`.
- Nhãn liên quan phải do chủ dự án duyệt. Nhãn suy từ chính luật của `select.py` thì chỉ số là vòng tròn (design mục
  5.8).

## Chạy

08 chưa có target trong `run.TARGETS`. Lệnh hôm nay chạy test của luật chọn bài:

```bash
uv run pytest tests/services/test_select.py -q
```

- Không có lời gọi model, nên không có `--backend real` và không tốn tiền.
- Sau Task 16: `uv run python tests/eval/run.py --agent 08`. Target này luôn chạy 1 lần và không cần `--yes`.
