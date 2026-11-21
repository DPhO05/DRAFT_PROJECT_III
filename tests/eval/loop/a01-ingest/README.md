# a01 Ingest: vòng đánh giá

**TL;DR:** 01 cắt bài bằng code và chỉ gọi model khi bài không ghi mã hoặc ghi mã lạ, để tìm bài giống nhất trong
ngân hàng. Eval đo phần có model đó: 10 bài không mã, chạy k = 3 lần, chấm bằng code.

- Code của agent: `src/tutor/agents/a01_ingest/ingest.py` (`ingest.run`, `ingest.MatchResult`).
- Code eval: `components.evaluate_01`, `components._match_01`, `components.oracle_01` trong `tests/eval/components.py`.
- Test của eval: `tests/eval/test_components.py`, các test tên `test_01_...`.

## Đánh giá cái gì

- Bài không có mã: 01 có chọn đúng mã trong ngân hàng không.
- Bài không có trong ngân hàng: 01 có để trống mã và gắn cờ `low_match` không.
- Phần cắt bài, cắt bước là code tất định. Nó đã có test riêng: `tests/agents/test_ingest.py`,
  `tests/agents/test_ingest_fixtures.py`, `tests/services/test_latex.py`. Eval không chạy lại phần đó.

## Năm bước

| bước | với 01 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | 10 bài `tests/eval/tasks/ingest_01.json`: 8 có trong ngân hàng, 2 ngoài | riêng |
| [2 Environment](2-environment/README.md) | thế giới mới mỗi run; ngân hàng `data/dummy/bank`, chỉ đọc | `agents.trials` chung |
| [3 Trials & traces](3-trials-traces/README.md) | k = `--runs`; trace `run<k>.jsonl` | chung |
| [4 Graders](4-graders/README.md) | chỉ code: `metrics.passed_01` | riêng |
| [5 Scorecard](5-scorecard/README.md) | `metrics.score_01`: hit@1, hit@3, MRR, độ chính xác của cờ | `agents.summarize` chung |

## Ba mức grader

| mức | kiểm gì | hàm hoặc trường |
|---|---|---|
| Outcome | mã chọn bằng `expect_ref`; bài ngoài ngân hàng có cờ `low_match` | `metrics.passed_01` |
| Trajectory | đúng 1 lời gọi model cho mỗi bài | `model_calls` = 1 trong `metrics.passed_01` |
| Component | hit@1, hit@3, MRR của danh sách ứng viên | `metrics.score_01` |
| Component | không mã ứng viên nào nằm ngoài ngân hàng | `bad_candidates` = 0 |
| Component | trong các bài có cờ `low_match`, bao nhiêu thật sự ngoài ngân hàng | `low_match_precision` |

## Cổng

- `tests/eval/gate.py` xét `01-dev`: `hit_at_1` ≥ 0.90, và luật không tụt cho `hit_at_1`, `hit_at_3`, `mrr`, `passed`.
- Cổng tầng 0: `tests/eval/test_gate.py` chạy 01 với oracle.
- Phiên bản prompt của 01 có hai bản (một mỗi lớp). `gate.unverified` so từng phiên bản với scorecard thật.

## Chưa có

- Chạy thật: chưa có lần chạy `--backend real` của 01. Chưa có baseline thật cho luật không tụt.
- Design mục 5.2 muốn đo "0 lời gọi cho bài có mã hợp lệ". Bộ task hôm nay chỉ có bài không mã, nên trường hợp
  này chưa được đo.

## Chạy

```bash
uv run python tests/eval/run.py --agent 01 --backend fake --runs 3
```

- `--backend fake` dùng `components.oracle_01`: một ứng viên đúng ở điểm 0.95, hoặc không ứng viên nào. Điểm luôn 1.0.
- `--only m1 m9` chỉ chạy các task đó. Suite `compact` chạy `m1` đến `m4`, `m9`, `m10`.
- Chạy thật cần `--backend real --yes` và tốn tiền. Design mục 11.2 ước tính 30 lời gọi, khoảng $0.79: prompt của 01
  chứa đề của cả một lớp.
