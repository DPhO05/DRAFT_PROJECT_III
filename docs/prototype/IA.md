# IA — PROJECT_III tutor app, HTML draft (clickable prototype, mock data)

Build spec for the tab builders. Data shapes, shell API and DOM rules live in `contract.md` (same folder): read it first.
UI language: Vietnamese with full diacritics. Labels in this file are exact; keep them.
Today in the mock = **2026-10-21** (`MOCK.meta.today`). Mock months: 2026-09, 2026-10.

Sources: spec `docs/superpowers/specs/2026-10-20-multi-agent-tutor-design.md`, `docs/architecture/schema.sql`,
gen_docx.py §2 (FR1–FR9, NFR1–NFR10, workflow), §3.4–3.6, §5, §7.7, §8.3, §10; diagrams 00–11; `data/dummy/bank/*` (refs 001–031).

---

## 0. Skeleton decision

| from | kept |
|---|---|
| Workflow-first (P1) | skeleton: sidebar grouped by the teacher's routine; G1 loop on ONE stepper screen (`session`); review screens live in the domain tab, the queue routes to them; CLI line under main buttons; data-state colours; "Con số này từ đâu?"; commit receipt toast; privacy + cost chips; A/E/R/N/J/K keys |
| Entity-first (P2) | "Chú thích hệ thống" toggle; two-store gauge (checkpoints.db vs tutor.db); "Sửa lỗi đã lưu" (supersedes + replay); Elo calculator; "Dựng lại trạng thái từ lịch sử"; class heatmap HS × KC; "Không làm (cố ý)"; phase chips P0–P4 / P5–P7; "Đặt lại dữ liệu mẫu" |
| Transparency-first (P3) | separate `logs` tab (llm.jsonl, cost, agent quality, pass^3 check, prompt versions); provenance marks LLM / code / GV (Excalidraw legend); live graph strip; Profiler preview + "rows to write" list before commit; backup-before-commit toast; thread state viewer + "Huỷ thread"; disabled buttons always say why; "Giả lập lỗi giữa chừng" |

Dropped on purpose (one line each, shown in `map` › Không làm): bulk "duyệt tất cả" (NFR4; diagram 04 "Verifier đồng ý không có nghĩa lỗi đúng"), batch "tạo cho cả lớp" buttons (CLI is per student), global search, calendar/timetable (schema has only `session.held_on`, `recommendation.for_date`), login/roles, student chatbot, LMS, handwriting OCR.
Students: **6** (HS-01…HS-06; HS-01–03 lớp 9, HS-04–06 lớp 8), per the contract.

## 1. Tabs (11)

| # | id | title_vi | sidebar group | phase chip | one line |
|---|---|---|---|---|---|
| 1 | `today` | Hôm nay | Mỗi ngày | — | what to do now, warnings, routine cards |
| 2 | `review` | Hộp duyệt | Mỗi ngày | — | single queue of all paused graphs (= `tutor review`), routes to review screens |
| 3 | `session` | Buổi học | Sau buổi học | — | G1 stepper: nộp bài → chạy → xác nhận → duyệt lỗi → ghi DB; session list + detail |
| 4 | `recommend` | Gợi ý bài | Trước buổi sau | P6 | G4: code picks, 08 writes reason, teacher approves |
| 5 | `report` | Báo cáo tháng | Cuối tháng | P7 | G5: facts → 3 insights → 09 → audit → teacher edits/approves |
| 6 | `students` | Học sinh | Theo dõi | — | profiles, Elo per KC, misconceptions, history (read view of tutor.db) |
| 7 | `bank` | Ngân hàng bài | Chuẩn bị | P5 | problem bank, G2 tag + rubric review, G3 difficulty review |
| 8 | `catalog` | Danh mục | Chuẩn bị | — | KC list, prerequisites, 18 error codes + examples (FR9) |
| 9 | `ops` | Vận hành | Hệ thống | — | threads/checkpoints, resume, backup, storage, settings, privacy |
| 10 | `logs` | Nhật ký & chi phí | Hệ thống | — | LLM call log, cost per agent/session/month, agent quality, prompt stability |
| 11 | `map` | Bản đồ hệ thống | Hệ thống | — | layers, 9 agents, 5 graphs, 16 tables, CLI ↔ app, glossary, open decisions, tour |

Phase chip text: P5–P7 tabs show a small chip "làm sau bản đầu (P5–P7)" next to the nav label (gen_docx §8.5: MVP = P0–P4).

## 2. Global shell (built once, see contract §10–§12)

- **Sidebar** (left; collapses to a "Menu" button under 720 px): groups in the order of §1; nav links `[data-tab-link]`. Badges: `review` = number of awaiting threads; `ops` = number of failed threads (red).
- **Top bar**: app name "Trợ lý gia sư Toán"; date "21/10/2026"; button **"Nộp bài"** (→ `session`, step 1) with CLI hint; **"Chờ duyệt (n)"** (→ `review`); **two-store gauge**: amber dashed pill "Đề xuất chờ duyệt: N · checkpoints.db" and green solid pill "Đã duyệt: M dòng · tutor.db" (M = sum of `MOCK.db` row counts; changes on every commit); cost meter "Tháng 10: $x / $budget" (→ `logs`); privacy chip "API chỉ nhận mã HS" (→ `ops` › Riêng tư); toggle **"Chú thích hệ thống"**.
- **Chú thích hệ thống** (explain mode): when on, `body.explain` shows every `ui.annot()` chip: `[G1]` `[03 Diagnoser]` `[bảng mistake]` `[>_ tutor review]`; hover = 1-line meaning (from `MOCK.meta.glossary`). Off by default; state kept in `localStorage` (try/catch).
- **Data-state language** (same everywhere, legend in footer): amber dashed border = proposal in `checkpoints.db` (not written); green solid = row in `tutor.db`; grey + strike-through = rejected (still stored for accuracy stats); grey square = file in `data/`.
- **Provenance marks** on values and text: rounded "LLM", square "code", dashed "GV" (Excalidraw legend of diagrams 00–11).
- **CLI hint**: monospace line `>_ tutor …` under every button that starts a graph or reviews one.
- **Receipt toast** after every commit: "1 transaction · +4 attempt · +6 mistake · +9 skill_event · skill_state · misconception_log · session → committed". Preceded (G1 only) by "Đã sao lưu data/backup/tutor-2026-10-21.db".
- **Cost chip** after every simulated run: "≈ 41 200 token · $0.62 (giả định)" from the run's mock calls.
- **Privacy chip** on every button that calls the LLM: "gửi API dưới mã HS-03".
- **Graph strip** (`ui.graphStrip`): mini G1–G5 chain from `MOCK.meta.graphs`; current node pulses; stop nodes show a hand icon + "đang chờ thầy/cô"; commit nodes green; failed node red. Used in session, review, recommend, report, bank, ops, map.
- **"Con số này từ đâu?"** (`ui.why`): small "?" button next to computed numbers → popover with formula + real inputs.
- **Disabled buttons** always render their reason as visible small text (never a silent grey).
- **Footer**: legend (colours + shapes) · "Chạy local · 1 người dùng · không đăng nhập · dữ liệu giả" · button "Đặt lại dữ liệu mẫu" (`data-no-autoclick`; reloads page).
- **Theme**: light + dark via tokens; phone width works with 16 px gutters, no horizontal page scroll (wide tables scroll inside their own box).

---

## 3. Tab specs

Action table columns: label (exact VI) → simulated effect → backing mechanism (spec / schema / CLI). `[NA]` = carries `data-no-autoclick`.

### 3.1 `today` — Hôm nay

Purpose: one look = what needs the teacher now, plus the 4-moment routine (gen_docx §2.1).

Sections (in order):
1. **Việc cần làm** — counts per graph from `ctx.queue.list()` as chips (G1 Lỗi buổi học · G2 Tag KC + rubric · G3 Độ khó · G4 Gợi ý · G5 Báo cáo), then the 5 oldest unlocked items: graph pill, subject (student code + name / bank file / KC group), stop reason (`stageLabel`), "chờ từ" (relative to today). Label under heading: "nằm trong checkpoints.db, chưa vào tutor.db".
2. **Cảnh báo** — failed threads (`status='failed'`: HS-06 19/10 dừng ở 03 Diagnoser, `error`), locked G1 threads (HS-05 20/10 "chờ buổi 17/10"), running threads (HS-01 21/10 tại 02 Grader).
3. **Nhịp dùng** — 4 cards, each: heading, one-line what, numbers, 1 primary button, CLI hint:
   - "Lần đầu / khi thêm bài": bank readiness `ready/total` (245/310), pending G2/G3 counts → "Mở Ngân hàng bài". CLI `tutor bank tag <bank.tex>`, `tutor bank difficulty`.
   - "Sau mỗi buổi học": awaiting G1 count → "Nộp bài vừa học", "Duyệt tiếp". CLI `tutor ingest <hs> <file>`, `tutor review`.
   - "Trước buổi sau": students needing a list = no approved `recommendation` with `for_date` > their last committed `held_on` → "Gợi ý bài". CLI `tutor recommend <hs>`.
   - "Cuối tháng": 2026-09 approved reports `x/6`, 2026-10 "còn 10 ngày" → "Mở Báo cáo tháng". CLI `tutor report <hs> <tháng>`.
4. **Học sinh cần chú ý** — rows: Δθ (mean over KCs) < 0 at last committed session; lỗi lặp = misconception with `count ≥ 2` and `resolved_at = null`; failed session. Click → `students?student=`.
5. **Hệ thống** — last commit time, last backup (`MOCK.files.backups[0]`), month cost vs budget (from `MOCK.files.llm_log`). Links to `ops`, `logs`.
6. **Hoạt động gần đây** — `MOCK.ui.activity` newest 8, each with annot chips (graph, agent, table).

Actions:
| label | effect | backing |
|---|---|---|
| Nộp bài vừa học | `ctx.nav('session', {step:1})` | G1; `tutor ingest <hs> <file>` |
| Duyệt tiếp | open oldest unlocked awaiting thread via `ctx.queue.open(thread_id)` | `tutor review` (no id = first waiting) |
| Mở (per row) | `ctx.queue.open(thread_id)` | `tutor review <id>`; LangGraph interrupt |
| Chạy lại từ checkpoint | `ctx.threads.resume('g1-hs06-20261019')`: failed → running → (1.2 s) awaiting_review, toast "Chạy tiếp HS-06 từ node 03 Diagnoser — các bài đã xong không chạy lại"; new G1 item appears | NFR9; SqliteSaver; `session.status` failed → awaiting_review |
| Mở buổi 17/10 | `ctx.queue.open('g1-hs05-20261017')` | rule: one student's sessions reviewed in date order (gen_docx §3.4) |
| Mở Ngân hàng bài / Gợi ý bài / Mở Báo cáo tháng | nav to `bank` / `recommend` / `report?month=2026-09` | navigation |
| Xem hành trình một bài làm [NA] | starts the tour of `map` (contract `App.tour`) | replays G1 → G4 → G5 on mock |

Empty: queue empty → "Không có gì chờ duyệt. Mọi đề xuất đã vào tutor.db." No warnings → "Không có thread lỗi."
Links to: session, review, recommend, report, bank, students, ops, logs, map.

### 3.2 `review` — Hộp duyệt

Purpose: the ONE queue for every graph paused at DỪNG (spec §10, gen_docx 10.3 #9). Proves nothing enters tutor.db before review. G1 mistake review itself happens in `session`; this tab lists and routes.

Sections:
1. **Banner (fixed)**: "Các mục dưới đây đang nằm trong checkpoints.db, CHƯA vào tutor.db. Chỉ khi thầy/cô duyệt, commit node mới ghi — mỗi lần duyệt là 1 transaction." + explainer box: "DỪNG = graph lưu state vào checkpoints.db rồi chờ bạn · Duyệt = cho graph chạy tiếp tới node commit".
2. **Bộ lọc**: graph chips with counts (G1…G5), student select ("Tất cả HS" + 6).
3. **Danh sách chờ** (table): thread_id (mono) · graph pill · subject · lý do dừng (`stageLabel`: "chờ xác nhận khớp bài" / "chờ duyệt lỗi" / "chờ chọn KC + duyệt rubric" / "chờ duyệt xếp hạng độ khó" / "chờ duyệt danh sách bài" / "chờ duyệt report") · số mục (proposals) · bất đồng 04 (G1: count of verdict ≠ agree) · chờ từ · status (`waiting` | `locked`) · action "Mở". Sort: G1 grouped by student, `held_on` ascending; then others by `interrupted_at`.
   - Locked rows: greyed, lock icon, reason "Elo cập nhật tuần tự: duyệt buổi 17/10 của HS-05 trước"; "Mở" disabled with that reason visible.
4. **Thread lỗi / đang chạy** (not reviewable): HS-06 19/10 failed at 03 Diagnoser (error text), HS-01 21/10 running at 02 Grader.
5. Note line: "Không có nút 'Duyệt tất cả' — cố ý: giáo viên quyết từng đề xuất (NFR4)."

Actions:
| label | effect | backing |
|---|---|---|
| Mở | `ctx.queue.open(id)` routes by graph/stage: G1 → `session?thread=` (step 3 if stage `g1.confirm_match`, else step 4); G2 → `bank?review=<id>`; G3 → `bank?difficulty=<id>`; G4 → `recommend?thread=`; G5 → `report?thread=` | `tutor review <id>`; graph resumes from its interrupt |
| Duyệt tiếp mục ưu tiên | opens the first unlocked row of the sorted table | `tutor review` |
| Lọc (chips/select) | filters table in place | thread metadata in checkpoints.db |
| Chạy lại từ checkpoint | `ctx.threads.resume(id)` (same as today) | NFR9 |
| Mở buổi chặn | on locked row: opens the blocking thread | date-order rule |

Empty: "Hộp duyệt trống — không graph nào đang dừng." Filter empty: "Không có mục nào cho bộ lọc này."
Annot: `[tutor review]` `[checkpoints.db]` `[interrupt()]`. Links: session, bank, recommend, report, ops.

### 3.3 `session` — Buổi học (heaviest; G1, FR1–FR5, agents 01–05)

Purpose: the after-class loop on one screen. Stepper: **1 Nộp bài → 2 Chạy G1 → 3 Xác nhận (chỉ khi có cờ) → 4 Duyệt lỗi → 5 Ghi DB & tiến bộ**. Also the session list and read-only detail of committed sessions.

Routing (params): none → list view; `step=1` (+ optional `student`) → submit form; `thread=<id>` → stepper for that G1 thread at its stage; `session=<id>` → read-only detail (committed) or redirect to its thread when not committed.

Sections:
1. **Danh sách buổi** (list view): table of `db.session`: held_on · HS (code + name) · nguồn (tex/pdf chip + `source_path`) · số bài · điểm (sum score / sum max) · lỗi đã duyệt (mistake_current count) · status pill · thread_id. Filters: HS, tháng, status. Row "Mở". Primary button "Nộp bài mới".
2. **Step 1 — Nộp bài**: select HS (shows "API nhận: HS-03"), ngày học (default today), file picker = buttons for `MOCK.files.inbox` (name, kind, short sha256). After pick: file chip (name, tex/pdf, sha256 8 chars); PDF note "01 sẽ chép LaTeX từ PDF + kiểm tra với text layer". Annot `[01 Ingest]` `[bảng session]`.
3. **Step 2 — Chạy G1**: graph strip G1 with one lane per problem (`02 · 03 · 04`), each node shows ms + tokens from the run; "① ghi session" note: "dòng session được ghi ngay (status running) — phần còn lại chỉ ghi ở ②". Button "Xem bản chép LaTeX" (transcript modal). Ends at DỪNG with toast.
4. **Step 3 — Xác nhận** (only when the thread stage is `g1.confirm_match`; mock thread HS-04 20/10 PDF): per flagged attempt:
   - `low_match` (no id; LLM compared statements): candidate list with score (8DS-PS-005 0.71 · 8DS-PS-003 0.64 · 8DS-PS-014 0.41), statement preview rendered.
   - `mismatch` (PDF): side-by-side "bản chép" vs "text layer" with the differing token highlighted ("−1" vs "+1"), note "model hay tự sửa lỗi HS khi chép (Seong 2026)".
   - `no_rubric` (8DS-PT1-017: KC tag approved, rubric left undecided in its G2 batch): inline `ui.rubricEditor` with the rubric 02 just generated. Note under it: "rubric duyệt ở đây được ghi cùng commit ② (attempt.rubric_id NOT NULL) — sơ đồ 11 chưa liệt kê rubric trong commit ②: điểm cần chốt".
   Continue button enabled only when every flag is resolved.
5. **Step 4 — Duyệt lỗi** (3 columns; on phone they stack): attempt tabs (seq 1..n, ref, score, count of proposals) above.
   - Left "Bài làm HS": frame titled "UNTRUSTED INPUT · HS-03" with numbered steps (`steps_json`), steps with a proposal tinted; toggle "Lời giải mẫu".
   - Middle "02 Grader": rubric items (passed ✓/✗ + evidence LaTeX), score `x/max`, code check chip "tổng = tổng các mục ✓ · mục đạt có bằng chứng ✓", flag `alt_method` with button.
   - Right "Đề xuất lỗi": cards ordered **04 phản đối/sai mã → confidence < 0.6 → còn lại** (heading per group). Card: bước, mã lỗi chip, KC chip (or "không gắn KC — không ảnh hưởng Elo"), mô tả, evidence (LaTeX), confidence bar, two boxes "Diagnoser (03) nói" | "Verifier (04) nói" (+ reason, suggested code) separated by a dashed rule "không chung context", footer "Hệ thống không tự quyết — thầy/cô quyết". Buttons A/E/R. Decided cards switch style (green "confirmed"/"edited" pending-commit, grey strike "rejected").
   - Under the columns: progress "Đã quyết 3/6", review timer (mm:ss since open), box "Ngữ cảnh 03 đã dùng: 5 lỗi đã duyệt gần nhất của HS-03" (from db, rendered as chips).
6. **Profiler preview** (appears after "Chạy Profiler"): table per (attempt, KC): X, P, θ trước → θ sau, δ (each with `ui.why`); misconception changes (mới / lặp lại / đã hết / resolved); Δθ vs previous committed session; `knowledge_state` text (≤150 từ, LLM mark, "viết từ số liệu, không tự chấm"); list "Sẽ ghi vào tutor.db (1 transaction)": attempt ×n, mistake ×n, skill_event ×n, skill_state, misconception_log, session → committed.
7. **Step 5 — Kết quả**: receipt, Δθ bars per KC (signed), error-code chips lặp lại / mới / đã hết, resolved misconceptions, knowledge_state, next-step buttons.
8. **Read-only detail** (`session=<committed id>`): header (held_on, source_path, kind, sha256, thread_id, review time, session cost from llm_log); attempts with grade + mistakes (status badges confirmed/edited/rejected/added; "đề xuất gốc LLM" vs final diff from `llm_json`; supersedes chain "thay bằng #id").
9. **Failed/locked/running thread view**: failed → strip with red node + error + resume button; locked → banner + button to blocking thread; running → plays remaining nodes (~3 s, `MOCK.ui.demo_runs[thread.demo_run]`) then lands on step 4.

Actions:
| label | effect | backing |
|---|---|---|
| Nộp bài mới | `ctx.nav('session',{step:1})` | — |
| Chọn tệp (one per inbox file) | fills file chip | `session.source_path` (data/inbox/), `source_kind`, `source_sha256` |
| Bắt đầu xử lý | disabled until HS + file (reason shown). Duplicate (same student + sha256 as an existing session) → error toast "File này đã nộp cho HS-03 ngày 20/10 (trùng sha256)" and stop. Else: new `db.session` (running, new thread_id), new thread; animate strip; ends at DỪNG; thread → awaiting_review; toast "Sẵn sàng duyệt: 3 bài, 4 lỗi đề xuất"; badge +1; cost chip | `tutor ingest <hs> <file>`; G1 ①, 01 → Send per problem (02·03·04) → interrupt; `UNIQUE(student_id, source_sha256)` |
| Xem bản chép LaTeX | modal with `transcript_latex`; PDF mismatches highlighted | 01 step 1b/2; `session.transcript_latex` |
| Giả lập lỗi giữa chừng [NA] | during a run: lane 3 node 03 turns red, session/thread → failed, toast "Lỗi API ở 03 Diagnoser — xem Vận hành" | `session.status='failed'`, NFR9 |
| Chạy lại từ checkpoint | `ctx.threads.resume(id)`; only the failed node and later run | SqliteSaver checkpoint |
| Xác nhận bài khớp | picks a candidate; flag cleared; `attempt.problem_id` set | 01 step 4; G1 first stop |
| Chọn bài khác | modal: bank search (ref + statement) → choose | 01 step 3–4 |
| Dùng text layer (giữ lỗi HS) / Giữ bản chép | resolves `mismatch` flag | 01 step 2 (gen_docx 10.3 #1) |
| Duyệt rubric | rubric chip "rubric v1"; flag cleared | 02 steps 2–3; `rubric(version, approved_at)` |
| Chạy tiếp | animates lanes 02·03·04, stage → `g1.review`, step 4 | `tutor review <id>` resumes |
| Chấp nhận cách giải khác | `alt_method` flag turns green | 02 step 5; `attempt.flags_json` |
| Chấp nhận (A) | card → "confirmed (chờ ghi)" | `mistake.status='confirmed'` at commit ②; FR4 |
| Sửa (E) | modal: mã lỗi (only `active` codes, grouped by 5 categories), KC (only KCs of this problem from `problem_kc`, or "không gắn KC"), bước, mô tả, ghi chú → card "edited" + diff vs LLM | `status='edited'`; `llm_json` keeps original; `teacher_note` |
| Bỏ (R) | card grey strike "rejected"; note "vẫn lưu để đo độ chính xác" | `status='rejected'`; excluded by `mistake_current`; spec §12 |
| Thêm lỗi bị sót (N) | click a step in left column → modal (mã, KC, mô tả) → new card "added", no 03/04 boxes | `status='added'`, `llm_json NULL` (CHECK) |
| Xem bằng chứng | highlights + scrolls to the step in left column | `evidence_latex`, `steps_json.pos`; NFR3 |
| Xem đề xuất gốc | drawer with the 03 JSON | `mistake.llm_json` |
| Xem lời gọi LLM | `ctx.nav('logs',{thread})` | `data/logs/llm.jsonl` |
| Tạm dừng, duyệt sau | decisions kept in thread state; toast "Đã lưu, còn trong Hộp duyệt"; nav `today` | thread stays at interrupt |
| Chạy Profiler | enabled only when every card is decided (reason shown); shows Profiler preview | 05: code Elo/streak/misconception, LLM knowledge_state |
| Ghi vào tutor.db | toast backup, then receipt; appends attempt/mistake/skill_event rows, recomputes skill_state/misconception_log, session → committed, `ctx.queue.resolve`; unlocks the student's next session; step 5 | G1 commit ② (1 transaction, NFR5); `.backup` before commit (gen_docx §7.7) |
| Gợi ý bài buổi sau cho HS này | `ctx.nav('recommend',{student})` | G4 |
| Xem hồ sơ | `ctx.nav('students',{student})` | — |
| Sửa lỗi đã lưu (detail view) | modal → new mistake row with `supersedes_id`; old row struck "thay bằng #id"; toast "replay skill_state, misconception_log của HS-03" (recompute) | append-only + supersedes + replay (schema rule 3–4) |
| Mở buổi chặn (locked) | `ctx.queue.open(blocker)` | date-order rule |

Keyboard (step 4 only, ignored inside inputs): A accept · E edit · R reject · N add · J/K next/previous card.
Edge states: no thread/params → list; thread committed → redirect to detail; all attempts with 0 proposals → "02/03 không tìm thấy lỗi — vẫn cần thầy/cô xác nhận" and Profiler button enabled; empty inbox → "Không có file trong data/inbox".
Annot per area: `[01 Ingest]`, `[02 Grader]`, `[03 Diagnoser]`, `[04 Verifier]`, `[05 Profiler]`, `[G1]`, `[bảng attempt/mistake/skill_event]`, `[>_ tutor ingest]`, `[>_ tutor review <id>]`.
Links: review, recommend, students, bank, catalog, logs, ops.

### 3.4 `recommend` — Gợi ý bài (G4, FR7, agent 08)

Purpose: before the next class. Code picks KCs and problems by rule; 08 only checks fit + writes 1 line; teacher approves/replaces.

Params: `student`, `thread`. With `thread` → that G4 proposal (mock `g4-hs02-20261023`). With `student` only → that student's history + "Tạo gợi ý".

Sections:
1. **Chọn**: HS select, `for_date` (default = last committed held_on + 7 days; editable; label "ngày buổi sau do thầy/cô chọn"), button "Tạo gợi ý" + CLI `tutor recommend HS-02 --date 2026-10-23` + privacy chip.
2. **Luật (code · select.py)**: ratio sliders 40/50/10 (from `settings.reco`; local preview, "chỉ code, không gọi LLM"), derived split "6 bài = 2 ôn · 3 vừa sức · 1 thử thách" with `ui.why` (6×0.4=2.4→2, 6×0.5=3, 6×0.1=0.6→1; rounding rule: largest remainder, mock assumption), filters list (đúng KC · chưa làm trong 30 ngày · có rubric · có δ đã duyệt), zpd window [−0.5, 0.5], "≥3 KC" indicator.
3. **Bước 1 — Chọn KC (code)**: table KC · θ · bucket chip (ôn / vừa sức / thử thách) · lý do bằng số ("misconception notational.operator_swap chưa hết" / "θ−δ = −0.30 ∈ [−0.5, 0.5]" / "đủ KC tiên quyết").
4. **Bước 2 — Ứng viên đã lọc**: per KC, sorted by |θ−δ|; excluded rows faded with reason ("đã làm 2026-10-06 (< 30 ngày)", "chưa có rubric", "δ chưa duyệt").
5. **Bước 3 — Danh sách đề xuất** (amber, pending): 6 cards: ref, statement (typeset), KC, bucket chip, δ, θ−δ, lần làm gần nhất, rubric vN, reason (LLM mark "08") + "Vì sao bài này?". Footer: KC mix check "6 KC ✓ (≥3)".
6. **Lịch sử đã duyệt** (green): `db.recommendation` of the student grouped by `for_date`, status chips approved/rejected/added.
7. **File .md**: chip `data/out/recommend-HS-02-2026-10-23.md`.

Actions:
| label | effect | backing |
|---|---|---|
| Tạo gợi ý | animate G4 strip (đọc skill_state → select.py → 08 → DỪNG); code picks via `ctx.calc.selectRecommendations(db, settings, student, for_date)`, 08 reasons from `ui.demo_runs['g4-new'].reason_templates`; creates a G4 thread; cards appear; badge +1 | `tutor recommend <hs> [--date]`; G4 |
| Đổi tỉ lệ (sliders) | recomputes split + Bước 1 buckets live | `select.py` config (FR7 "tỉ lệ cấu hình được") |
| Vì sao bài này? | popover: bucket rule, θ, δ, |θ−δ|, unresolved misconception, last done, filters passed | skill_state, misconception_log, problem.delta, attempt history |
| Bỏ | card strike "rejected"; KC-mix recomputed; warn if < 3 KC | `recommendation.status='rejected'` |
| Thay bằng bài khác | modal limited to Bước 2 non-excluded candidates of the same KC → old card rejected, new card "approved", same bucket | status rows |
| Thêm bài tự chọn | bank search modal → card "added", bucket empty | `status='added'`, `bucket NULL` |
| Xem file .md | modal showing the .md text | `data/out/*.md` (CLI: GV sửa .md rồi `tutor review`) |
| Tải .md [NA] | `ui.download` | same |
| Duyệt danh sách | commits: rows approved (undecided cards = approved), rejected, added → `db.recommendation`; receipt "+7 recommendation (5 approved, 1 rejected, 1 added)"; `ctx.queue.resolve` | G4 commit; `UNIQUE(student_id, for_date, problem_id)` |

Edge: no student → "Chọn học sinh"; student with no committed session → "Chưa có buổi đã duyệt: θ = 0 mọi KC (NFR2) — luật vẫn chạy"; no candidates for a KC → "Thiếu bài sẵn sàng cho KC này — mở Ngân hàng bài" (link); thread already committed → read-only.
Links: students, bank, review, logs.

### 3.5 `report` — Báo cáo tháng (G5, FR8, agent 09)

Purpose: month end. SQL facts with `fact_id` → code picks 3 insights → 09 writes → code audits each sentence → teacher edits + approves. No over-praise when results are low.

Params: `thread`, `student`, `month`.

Sections:
1. **Bảng HS × tháng** (2026-09, 2026-10): cells "chưa tạo" / "chờ duyệt" (amber) / "đã duyệt" (green); click opens. 2026-10 header note "tháng chưa hết (còn 10 ngày)".
2. **G5 strip**: facts.py → chọn 3 insight → 09 Reporter → audit.py → DỪNG → commit.
3. **Facts (code · SQL)**: table fact_id · loại · nhãn · giá trị (e.g. F02 tỉ lệ đạt rubric = 68%). Insight facts tagged "xu hướng / điểm đổi / ngoại lệ / đa số".
4. **3 insight** (code mark): each names its type + fact ids.
5. **Bản nháp** (LLM mark): sentences with `[F02]` chips; badge per sentence: đạt (green) / đã viết lại 1 lần (amber, with first draft on hover) / bị bỏ (grey strike, in a collapsed "Câu bị bỏ (n)" list with reason). Tone banner when `tone.low_results`: "Kết quả thấp (tỉ lệ đạt 46% < 50%) → không khen quá tay"; sentences with `tone_flag` outlined.
6. **Đã duyệt**: approved reports render `text_md` with fact chips (read-only).

Actions:
| label | effect | backing |
|---|---|---|
| Tạo report | for a "chưa tạo" cell: animate strip; facts computed by code from `db` (same fact kinds as contract `Fact`), sentences from `ui.demo_runs['g5-new']` templates (1 rewritten, 1 dropped), audit by `ctx.calc.audit`; new G5 thread; badge +1 | `tutor report <hs> <tháng>`; facts.py, 09, audit.py |
| Chip fact `[Fxx]` | highlights fact row; popover value + SQL snippet + "Xem nguồn" | `report.facts_json`; NFR3 |
| Xem nguồn | `ctx.nav('students',{student, tab:'history'})` | trace back to sessions/mistakes |
| Sửa câu | inline edit; code re-audits that sentence (numbers vs cited facts): mismatch → red + "số 65% không khớp F02 = 68%" (warning only; label "re-audit bản GV sửa: đề xuất, spec chưa có") | audit.py |
| Chạy lại audit | recomputes all badges | audit.py |
| Xem câu bị bỏ | expands dropped list with reasons | `report.audit_json` |
| Xem file .md / Tải .md [NA] | modal / download | `data/out/` |
| Duyệt & ghi report | receipt "+1 report (HS-02 · 2026-09)"; cell → đã duyệt; `ctx.queue.resolve` | G5 commit → `report(facts_json, text_md, audit_json, approved_at)`; `UNIQUE(student_id, month)` |

Edge: student with 0 committed sessions in month → "Không đủ dữ liệu: 0 buổi đã duyệt trong tháng" (Tạo report disabled with reason); approved cell → read-only (no re-approve; UNIQUE).
Links: students, review, logs.

### 3.6 `students` — Học sinh (FR5, agent 05, NFR7)

Purpose: approved state per student (read view of tutor.db); every number computed by code; 05 only writes the summary.

Params: `student`, `tab` (`progress|skills|misconceptions|history|outputs`), `kc`.

Sections:
1. **Danh sách**: table code · tên (label "chỉ lưu trên máy") · lớp · buổi gần nhất · số buổi tháng 10 · θ TB + sparkline · lỗi lặp chưa hết · badge "có buổi chờ duyệt". Filters lớp 8/9, "Hiện HS đã lưu trữ".
2. **Bản đồ nhiệt cả lớp** (below list): rows HS, columns KC (grouped by KC group, only KCs with data), cell colour = θ (diverging, legend −1…+1), empty = chưa có dữ liệu. Click cell → profile `tab=skills&kc=`.
3. **Hồ sơ** header: tên, lớp, ghi chú, chip "Gửi API dưới mã HS-03", quick buttons.
4. Sub-tabs (`ui.segmented`):
   - **Tiến bộ**: KPIs (số buổi, tỉ lệ đạt rubric, Δθ TB vs buổi trước, misconception đã hết) each with `ui.why`; "So với buổi trước": signed Δθ bars per KC; code chips lặp lại / mới / đã hết; `knowledge_state` of last committed session (LLM mark "05 viết từ số liệu").
   - **Kỹ năng (Elo)**: table KC · θ · n_attempts · correct_streak · last_seen grouped by KC group; line chart θ over sessions for the selected KC (from `skill_event`); drawer listing events (attempt ref, X, P, θ trước → sau, δ).
   - **Lỗi lặp lại**: `misconception_log` table (mã, KC, first_seen, last_seen, count, tiến độ "đúng liên tiếp 1/2", resolved_at); bars: frequency by 5 categories, 2026-09 vs 2026-10.
   - **Lịch sử buổi**: timeline of sessions with status pill; "Xem buổi" per row.
   - **Gợi ý & báo cáo**: approved recommendations by for_date; reports by month.

Actions:
| label | effect | backing |
|---|---|---|
| Thêm học sinh | modal (tên, lớp, ghi chú) → new row HS-07; toast "Đã thêm · mã gửi API: HS-07" | `student` (teacher entry) |
| Sửa thông tin | inline edit name/grade/note | `student.name, grade, note` |
| Lưu trữ | confirm → `archived_at` set, row moves under filter | `student.archived_at` |
| Nộp bài cho HS này | `ctx.nav('session',{step:1, student})` | G1 |
| Gợi ý buổi sau | `ctx.nav('recommend',{student})` | G4 |
| Tạo report tháng | `ctx.nav('report',{student, month:'2026-10'})` | G5 |
| Xem cách tính θ (`?`) | popover/calculator with real event: θ=0.10, δ=0.35 → P=1/(1+e^−(θ−δ))=0.44; X=0 → θ=0.10+0.3·(0−0.44)=−0.03; inputs θ/δ/X editable to try | `skill_event`; elo.py (K=0.3); 05 steps 1–2 |
| Dựng lại trạng thái từ lịch sử | progress → recompute skill_state + misconception_log from events/mistakes, compare → toast "Dựng lại từ N skill_event — khớp 100%" (`ctx.calc.replay` vs stored rows) | schema rule 4; FR5 "dựng lại được từ lịch sử" |
| Xem buổi | `ctx.nav('session',{session})` | `attempt_current`, `mistake_current` |
| Xem dữ liệu gửi API | `ui.payloadModal('03', code)`: student only as HS-03, work inside UNTRUSTED INPUT | NFR6, NFR7; `tutor/llm.py` |

Edge: new student → "Chưa có buổi đã duyệt · θ = 0 cho mọi KC (không cần train — NFR2)"; archived → banner "Đã lưu trữ"; KC with < 2 events → chart replaced by text.
Links: session, recommend, report, catalog, logs.

### 3.7 `bank` — Ngân hàng bài (FR6, G2, G3, agents 06, 02 rubric, 07)

Purpose: first-time setup and adding problems. Load .tex, tag KCs (top-5, teacher picks), generate + approve rubric (G2), rank difficulty by pairs + Bradley-Terry (G3). Shows which problems are ready for grading and recommending.

Params: `problem` (ref) → detail drawer; `review=<g2 thread>` → tag + rubric review; `difficulty=<g3 thread>` → difficulty review; `kc` → list filter.

Sections:
1. **Stepper**: 1 Danh mục KC (link catalog) → 2 Nạp .tex → 3 Gắn KC + rubric (G2) → 4 Độ khó (G3) → Sẵn sàng. Each step shows counts.
2. **Tiến độ theo chủ đề**: 10 rows (bank files) × three bars: đã tag · có rubric · có δ (out of 31). Mock: 8 files tagged + δ (3 problems there lack a rubric: 8DS-PT1-017, 9DS-PT2-019, 9DS-CAN-019 → status `thieu_rubric`); `9-ham-so-y-ax2.tex` tagged + rubric, δ pending (G3); `8-ham-so-bac-nhat.tex` waiting in G2 — its 31 problems exist only in the checkpoint, so their rows render amber dashed with chip "chỉ trong checkpoints.db".
3. **Độ khớp nhãn người soạn** (small card): "% kc_du_kien nằm trong top-5 của 06: 92% · GV chọn trùng KC dự kiến đầu tiên: 41%" (from `MOCK.ui.agent_quality['06']`), note "tiêu chí P5".
4. **Danh sách bài**: filters chủ đề, lớp, KC, trạng thái (`ready` / `thieu_rubric` / `cho_do_kho` / `cho_duyet_tag`); columns ref · đề (1 line) · KC đã duyệt · nhãn trong file (`expected_kc`, `expected_difficulty` 1–5; label "nhãn người soạn, chưa phải tag đã duyệt") · rubric vN · δ (lock icon when approved) · số lượt HS làm · trạng thái. List = `db.problem` (279) ∪ problems in the G2 thread state (31, amber dashed).
5. **Chi tiết bài** (drawer): statement + solution steps typeset; per-step KC tags + evidence; rubric versions (items, max_score, approved_at); `problem_pair` rows of this problem; who did it (students, date, score).
6. **Duyệt tag + rubric (G2)**: left list of the batch's 31 problems with decided state; right: per solution step, 5 candidates (KC code + name, cosine, hạng LLM, evidence snippet, prereq warning chip) as checkboxes (≥1 required per problem; step_idx 0 = cả bài for problems without step-level candidates); "Thêm KC khác"; `ui.rubricEditor` with the 02 draft (items, points, accepted alternative methods, version). Progress "Đã duyệt 3/31".
7. **Duyệt độ khó (G3)**: KC selector (9DS-HSB2-01…04); pairs table (A, B, trả lời (A,B), trả lời (B,A), kết quả a/b/hoà — mismatched = hoà); ranking table per KC: hạng · ref · bt_score · δ · n_comparisons · ▲▼ buttons · "GV chỉnh" mark.

Actions:
| label | effect | backing |
|---|---|---|
| Nạp file .tex | modal choose one of `MOCK.files.bank`; mock parse result "31 bài (001–031) · 31 đã có (khớp ref) · 0 bài mới · 0 khối dở dang bị bỏ qua" | latex.py (pylatexenc) splits `\begin{problem}[ref]`; `problem.ref UNIQUE`; `tutor bank tag <bank.tex>` |
| Mở duyệt tag (on a G2-pending topic) | `ctx.queue.open('g2-8-ham-so-bac-nhat')` | `tutor review <id>` |
| Chọn KC (checkbox) | marks choice; others fade | 06 step 5; only chosen tags reach `problem_kc` |
| Thêm KC khác | modal: search 74 KCs; "Tạo KC mới" (code, tên, mô tả, nhóm) adds to `db.kc` and the list | 06 step 5; `kc` |
| Sửa rubric (editor) | edit/add/remove items; total updates | `rubric.items_json`, `max_score` |
| Duyệt bài này | problem marked decided (green within batch) | thread decisions |
| Ghi lô vào tutor.db | enabled when 31/31 decided (reason shown); receipt "+31 problem · +n problem_kc · +31 rubric v1 · kc.embedding"; topic → tagged; "Xếp độ khó" enabled for it; `ctx.queue.resolve` | G2 commit: problem, problem_kc, rubric, kc.embedding |
| Xếp độ khó | on a tagged topic without δ: animate G3 (ghép cặp ~10/bài → 07 hỏi 2 chiều → bt.py) → new G3 thread; on an untagged topic disabled "cần tag KC đã duyệt (G3 chạy sau G2)" | `tutor bank difficulty`; G3 |
| ▲ / ▼ (đổi chỗ) | moves problem in KC ranking; δ re-spaced; "GV chỉnh" | 07 step 4 |
| Duyệt độ khó | δ locked (`difficulty_approved_at`); receipt "+155 problem_pair · 31 δ"; `ctx.queue.resolve` | G3 commit: problem_pair, problem.bt_score/delta; δ fixed (spec §8) |
| Xem các cặp so sánh | modal of `problem_pair` rows for a problem | `problem_pair(harder_ab, harder_ba)` |
| Tính lại khi thêm bài | toast "Fit lại BT với 1240 cặp cũ + 0 cặp mới — δ đã duyệt không đổi" | FR6 keep pairs to refit |
| Sửa rubric (detail, ready problem) | editor → saves `rubric` v(n+1) with `approved_at` (teacher-authored); old version kept | `UNIQUE(problem_id, version)` |
| Xem đề + lời giải | drawer, typeset | `statement_latex`, `solution_latex` |

Edge: no KC catalog → step 1 warning "Chưa có danh mục KC — mở Danh mục"; filter empty; G3 for a KC with < 2 problems → "không đủ bài để so cặp".
Annot: `[G2]` `[06 Tagger]` `[02 Grader · sinh rubric]` `[G3]` `[07 Difficulty]` `[bt.py]` `[bảng problem_kc/rubric/problem_pair]`.
Links: catalog, review, recommend, session.

### 3.8 `catalog` — Danh mục (FR9)

Purpose: catalogs the teacher maintains and which agent reads them. Label: "Cách nhập chưa chốt — đề xuất CSV/YAML + lệnh import (gen_docx §10.4)".

Sub-tabs (`ui.segmented`): **Kỹ năng (KC)** · **Tiên quyết** · **Mã lỗi**.
1. **Kỹ năng**: tree 10 groups → 64 KCs (from kc.csv), filter lớp 8/9, text filter. Detail panel: code, tên, mô tả (label "dùng để embedding cho 06"), nhóm, lớp, embedding status (`embed_model` or "cũ — cần chạy lại 06"), số bài gắn KC (→ bank), θ của từng HS trên KC này (mini bars → students).
2. **Tiên quyết**: for the selected KC: three columns "KC tiên quyết" → KC → "KC phụ thuộc"; full edge table (74 rows); DAG status "Không có vòng ✓".
3. **Mã lỗi**: 5 category blocks (computational 4, conceptual 5, notational 3, presentation 5, other 1): code · mô tả · ví dụ (LaTeX, label "đưa vào prompt 03") · bật/tắt · dùng (2026-09 / 2026-10 counts) · % bị GV bỏ. Warning "5/18 mã chưa có ví dụ (FERMAT: có ví dụ thì chính xác hơn ~0.03)". `other.unclear` lock icon "bắt buộc giữ". Box "Xem trước prompt 03: taxonomy + ví dụ (prompt_version 03-v4)".

Actions:
| label | effect | backing |
|---|---|---|
| Nhập từ CSV | modal: kc.csv + kc_prereq.csv (UTF-8 BOM) → preview from `MOCK.ui.catalog_import_preview` ("0 KC mới · 1 mô tả đổi · 0 quan hệ mới") → "Áp dụng" → toast; changed KC embedding → stale | `kc`, `kc_prereq`; FR9 |
| Xuất CSV [NA] | download kc.csv / kc_prereq.csv / error_code.csv | read tables |
| Thêm KC | modal (code, tên, mô tả, nhóm, lớp) → node in tree | `kc` |
| Sửa KC | inline; changing mô tả → embedding "cũ" + hint "chạy lại 06 (G2) để cập nhật embedding" | `kc.description`, `kc.embedding` |
| Thêm tiên quyết | select KC → edge; self → blocked "CHECK kc_id <> prereq_id"; cycle → error toast "Tạo vòng: 9DS-PT2-03 → 9DS-PT2-02 → 9DS-PT2-03" | `kc_prereq`; DAG check (06 step 4) |
| Xoá tiên quyết | edge removed | `kc_prereq` |
| Thêm ví dụ / Sửa ví dụ | inline LaTeX; save → banner "Prompt 03 đổi: 03-v4 → 03-v5 · chạy kiểm tra ổn định 3 lần trước khi dùng" + link `logs` | `error_code.example`; NFR8 |
| Sửa mô tả mã | inline, same banner | `error_code.description` |
| Thêm mã lỗi | modal: category (5) + sub → code `<category>.<sub>` | `error_code` CHECK category |
| Tắt / Bật | toggles `active`; disabled codes vanish from the Sửa (E) dropdown; `other.unclear` disabled with reason; no delete button (note: lỗi cũ còn tham chiếu) | `error_code.active` |
| Xem lỗi mang mã này | modal list from `mistake_current` (HS, buổi, bài) → session detail | view `mistake_current` |

Edge: KC search empty; KC without problems → "Chưa có bài gắn KC này".
Links: bank, session, students, logs.

### 3.9 `ops` — Vận hành (NFR1, NFR5, NFR7, NFR9)

Purpose: the running machine: every thread of G1–G5, where it stopped, checkpoints, resume, storage, backup, settings, privacy.

Sections:
1. **5 làn graph**: `ui.graphStrip` for G1–G5 with dots = threads at their `current_node` / `interrupted_at` (click dot → thread detail).
2. **Thread** table: thread_id · graph · subject · bắt đầu · node hiện tại · status (running / awaiting_review / committed / failed) · số checkpoint. Filters graph, status.
3. **Chi tiết thread** (drawer): checkpoint timeline (node, at); state snapshot JSON (`state` keys: attempts, flags, grades, mistakes, verdicts, decisions, profile — SessionState per gen_docx §3.4); error when failed.
4. **Quy tắc vận hành**: date-order review per student; duplicate-file block; G3 after G2; only commit nodes write tutor.db.
5. **Lưu trữ**: `data/tutor.db` (16 bảng + 2 view, row count per table from `MOCK.db`), `data/checkpoints.db` (n threads), `data/inbox/`, `data/out/`, `data/logs/llm.jsonl`, `data/backup/`; label "1 máy · 1 người dùng · không đăng nhập".
6. **Sao lưu**: `MOCK.files.backups` list.
7. **Cài đặt**: reco ratios 40/50/10, số bài/buổi 6, không lặp 30 ngày, trộn ≥3 KC, vùng vừa sức [−0.5, 0.5]; K = 0.3 and ngưỡng resolved = 2 read-only ("cố định theo spec §8"); ngưỡng confidence thấp 0.6 (mock assumption); model per agent 01–09 (select, default `claude-opus-5-5`); ngân sách tháng (label "chưa chốt"); live preview "6 bài = 2 ôn / 3 vừa sức / 1 thử thách".
8. **Riêng tư & an toàn**: table tên ↔ mã HS ("chỉ trên máy này"); toggle "Chỉ gửi mã HS lên API" (NFR7, label "đề xuất, chờ chốt"); sample UNTRUSTED INPUT frame.

Actions:
| label | effect | backing |
|---|---|---|
| Xem state | thread drawer | checkpoints.db |
| Chạy lại từ checkpoint cuối | `ctx.threads.resume(id)` | NFR9 |
| Huỷ thread [NA] | confirm → thread removed, queue updated, toast "tutor.db không đổi vì chưa commit" (G1: session row → failed, note) | proposals live only in checkpoints |
| Dọn thread đã commit | removes `committed` threads from table; toast count | gen_docx §7.7 "xoá thread cũ sau khi commit" |
| Mở trong Hộp duyệt | `ctx.queue.open(id)` | `tutor review <id>` |
| Sao lưu ngay | prepend `data/backup/tutor-2026-10-21.db` (size from mock); toast | NFR9; `sqlite3 .backup` |
| Lưu cài đặt | writes `MOCK.settings`; toast; recommend + top-bar budget read new values | select.py, llm.py config |
| Xem nội dung gửi API | `ui.payloadModal(agent, code)` | NFR6, NFR7 |

Edge: no failed thread → "Không có thread lỗi"; no backups → "Chưa sao lưu lần nào".
Links: review, session, logs, map.

### 3.10 `logs` — Nhật ký & chi phí (NFR3, NFR8, NFR10, spec §12)

Purpose: traceability and cost of every LLM call; agent quality measured from the teacher's review decisions.

Params: `thread`, `agent`, `student`.

Sections:
1. **KPI**: chi phí tháng 10 vs ngân sách (from settings), tháng 9, TB mỗi buổi G1; label "đơn giá giả định — bản nháp".
2. **Chi phí theo agent** (bars 01–09), **theo buổi** (table: session, HS, số lời gọi, token, chi phí), tháng 9 vs 10.
3. **Nhật ký lời gọi LLM** (`MOCK.files.llm_log`): giờ · agent · graph · thread · HS (mã) · prompt_version · model · token vào/ra/cache · ms · chi phí · kết quả (ok / retry / schema_error → flag chip). Filters agent/graph/HS/thread; prefilled from params.
4. **Chi tiết lời gọi** (drawer): prompt structure — cached fixed part (taxonomy + ví dụ / rubric / lời giải mẫu) · `<UNTRUSTED INPUT student="HS-03">` block · output JSON; note "tên HS không bao giờ có trong prompt".
5. **Chất lượng agent** (computed from `db.mistake` etc. + `MOCK.ui.agent_quality`): 03 % bị bỏ / sửa / GV thêm; 04 % đồng ý với GV; kappa mã lỗi GV–LLM; 06 top-5 hit; 09 % câu trượt audit; thời gian duyệt TB / buổi. Each with `ui.why`.
6. **Prompt & độ ổn định**: `MOCK.ui.prompt_versions`: agent · version · đổi lúc · trạng thái kiểm tra 3 lần (pass^3, % tiêu chí đổi điểm).
7. **Nhật ký quyết định GV**: from committed mistakes/recommendations/reports: mục · quyết định · lúc · trước/sau.

Actions:
| label | effect | backing |
|---|---|---|
| Lọc theo agent / graph / HS / thread | filters log + charts | `data/logs/llm.jsonl` |
| Xem prompt & output | call drawer | `tutor/llm.py` gateway; NFR6/7 |
| Chạy kiểm tra ổn định (3 lần) | progress 3 runs (≈2 s) → updates that prompt version: "pass^3 ✓ · 6% tiêu chí đổi điểm" | NFR8; spec §12 (Tonmoy 2026) |
| Xuất CSV chi phí [NA] | download | llm.jsonl |
| Đổi ngân sách | `ctx.nav('ops',{section:'settings'})` | single place for settings |

Edge: filter empty → "Không có lời gọi nào khớp bộ lọc".
Links: ops, session, catalog, map.

### 3.11 `map` — Bản đồ hệ thống

Purpose: let a non-technical owner understand the whole system; every node links to the screen that uses it.

Sections:
1. **5 tầng** (diagram 10): Giao diện (app ← CLI typer) → Điều phối (LangGraph, 5 graph, checkpoint + interrupt, commit node, repo.py) → Agent LLM 01–09 → Dịch vụ code (latex, pdftext, elo, bt, select, facts, audit, embed) → Hạ tầng (llm.py gateway, MiniLM local, Anthropic API ngoài máy); right column storage (inbox, out, checkpoints.db, tutor.db, llm.jsonl). Boxes clickable.
2. **5 graph** G1–G5 (diagram 11): strips + CLI command + "Mở màn hình".
3. **9 agent**: cards: đầu vào → bước (each tagged [LLM]/[code]/[GV]) → đầu ra schema; "trả đề xuất, không ghi DB"; paper source; buttons "Xem trong app" and "Xem hoạt động thật" (→ `logs?agent=`). Text from diagrams 01–09 (hard-coded in map.js).
4. **Dữ liệu**: 16 bảng + 2 view in groups A–D with "ai ghi" (GV / G1 / G2–G3 / G4–G5) and live row counts from `MOCK.db`; two stores explained.
5. **CLI ↔ app**: table command → tab › button (6 commands).
6. **Nguyên tắc**: một nơi ghi; Verifier độc lập; số do code tính; graph cố định; không gì vào DB trước khi duyệt; chỉ thêm dòng (append-only).
7. **Thuật ngữ**: KC, Attempt, Mistake, Rubric, θ, δ, Elo, vừa sức (ZPD), Bradley-Terry, fact_id, checkpoint, interrupt, commit node, thread (from `MOCK.meta.glossary`).
8. **Không làm (cố ý)**: chatbot HS, OCR viết tay, LMS, đăng nhập/phân quyền, nút duyệt tất cả, lịch học, train knowledge tracing — 1-line reason each.
9. **Chưa chốt** (gen_docx §10.1–10.2): 6 questions + 9 proposed choices (phạm vi bản đầu P0–P4, nhánh PDF, model, ẩn danh, mã lỗi + ví dụ, giao diện, số bài gợi ý, repo, spec).

Actions:
| label | effect | backing |
|---|---|---|
| Bấm node / agent / bảng | side drawer with explanation + "Mở màn hình liên quan" | diagrams 00–12 |
| Mở màn hình | `ctx.nav(tab, params)` | navigation |
| Bật chú thích hệ thống | toggles the global explain mode | UI only |
| Chạy thử một vòng [NA] | `App.tour.start()` — 8 steps: Hôm nay → Buổi học (HS-03 20/10, step 4) → Ghi DB → Học sinh (θ đổi) → Gợi ý bài (HS-02) → Báo cáo tháng (HS-02 2026-09) → Vận hành → Nhật ký; caption bubble each step, Next/Prev/Exit | replays G1 → G4 → G5 on mock |

Links: every tab.

---

## 4. Cross-tab flows

1. **After class (G1)**: top bar "Nộp bài" → `session` step 1 → pick HS-02 + `hs02-2026-10-21.tex` → "Bắt đầu xử lý" → strip 01 → lanes 02·03·04 → DỪNG (badge +1) → step 4 A/E/R/N on each card → "Chạy Profiler" → "Ghi vào tutor.db" (backup toast, receipt; gauges move amber → green) → step 5 → "Gợi ý bài buổi sau cho HS này" → `recommend` → "Tạo gợi ý" → "Duyệt danh sách" → `students` shows new θ + list.
2. **Process now, review later**: step 4 "Tạm dừng, duyệt sau" → `today` lists it → "Duyệt tiếp" → same screen, decisions kept.
3. **Flagged ingest (stop 1)**: `review` → HS-04 20/10 "chờ xác nhận khớp bài" → `session` step 3 → confirm match, resolve mismatch, approve rubric for 8DS-PT1-017 → "Chạy tiếp" → step 4.
4. **Elo order lock**: `review` shows HS-05 20/10 locked → open HS-05 17/10 → commit → 20/10 unlocks (badge −1, lock gone).
5. **Failure + resume**: `today` warning HS-06 failed at 03 → "Chạy lại từ checkpoint" (same in `review`, `ops`, `session`) → running → awaiting_review → appears in `review`. Also: during a run "Giả lập lỗi giữa chừng" → `ops` shows failed.
6. **Bank setup**: `catalog` "Nhập từ CSV" → `bank` "Nạp file .tex" → `review` G2 → `bank?review=` choose KCs + rubric → "Ghi lô" → "Xếp độ khó" (now enabled) → G3 → ▲▼ → "Duyệt độ khó" (δ locked) → problems become candidates in `recommend`.
7. **Missing KC while tagging**: `bank` G2 "Thêm KC khác" → "Tạo KC mới" → back to selection (KC also visible in `catalog`).
8. **Month end (G5)**: `report` grid → HS-02 2026-09 (chờ duyệt) → chips/audit → "Sửa câu" → "Duyệt & ghi report" → `students` › Gợi ý & báo cáo.
9. **Trace back**: report sentence `[F04]` → fact row → "Xem nguồn" → `students` history → "Xem buổi" → `session` detail mistake evidence → "Xem lời gọi LLM" → `logs` filtered to that thread's 03 call.
10. **Catalog change ripples**: `catalog` edit error-code example → prompt 03 → 03-v5 (`logs` › Prompt shows "chưa kiểm 3 lần") → "Chạy kiểm tra ổn định". Edit KC description → embedding stale → hint to re-run 06.
11. **Settings ripple**: `ops` › Cài đặt change ratio → `recommend` rule box shows new split.
12. **Learn the system**: `map` node → "Mở màn hình"; any screen with "Chú thích hệ thống" on → chips; `map` "Chạy thử một vòng".

---

## 5. Coverage matrix

| item | tab › element |
|---|---|
| FR1 Nhập bài (tex/PDF, khớp id, cờ, chặn trùng, giữ lỗi HS) | session › step 1–3 (duplicate toast, low_match, mismatch); today/top bar "Nộp bài" |
| FR2 Chấm theo rubric (version, bằng chứng, tổng = tổng mục, cách giải khác) | session › step 4 middle; session step 3 inline rubric; bank › rubric editor/versions |
| FR3 Chẩn đoán + Verifier độc lập (agree/disagree/wrong_code, không tự hoà giải) | session › mistake cards "Diagnoser nói / Verifier nói" |
| FR4 Duyệt lỗi (ưu tiên, A/E/R/N, 1 transaction, giữ llm_json) | session › step 4 + commit; review › G1 rows |
| FR5 Tiến bộ (Elo, Δθ, lặp/mới/hết, knowledge_state, dựng lại) | session › Profiler preview + step 5; students (all sub-tabs, "Dựng lại trạng thái") |
| FR6 Ngân hàng (top-5, rubric, BT 2 chiều, δ cố định, giữ cặp) | bank (G2 + G3 sections, "Tính lại khi thêm bài") |
| FR7 Gợi ý (40/50/10, lọc 30 ngày + rubric, ≥3 KC, lý do 1 dòng, .md) | recommend; ops › Cài đặt |
| FR8 Report (fact_id, 3 insight, audit, viết lại 1 lần/bỏ, không khen quá tay) | report |
| FR9 Danh mục (KC, tiên quyết, mã lỗi + ví dụ) | catalog |
| NFR1 Local, 1 người dùng | footer; ops › Lưu trữ; map › Hạ tầng; no login |
| NFR2 Không cần train | students new-student state (θ = 0); map › Nguyên tắc |
| NFR3 Truy vết | session "Xem bằng chứng"; report fact chips; logs; flow 9 |
| NFR4 GV kiểm soát, không chế độ tự động | review banner + no bulk button; amber/green language; map › Không làm |
| NFR5 Một nơi ghi | receipt toasts; two-store gauge; map › Nguyên tắc |
| NFR6 UNTRUSTED INPUT | session left column frame; payload modal (students/ops/logs) |
| NFR7 Chỉ gửi mã HS | privacy chips; students header; ops › Riêng tư; logs prompt view |
| NFR8 Chạy lại 3 lần khi đổi prompt | logs › Prompt & độ ổn định; catalog banner |
| NFR9 Resume + backup | "Chạy lại từ checkpoint" (today/review/session/ops); ops › Sao lưu; backup toast before G1 commit |
| NFR10 Chi phí agent/buổi | logs; top-bar meter; cost chip; session detail cost |
| Agent 01 Ingest | session step 2–3 |
| Agent 02 Grader | session step 4 middle; bank rubric (G2); session step 3 inline rubric |
| Agent 03 Diagnoser | session mistake cards; catalog prompt preview |
| Agent 04 Verifier | session verifier box + queue order; logs 04 agreement |
| Agent 05 Profiler | session Profiler preview/step 5; students |
| Agent 06 Tagger | bank G2 top-5; catalog embedding status |
| Agent 07 Difficulty | bank G3 pairs + ranking |
| Agent 08 Recommender | recommend step 3 reason |
| Agent 09 Reporter | report draft + audit |
| G1 session_graph | session strip; review; ops lane |
| G2 bank_graph (tag) | bank review; review; ops |
| G3 bank_graph (độ khó) | bank difficulty; review; ops |
| G4 recommend_graph | recommend; review; ops |
| G5 report_graph | report; review; ops |
| `tutor ingest <hs> <file>` | session "Bắt đầu xử lý" (+ top bar, today, students) |
| `tutor review [id]` | review (list = no id, "Mở" = id); today "Duyệt tiếp" |
| `tutor recommend <hs> [--date]` | recommend "Tạo gợi ý" |
| `tutor report <hs> <tháng>` | report "Tạo report" |
| `tutor bank tag <bank.tex>` | bank "Nạp file .tex" + G2 review |
| `tutor bank difficulty` | bank "Xếp độ khó" |
| Statuses confirmed/edited/rejected/added (no proposed in DB) | session cards + detail; students history |
| Append-only + supersedes + replay | session detail "Sửa lỗi đã lưu"; students "Dựng lại" |
| Date-order review, duplicate block, G3 after G2 | review locks; session duplicate toast; bank disabled reason; ops rules |
| checkpoints.db vs tutor.db | top-bar gauge; colours; review banner; ops "Huỷ thread" |
| Open decisions (gen_docx §10) | map › Chưa chốt; catalog FR9 label; ops NFR7 label; settings budget label |
