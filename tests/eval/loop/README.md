# Vòng đánh giá của gia sư Toán

**TL;DR:** Mọi eval trong repo đi theo một vòng 5 bước: task chạy trong môi trường cô lập, grader chấm trace, scorecard ghi
kết quả, lỗi ở production quay lại thành task mới. Thư mục này chỉ là tài liệu. Code nằm ở `tests/eval/`.

- Hình tổng quan: `tests/eval/loop/eval-loop.excalidraw`. Mở bằng excalidraw.com.
- Mỗi agent và mỗi workflow có một thư mục. Trong đó `README.md` nói tổng quan, 5 thư mục con nói từng bước.
- Tài liệu chỉ ghi điều code làm hôm nay. Phần build plan làm sau nằm trong mục "Chưa có", kèm số Task.

## Năm bước

Mỗi bước có một check. Chưa qua check thì chưa tin con số.

| bước | làm gì | check | code trong repo |
|---|---|---|---|
| 1 Tasks | input, tiêu chí đạt; tự viết, sinh ra | bao phủ cách dùng thật | `tests/eval/questions_00.json`, `tests/eval/tasks/` |
| 2 Environment | cô lập; dữ liệu, công cụ, người dùng giả | sạch, không rò | `agents.trials`, `run.evaluate` |
| 3 Trials & traces | k lần chạy mỗi task; trace đủ | ổn định qua các lần | cờ `--runs`, `agents.read_log` |
| 4 Graders | code, LLM judge, hiệu chỉnh với người | khớp với người chấm | `tests/eval/metrics.py` |
| 5 Scorecard | success, pass^k, chi phí; cổng cho mỗi thay đổi | khớp production | `tests/eval/scorecard.py` |

- Bộ bài của G1 khai báo trong `tests/eval/sets.json`. Thế giới dùng chung nằm ở `tests/assistant_fix.py`.
- Mũi tên phản hồi "lỗi production thành task mới" chưa có code. Task 20 và Task 21 thêm `tests/eval/harvest.py`.
- Hôm nay mọi task là synthetic (`source: synthetic`). Check của bước 1 và bước 5 chưa đạt.

## Ba mức grader

> Outcome cho biết là hỏng. Trajectory và component cho biết hỏng ở đâu. Dùng cả ba.

| mức | câu hỏi | ví dụ trong repo |
|---|---|---|
| Outcome | task xong chưa | `metrics.passed_00`, `metrics.passed_04`, `metrics.first_wrong_step` |
| Trajectory | đường đi có đúng không | `metrics._tools_ok`, `metrics.rules_ok`, số lời gọi `model_calls` |
| Component | từng phần có chạy đúng không | `metrics.score_01` (hit@k, MRR), `metrics.score_04` (`recall_disagree`) |

- Mọi grader hôm nay là code. LLM judge (faithfulness) là Task 18. Hiệu chỉnh với người là Task 19.
- Một task đạt khi mọi kiểm tra của nó đạt. Điểm từng phần vẫn báo riêng trong `per_run`.

## Ba backend

| `--backend` | là gì | lời gọi thật | chứng minh gì |
|---|---|---|---|
| `fake` | oracle: `FakeLLM` (`tests/fakes.py`) trả đúng nhãn | 0 | task giải được, grader đúng; điểm luôn 1.0 |
| `dev` | `devfake.DevFakeLLM`, tất định; mặc định của `run.py` | 0 | đường ống chạy hết |
| `real` | model trong settings của app, cần thêm `--yes` | có, tốn tiền | chất lượng thật của prompt và model |

- Test tự động không bao giờ gọi API thật: fixture `no_real_llm` trong `tests/conftest.py` xoá khoá và cài `FakeLLM`.
- Số tiền của một lần chạy `fake` hay `dev` chỉ là số của đường ống. Chỉ dòng `backend: real` mới là chi phí
  thật.

---

## Thư mục

| thư mục | `--agent` | gọi LLM | task | k | trạng thái |
|---|---|---|---|---|---|
| `tests/eval/loop/a00-orchestrator/` | `00` | có, vòng công cụ | 20 câu | 3 | chạy được |
| `tests/eval/loop/a01-ingest/` | `01` | khi bài thiếu mã | 10 bài | 3 | chạy được |
| `tests/eval/loop/a02-grader/` | `g1` | có | bài của G1 | 3 | một phần, đọc từ G1 |
| `tests/eval/loop/a03-diagnoser/` | `g1` | có | bài của G1 | 3 | một phần, đọc từ G1 |
| `tests/eval/loop/a04-verifier/` | `04` | có | 12 kết luận | 3 | chạy được |
| `tests/eval/loop/a08-recommender/` | chưa có | không | chưa có | 1 | chỉ test pytest |
| `tests/eval/loop/a09-reporter/` | `09` | có, 1 đến 2 lời gọi | 6 kỳ | 3 | chạy được |
| `tests/eval/loop/workflows/` | `g1`, `g5`, `00` | xem từng workflow | | | xem `tests/eval/loop/workflows/README.md` |

Hai agent không có thư mục:

- **05 Profiler:** không gọi LLM; code tất định trong `src/tutor/services/elo.py`, đã có test pytest
  (`src/tutor/agents/a05_profiler/README.md`).
- **06 Tagger:** chưa có code; gia sư tự chọn kỹ năng ở G2 (`src/tutor/agents/a06_tagger/README.md`).

## Phần dùng chung

Các bước sau giống nhau cho mọi target, trừ G1 có vòng lặp riêng trong `run.evaluate`.

| hàm | file | bước | làm gì |
|---|---|---|---|
| `agents.trials` | `tests/eval/agents.py` | 2, 3 | mỗi run một thế giới mới `work/run<k>`, `llm.jsonl` riêng, chép trace |
| `assistant_fix.world` | `tests/assistant_fix.py` | 2 | ngân hàng mẫu, HS-01, HS-02, HS-03 đã lưu trữ, vài buổi học |
| `agents.read_log` | `tests/eval/agents.py` | 3 | đọc `llm.jsonl` qua `llm.iter_log`, tính `cost_usd` |
| `agents.leak_count` | `tests/eval/agents.py` | 2, 4 | đếm chuỗi còn họ tên học sinh |
| `agents.summarize` | `tests/eval/agents.py` | 5 | `pass_k`, `success`, `tally`, `name_leaks`, `calls` |
| `metrics.tally` | `tests/eval/metrics.py` | 3, 5 | task thiếu ở một run tính là trượt |
| `metrics.usage` | `tests/eval/metrics.py` | 5 | lời gọi, USD, token, `ms_p50`, `ms_p95`, `error_rate` |
| `run.main` | `tests/eval/run.py` | mọi bước | CLI, `run.TARGETS`, `--backend real` cần `--yes` |
| `scorecard.build` | `tests/eval/scorecard.py` | 5 | file mới nhất của mỗi cặp (set, backend) thành một dòng |

- Backend dựng một lần ở run 1, vì fake có trạng thái đếm qua các run.
- Các task trong cùng một run dùng chung thế giới của run đó. Thế giới mới theo run, không theo từng trial.

## Lệnh

```bash
uv run pytest tests/eval -q
uv run python tests/eval/run.py --agent 04 --backend fake --runs 3
uv run python tests/eval/scorecard.py
```

- `run.py` ghi kết quả vào `data/eval/results/`, trace vào `data/eval/traces/`. `scorecard.py` ghi `data/eval/scorecards/`. Git bỏ qua
  `data/eval/`.
- Chạy thật: `--backend real --yes`. Lệnh gọi API thật và tốn tiền.

---

## Chưa có

| Task | thêm gì |
|---|---|
| 13 | chỉ số component của 02 và 03 trong G1: bằng chứng nguyên văn, cờ, confusion matrix |
| 14 | target `--agent 02r`: rubric nháp của 02 |
| 15 | chỉ số trajectory của G1 từ `llm.jsonl`: thứ tự 02, 03, 04, số lời gọi mỗi file, `confirm_ok` |
| 16 | target `--agent 08` và recall@5 của `search_problems` |
| 17 | workflow chỉ có code (05, 08, G2, G4) lên scorecard: `tests/eval/workflows.json` |
| 18 | judge faithfulness, cờ `--judge` và `--judge-model`: `tests/eval/judges.py` |
| 19 | hiệu chỉnh judge với người chấm: `tests/eval/calibrate.py` |
| 20, 21 | lỗi production thành task nháp: `tests/eval/harvest.py`, file `production.json` |
| 22 | cổng: sàn và luật không tụt so với baseline, `tests/eval/gate.py`, `tests/eval/baseline.json` |
| 23 | cổng tầng 0 trong pytest: `tests/eval/test_gate.py` |
| 24 | bộ chạy thật `full` và `compact`, cờ `--suite`: `tests/eval/suites.json` |

## Nguồn

| nguồn | ở đâu |
|---|---|
| hình "Evaluation Loop: What to Test, How to Grade" | ảnh của chủ dự án, không có trong repo |
| design plan (tiếng Việt), mục 1, 4 đến 9 | `docs/superpowers/plans/2026-11-21-eval-loop.md`, chỉ có ở máy chủ dự án |
| build plan (tiếng Anh), Task 1 đến 24 | `docs/superpowers/plans/2026-11-21-eval-loop-build.md`, chỉ có ở máy chủ dự án |

- Task 1 đến 12 của build plan đã có trên nhánh này. Task 13 đến 24 chưa làm.
