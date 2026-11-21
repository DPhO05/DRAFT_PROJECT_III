# Vòng đánh giá của gia sư Toán

**TL;DR:** Mọi eval trong repo đi theo một vòng 5 bước: task chạy trong môi trường cô lập, grader chấm trace, scorecard ghi
kết quả, lỗi ở production quay lại thành task mới. Thư mục này chỉ là tài liệu. Code nằm ở `tests/eval/`.

- Hình tổng quan: `tests/eval/loop/eval-loop.excalidraw`. Mở bằng excalidraw.com.
- Mỗi agent và mỗi workflow có một thư mục. Trong đó `README.md` nói tổng quan, 5 thư mục con nói từng bước.
- Tài liệu chỉ ghi điều code làm hôm nay. Cả 24 task của build plan đã build. Mục "Chưa có" chỉ ghi phần chưa làm được.
- Chưa có kết quả của lần chạy thật nào cho bộ task này. `tests/eval/baseline.json` có `real` rỗng.

## Năm bước

Mỗi bước có một check. Chưa qua check thì chưa tin con số.

| bước | làm gì | check | code trong repo |
|---|---|---|---|
| 1 Tasks | input, tiêu chí đạt; tự soạn, chọn từ dữ liệu thật | bao phủ cách dùng thật | `questions_00.json`, `tasks/`, `harvest.py` |
| 2 Environment | cô lập; dữ liệu, công cụ, người dùng giả | sạch, không rò | `agents.trials`, `run.evaluate` |
| 3 Trials & traces | k lần chạy mỗi task; trace đủ | ổn định qua các lần | cờ `--runs`, `--suite`, `agents.read_log` |
| 4 Graders | code, LLM judge, hiệu chỉnh với người | khớp với người chấm | `metrics.py`, `judges.py`, `calibrate.py` |
| 5 Scorecard | success, pass^k, chi phí; cổng cho mỗi thay đổi | khớp production | `scorecard.py`, `gate.py`, `baseline.json` |

- Bộ bài của G1 khai báo trong `tests/eval/sets.json`. Thế giới dùng chung nằm ở `tests/assistant_fix.py`.
- Mũi tên phản hồi "lỗi production thành task mới" có code: `tests/eval/harvest.py`. Nó chưa chạy trên dữ liệu thật.
- Mọi bộ task nằm trong repo là tự soạn (`source: synthetic`). Task gom từ production chỉ là bản nháp (`source: production`,
  `status: draft`) và chỉ nằm ở máy chủ dự án. Check của bước 1 và bước 5 chưa đạt.

## Ba mức grader

> Outcome cho biết là hỏng. Trajectory và component cho biết hỏng ở đâu. Dùng cả ba.

| mức | câu hỏi | ví dụ trong repo |
|---|---|---|
| Outcome | task xong chưa | `metrics.passed_00`, `metrics.passed_04`, `metrics.first_wrong_step` |
| Trajectory | đường đi có đúng không | `metrics._tools_ok`, `metrics.rules_ok`, `model_calls`, `metrics.trajectory` (G1) |
| Component | từng phần có chạy đúng không | `metrics.score_01` (hit@k, MRR), `metrics.score_04`, `metrics.components` (G1) |

- Phần lớn grader là code. Một grader dùng LLM: `judges.faithfulness`, chạy khi có cờ `--judge`, cho 00, 09 và g5. Nó chỉ báo cáo,
  không đổi kết quả đạt hay trượt.
- `calibrate.py` đo judge với người chấm. Chưa có người chấm nào, nên `judge_trusted` trong `tests/eval/baseline.json` là `false`.
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
- `--judge` chạy với `fake` và `real`. Với `dev` bị từ chối vì devfake không có judge. `real` cần thêm `--judge-model`.
- Target `08` không gọi model nên không cần `--yes`.

---

## Thư mục

| thư mục | `--agent` | gọi LLM | task | k | trạng thái |
|---|---|---|---|---|---|
| `tests/eval/loop/a00-orchestrator/` | `00` | có, vòng công cụ | 20 câu | 3 | chạy được |
| `tests/eval/loop/a01-ingest/` | `01` | khi bài thiếu mã | 10 bài | 3 | chạy được |
| `tests/eval/loop/a02-grader/` | `g1`, `02r` | có | bài của G1; 4 mã bài cho rubric | 3 | `02r` chạy được; chấm bài đọc từ G1 |
| `tests/eval/loop/a03-diagnoser/` | `g1` | có | bài của G1 | 3 | đọc từ G1, có component và trajectory |
| `tests/eval/loop/a04-verifier/` | `04` | có | 12 kết luận | 3 | chạy được |
| `tests/eval/loop/a08-recommender/` | `08` | không | 5 hồ sơ, 6 câu tìm | 1 | chạy được; nhãn còn nháp |
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
| `metrics.components` | `tests/eval/metrics.py` | 4 | G1: bằng chứng nguyên văn, cờ, confusion matrix của 02 và 03 |
| `metrics.trajectory` | `tests/eval/metrics.py` | 4 | G1: lời gọi mỗi thread, thứ tự 02, 03, 04, `retry`, `schema_error` |
| `judges.faithfulness` | `tests/eval/judges.py` | 4 | judge: mỗi câu có số liệu đỡ không |
| `metrics.tally` | `tests/eval/metrics.py` | 3, 5 | task thiếu ở một run tính là trượt |
| `metrics.usage` | `tests/eval/metrics.py` | 5 | lời gọi, USD, token, `ms_p50`, `ms_p95`, `error_rate` |
| `run.main` | `tests/eval/run.py` | mọi bước | CLI, `run.TARGETS`, `--backend real` cần `--yes` |
| `scorecard.build` | `tests/eval/scorecard.py` | 5 | file mới nhất của mỗi cặp (set, backend) thành một dòng |
| `scorecard.code_rows` | `tests/eval/scorecard.py` | 5 | cờ `--with-tests`: một dòng `<target>-tests` cho mỗi workflow |
| `gate.check` | `tests/eval/gate.py` | 5 | sàn và luật không tụt so với `baseline.json` |
| `run._suite` | `tests/eval/run.py` | 3 | cờ `--suite`: chạy một dãy bước trong `suites.json` |

- Backend dựng một lần ở run 1, vì fake có trạng thái đếm qua các run.
- Các task trong cùng một run dùng chung thế giới của run đó. Thế giới mới theo run, không theo từng trial.

## Lệnh

```bash
uv run pytest tests/eval -q
uv run python tests/eval/run.py --agent 04 --backend fake --runs 3
uv run python tests/eval/run.py --suite compact --backend fake --runs 1
uv run python tests/eval/scorecard.py --with-tests
uv run python tests/eval/gate.py data/eval/scorecards/<file>.json --backend fake
```

- `run.py` ghi kết quả vào `data/eval/results/`, trace vào `data/eval/traces/`. `scorecard.py` ghi `data/eval/scorecards/`. Git bỏ qua
  `data/eval/`.
- Chạy thật: `--backend real --yes`. Lệnh gọi API thật và tốn tiền.
- `--suite full` hoặc `--suite compact` chạy một dãy target theo `tests/eval/suites.json`. Với `real`, `run.py` in số lời gọi dự kiến
  và dừng (mã thoát 3) khi một bước gọi nhiều hơn dự kiến quá 30 %. Suite không chạy với `--backend dev`.
- `scorecard.py --with-tests` thêm một dòng `<target>-tests` cho 05, 08, G1, G2, G4, G5 và chat. Các test của chúng khai báo trong
  `tests/eval/workflows.json`. Dòng này có `backend: code`, 0 lời gọi.

## Cổng

- `tests/eval/gate.py` đọc một file scorecard và `tests/eval/baseline.json`, in `ĐẠT`, `TRƯỢT` hoặc `BỎ QUA` cho từng giá trị. Mã thoát 1
  khi có `TRƯỢT`. Mặc định chỉ xét dòng `backend: real`.
- `floors`: sàn theo bộ, ví dụ `recall` ≥ 0.90 và `precision` ≥ 0.75 cho `g1-*`, `pass_k` ≥ 0.85 cho `00-dev`.
  `name_leaks` = 0 và `approval_ok` = 1.0 là sàn cứng: thiếu số cũng là `TRƯỢT`.
- Sàn faithfulness ≥ 0.95 chỉ tính khi `judge_trusted` là `true`. Hôm nay nó là `false`, nên các sàn này `BỎ QUA`.
- `no_drop`: so với dòng trong `real.rows`, nhiều nhất `tolerance_tasks` task đạt ở baseline được tụt. Chỉ xét task có ở cả hai bên.
  `real.rows` đang rỗng, nên luật này chưa có gì để so.
- Cổng tầng 0 là test pytest `tests/eval/test_gate.py`: mọi target chạy với oracle, rồi `gate.check` trên các dòng đó. Test này
  không gọi model thật và chạy trong `uv run pytest tests/eval -q`.
- `gate.unverified` liệt kê phiên bản prompt chưa có scorecard thật. Hôm nay chỉ test gọi nó, `gate.main` chưa gọi.
- Gate xét dòng `backend: code` bằng `--backend code` thì mọi dòng `<target>-tests` trượt sàn cứng `name_leaks`, vì dòng đó không có số này.

## Việc đang sửa

- Một lần chạy với `--only` hoặc `--files` tạo dòng một phần. `scorecard.build` giữ file mới nhất của mỗi cặp (set, backend), nên dòng một
  phần thay dòng của bộ đầy đủ, và gate không phân biệt được. Đang sửa trong review cuối.
- Hai suite có bước một phần. `compact` cho `00-dev` 14 task thay vì 20, `01-dev` 6 thay vì 10, `09-dev` 3 thay vì 6, `g1-dev` 9 bài thay vì 40,
  `g1-heldout` 10 bài thay vì 20 (đo bằng `--suite compact --backend fake --runs 1`). `full` chỉ chạy `s01.tex` và `s04.tex` cho `g1-dev`.

## Chưa có

- Chạy thật: chưa có lần chạy `--backend real` nào cho 24 task. Số thật duy nhất là lần chạy G1 ngày 2026-11-04 (design mục 1.3).
- Baseline thật: `real` trong `tests/eval/baseline.json` rỗng. Chưa có luật không tụt nào chạy.
- Nhãn của chủ dự án: nhãn của 08 còn nháp (xem `tests/eval/loop/a08-recommender/README.md`). Chưa có người chấm cho judge.
- Chạy `harvest.py` trên dữ liệu thật. Code và test đã có, chưa có lần chạy nào.
- GitHub Actions: chưa có workflow nào chạy cổng.

## Đã build

| nhóm | thêm gì | file |
|---|---|---|
| component của 02 và 03 | `metrics.components`: bằng chứng nguyên văn, cờ, confusion matrix, `agree_on_right` | `tests/eval/metrics.py` |
| target `02r` | rubric nháp của 02, 4 mã bài | `tests/eval/components.py`, `tests/eval/tasks/rubric_02.json` |
| trajectory G1 | `metrics.trajectory`: thứ tự 02, 03, 04, trần lời gọi, `confirm_ok` | `tests/eval/metrics.py`, `tests/eval/run.py` |
| target `08` | xếp hạng 5 hồ sơ, recall@5 của `search_problems` | `tests/eval/components.py`, `tests/eval/tasks/reco_08.json` |
| test code lên scorecard | `scorecard.py --with-tests` | `tests/eval/workflows.json` |
| judge | `judges.faithfulness`, cờ `--judge` và `--judge-model` | `tests/eval/judges.py` |
| hiệu chỉnh judge | `calibrate.py sample`, `judge`, `score` | `tests/eval/calibrate.py` |
| lỗi production thành task nháp | `harvest.py`, `production.json` | `tests/eval/harvest.py` |
| cổng | sàn và luật không tụt | `tests/eval/gate.py`, `tests/eval/baseline.json` |
| cổng tầng 0 | test pytest | `tests/eval/test_gate.py` |
| bộ chạy thật | `--suite full`, `--suite compact` | `tests/eval/suites.json` |

## Nguồn

| nguồn | ở đâu |
|---|---|
| hình "Evaluation Loop: What to Test, How to Grade" | ảnh của chủ dự án, không có trong repo |
| design plan (tiếng Việt), mục 1, 4 đến 9 | `docs/superpowers/plans/2026-11-21-eval-loop.md`, chỉ có ở máy chủ dự án |
| build plan (tiếng Anh), Task 1 đến 24 | `docs/superpowers/plans/2026-11-21-eval-loop-build.md`, chỉ có ở máy chủ dự án |

- Cả 24 task của build plan đã build trên nhánh này.
