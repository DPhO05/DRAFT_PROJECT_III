# a02 Grader: vòng đánh giá

**TL;DR:** 02 chấm từng mục rubric đạt hay không, kèm bằng chứng trích từ bài làm. 02 chưa có target riêng. Hôm nay nó
chỉ được đo bên trong lần chạy G1, bằng một số: % mục rubric đổi kết quả giữa các run.

- Code của agent: `src/tutor/agents/a02_grader/grader.py` (`grader.grade`, `grader.generate_rubric`).
- Trong G1, 02 là node `grade` của mỗi lane (`session.build`).
- Code eval: `run.evaluate`, `run._one` trong `tests/eval/run.py`. Oracle của 02 là `lane_handlers` trong `tests/fakes.py`.

## Đánh giá cái gì

- Kết quả đạt hay không của từng mục rubric, cho từng bài, ở cổng `gate_review` của G1.
- Độ ổn định: cùng một bài, cùng rubric, 02 có cho cùng kết quả qua k run không.
- Đầu vào của 02 trong G1 là cố định với mỗi bài (bước, đề, rubric). Vì vậy đọc 02 từ trial của G1 vẫn là
  "một phần, đầu vào cố định" (design mục 5.3).

## Năm bước

| bước | với 02 | chung hay riêng |
|---|---|---|
| [1 Tasks](1-tasks/README.md) | dùng bài của G1: `g1-dev` và `g1-heldout` | chung với G1 |
| [2 Environment](2-environment/README.md) | môi trường của G1 | chung với G1 |
| [3 Trials & traces](3-trials-traces/README.md) | đọc từ trial của G1; dòng `agent` = `02` trong `run<k>.jsonl` | chung với G1 |
| [4 Graders](4-graders/README.md) | `metrics.stability`: `items_changed_pct` | riêng phần số |
| [5 Scorecard](5-scorecard/README.md) | `items_changed_pct` trong dòng G1; lời gọi và USD của 02 trong `by_agent` | chung với G1 |

## Ba mức grader

| mức | kiểm gì | hôm nay |
|---|---|---|
| Outcome | bài sạch được điểm tối đa | chưa có: Task 13 (`clean_full_marks`) |
| Trajectory | 1 lời gọi mỗi bài, không `schema_error`, không `retry` | chưa có: Task 15 |
| Component | % mục rubric đổi kết quả giữa các run | có: `metrics.stability` |
| Component | bằng chứng là chuỗi con nguyên văn của bài; cờ của `Grade` | chưa có: Task 13 |
| Component | rubric nháp hợp lệ | chưa có: Task 14 |

## Chưa có

- Task 13: `evidence_02` (bằng chứng nguyên văn), `flags`, `clean_full_marks` trong `metrics.components`. Oracle sẽ trích đúng
  bước.
- Task 14: target `--agent 02r` cho `grader.generate_rubric`, 4 bài trong `tests/eval/tasks/rubric_02.json`.
- Task 15: số `retry` và `schema_error` theo agent, đọc từ `llm.jsonl`.
- Chưa có nhãn đạt hay không cho từng mục rubric. Design mục 5.3 để chủ dự án điền dần trường `expect_items`.

## Chạy

02 chạy bên trong G1:

```bash
uv run python tests/eval/run.py --agent g1 --set g1-dev --backend fake --runs 3
```

- Xem `items_changed_pct` ở dòng `stability:` và lời gọi của 02 ở `calls.by_agent` của file kết quả.
- Chạy thật cần `--backend real --yes` và tốn tiền. Nó chạy cả 01, 02, 03, 04. Design mục 11.2 ước tính 102 lời gọi,
  khoảng $1.01 cho `--files s01.tex s04.tex`.
