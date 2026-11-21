# G1 buổi chấm bài: vòng đánh giá

**TL;DR:** G1 nhận file bài làm, chạy 01 rồi mỗi bài một lane 02, 03, 04, và dừng ở cổng `gate_review` chờ gia sư duyệt.
Eval chạy G1 thật trên file bài có lỗi gài, tới cổng đó, k = 3 lần, rồi so đề xuất với nhãn bằng code.

- Graph: `src/tutor/graphs/session.py` (`session.build`, `session.submit`).
- Node theo thứ tự: `ingest`, `prepare`, cổng `gate_confirm_match` khi có cờ, `lane` (`grade`, `diagnose`, `verify`), `queue`, cổng
  `gate_review`, `profile`, cổng `gate_confirm_commit`, `commit`.
- Code eval: `run.evaluate`, `run._one`, `run.oracle`, `run.load_labels`, `run.load_sets` trong `tests/eval/run.py`.
- Test của eval: `tests/eval/test_harness.py`.

## Đánh giá cái gì

- Đề xuất lỗi ở cổng `gate_review` so với lỗi gài: recall, precision, bước sai đầu tiên.
- Luồng có tới được cổng không, hay thread bị `failed`.
- Kết quả từng mục rubric có ổn định qua các run không.
- Phần sau cổng (`profile`, `commit`) không chạy trong eval. Nó có test pytest riêng.

## Năm bước

| bước | với G1 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | `g1-dev` 40 bài, `g1-heldout` 20 bài, khai báo trong `tests/eval/sets.json` | riêng |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run: DB, ngân hàng mẫu, `inbox`, `Runner` | vòng riêng |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl`; đề xuất trong khoá `problems` | chung |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.score`, `metrics.stability`, `metrics.g1_passed` | riêng |
| [5 Scorecard](5-scorecard/README.md) | recall, precision, pass^k, `flow_errors`, chi phí | `metrics.tally`, `metrics.usage` chung |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | ở cổng `gate_review`: recall, precision của lỗi gài; bài sạch có 0 đề xuất | có: `metrics.score` |
| Outcome | luồng tới cổng, không thread nào `failed` | có: `errors`, `flow_errors` |
| Outcome | `commit` ghi đúng dòng sau quyết định mẫu | test pytest `tests/graphs/test_session.py` |
| Trajectory | không ghi DB trước cổng duyệt | test pytest `tests/graphs/test_no_write_before_review.py` |
| Trajectory | lane gọi 02, 03, rồi 04; lời gọi mỗi file trong `max_calls`; dừng đúng lúc ở `gate_confirm_match` | Task 15 |
| Component | các kiểm tra của 01, 02, 03, 04 | xem `tests/eval/loop/a01-ingest/` đến `tests/eval/loop/a04-verifier/` |

## Chưa có

- Task 13: chỉ số component của 02 và 03, và `name_leaks` cho G1.
- Task 15: `metrics.trajectory`: `order_ok`, `over_budget`, `retries`, `schema_errors`, `confirm_ok`.
- Task 17: hai test pytest trên lên scorecard.
- Task 20: buổi chấm đã duyệt ở production thành task nháp, nhãn theo quyết định của gia sư.
- Task 22: sàn `flow_errors` = 0, `recall` ≥ 0.90, `precision` ≥ 0.75.
- Task 24: bộ chạy thật `full` và `compact`.

## Chạy

```bash
uv run python tests/eval/run.py --agent g1 --set g1-dev --backend fake --runs 3
uv run python tests/eval/run.py --agent g1 --set g1-heldout --backend fake --runs 3
```

- `--backend fake` dùng `run.oracle`: 03 trả đúng nhãn, 04 luôn `agree`. Điểm luôn 1.0.
- `--files s01.tex s04.tex` chỉ chạy các file đó. `--only` không dùng cho g1.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 102 lời gọi, khoảng $1.01 cho
  `--files s01.tex s04.tex` (9 bài). Bộ `g1-heldout` khoảng 189 lời gọi, $1.87.
- `g1-dev` không có `--files` chạy cả 40 bài. Design không có ước tính cho cỡ này.
