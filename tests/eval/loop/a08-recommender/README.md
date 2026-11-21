# a08 Recommender: vòng đánh giá

**TL;DR:** 08 không gọi LLM. `select.rank_problems` chọn bài cho phiếu theo ba nhóm: ôn, vừa sức, thử thách. Target `--agent 08` xếp
hạng 5 hồ sơ học sinh và so với nhãn của chủ dự án. Nhãn còn là bản nháp. Bộ xếp hạng đạt 0/6 bài khớp nhãn ở ba hồ sơ: xem "Việc của chủ dự án".

- Code của agent: `src/tutor/agents/a08_recommender/select.py` (`select.rank_problems`, `select.BUCKETS`).
- Ai gọi 08: công cụ `rank_problems` của 00 (`tools.Toolbox`). G4 kiểm nhóm của từng bài (`src/tutor/graphs/worksheet.py`).
- Code eval: `components.evaluate_08`, `components._rank_08` trong `tests/eval/components.py`.
- Test của eval: `tests/eval/test_components.py`, các test tên `test_08_...`.
- Code tất định: chạy k lần cho cùng kết quả, không cần judge (design mục 2, phạm vi đã cắt).

## Đánh giá cái gì

- Luật chọn bài: không lặp bài gần đây, đúng lớp, đúng tỉ lệ nhóm, đủ kỹ năng. Các luật này có test pytest `tests/services/test_select.py`.
- Phiếu có chứa bài chủ dự án đánh dấu là liên quan không (P@n, recall@n), và không chứa bài trong `must_not`.
- Công cụ `search_problems` của 00 có trả bài liên quan trong 5 kết quả đầu không (recall@5).

## Năm bước

| bước | với 08 |
|---|---|
| [1 Tasks](1-tasks/README.md) | 5 hồ sơ trong `reco_08.json`, 6 câu tìm trong `search_00.json`; nhãn nháp |
| [2 Environment](2-environment/README.md) | `agents.trials` với `FakeLLM` không có handler: lời gọi model nào cũng lỗi |
| [3 Trials & traces](3-trials-traces/README.md) | k = 1, 0 lời gọi; file kết quả `<created>_08.json` |
| [4 Graders](4-graders/README.md) | code: `metrics.passed_08`, `metrics.score_08` |
| [5 Scorecard](5-scorecard/README.md) | dòng `08-dev`; dòng test code `08-tests` |

## Ba mức grader

| mức | kiểm gì | ở đâu |
|---|---|---|
| Outcome | phiếu có đủ n bài, hoặc có cảnh báo khi ngân hàng thiếu bài hợp; không bài nào trong `must_not` | `metrics.passed_08` |
| Trajectory | không áp dụng: một hàm, không có bước trung gian | không có |
| Component | luật chọn bài | `tests/services/test_select.py`, dòng `08-tests` |
| Component | P@n và recall@n so với danh sách bài liên quan | `metrics.score_08`: `p_at_n`, `recall_at_n` |
| Component | recall@5 của `search_problems` | `extra.search_recall_at_5` |

## Việc của chủ dự án

- Nhãn của 5 hồ sơ và 6 câu tìm đều `status: draft`: 11 nhãn nháp. CLI in cảnh báo cho tới khi chủ dự án duyệt.
- Bộ xếp hạng đạt 0/6 bài khớp nhãn ở các hồ sơ `new`, `solid` và `grade8`. `repeat` đạt 3/6 và `used-up` đạt 6/6.
  Đo ngày 2026-11-21 bằng `run.py --agent 08`: `p_at_n` = 0.300, `recall_at_n` = 0.180, `search_recall_at_5` = 0.900.
- Đó là hành vi thật của bộ xếp hạng, không phải lỗi của eval. Reviewer đã thăm dò ba nguyên nhân:
  - Bài mức 1 và 2 không bao giờ được chọn khi còn bài mức từ 3 (`bank.level_delta`, `reco.zpd_window` trong `config.defaults`).
  - Kỹ năng nền mạnh không nâng kỹ năng sau trong `select.rank_problems`.
  - Các bài bằng điểm xếp theo thứ tự `ref`, nên phiếu hay chỉ có một chủ đề.
- Nhãn nháp chưa được tinh chỉnh theo bộ xếp hạng. Chủ dự án quyết định đổi nhãn hay đổi bộ xếp hạng trước khi đặt sàn nào cho 08.
  `tests/eval/baseline.json` hôm nay không có sàn cho 08.
- `metrics.passed_08` vẫn đạt (`passed` = 1.000) vì nó chỉ kiểm phiếu đủ bài và không có bài cấm, không kiểm P@n.

## Chưa có

- Nhãn đã duyệt của chủ dự án cho 08.
- Chạy thật không áp dụng: 08 không gọi model.

## Chạy

```bash
uv run python tests/eval/run.py --agent 08
uv run pytest tests/services/test_select.py -q
```

- Target 08 luôn chạy 1 lần, không cần `--yes`, kể cả với `--backend real`: không có lời gọi model, không tốn tiền.
- In thêm `search recall@5=` và dòng cảnh báo nhãn nháp, sau dòng `prompt_version:`. Với 08 dòng `prompt_version:` để trống.
