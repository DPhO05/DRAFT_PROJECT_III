# BACKBONE — khung việc chung cho 2 bản SDD PROJECT_III (Monolith · Microservice)

Lập 2026-10-28. Nguồn: tài liệu thiết kế v0.2 (`docs/update.docx`, 22/10), spec `docs/superpowers/specs/2026-10-20-multi-agent-tutor-design.md`, `docs/architecture/schema.sql`, `docs/prototype/IA.md` + `contract.md`, `data/dummy/bank`, `data/dummy/tools`.

Quy ước dùng chung:

- ID task `Pn-Txx` **trung lập kiến trúc**; 2 bản SDD giữ nguyên ID, tên, phụ thuộc. Task hạ tầng riêng thêm với prefix `MONO-Pn-xx` / `MS-Pn-xx`, không đánh lại số task chung.
- Task UI giả định có endpoint HTTP JSON tương ứng (C-03). Dựng tiến trình / service / endpoint = task hạ tầng của từng bản.
- Ước lượng = ngày công, 1 dev, đã gồm viết test. Chưa gồm thời gian chờ chủ dự án (câu trả lời §11.1, bộ bài thật) và thời gian lịch của pilot.
- Thuật ngữ theo tài liệu thiết kế: GV, HS, KC, Hộp duyệt, DỪNG, commit ①/②, thread, checkpoint, đề xuất / đã duyệt.
- "đề xuất (chưa chốt)" = tài liệu thiết kế chưa quyết; cả 2 bản SDD phải ghi cùng cách.

---

## 1. Giai đoạn

MVP (bản đầu) = **P0–P4** (§9.5, §11.2 #1). Cột "Nội dung" và "Xong khi" chép nguyên văn §9.5.

| Pha | Tên | Nội dung (§9.5) | Xong khi (§9.5) | Kiểm bằng task | MVP |
|---|---|---|---|---|---|
| P0 | Khởi tạo | git init, project uv, ruff, pytest; schema.sql + repo.py; chọn công nghệ app, dựng khung app (thanh bên, Hôm nay) | Test schema chạy được và chặn đúng 7 kiểu dữ liệu sai | P0-T03 (7 kiểu: C-17) | ✓ |
| P1 | Ingest | latex.py, 01 Ingest, ① ghi session; Danh mục (nhập KC từ CSV); Buổi học bước 1–2 | 10 file mẫu: đúng số bài, đúng id, đúng số bước | P1-T02 (10 file ngân hàng dummy), P1-T08 (bài HS mẫu) | ✓ |
| P2 | Chấm + chẩn đoán | 02, 03, 04; G1 chạy tới bước chờ duyệt; Buổi học bước 3 (xác nhận cờ) | Chạy trên bộ đánh giá: đo đúng bước sai, kappa mã lỗi | P2-T10 trên bộ bài mẫu có nhãn gài; bộ thật: P8-T04 | ✓ |
| P3 | Duyệt + commit | Buổi học bước 4–5 + Hộp duyệt (CLI: tutor review), commit ② | Test: không có gì vào tutor.db trước khi duyệt; edit / reject / thêm được lưu | P3-T10, P3-T02 | ✓ |
| P4 | Profiler | elo.py, misconception, knowledge_state; Học sinh (hồ sơ, Elo), xem trước Profiler | Unit test Elo; replay skill_event cho đúng skill_state | P4-T01, P4-T05 | ✓ |
| P5 | Ngân hàng | 06, 02 rubric, 07, bt.py; G2, G3; Ngân hàng bài | GV tìm được KC đúng trong top-5 ở phần lớn bài (đo tỉ lệ) | P5-T09 (ngưỡng: C-23) | |
| P6 | Gợi ý | select.py, 08; G4; Gợi ý bài | Unit test luật: tỉ lệ, 30 ngày, ≥ 3 KC | P6-T01 | |
| P7 | Report | facts.py, audit.py, 09; G5; Báo cáo tháng | Test audit bắt được câu sai số; GV đọc thử 3 report | P7-T02, P7-T07 | |
| P8 | Đóng gói + đánh giá thật *(đề xuất, ngoài §9.5)* | Gói cài cho máy GV; đánh giá trên bộ bài thật; kiểm ổn định mọi prompt; Bản đồ hệ thống; chạy thử 1 tháng | GV tự cài và mở app theo hướng dẫn; báo cáo đủ chỉ số §9.6 trên ≥ 20 bài thật; 9/9 agent đạt kiểm 3 lần (NFR8) | P8-T01, P8-T04, P8-T05 | |

### Vì sao thêm P8

- Không pha nào trong §9.5 lo việc cài lên máy GV (lần đầu tạo `data/`, nâng schema khi cập nhật, khôi phục bản sao) — NFR1, NFR9.
- "Xong khi" P2 cần bộ đánh giá thật, nhưng §1.5 / §9.6 ghi chưa có bài HS nào và nhãn = quyết định GV khi duyệt (màn hình P3). Đo thật chỉ làm được sau P3 + khi chủ dự án gửi bài (§11.1 câu 4) → gom vào P8-T04.
- NFR8 (3 lần chạy trước khi dùng prompt) phải phủ cả 05–09, chỉ đủ agent sau P7.
- Bản đồ hệ thống "chưa xếp vào giai đoạn nào" (§4.2, §9.5) → đặt ở P8, bỏ được.
- §10: đối chiếu số liệu tiến bộ với cảm nhận GV sau vài tháng dùng thật.

### Màn hình theo pha

| Màn hình | Pha (task) | Nguồn xếp pha |
|---|---|---|
| Hôm nay | P0 khung (P0-T07) → P3 việc cần làm, cảnh báo (P3-T09) → P4 HS cần chú ý (P4-T08) → thẻ nhịp P5/P6/P7 (P5-T10, P6-T05, P7-T08) | §9.5 P0; §4.5 |
| Hộp duyệt | P3 (P3-T07) | §9.5 P3 |
| Buổi học | bước 1–2 P1 (P1-T11); bước 3 P2 (P2-T06); bước 4–5 P3 (P3-T05, P3-T06); xem trước Profiler, Sửa lỗi đã lưu P4 (P4-T06, P4-T05) | §9.5 P1–P4 |
| Học sinh | thêm / sửa / lưu trữ P1 (P1-T06, kéo sớm); hồ sơ, Elo P4 (P4-T07) | §9.5 P4; §3.5 bước 2 |
| Danh mục | KC + tiên quyết P1 (P1-T04); Mã lỗi P2 (P2-T07) | §9.5 P1 |
| Vận hành | bản đầu P2 (P2-T09); chạy lại / huỷ / sao lưu P3 (P3-T08); Cài đặt + Riêng tư P4 (P4-T09) | §4.2, §9.5 "làm dần từ P2" |
| Nhật ký & chi phí | bản đầu P2 (P2-T08); chất lượng agent, ổn định P4 (P4-T10) | §4.2, §9.5 "làm dần từ P2" |
| Ngân hàng bài | P5 (P5-T06..T08) | §4.2 "làm sau bản đầu" |
| Gợi ý bài | P6 (P6-T04) | §4.2 |
| Báo cáo tháng | P7 (P7-T05) | §4.2 |
| Bản đồ hệ thống | P8 (P8-T03), đề xuất | §4.2: chưa xếp |

---

## 2. Danh sách task (trung lập kiến trúc)

Cột: ID · Tên · Mô tả · Đầu ra · Phụ thuộc · Tiêu chí xong · FR/NFR · Ngày.

### P0 — Khởi tạo

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P0-T01 | Khởi tạo repo + project | git init; uv, Python 3.12, ruff, pytest; dựng cây §9.2; `.gitignore` cho file chạy trong `data/` | `pyproject.toml`, `tutor/{cli.py,llm.py,graphs/,agents/,services/,db/}`, `app/`, `tests/` | — | `uv run pytest`, `uv run ruff check` xanh; `git status` không thấy `tutor.db`, `checkpoints.db`, `inbox/`, `out/`, `logs/`, `backup/` | NFR1 | 0.5 |
| P0-T02 | Schema + khởi tạo DB + migration | Chép `schema.sql` vào `tutor/db/`; chưa có `data/tutor.db` thì tạo (gồm seed 18 mã lỗi); mỗi kết nối `PRAGMA foreign_keys = ON`, `timeout=5`; WAL; `PRAGMA user_version` + chạy `migrations/NNN.sql` theo thứ tự (§8.7) | `tutor/db/schema.sql`, `tutor/db/repo.py` (connect, init, migrate), `tutor/db/migrations/` | P0-T01 | Test: DB mới có 16 bảng + 2 view + 18 dòng `error_code`; init 2 lần không lỗi; migration giả nâng `user_version` 0 → 1 | NFR5 | 1 |
| P0-T03 | Test schema: 7 kiểu dữ liệu sai | Mỗi kiểu (C-17) 1 test insert phải ném `sqlite3.IntegrityError` | `tests/db/test_schema.py` | P0-T02 | 7/7 test xanh (= "Xong khi" P0) | NFR5 | 0.5 |
| P0-T04 | repo.py: mẫu đọc/ghi + sao lưu | Hàm ghi chạy trong `with conn:` (1 transaction); hàm đọc dùng view `*_current`; `backup()` bằng sqlite3 backup API; test kiến trúc: ngoài `repo.py` không có SQL ghi vào tutor.db | `tutor/db/repo.py`, `tests/db/test_single_writer.py` | P0-T02 | Quét mã: SQL `INSERT/UPDATE/DELETE` ngoài `tutor/db/repo.py` = 0; `backup()` ra file mở được, đủ số dòng | NFR5, NFR9 | 1 |
| P0-T05 | Cài đặt + mã HS | Đọc / ghi `data/settings.json` (C-06), mặc định trong code = contract §4; `student_code(id)` → `HS-%02d` (C-11); K = 0.3, θ0 = 0, resolve_streak = 2 là hằng | `tutor/config.py` *(đề xuất, ngoài §9.2)* | P0-T01 | Thiếu file → mặc định; ghi rồi đọc lại bằng nhau; `student_code(3) == "HS-03"` | FR7, NFR7 | 0.5 |
| P0-T06 | Chốt công nghệ app (ADR) | ADR 1 trang theo C-01, gửi chủ dự án (§11.1 câu 7, 8) | `docs/adr/001-app.md` | — | Chủ dự án ghi "đồng ý" hoặc chọn phương án khác | NFR1 | 0.5 |
| P0-T07 | Khung app (shell) | Chuyển shell bản nháp sang dữ liệu thật qua 1 lớp fetch chung: thanh bên 11 mục theo nhịp (nhãn "làm sau bản đầu (P5–P7)"), thanh trên (Nộp bài, Chờ duyệt (n), 2 đồng hồ dữ liệu, chi phí tháng, chip "API chỉ nhận mã HS"), Chú thích hệ thống, sáng / tối, ≤ 720 px thu Menu; Hôm nay ở trạng thái rỗng; lệnh `tutor app` mở trình duyệt | `app/` (shell, `app/api.js`), `tutor/cli.py` (`tutor app`) | P0-T04, P0-T05, P0-T06 | App mở ở `127.0.0.1`; đủ 11 mục; Hôm nay hiện "Không có gì chờ duyệt…"; đồng hồ tutor.db = tổng số dòng thật | NFR1 | 2 |
| P0-T08 | Robot kiểm UI | Chuyển `docs/prototype/check.py` (Playwright) sang app thật: bấm mọi nút không có `data-no-autoclick`, bắt nút chết, lỗi console, tràn ngang ở 390 px | `tests/ui/check.py` | P0-T07 | Chạy trên khung app: 0 lỗi console, 0 tràn ngang | NFR1 | 0.5 |
| P0-T09 | Migration 001 (cột đề xuất) | Thêm `kc.lop` (C-10), `session.review_seconds` (C-09) nếu chủ dự án duyệt; cập nhật `docs/architecture/schema.sql` | `tutor/db/migrations/001.sql` | P0-T02 | DB `user_version` 0 → 1, cột mới có, dữ liệu cũ còn nguyên | FR9, §9.6 | 0.5 |

### P1 — Ingest

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P1-T01 | LLM gateway | `llm.call(agent, phần cố định, bài HS, schema, ngữ cảnh)` dùng `client.messages.parse` với Pydantic; prompt cache cho phần cố định; bài HS luôn trong khung UNTRUSTED INPUT (thoát chuỗi đóng khung); retry lỗi mạng / quá tải; sai schema → thử lại 1 lần rồi gắn cờ; model theo settings (C-13); ghi 1 dòng `llm.jsonl` (C-07); `FakeLLM` cho test (§9.4). *§9.5 không xếp llm.py vào pha nào; 01 cần từ P1* | `tutor/llm.py`, `tests/fakes.py` | P0-T05 | Unit: dòng log đủ trường C-07; prompt không chứa `student.name`; bài HS chứa chuỗi đóng khung vẫn nằm trong khung; sai schema 2 lần → cờ, không có lần 3 | NFR3, NFR6, NFR7, NFR10 | 2 |
| P1-T02 | services/latex.py | pylatexenc cắt `\begin{problem}[id]` và `\begin{solution}[…]` (dùng lại cấu hình environment của `bankcheck.py`), bỏ qua comment; tách bước theo đoạn / dòng / phương trình, giữ `pos`/`pos_end`; đọc metadata `% nguon`, `% lop`, `% kc_du_kien`, `% do_kho_du_kien` | `tutor/services/latex.py`, `tests/services/test_latex.py` | P0-T01 | 10 file `data/dummy/bank`: 310 bài, id khớp `bankcheck.py`, 343 lời giải, số bước mỗi lời giải = số đoạn (= "Xong khi" P1, phần ngân hàng) | FR1, FR6 | 2 |
| P1-T03 | Nhập danh mục KC từ CSV | Hàm repo đọc `kc.csv` + `kc_prereq.csv` (UTF-8 BOM), code → id, `parent_code`, chặn tự trỏ và vòng (DFS như `bankcheck.py`); xem trước (mới / đổi / quan hệ mới); áp dụng 1 transaction; đổi mô tả KC → `kc.embedding = NULL` | `tutor/db/repo.py` (import_catalog), `tests/db/test_catalog.py` | P0-T04, P0-T09 | `data/dummy/bank` → 74 kc, 74 kc_prereq; nhập lại → 0 thay đổi; CSV có vòng → từ chối, báo đường vòng | FR9 | 1.5 |
| P1-T04 | Danh mục: Kỹ năng + Tiên quyết | Cây nhóm → KC, lọc lớp, chi tiết KC, Thêm / Sửa KC, Thêm / Xoá tiên quyết (chặn tự trỏ, chặn vòng), Nhập từ CSV (xem trước → Áp dụng), Xuất CSV | `app/` (catalog) | P1-T03, P0-T07 | Robot UI xanh; thêm tiên quyết tạo vòng → lỗi kèm đường vòng; xuất rồi nhập lại → 0 thay đổi | FR9 | 2 |
| P1-T05 | Nạp sẵn ngân hàng dummy (dev/test) | Script nạp `problem` từ 10 file (`source = "dummy:<file>"`); `problem_kc` từ `% kc_du_kien` (step_idx như contract §5); rubric v1 sinh bằng code (1 mục / đoạn, Đáp số gộp mục cuối); δ = (do_kho_du_kien − 3) × 0.6, `difficulty_approved_at` = lúc nạp. Từ chối chạy trên `data/tutor.db` nếu thiếu cờ `--dev` (C-32) | `tutor/db/seed_dummy.py` | P1-T02, P1-T03 | DB dev: 310 problem, 310 rubric, 310 δ, mọi bài ≥ 1 problem_kc; query "bài ứng viên cho 1 KC" (§8.6) trả dòng | FR2, FR5 | 1 |
| P1-T06 | Học sinh (tối thiểu) | Hàm repo thêm / sửa / lưu trữ HS; màn hình Học sinh: danh sách (mã, tên "chỉ lưu trên máy", lớp), Thêm / Sửa / Lưu trữ. *Kéo từ P4: §3.5 bước 2 cần HS có trước khi nộp* | `tutor/db/repo.py`, `app/` (students) | P0-T04, P0-T07 | Thêm HS → toast "mã gửi API: HS-0n"; Lưu trữ → `archived_at`, ẩn khỏi danh sách mặc định | FR5, NFR7 | 1 |
| P1-T07 | Bộ bài làm HS mẫu (fixture) | ~10 file `.tex` bài HS dựng từ ngân hàng dummy, 3–5 bài / file, lỗi gài sẵn + nhãn (bài, bước, mã lỗi, KC); gồm 1 bài thiếu id, 1 bài có câu chèn lệnh, 1 cặp file trùng; 2 PDF biên dịch sẵn (1 PDF để thử bản chép lệch; cần TeX có gói `vietnam`) | `tests/fixtures/submissions/`, `labels.json` | P1-T02 | latex.py cắt đúng mọi file; nhãn chỉ dùng mã có trong `error_code` và KC có trong `problem_kc` của bài | FR1, FR3, NFR6 | 1.5 |
| P1-T08 | Agent 01 Ingest (.tex) | Cắt bằng latex.py; có id → khớp `problem.ref`; không id → LLM so đề (C-12) trả ứng viên + điểm, dưới ngưỡng → cờ `low_match`; bài chưa có rubric đã duyệt → cờ `no_rubric`; tách bước; transcript giữ nguyên lỗi HS | `tutor/agents/ingest.py` | P1-T01, P1-T02, P1-T05, P1-T07 | Fixture: khớp id 100 % với bài có id; bài thiếu id có cờ, ứng viên đúng trong top-3 (FakeLLM); transcript == file nguồn; số bước đúng nhãn (= "Xong khi" P1, phần bài HS) | FR1 | 2 |
| P1-T09 | Agent 01 nhánh PDF *(có điều kiện)* | PDF → document block, chép LaTeX nguyên văn; `services/pdftext.py` lấy text layer (C-35), kiểm mọi số và biến của bản chép có trong text layer, lệch → cờ `mismatch`. Bỏ cả task nếu §11.1 câu 2 = HS nộp được .tex (§11.2 #2) | `tutor/agents/ingest.py`, `tutor/services/pdftext.py` | P1-T08 | PDF lệch dấu → cờ `mismatch`; PDF sạch → 0 cờ | FR1 | 2 |
| P1-T10 | G1 phần đầu: ① ghi session + 01 | `graphs/state.py` (SessionState Pydantic), `graphs/session.py`: chặn trùng sha256 và ngày học sớm hơn buổi đã ghi → ① insert session (running, thread_id C-05) → 01 → DỪNG `confirm_match` nếu có cờ; SqliteSaver (C-04); lỗi → session failed, chạy lại từ checkpoint cuối; lệnh `tutor ingest <hs> <file>`. Graph kết thúc sau 01 (P2 nối tiếp) | `tutor/graphs/{state,session}.py`, `tutor/cli.py` | P1-T06, P1-T08 | Test FakeLLM: file trùng → từ chối trước ①; ngày sớm hơn → từ chối; lỗi gài sau 01 → failed, chạy lại không gọi lại 01 | FR1, NFR9 | 2.5 |
| P1-T11 | Buổi học bước 1–2 | Danh sách buổi; bước 1 (chọn HS, ngày, file trong `data/inbox/`, sha256, chip PDF); bước 2 dải graph G1 theo tiến độ thread, Xem bản chép LaTeX, toast nộp trùng | `app/` (session) | P1-T10, P0-T07 | Robot UI xanh; nộp trùng → toast "trùng sha256"; chạy xong dừng ở `confirm_match` hoặc hết 01 | FR1 | 2 |

### P2 — Chấm + chẩn đoán

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P2-T01 | Agent 02 Grader (chấm) | Prompt = rubric + lời giải mẫu + 1 ví dụ chấm + bài HS (UNTRUSTED); Grade từng mục + `evidence_latex`; code kiểm tổng điểm = tổng mục, mục đạt phải có bằng chứng, cờ `alt_method` | `tutor/agents/grader.py` | P1-T01, P1-T05 | Unit: tổng lệch → cờ; mục đạt thiếu bằng chứng → cờ; `alt_method` → vào hàng duyệt | FR2, NFR3 | 2 |
| P2-T02 | Agent 02 sinh rubric | Lời giải mẫu → mục nhị phân bám bước / ý, ghi cách giải khác được chấp nhận; dùng cho cờ `no_rubric` (G1) và G2 (P5) | `tutor/agents/grader.py` (generate_rubric) | P1-T01, P1-T02 | 10 bài dummy: đúng schema, ≥ 1 mục / bài, `max_score` = tổng điểm mục | FR2, FR6 | 1 |
| P2-T03 | Agent 03 Diagnoser | 2 lượt (viết lại lời giải đúng theo cách HS → so tìm bước sai đầu + bước sai khác); taxonomy mã đang bật + 1 ví dụ / mã; 5 lỗi đã duyệt gần nhất (SQL §8.6, C-14); `kc_id` chỉ trong `problem_kc` của bài; confidence; `prompt_version` (C-08) | `tutor/agents/diagnoser.py` | P1-T01, P1-T05 | Unit: mã không active hoặc `kc_id` ngoài bài → loại + cờ; prompt đủ ví dụ các mã có ví dụ; test FakeLLM | FR3, NFR3 | 2.5 |
| P2-T04 | Agent 04 Verifier + thứ tự hàng duyệt | Mỗi lần 1 lỗi, chỉ thấy kết luận của 03 + bài + lời giải mẫu; verdict `agree` / `disagree` / `wrong_code` + lý do (+ mã gợi ý); 1 lượt, không tự hoà giải; hàm xếp: phản đối / sai mã → confidence < ngưỡng (C-27) → còn lại | `tutor/agents/verifier.py` | P2-T03 | Test: prompt 04 không chứa lý luận / prompt của 03; thứ tự đúng trên 6 thẻ mẫu | FR3, FR4 | 1.5 |
| P2-T05 | G1 song song tới DỪNG duyệt | Send mỗi bài 02 → 03 → 04; DỪNG `confirm_match` khi có cờ, chạy tiếp với quyết định (chọn bài, bản chép, rubric); trước DỪNG duyệt đặt `session.status = awaiting_review`; chạy lại chỉ node lỗi và node sau | `tutor/graphs/session.py` | P1-T10, P2-T01, P2-T02, P2-T04 | Test FakeLLM: 3 bài chạy 3 lane; lỗi gài ở 03 lane 2 → chạy lại chỉ gọi 03, 04 của lane 2 (đếm lời gọi); tutor.db chỉ có dòng session | FR1, FR2, FR3, NFR9 | 2.5 |
| P2-T06 | Buổi học bước 3 (xác nhận cờ) | `low_match`: chọn ứng viên / Chọn bài khác; `mismatch`: bản chép ↔ text layer; `no_rubric`: sửa + duyệt rubric tại chỗ (C-16); Chạy tiếp chỉ bật khi hết cờ, ghi lý do | `app/` (session) | P2-T05, P1-T11 | Robot UI xanh; còn cờ → nút tắt kèm "còn n cờ chưa xử lý"; hết cờ → G1 chạy tới DỪNG duyệt | FR1, FR2 | 2 |
| P2-T07 | Danh mục › Mã lỗi | 5 nhóm; thêm mã `<category>.<sub>`; thêm / sửa ví dụ; bật / tắt (`other.unclear` khoá, không xoá); Xuất CSV (C-30); đổi ví dụ / mô tả → `prompt_version` 03 đổi + nhãn "chưa kiểm 3 lần" | `app/` (catalog), `tutor/db/repo.py` | P1-T04, P2-T03 | Tắt mã → biến khỏi prompt 03 và menu Sửa (E); tắt `other.unclear` bị chặn; sửa ví dụ → `prompt_version` mới trong `llm.jsonl` | FR9, NFR8 | 1.5 |
| P2-T08 | Nhật ký & chi phí (bản đầu) | Đọc `llm.jsonl`: chi phí tháng / ngân sách (đơn giá trong settings, ghi "giả định"), theo agent, theo buổi; bảng lời gọi lọc agent / graph / HS / thread; xem prompt & output; đồng hồ chi phí ở thanh trên | `app/` (logs), hàm đọc log | P1-T01, P0-T07 | Tổng chi phí trên màn hình = tính tay từ `llm.jsonl` mẫu; lọc theo thread ra đúng lời gọi | NFR3, NFR10 | 2 |
| P2-T09 | Vận hành (bản đầu) + liệt kê thread | Hàm liệt kê thread từ checkpoint (C-05: graph, đối tượng, node hiện tại, trạng thái, số checkpoint); bảng thread, xem state; khối Lưu trữ (đường dẫn, số dòng mỗi bảng) | `tutor/graphs/threads.py` *(đề xuất, ngoài §9.2)*, `app/` (ops) | P1-T10, P0-T07 | Thread đang chạy / DỪNG / lỗi hiện đúng trạng thái; state hiện đủ khoá SessionState | NFR1, NFR9 | 1.5 |
| P2-T10 | Harness đánh giá + kiểm 3 lần | Chạy G1 tới DỪNG duyệt trên 1 bộ bài có nhãn; tính tỉ lệ đúng bước sai, kappa mã lỗi GV–LLM, tỉ lệ bỏ / thêm, % tiêu chí đổi điểm qua 3 lần (pass^3); lưu theo `prompt_version` | `tests/eval/` (runner, metrics) | P2-T05, P1-T07 | Chạy trên fixture P1-T07 ra đủ chỉ số; kappa khớp ví dụ tính tay (= "Xong khi" P2 trên bộ mẫu) | NFR8, §9.6 | 2 |
| P2-T11 | Tiếp nhận bộ đánh giá thật | Script ẩn danh 20–50 bài thật (tên → mã HS); lưu ngoài repo; nhãn = quyết định GV khi duyệt (từ P3). Phụ thuộc ngoài: §11.1 câu 4 | script ẩn danh, `data/eval/` (không commit) | P0-T05 | ≥ 20 file; tìm tên HS trong bộ = 0 kết quả | NFR7, §9.6 | 1 |

### P3 — Duyệt + commit

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P3-T01 | Quyết định duyệt trong thread | Decision `accept` / `edit` / `reject` / `add` lưu trong state; Sửa chỉ chọn mã đang bật + KC của bài; `add` có `llm_json` NULL; Tạm dừng, duyệt sau giữ quyết định; đồng hồ duyệt cộng dồn (C-09) | `tutor/graphs/state.py`, `tutor/graphs/session.py` | P2-T05 | Unit: ánh xạ quyết định → dòng mistake đúng contract §7; dừng rồi mở lại giữ nguyên quyết định | FR4 | 1.5 |
| P3-T02 | Commit ② (attempt, mistake, rubric, session) | `repo.commit_session`: sao lưu (C-29), rồi 1 transaction ghi attempt, mistake (giữ `llm_json`), rubric duyệt ở bước 3 (C-16), session → committed (+ `review_seconds`); trả biên nhận số dòng. Bảng skill_* thêm ở P4-T04 | `tutor/db/repo.py`, `tutor/graphs/session.py` | P3-T01, P0-T04 | Lỗi gài giữa transaction → 0 dòng mới; file sao lưu có trước commit; edit / reject / add lưu đúng status (= "Xong khi" P3, vế 2) | FR4, NFR5, NFR9 | 2 |
| P3-T03 | Hàng đợi + khoá theo ngày | Xếp G1 → G5 (G1 theo HS rồi `held_on` tăng; graph khác theo checkpoint cuối); khoá thread G1 khi cùng HS có buổi sớm hơn đang chờ / lỗi / đang chạy (C-28), kèm lý do + thread chặn | `tutor/graphs/threads.py` | P2-T09 | Unit: 3 ca khoá (chờ, lỗi, đang chạy) + 1 ca mở khoá sau commit | FR4, NFR4 | 1.5 |
| P3-T04 | CLI `tutor review [id]` | Không id: in hàng đợi; có id: duyệt G1 trên terminal (A / E / R / N) rồi chạy tiếp tới commit | `tutor/cli.py` | P3-T02, P3-T03 | Test CLI (FakeLLM, input kịch bản): ingest → review id → session committed | FR4 | 1.5 |
| P3-T05 | Buổi học bước 4 (Duyệt lỗi) | 3 cột (bài HS trong khung UNTRUSTED INPUT · 02 Grader · thẻ lỗi theo thứ tự P2-T04 với "Diagnoser nói / Verifier nói"); phím A / E / R / N, J / K; Sửa (mã active, KC của bài); Thêm lỗi bị sót bằng bấm vào bước; đồng hồ duyệt; ngữ cảnh 5 lỗi của 03; Tạm dừng, duyệt sau; không có nút "Duyệt tất cả" | `app/` (session) | P3-T01, P2-T06 | Robot UI xanh; phím A / E / R / N đổi đúng trạng thái thẻ; mở lại sau Tạm dừng giữ quyết định | FR4, NFR4, NFR6 | 3 |
| P3-T06 | Buổi học bước 5 + xem buổi đã ghi | Toast sao lưu + biên nhận "1 transaction · +n …"; xem buổi committed: bài, chấm, lỗi theo status, đề xuất gốc vs bản cuối (`llm_json`) | `app/` (session) | P3-T02, P3-T05 | Số trên biên nhận = số dòng thật thêm vào tutor.db | FR4, NFR3 | 1.5 |
| P3-T07 | Hộp duyệt | Banner cố định; lọc graph / HS; bảng chờ (thread_id, graph, đối tượng, lý do dừng, số mục, bất đồng 04, chờ từ, trạng thái); dòng khoá có lý do + Mở buổi chặn; khối thread lỗi / đang chạy; Mở → đúng màn hình (§3.4) | `app/` (review) | P3-T03, P0-T07 | Robot UI xanh; Mở G1 có cờ → bước 3, không cờ → bước 4; dòng khoá: nút Mở tắt kèm lý do | FR4, NFR4, NFR9 | 1.5 |
| P3-T08 | Vận hành: chạy lại, huỷ, dọn, sao lưu | Chạy lại từ checkpoint cuối; Huỷ thread (G1 theo C-15); Dọn thread đã commit; Sao lưu ngay + danh sách bản sao | `app/` (ops), `tutor/graphs/threads.py`, `tutor/db/repo.py` | P3-T02, P2-T09 | Huỷ thread G2–G5 → tutor.db không đổi; Huỷ G1 → đúng C-15; Sao lưu ngay → file mới mở được | NFR9 | 1.5 |
| P3-T09 | Hôm nay: việc cần làm + cảnh báo | Đếm theo graph + 5 mục chờ lâu nhất (Mở, Duyệt tiếp); cảnh báo thread lỗi / bị khoá / đang chạy (Chạy lại từ checkpoint); khối Hệ thống (commit cuối, sao lưu cuối, chi phí tháng) | `app/` (today) | P3-T03, P2-T08 | "Chờ duyệt (n)" = số mục trong Hộp duyệt; Duyệt tiếp mở mục chưa khoá đầu tiên | NFR4, NFR9 | 1 |
| P3-T10 | Test bất biến "không gì vào DB trước khi duyệt" | Mọi đường G1 (có / không cờ, tạm dừng, lỗi + chạy lại, huỷ): tutor.db chỉ đổi dòng session cho tới commit ②; không lệnh / endpoint nào commit khi còn đề xuất chưa quyết | `tests/graphs/test_no_write_before_review.py` | P3-T02, P3-T04 | Test xanh (= "Xong khi" P3, vế 1) | NFR4, NFR5 | 1 |

### P4 — Profiler

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P4-T01 | services/elo.py: Elo | P = 1 / (1 + e^−(θ − δ)), θ ← θ + K(X − P), K = 0.3, θ0 = 0; X theo (attempt, KC) từ `mistake_current` có `kc_id`; lỗi không KC không ảnh hưởng Elo; bài chưa có δ → C-19 | `tutor/services/elo.py`, test | P0-T01 | Unit: θ = 0.10, δ = 0.35, X = 0 → P = 0.44, θ = −0.03; X = 0 không bao giờ làm θ tăng (tỉ lệ sai hướng = 0); HS mới θ = 0 (= "Xong khi" P4, vế 1) | FR5, NFR2 | 1 |
| P4-T02 | Lỗi lặp, so với buổi trước, replay | misconception_log (khoá HS, mã, KC; resolved khi ≥ 2 đúng liên tiếp sau lần sai cuối; tái xuất hiện → xoá `resolved_at`, count + 1); Δθ theo KC; mã lặp lại / mới / đã hết (SQL §8.6); `replay(student)` dựng skill_event / skill_state / misconception_log từ lịch sử (C-18, C-20) | `tutor/services/elo.py` | P4-T01, P0-T04 | Unit trên fixture 3 buổi: resolved đúng buổi; lặp / mới / hết khớp query §8.6 | FR5 | 1.5 |
| P4-T03 | Agent 05 Profiler (phần LLM) | LLM viết `knowledge_state` ≤ 150 từ CHỈ từ số liệu P4-T02; code kiểm ≤ 150 từ và không có số lạ | `tutor/agents/profiler.py` | P1-T01, P4-T02 | Unit: > 150 từ → viết lại 1 lần rồi cờ; số không có trong đầu vào → cờ | FR5 | 1 |
| P4-T04 | G1: node 05 + commit ② đủ bảng | Node 05 sau DỪNG duyệt; commit ② ghi thêm skill_event, skill_state, misconception_log, `knowledge_state` trong cùng transaction; buổi sau của HS được mở khoá | `tutor/graphs/session.py`, `tutor/db/repo.py` | P4-T03, P3-T02 | Test: 2 HS × 3 buổi commit theo ngày → skill_state == `replay()`; lỗi trong transaction → 0 dòng | FR5, NFR5 | 1 |
| P4-T05 | Sửa lỗi đã lưu + Dựng lại trạng thái | Buổi học › Sửa lỗi đã lưu: dòng mistake mới + `supersedes_id`, rồi replay HS đó trong 1 transaction; Học sinh › Dựng lại trạng thái từ lịch sử (báo % khớp) | `tutor/db/repo.py`, `app/` (session, students) | P4-T04, P3-T06 | Sửa lỗi cũ → trạng thái == tính lại từ đầu; replay skill_event cho đúng skill_state (= "Xong khi" P4, vế 2) | FR5 | 2 |
| P4-T06 | Xem trước Profiler | Bảng (attempt, KC): X, P, θ trước → sau, δ (nút "?"); thay đổi lỗi lặp; Δθ; `knowledge_state`; danh sách "Sẽ ghi vào tutor.db (1 transaction)"; Chạy Profiler chỉ bật khi mọi thẻ đã quyết | `app/` (session) | P4-T04, P3-T05 | Số trên bản xem trước = số ghi sau commit; nút tắt kèm "còn n đề xuất chưa quyết" | FR5, NFR3 | 1.5 |
| P4-T07 | Học sinh: hồ sơ | Tiến bộ; Kỹ năng (Elo, biểu đồ θ từ skill_event); Lỗi lặp lại; Lịch sử buổi; bản đồ nhiệt HS × KC; máy tính Elo; Xem dữ liệu gửi API (chỉ mã HS, khung UNTRUSTED) | `app/` (students) | P4-T05, P1-T06 | Robot UI xanh; θ trên hồ sơ = skill_state; payload mẫu không chứa tên HS | FR5, NFR3, NFR7 | 3 |
| P4-T08 | Hôm nay: HS cần chú ý + nhịp "Sau mỗi buổi học" | HS có Δθ TB < 0, lỗi lặp ≥ 2 lần chưa hết, buổi lỗi; thẻ nhịp G1 | `app/` (today) | P4-T04, P3-T09 | Danh sách khớp query tay trên fixture | FR5 | 0.5 |
| P4-T09 | Vận hành › Cài đặt + Riêng tư & an toàn | Sửa `settings.json` (tỉ lệ gợi ý, số bài, số ngày không lặp, ngưỡng confidence, model mỗi agent, ngân sách); K, ngưỡng resolved chỉ đọc; bảng tên ↔ mã HS; công tắc "Chỉ gửi mã HS" (đề xuất) | `app/` (ops), `tutor/config.py` | P2-T09, P0-T05 | Lưu → đọc lại đúng; đổi model của 03 → lời gọi sau ghi model mới trong `llm.jsonl` | FR7, NFR7 | 1.5 |
| P4-T10 | Nhật ký: chất lượng agent + ổn định prompt | Chất lượng đo từ quyết định GV (03 % bị bỏ / sửa / GV thêm; 04 % đồng ý GV; kappa mã lỗi; thời gian duyệt TB / buổi); Prompt & độ ổn định (pass^3 theo `prompt_version`, nút Chạy kiểm tra ổn định gọi harness); nhật ký quyết định GV | `app/` (logs) | P2-T08, P2-T10, P3-T02 | Chỉ số trên màn hình = tính tay trên fixture; prompt chưa kiểm hiện "chưa kiểm 3 lần" | NFR3, NFR8, NFR10 | 1.5 |
| P4-T11 | E2E bản đầu | Kịch bản trên fixture: 2 HS × 3 buổi, có cờ, lỗi + chạy lại, khoá ngày, sửa lỗi đã lưu; quét `llm.jsonl` không có tên HS; bài có câu chèn lệnh vẫn ra output đúng schema; robot UI 6 màn hình MVP + Nhật ký | `tests/e2e/`, `tests/ui/` | P4-T05, P4-T06, P4-T07, P4-T08, P4-T09, P4-T10, P0-T08 | Toàn bộ xanh; chi phí mỗi buổi đọc được từ `llm.jsonl` | FR1–FR5, NFR3–NFR10 | 2 |

### P5 — Ngân hàng

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P5-T01 | services/embed.py | MiniLM local (sentence-transformers): embed mô tả KC → `kc.embedding` (float32 BLOB) + `embed_model`; cosine top-5; `embedding` NULL = cũ | `tutor/services/embed.py` | P1-T03 | Unit: top-5 đúng trên vector cố định; embed 74 KC chạy CPU, không gọi mạng sau khi đã tải model | FR6 | 1.5 |
| P5-T02 | Agent 06 Tagger | Tách bước lời giải mẫu (latex.py) → LLM mô tả kỹ năng từng bước → embedding top-5 → LLM xếp hạng + trích bằng chứng + cảnh báo tiên quyết | `tutor/agents/tagger.py` | P5-T01, P1-T01, P1-T02 | Trên dummy: đo được % `kc_du_kien` nằm trong top-5 (§9.6) | FR6 | 2.5 |
| P5-T03 | G2 bank_graph (tag) | latex.py cắt → mỗi bài 06 + 02 sinh rubric → DỪNG (GV chọn ≥ 1 KC / bài, sửa rubric) → commit 1 transaction: problem, problem_kc (chỉ tag GV chọn), rubric, `kc.embedding`; ref đã có → bỏ qua, báo; `tutor bank tag <bank.tex>` + `tutor review` cho G2 | `tutor/graphs/bank.py`, `tutor/cli.py` | P5-T02, P2-T02, P3-T03 | Test FakeLLM: tutor.db không đổi tới commit; chỉ KC GV chọn được lưu; nạp lại cùng file → "0 bài mới" | FR6, NFR4, NFR5 | 2.5 |
| P5-T04 | services/bt.py | Fit Bradley-Terry từ cặp hỏi 2 chiều (lệch = hoà); quy về δ theo C-21; fit lại khi thêm cặp, δ đã duyệt không đổi | `tutor/services/bt.py` | P0-T01 | Unit: dữ liệu giả biết trước thứ tự → Spearman ≥ 0.9; hoà xử lý đúng; fit lại không đổi δ đã duyệt | FR6 | 1.5 |
| P5-T05 | Agent 07 + G3 bank_graph (độ khó) | Ghép cặp (C-22, ~10 cặp / bài) → 07 hỏi (A, B) và (B, A) → bt.py → DỪNG (GV đổi chỗ ▲▼) → commit problem_pair, `bt_score`, `delta`, `n_comparisons`, `difficulty_approved_at`; từ chối khi chưa có tag đã duyệt; `tutor bank difficulty` (+ `tutor review` cho G3) | `tutor/agents/difficulty.py`, `tutor/graphs/bank.py` | P5-T04, P5-T03 | Chủ đề chưa tag → từ chối kèm lý do; chạy lại không đổi δ đã duyệt; đo tương quan δ ↔ `% do_kho_du_kien` | FR6 | 3 |
| P5-T06 | Ngân hàng bài: khung + danh sách | Stepper 5 bước; tiến độ theo chủ đề (đã tag / có rubric / có δ); danh sách bài + trạng thái (gồm dòng chỉ có trong checkpoint); chi tiết bài; Nạp file .tex; Sửa rubric (version mới qua repo) | `app/` (bank) | P5-T03, P0-T07 | Robot UI xanh; trạng thái bài đúng quy tắc contract §5 | FR2, FR6 | 2.5 |
| P5-T07 | Duyệt tag + rubric (G2) | Mỗi bước 5 ứng viên (cosine, hạng LLM, bằng chứng, cảnh báo tiên quyết); Thêm KC khác / Tạo KC mới; sửa rubric; Duyệt bài này; Ghi lô vào tutor.db chỉ bật khi duyệt đủ | `app/` (bank) | P5-T06 | Ghi lô tắt kèm "còn n bài chưa duyệt"; biên nhận = số dòng thật | FR6, NFR4 | 2.5 |
| P5-T08 | Duyệt độ khó (G3) | Chọn KC; bảng cặp (A, B) / (B, A) / kết quả; xếp hạng (`bt_score`, δ, n); ▲▼; dấu "GV chỉnh"; Duyệt độ khó; Tính lại khi thêm bài | `app/` (bank) | P5-T05, P5-T06 | Robot UI xanh; ▲▼ đổi thứ tự δ; sau duyệt δ có dấu khoá | FR6 | 2 |
| P5-T09 | Đo tiêu chí P5 | Chạy G2 / G3 trên dummy (DB mới): % `kc_du_kien` trong top-5, tương quan δ; khi GV dùng thật: % bài có KC GV chọn nằm trong top-5 (không phải Thêm KC khác) | `tests/eval/bank_metrics.py` | P5-T07, P5-T08 | Báo cáo 2 tỉ lệ, đạt ngưỡng C-23 (= "Xong khi" P5) | FR6 | 1 |
| P5-T10 | Hôm nay + Danh mục: phần ngân hàng | Thẻ nhịp "Lần đầu / khi thêm bài" (sẵn sàng / tổng); trạng thái embedding (cũ / mới) trong Danh mục | `app/` (today, catalog) | P5-T03, P3-T09, P1-T04 | Số sẵn sàng = đếm SQL | FR6 | 0.5 |

### P6 — Gợi ý

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P6-T01 | services/select.py | Chia số bài theo tỉ lệ (C-24); KC ôn = lỗi lặp chưa hết; vừa sức θ − δ ∈ [−0.5, 0.5]; thử thách theo C-24; lọc đúng KC, chưa làm trong 30 ngày, có rubric, δ đã duyệt (kèm lý do loại); xếp \|θ − δ\|; trộn ≥ 3 KC | `tutor/services/select.py` | P4-T04, P5-T05 | Unit: 6 → 2/3/1; đổi tỉ lệ → đổi chia; làm 29 ngày trước bị loại, 31 ngày được giữ; ≥ 3 KC; HS mới θ = 0 vẫn chạy (= "Xong khi" P6) | FR7, NFR2 | 2.5 |
| P6-T02 | Agent 08 Recommender | Chỉ nhận danh sách đã lọc; kiểm phù hợp + lý do 1 dòng (C-25); code loại mọi `problem_id` ngoài danh sách | `tutor/agents/recommender.py` | P6-T01, P1-T01 | FakeLLM trả bài ngoài danh sách → bị loại + cờ | FR7 | 1 |
| P6-T03 | G4 recommend_graph | Đọc trạng thái → select.py → 08 → ghi bản nháp `data/out/recommend-<HS>-<ngày>.md` → DỪNG → quyết định (duyệt / bỏ / thay cùng KC từ danh sách lọc / thêm) → commit recommendation → ghi lại .md đã duyệt; `tutor recommend <hs> [--date]`; đường CLI: sửa .md rồi `tutor review` | `tutor/graphs/recommend.py`, `tutor/cli.py` | P6-T02, P3-T03 | Thay chỉ nhận bài cùng KC trong danh sách lọc; thẻ chưa quyết = duyệt; chặn trùng (student, for_date, problem) | FR7, NFR4 | 2.5 |
| P6-T04 | Màn hình Gợi ý bài | Chọn HS + ngày; hộp luật (thanh trượt xem trước, chỉ code); Bước 1–3; thẻ Bỏ / Thay / Thêm / Vì sao bài này?; lịch sử đã duyệt; xem / tải .md; Duyệt danh sách | `app/` (recommend) | P6-T03, P4-T09 | Robot UI xanh; cảnh báo khi < 3 KC; biên nhận đúng số dòng | FR7 | 2.5 |
| P6-T05 | Hôm nay + Học sinh: phần gợi ý | Thẻ "Trước buổi sau" (HS chưa có danh sách đã duyệt cho ngày sau buổi cuối); tab Gợi ý & báo cáo (gợi ý); nút từ Buổi học bước 5 | `app/` (today, students, session) | P6-T03, P4-T07, P4-T08 | Số HS cần danh sách = query tay | FR7 | 0.5 |

### P7 — Report

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P7-T01 | services/facts.py | SQL → `facts.json`, mỗi fact có `fact_id` + câu SQL (số bài, số buổi, tỉ lệ đạt rubric, Δθ theo KC §8.6, mã thường gặp, lỗi lặp, đã hết); chọn 3 insight (C-26) | `tutor/services/facts.py` | P4-T04 | Cùng DB → cùng `facts.json`; Δθ khớp query §8.6 | FR8, NFR3 | 2.5 |
| P7-T02 | services/audit.py | Mỗi câu ≥ 1 `[Fxx]`; mọi số khớp fact được trích (chuẩn hoá `,` và `%`); các phần cộng lại bằng tổng; cảnh báo giọng văn khi tỉ lệ đạt < ngưỡng (C-27) | `tutor/services/audit.py` | P7-T01 | Câu sai số → trượt kèm lý do "số 70% không khớp F02 = 68%"; câu không fact_id → trượt; câu đúng → đạt (= "Xong khi" P7, vế 1) | FR8, NFR3 | 1.5 |
| P7-T03 | Agent 09 Reporter | Viết theo mục tiêu (KC vững → khen + mở rộng; yếu → lời khuyên gắn tiên quyết và bài gợi ý); câu trượt audit viết lại đúng 1 lần, vẫn trượt → bỏ | `tutor/agents/reporter.py` | P7-T02, P1-T01 | FakeLLM: đúng 1 lần viết lại; câu trượt 2 lần ghi "bỏ" trong `audit_json` | FR8 | 1.5 |
| P7-T04 | G5 report_graph | facts → 3 insight → 09 → audit → ghi bản nháp .md → DỪNG (GV sửa câu, audit lại chỉ cảnh báo) → commit report → ghi lại .md; 0 buổi đã duyệt trong tháng → từ chối kèm lý do; `tutor report <hs> <tháng>` | `tutor/graphs/report.py`, `tutor/cli.py` | P7-T03, P3-T03 | Duyệt lần 2 cùng tháng bị chặn (UNIQUE); tutor.db không đổi tới commit | FR8, NFR4 | 2 |
| P7-T05 | Màn hình Báo cáo tháng | Bảng HS × tháng; dải G5; bảng facts; 3 insight; bản nháp có chip `[Fxx]` + nhãn đạt / đã viết lại / bị bỏ; Sửa câu; Chạy lại audit; Duyệt & ghi report; bản đã duyệt chỉ đọc | `app/` (report) | P7-T04 | Robot UI xanh; sửa câu sai số → cảnh báo đỏ | FR8 | 2.5 |
| P7-T06 | Truy vết ngược | Câu `[F04]` → dòng fact → Xem nguồn → lịch sử buổi → bằng chứng lỗi → Xem lời gọi LLM (lọc thread + agent) | `app/` (report, students, session, logs) | P7-T05, P4-T07, P4-T10 | Robot đi hết chuỗi trên fixture | NFR3 | 1 |
| P7-T07 | GV đọc thử 3 report | Chạy G5 cho 3 HS trên ≥ 1 tháng dữ liệu đã duyệt; GV ghi nhận xét (đúng số, không khen quá tay, độ dài). Phụ thuộc ngoài: 1 tháng dữ liệu thật | biên bản nhận xét | P7-T05 | GV chấp nhận 3/3 hoặc có danh sách sửa (= "Xong khi" P7, vế 2) | FR8 | 0.5 |
| P7-T08 | Hôm nay + Học sinh: phần report | Thẻ "Cuối tháng"; tab Gợi ý & báo cáo (report) | `app/` (today, students) | P7-T04, P6-T05 | Số report đã duyệt = query tay | FR8 | 0.5 |

### P8 — Đóng gói + đánh giá thật *(đề xuất)*

| ID | Tên | Mô tả | Đầu ra | Phụ thuộc | Tiêu chí xong | FR/NFR | Ngày |
|---|---|---|---|---|---|---|---|
| P8-T01 | Đóng gói cài đặt | 1 lệnh cài (uv) + `tutor app`; lần đầu tạo `data/` và tutor.db; cập nhật → chạy migration; khôi phục = chép bản sao về | gói cài | P5-T10, P6-T05, P7-T08 | Máy sạch: cài + mở app ≤ 30 phút theo hướng dẫn | NFR1, NFR9 | 1.5 |
| P8-T02 | Hướng dẫn GV | 1 trang: cài, nộp bài, duyệt, sao lưu / khôi phục, quy ước soạn .tex (`data/inbox/bank`) | `docs/huong-dan-gv.md` | P8-T01 | GV làm theo không cần hỏi dev | NFR1 | 0.5 |
| P8-T03 | Bản đồ hệ thống | Chuyển `map.js`: 5 tầng, 5 graph, 9 agent, dữ liệu (số dòng thật), CLI ↔ app, nguyên tắc, thuật ngữ, không làm, chưa chốt, Chạy thử một vòng (chỉ điều hướng). Bỏ được nếu chủ dự án không cần | `app/` (map) | P7-T05 | Robot UI xanh; Chạy thử không ghi gì vào tutor.db | — | 1 |
| P8-T04 | Đánh giá trên bộ thật | Harness trên ≥ 20 bài thật GV đã duyệt: đúng bước sai, kappa mã lỗi, % bỏ / thêm, % câu report trượt audit, pass^3, thời gian duyệt / buổi, chi phí / buổi so ngân sách | báo cáo đánh giá | P2-T10, P2-T11, P4-T11 | Đủ chỉ số §9.6 (= "Xong khi" P2 trên bộ thật) | NFR8, NFR10, §9.6 | 2 |
| P8-T05 | Kiểm ổn định mọi prompt | Mọi `prompt_version` đang dùng (01–09) chạy 3 lần trên bộ đánh giá phù hợp (G1: bộ bài; 06/07: dummy; 05/08/09: fixture), ghi pass^3 | kết quả trong Nhật ký | P2-T10, P5-T05, P6-T02, P7-T03 | 9/9 agent có trạng thái kiểm 3 lần | NFR8 | 1.5 |
| P8-T06 | Chạy thử 1 tháng + đối chiếu GV | GV dùng thật 1 tháng; đối chiếu tiến bộ (θ) với cảm nhận GV (§10); lập danh sách sửa | biên bản + danh sách sửa | P8-T01, P8-T04 | Có biên bản; chi phí tháng thật đo từ `llm.jsonl` | NFR10 | 0.5 |

---

## 3. Quyết định dùng chung (2 bản SDD ghi giống nhau)

Trạng thái: **chốt** = chủ dự án đã chốt hoặc tài liệu thiết kế đã quyết; **đề xuất (chưa chốt)** = backbone chọn, chờ chủ dự án.

| # | Chủ đề | Nội dung | Trạng thái | Nguồn / lý do |
|---|---|---|---|---|
| C-01 | Công nghệ app | Web chạy local trong trình duyệt. Frontend HTML + JS thuần + MathJax 3.2.2, dùng lại shell và 11 tab của `docs/prototype/src`, thay `MOCK` bằng gọi API. Backend Python 3.12 HTTP JSON (FastAPI + uvicorn), chỉ nghe `127.0.0.1`, mở bằng `tutor app` | đề xuất (chưa chốt) | 11 màn hình đã có trong bản nháp; cùng ngôn ngữ với graph nên dùng lại schema Pydantic cho API; không phải đóng gói desktop; bản nháp đã chạy ở 390 px. §11.1 câu 7 (desktop / điện thoại) còn mở |
| C-02 | CLI | typer; mỗi nút chạy / duyệt graph có lệnh tương đương (§9.3); CLI và app chạy cùng code graph | chốt (§1.3, §4.1) | §11.1 câu 8 vẫn hỏi lại, xem mục 6 |
| C-03 | App ↔ backend | HTTP JSON. Chạy graph trả `thread_id` ngay; app hỏi tiến độ bằng polling `GET` thread (~1 s). Nhóm endpoint giống nhau ở 2 bản: `/api/threads` (list, get, resume, cancel), `/api/sessions`, `/api/students`, `/api/catalog`, `/api/bank`, `/api/recommend`, `/api/report`, `/api/logs`, `/api/settings`, `/api/backup` | đề xuất (chưa chốt) | Frontend giống nhau thì 2 bản SDD so sánh được; polling là cách đơn giản nhất |
| C-04 | Checkpoint | LangGraph `SqliteSaver`, file SQLite tách khỏi tutor.db; `interrupt()` + resume cho DỪNG; `Send` cho lane mỗi bài. Cần đối chiếu API LangGraph hiện hành | chốt trong §9.1 (stack của tác giả, chủ dự án chưa duyệt) | §3.6, §8.7, §11.4 |
| C-05 | thread_id + danh sách thread | `g<n>-<đối tượng>-<yyyymmdd>[-k]` (ví dụ `g1-hs03-20261020`); metadata (graph, đối tượng, student_id, session_id, held_on) đi kèm checkpoint; Hộp duyệt đọc từ checkpoint, không thêm bảng vào tutor.db; trạng thái G1 lấy từ `session.status`, G2–G5 suy từ checkpoint (DỪNG = awaiting_review; lỗi ghi vào metadata = failed) | đề xuất (chưa chốt) | Theo ID trong bản nháp (contract §7); giữ tutor.db chỉ chứa dữ liệu đã duyệt |
| C-06 | File cấu hình | `data/settings.json` (thư viện json chuẩn đọc + ghi, app ghi được); mặc định trong code = contract §4; K, θ0, resolve_streak là hằng | đề xuất (chưa chốt) | §3.6, §11.4 đề xuất "1 file cấu hình trong data/"; TOML thì thư viện chuẩn không ghi được |
| C-07 | Dòng `llm.jsonl` | ts, agent, prompt_version, model, graph, thread_id, session_id, student_code, token vào / ra / đọc cache / ghi cache, ms, result (`ok` / `retry` / `schema_error`), output. Không có tên HS. Chi phí tính lúc đọc từ đơn giá trong settings | NFR3 / NFR10 chốt; danh sách trường đề xuất | §3.6, §9.4, IA §3.10 |
| C-08 | prompt_version | `<agent>-<8 ký tự sha256 phần prompt cố định>` (với 03 gồm taxonomy + ví dụ), nên tự đổi khi Danh mục đổi; NFR8 gắn theo version | đề xuất (chưa chốt) | IA §3.8: sửa ví dụ mã → prompt 03 lên version mới |
| C-09 | Thời gian duyệt | Cột `session.review_seconds INTEGER` (migration 001); app đếm, cộng dồn qua Tạm dừng trong state, commit ② ghi | đề xuất (chưa chốt) | §9.6, §11.4; chỉ số theo buổi, query được bằng SQL |
| C-10 | Lớp của KC | Cột `kc.lop` (migration 001) lấy từ `kc.csv`; lớp của bài suy từ tiền tố `ref`, không thêm cột | đề xuất (chưa chốt) | §11.4; quy ước mã `<lớp>DS-…` (Phụ lục C) |
| C-11 | Mã HS | `HS-%02d` theo `student.id`, không thêm cột; chỉ mã đi qua `llm.py` | đề xuất (chưa chốt) | contract §5 (†); NFR7 chờ chốt |
| C-12 | 01 khớp bài không id | LLM nhận đề các bài cùng lớp trong phần prompt cache, trả ≤ 3 ứng viên + điểm; điểm < ngưỡng → `low_match` | đề xuất (chưa chốt) | §5 01 bước 3; ngân hàng nhỏ (310 bài) |
| C-13 | Model | `claude-opus-5-5` cho cả 9 agent, adaptive thinking, `client.messages.parse`; hạ model sau khi đo chi phí | đề xuất (chưa chốt) | §9.1, §11.2 #3 |
| C-14 | Ngữ cảnh 03 | 5 lỗi đã duyệt gần nhất của HS, mọi KC | đề xuất (chưa chốt) | §11.2 #10 |
| C-15 | Huỷ thread G1 | Xoá dòng session failed (chưa có attempt) để nộp lại được cùng file | đề xuất (chưa chốt) | §11.2 #12 |
| C-16 | Rubric duyệt ở bước 3 G1 | Ghi trong cùng commit ② | đề xuất (chưa chốt) | §11.2 #15; `attempt.rubric_id NOT NULL` |
| C-17 | 7 kiểu dữ liệu sai (P0) | (1) FK sai (`attempt.session_id` không tồn tại); (2) `kc_prereq` tự trỏ; (3) `error_code.category` ngoài 5 nhóm; (4) nộp trùng (`student_id`, `source_sha256`); (5) `mistake.status = 'proposed'`; (6) `added` có `llm_json` hoặc status khác `added` mà `llm_json` NULL; (7) `report.month` sai định dạng. Vòng tiên quyết dài hơn 1 bước: schema không chặn → code chặn (P1-T03) | đề xuất (chưa chốt) | §9.5 không liệt kê 7 kiểu; chọn từ CHECK / FK / UNIQUE trong `schema.sql` |
| C-18 | Sửa lỗi đã lưu và skill_event | Phương án (a): coi skill_event là bản tóm tắt, xoá rồi replay; không đổi schema | đề xuất (chưa chốt) | §11.2 #13 |
| C-19 | Elo khi bài chưa có δ đã duyệt | Dùng δ = 0 tạm, ghi vào `skill_event.delta`; sau khi duyệt δ, "Dựng lại trạng thái" tính lại | đề xuất (chưa chốt) | §11.4 |
| C-20 | Nơi đặt code tiến bộ | misconception, so với buổi trước, replay nằm trong `services/elo.py` | đề xuất (chưa chốt) | §9.2 không có file riêng cho phần này |
| C-21 | BT → δ | Chuẩn hoá trung bình 0, hệ số 1; chỉnh hệ số khi có dữ liệu thật. Bỏ `0.6 × bt_score` của bản nháp | đề xuất (chưa chốt) | §6.4, §11.4 |
| C-22 | Ghép cặp G3 | Ghép trong từng KC đã duyệt, ~10 cặp / bài; fit BT chung cho mọi cặp của lô → 1 δ / bài; bảng xếp hạng hiện theo KC; KC < 2 bài → bỏ qua kèm lý do. "GV chỉnh" = thứ hạng theo δ khác thứ hạng theo `bt_score`, không thêm cột | đề xuất (chưa chốt) | §3.4, §6.4 "cùng KC"; §11.4 (bản nháp: cả chủ đề) |
| C-23 | Ngưỡng "phần lớn" (P5) | ≥ 80 % bài có KC GV chọn nằm trong top-5 | đề xuất (chưa chốt) | KC-Tagging: top-10 ~87 % (§5 06) |
| C-24 | Luật gợi ý chưa chốt | Làm tròn theo phần dư lớn nhất (6 → 2/3/1); KC thử thách: mọi tiên quyết θ ≥ 0, chọn KC có δ − θ > 0.5 nhỏ nhất | đề xuất (chưa chốt) | §6.5, §11.4 (theo bản nháp) |
| C-25 | Lý do bài ôn | Ghi số lần của mã lỗi; kèm tổng của KC khi khác | đề xuất (chưa chốt) | §11.2 #14 |
| C-26 | Chọn 3 insight | Giữ cách của bản nháp (xu hướng / ngoại lệ / đa số); "điểm đổi" và xếp hạng làm sau | đề xuất (chưa chốt) | §6.6, §11.4 |
| C-27 | Ngưỡng và giá giả định | confidence thấp 0.6; kết quả thấp 50 %; ngân sách $30 / tháng; đơn giá $5 / $25 / $0.5 mỗi 1M token vào / ra / đọc cache. App ghi chữ "giả định" | giả định | §4.1, §11.4 |
| C-28 | Khoá theo ngày | Khoá cả khi buổi trước lỗi / đang chạy; khoá do code tính, không lưu | đề xuất (chưa chốt) | §11.2 #11, §4.7 |
| C-29 | Sao lưu | sqlite backup trước mỗi commit G1 + nút Sao lưu ngay; tên `tutor-<yyyy-mm-dd>-<hhmmss>.db` để nhiều commit trong ngày không ghi đè | đề xuất (chưa chốt) (§8.7 ghi `tutor-<ngày>.db`) | §8.7, NFR9 |
| C-30 | Nhập mã lỗi | Không có định dạng nhập; chỉ sửa trong app + Xuất CSV | đề xuất (chưa chốt) | §2.2 FR9, §11.4 |
| C-31 | Nhánh PDF | Tách riêng P1-T09; bỏ nếu HS nộp được .tex | chờ §11.1 câu 2 | §11.2 #2 |
| C-32 | Ngân hàng cho bản đầu | Dev / test: nạp từ nhãn dummy (P1-T05). Dùng thật trước P5: nạp ngân hàng của GV bằng cùng script **chỉ khi GV tự viết** `% kc_du_kien` / `% do_kho_du_kien` (khi đó là tag GV) | đề xuất (chưa chốt) | §9.5 lưu ý phụ thuộc; Phụ lục C |
| C-33 | Thư viện cố định | pylatexenc 2.11 (pin); MiniLM local qua sentence-transformers | chốt trong §9.1 | §9.1 |
| C-34 | Test | Test graph dùng `FakeLLM`, không gọi API thật trong test tự động; eval chạy tay | chốt (§9.4) | §9.4, §9.6 |
| C-35 | Đọc text layer PDF | pypdf (thuần Python) | đề xuất (chưa chốt) | §9.1 không chọn thư viện |

---

## 4. Chỗ 2 bản SDD được khác nhau

Mỗi writer trả lời cột "Câu hỏi" theo kiến trúc của mình; cột "Bất biến" giữ nguyên ở cả 2 bản.

| # | Khía cạnh | Câu hỏi writer phải trả lời | Bất biến (cả 2 bản) |
|---|---|---|---|
| D-1 | Tiến trình / triển khai | Mấy tiến trình, khởi động bằng gì, `tutor app` làm gì trên 1 máy | NFR1: 1 máy, 1 người dùng, không server từ xa, không đăng nhập |
| D-2 | Sở hữu dữ liệu | Ai giữ `tutor.db`, ai được ghi bảng nào, FK giữa các nhóm bảng A–D còn không | NFR5: chỉ commit node + thao tác GV qua hàm repo được ghi; schema và FK như `schema.sql` |
| D-3 | Commit ② nguyên tử | Làm sao 1 lần duyệt = 1 transaction (attempt, mistake, skill_*, misconception_log, session, rubric) | FR4: ghi đủ hoặc không ghi gì; sao lưu trước commit G1 |
| D-4 | Interrupt / resume | Ai giữ graph đang DỪNG; lệnh resume đi qua đâu; chạy dài thì báo tiến độ thế nào | Tạm dừng giữ quyết định; chạy lại chỉ node lỗi và node sau |
| D-5 | Checkpoint ở đâu | 1 file hay mỗi thành phần 1 file; Hộp duyệt gom thread của G1–G5 ra sao | 1 hàng đợi chung; Huỷ thread chỉ xoá đề xuất; tutor.db không có đề xuất |
| D-6 | App gọi graph | Đường đi từ nút trong app tới graph; CLI đi đường nào | Bộ API C-03 giống nhau; CLI tương đương nút trong app |
| D-7 | Quan sát | Ai ghi `llm.jsonl` (1 file hay gom lại); khoá truy vết giữa các thành phần; health check | Dòng log theo C-07; `thread_id` là khoá truy vết |
| D-8 | Dev local + test | Cách chạy cả hệ khi dev; FakeLLM cắm vào đâu; test tích hợp / test hợp đồng | Test graph không tốn tiền API; robot UI chạy được |
| D-9 | Embedding (torch) | MiniLM nạp trong tiến trình chính hay tách riêng | 06 chạy local, không gửi KC ra ngoài để embed |
| D-10 | Lỗi giữa các thành phần | Lỗi mạng / thành phần chết giữa chừng thì graph và DB ra sao | NFR9: session failed, chạy lại từ checkpoint cuối |
| D-11 | Ghi đồng thời | App và CLI cùng chạy thì ai ghi SQLite, khoá ra sao | WAL, `timeout=5`; 1 nơi ghi |

> Hệ 1 người dùng, chạy local: không NFR nào đòi microservice. Bản Microservice nên nói thẳng cái giá phải trả (D-2, D-3, D-8) thay vì coi đó là lợi ích.

---

## 5. Tổng

Đếm bằng script trên các bảng ở mục 2 (81 task; phụ thuộc không có vòng, không task nào phụ thuộc pha sau, mọi ID phụ thuộc đều có thật).

| Pha | Số task | Ngày công |
|---|---|---|
| P0 Khởi tạo | 9 | 7.0 |
| P1 Ingest | 11 | 19.5 |
| P2 Chấm + chẩn đoán | 11 | 19.5 |
| P3 Duyệt + commit | 10 | 16.0 |
| P4 Profiler | 11 | 16.5 |
| **MVP (P0–P4)** | **52** | **78.5** |
| P5 Ngân hàng | 10 | 19.5 |
| P6 Gợi ý | 5 | 9.0 |
| P7 Report | 8 | 12.0 |
| P8 Đóng gói + đánh giá thật | 6 | 7.0 |
| **Tổng** | **81** | **126.0** |

- Chưa gồm task hạ tầng `MONO-*` / `MS-*` của từng bản.
- Chưa gồm thời gian chờ ngoài: §11.1 (nhất là câu 2, 4, 7), 1 tháng dữ liệu thật cho P7-T07 / P8-T06.
- Đề xuất cộng dự phòng 20 % khi lập lịch (*chưa đo*, chưa có số liệu năng suất thật).

---

## 6. Mâu thuẫn và khoảng trống trong nguồn

| # | Chỗ | Mâu thuẫn / khoảng trống | Backbone xử lý |
|---|---|---|---|
| 1 | §9.5 P2 "Xong khi" | Cần bộ đánh giá, nhưng §1.5 / §9.6: chưa có bài HS nào; nhãn = quyết định GV khi duyệt, mà màn hình duyệt ở P3 | P2 đo trên bộ gài lỗi (P2-T10); bộ thật đo ở P8-T04 |
| 2 | NFR8 | Mỗi lần đổi prompt phải chạy 3 lần trên bộ đánh giá trước khi dùng, nhưng bộ đánh giá chưa có | Tạm dùng fixture; đủ NFR8 ở P8-T05 |
| 3 | MVP vs P5 | Bản đầu dùng thật cần rubric, problem_kc, δ (`attempt.rubric_id NOT NULL`) mà chỉ P5 sinh; nhãn dummy "chỉ để test" | C-32: chỉ dùng nhãn khi chính GV viết; cần chủ dự án đồng ý |
| 4 | §9.5 P0 | "chặn đúng 7 kiểu dữ liệu sai" nhưng không liệt kê 7 kiểu | C-17 |
| 5 | §9.5 P1 | "10 file mẫu" không rõ là 10 file ngân hàng dummy hay bài HS (chưa có bài HS) | Kiểm cả hai: P1-T02 + P1-T07 / P1-T08 |
| 6 | §9.5 | `llm.py` không thuộc pha nào, dù 01 (P1) đã gọi LLM | P1-T01 |
| 7 | §9.5 vs §3.5 | Học sinh xếp ở P4, nhưng §3.5 bước 2 cần HS có sẵn trước khi nộp bài (P1) | P1-T06 làm phần tối thiểu |
| 8 | §9.2 | Không có module cho misconception / replay / danh sách thread / cấu hình | C-20; `graphs/threads.py`, `tutor/config.py` (đề xuất) |
| 9 | NFR7 vs schema | Chỉ gửi "mã HS", nhưng bảng `student` không có cột mã; bản nháp suy `HS-` + id (contract †) | C-11 |
| 10 | §11.1 câu 8 vs §1.3 / §4.1 | §1.3 / §4.1 ghi CLI giữ làm lệnh tương đương (chốt 21/10), §11.1 câu 8 vẫn hỏi có giữ CLI không | Coi là chốt (C-02); xin chủ dự án xoá câu 8 |
| 11 | Spec §5 vs v0.2 FR3 + schema | Verifier: spec ghi `agree` / `disagree`; v0.2 và schema có thêm `wrong_code` | Theo v0.2 + schema |
| 12 | Spec §5 vs §3.4 / §6.4 vs bản nháp | 07 ghép cặp "cùng chủ đề" (spec) / "cùng KC" (v0.2) / "cả chủ đề" (bản nháp, §11.4) | C-22 |
| 13 | Spec §11 vs §9.1 | Embedding "qua API hoặc MiniLM" vs MiniLM local | Theo §9.1 (C-33) |
| 14 | Spec §1 vs FR1 | Spec: đầu vào là PDF từ LaTeX; v0.2: .tex ưu tiên (spec §10 còn ghi CLI, §1.5 đã ghi nhận) | Theo v0.2 |
| 15 | §9.3 vs bản nháp | `tutor bank difficulty` không có tham số phạm vi, nhưng G3 chạy theo lô (chủ đề / nhóm KC) | Writer ghi lệnh kèm phạm vi, ví dụ `tutor bank difficulty [<chủ đề>]` (đề xuất) |
| 16 | §8.7 | `tutor-<ngày>.db`: nhiều commit G1 trong cùng ngày ghi đè bản sao | C-29 |
| 17 | §9.2 | Ghi `docs/PROJECT_III-tai-lieu-thiet-ke.docx`; thực tế v0.2 là `docs/update.docx` | Writer dùng đúng tên file |
| 18 | Đã có trong §11.2, chưa chốt | `rubric_id NOT NULL` vs commit ② (#15); `skill_event` UNIQUE vs chỉ thêm (#13); UNIQUE sha256 vs huỷ rồi nộp lại (#12) | C-16, C-18, C-15 |
