# a03 Diagnoser: vòng đánh giá

**TL;DR:** 03 tìm bước sai đầu tiên và các bước sai khác, gắn mã lỗi. 03 chưa có target riêng. Nó được đo bên trong
lần chạy G1: các đề xuất ở cổng `gate_review` so với lỗi gài trong `labels.json`.

- Code của agent: `src/tutor/agents/a03_diagnoser/diagnoser.py` (`diagnoser.run`, `diagnoser.DiagnosisOut`).
- Trong G1, 03 là node `diagnose` của mỗi lane, sau `grade` và trước `verify`.
- Code eval: `run.evaluate`, `run._one`, `run.oracle` trong `tests/eval/run.py`; số trong `metrics.score`.

## Đánh giá cái gì

- 03 có tìm ra lỗi gài không (recall), có thêm lỗi thừa không (precision).
- Bước sai đầu tiên có đúng không. Bài sạch thì 03 không được đề xuất gì.
- Mã lỗi 03 chọn có khớp nhãn không (Cohen's kappa).
- Không dùng accuracy: phần lớn các bước là đúng, nên agent không báo lỗi nào vẫn có accuracy cao (design mục 5.4).

## Năm bước

| bước | với 03 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | bài của G1 có lỗi gài: bước, mã lỗi, bước kéo theo | chung với G1 |
| [2 Environment](2-environment/README.md) | môi trường của G1; học sinh mới nên lịch sử lỗi rỗng | chung với G1 |
| [3 Trials & traces](3-trials-traces/README.md) | đọc từ trial của G1; dòng `agent` = `03` | chung với G1 |
| [4 Graders](4-graders/README.md) | `metrics.score`, `metrics.first_wrong_step`, `metrics.cohen_kappa` | riêng phần số |
| [5 Scorecard](5-scorecard/README.md) | `precision`, `recall`, `kappa`, `drop_rate`, `add_rate` trong dòng G1 | chung với G1 |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | đúng bước sai đầu tiên; bài sạch không có đề xuất | có: `metrics.first_wrong_step`, `first_wrong_step_acc` |
| Trajectory | 1 lời gọi mỗi bài, không `schema_error` | chưa có: Task 15 |
| Component | recall, precision trên tập bước sai; bước kéo theo không tính là thừa | có: `metrics.score` |
| Component | kappa mã lỗi giữa nhãn và 03 | có: `metrics.cohen_kappa` |
| Component | confusion matrix mã lỗi; bằng chứng nguyên văn; cờ của `Diagnosis` | chưa có: Task 13 |

- Pass^k của G1 chính là "bước sai đầu tiên đúng ở cả k run" (`metrics.g1_passed`). Nên outcome của G1 phần lớn là
  outcome của 03.
- Đầu vào của 03 có phần đến từ 02: danh sách mục rubric chưa đạt. Số của 03 đọc từ G1 không hoàn toàn là
  "đầu vào cố định" (design mục 5.4).

## Chưa có

- Task 13: `evidence_03`, `confusion`, `flags`, `clean_flagged`, `agree_on_right`, `agree_on_wrong` trong `metrics.components`.
- Task 15: lời gọi mỗi bài, `retry`, `schema_error`, thứ tự 02, 03, 04 trong mỗi lane.
- Task 22: sàn `recall` ≥ 0.90 và `precision` ≥ 0.75 cho mọi bộ G1.

## Chạy

03 chạy bên trong G1:

```bash
uv run python tests/eval/run.py --agent g1 --set g1-dev --backend fake --runs 3
```

- Dòng `run k:` in `precision`, `recall`, `kappa`, `first_wrong_step_acc` của từng run.
- Chạy thật cần `--backend real --yes` và tốn tiền. Nó chạy cả 01, 02, 03, 04. Design mục 11.2 ước tính 102 lời gọi,
  khoảng $1.01 cho `--files s01.tex s04.tex`.
