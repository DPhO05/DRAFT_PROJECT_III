# a02 Grader: vòng đánh giá

**TL;DR:** 02 chấm từng mục rubric đạt hay không, kèm bằng chứng trích từ bài làm, và viết rubric nháp khi bài thiếu rubric. Việc
chấm được đo bên trong lần chạy G1: độ ổn định, bằng chứng nguyên văn, cờ. Việc viết rubric nháp có target riêng `--agent 02r`.

- Code của agent: `src/tutor/agents/a02_grader/grader.py` (`grader.grade`, `grader.generate_rubric`).
- Trong G1, 02 là node `grade` của mỗi lane (`session.build`).
- Code eval của việc chấm: `run.evaluate`, `run._one` trong `tests/eval/run.py`. Oracle của 02 là `lane_handlers` trong `tests/fakes.py`.
- Code eval của rubric nháp: `components.evaluate_02r`, `components._draft_02r`, `components.oracle_02r` trong `tests/eval/components.py`.

## Đánh giá cái gì

- Kết quả đạt hay không của từng mục rubric, cho từng bài, ở cổng `gate_review` của G1.
- Độ ổn định: cùng một bài, cùng rubric, 02 có cho cùng kết quả qua k run không.
- Bằng chứng của mỗi mục đạt có phải chuỗi con nguyên văn của bài làm không.
- Bài sạch có được điểm tối đa không.
- Rubric nháp (`grader.generate_rubric`) có hợp lệ không: mục `r1`, `r2`, ... theo thứ tự, mỗi mục có điểm, tổng đúng, một lời gọi.
- Đầu vào của 02 trong G1 là cố định với mỗi bài (bước, đề, rubric). Vì vậy đọc 02 từ trial của G1 vẫn là
  "một phần, đầu vào cố định" (design mục 5.3).

## Năm bước

| bước | với 02 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | bài của G1 cho việc chấm; 4 mã bài trong `rubric_02.json` cho rubric nháp | chung với G1; `02r` riêng |
| [2 Environment](2-environment/README.md) | môi trường của G1 | chung với G1 |
| [3 Trials & traces](3-trials-traces/README.md) | đọc từ trial của G1; dòng `agent` = `02` trong `run<k>.jsonl` | chung với G1 |
| [4 Graders](4-graders/README.md) | `metrics.stability`, `metrics.components`; `metrics.passed_02r` | riêng phần số |
| [5 Scorecard](5-scorecard/README.md) | `items_changed_pct` trong dòng G1; dòng `02r-dev`; `by_agent` | chung với G1; `02r` riêng |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | bài sạch được điểm tối đa | có: `metrics.components`, `clean_full_marks` |
| Outcome | rubric nháp hợp lệ, một lời gọi | có: `metrics.passed_02r` (target `02r`) |
| Trajectory | số lời gọi mỗi thread, `schema_error`, `retry`, 02 chạy trước 03 và 04 | có: `metrics.trajectory` |
| Component | % mục rubric đổi kết quả giữa các run | có: `metrics.stability` |
| Component | bằng chứng là chuỗi con nguyên văn của bài; cờ của `Grade` | có: `metrics.components`, `evidence_02`, `flags` |

## Chưa có

- Chạy thật: chưa có lần chạy `--backend real` của `02r` hay của G1 sau 2026-11-04.
- Chưa có nhãn đạt hay không cho từng mục rubric. Design mục 5.3 để chủ dự án điền dần trường `expect_items`.

## Chạy

02 chạy bên trong G1:

```bash
uv run python tests/eval/run.py --agent g1 --set g1-dev --backend fake --runs 3
```

- Xem `items_changed_pct` ở dòng `stability:` và lời gọi của 02 ở `calls.by_agent` của file kết quả.
- Chạy thật cần `--backend real --yes` và tốn tiền. Nó chạy cả 01, 02, 03, 04. Design mục 11.2 ước tính 102 lời gọi,
  khoảng $1.01 cho `--files s01.tex s04.tex`.

Rubric nháp có target riêng:

```bash
uv run python tests/eval/run.py --agent 02r --backend fake --runs 3
```

- `--backend fake` dùng `components.oracle_02r`: 02 trả bản nháp một mục. Điểm luôn 1.0. Chạy thật dự kiến 12 lời gọi (`suites.json`).
