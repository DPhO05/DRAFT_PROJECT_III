# Contract — `window.MOCK`, shell API, DOM rules

Pairs with `IA.md`. Every tab module reads data ONLY from `window.MOCK` (via `ctx.data`) and talks to the page ONLY through the shell API below.
Field names follow `docs/architecture/schema.sql`. Fields marked **†** are mock-only (not in schema) — keep the dagger in code comments.
JSON columns keep their schema name (`steps_json`, `grade_json`, …) but hold **parsed** values (arrays/objects), never strings.
Dates `'YYYY-MM-DD'`, timestamps `'YYYY-MM-DDTHH:MM:SSZ'`, months `'YYYY-MM'`. Integer ids start at 1. Display: dd/mm/yyyy, θ/δ with 2 decimals and sign.

---

## 1. Files and load order

```text
proto/
  index.html        shell markup (#sidebar, #topbar, #view, #modal-root, #drawer-root, #toasts, footer) + script tags
  styles.css        tokens + shared component classes (§9)
  mock.js           window.MOCK + window.TutorCalc; static data + seeded generator, deterministic
  shell.js          window.App: routing, ctx, ui helpers, badges, gauges, tour
  tabs/<id>.js      one file per tab: today review session recommend report students bank catalog ops logs map
```

Order in `index.html`: inline MathJax config → `https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js` → `mock.js` → `shell.js` → `tabs/*.js` (order of the table above) → inline `App.start()`.
MathJax (SVG output) instead of KaTeX: the artifact host allows external stylesheets only from Google Fonts; tex-svg needs no CSS.
MathJax config: `tex: {inlineMath: [['$','$'],['\\(','\\)']], displayMath: [['\\[','\\]']]}`, `svg: {fontCache: 'global'}`, `startup: {typeset: false}`.
`mock.js` and `shell.js` are built BEFORE tab builders merge; tab builders code against this contract.

## 2. Top-level layout (mirrors the storage legend)

```js
window.MOCK = {
  meta:        { ... },   // static system description (graphs, agents, glossary, tables)
  settings:    { ... },   // config (select.py, elo.py, llm.py)
  db:          { ... },   // data/tutor.db — ONLY approved rows, 16 tables
  checkpoints: { threads: [...] },   // data/checkpoints.db — LangGraph threads + pending proposals
  files:       { inbox, bank, out, backups, llm_log },   // data/ folder
  ui:          { ... }    // prototype-only helpers (activity feed, demo runs, samples)
}
```

| key | used by |
|---|---|
| `meta` | all (shell strip, map, ops, logs, annot) |
| `settings` | recommend, ops, logs, report, session, top bar |
| `db` | all except map (map reads row counts) |
| `checkpoints.threads` | review, today, session, bank, recommend, report, ops, top bar |
| `files.inbox` | session |
| `files.bank` | bank, today |
| `files.out` | recommend, report |
| `files.backups` | ops, today |
| `files.llm_log` | logs, session (cost), today, top bar, ops |
| `ui.*` | see §7 |

---

## 3. `meta`

```js
meta: {
  today: '2026-10-21', months: ['2026-09','2026-10'], seed: 2026,
  graphs: { G1: Graph, G2: Graph, G3: Graph, G4: Graph, G5: Graph },
  agents: [ { id:'01', name:'Ingest', role_vi:'Chép LaTeX, cắt bài, tách bước', graphs:['G1'], tab:'session' }, ... ],  // 9 rows, ids '01'…'09'
  stage_labels: { 'g1.confirm_match':'chờ xác nhận khớp bài', 'g1.review':'chờ duyệt lỗi', 'g2.review':'chờ chọn KC + duyệt rubric',
                  'g3.review':'chờ duyệt xếp hạng độ khó', 'g4.review':'chờ duyệt danh sách bài', 'g5.review':'chờ duyệt report' },
  glossary: [ { term:'KC', vi:'Một kỹ năng nhỏ, đo được; danh sách do GV viết.' }, ... ],   // ≥ 14: KC, Attempt, Mistake, Rubric, θ, δ, Elo, vừa sức (ZPD), Bradley-Terry, fact_id, checkpoint, interrupt, commit node, thread
  tables: [ { name:'mistake', group:'B', writer:'G1 commit', note:'1 lỗi trong 1 attempt' }, ... ]  // 16 tables + 2 views (group 'view')
}
Graph = { id:'G1', name:'session_graph', title_vi:'Lỗi buổi học', cli:'tutor ingest <hs> <file>', commit_tables:[...], nodes:[Node] }
Node  = { id:'g1.03_diagnoser', label:'03 Diagnoser · bước sai, mã lỗi, KC', kind:'code'|'llm'|'stop'|'commit', agent?:'03', lane?:true }
```

Nodes (exact ids, from diagram 11; `lane:true` = runs once per problem in parallel):

| graph | node ids in order | commit_tables |
|---|---|---|
| G1 | `g1.write_session`(code "① ghi session") · `g1.01_ingest`(llm 01) · `g1.confirm_match`(stop "DỪNG nếu 01 gắn cờ") · `g1.02_grader`(llm 02, lane) · `g1.03_diagnoser`(llm 03, lane) · `g1.04_verifier`(llm 04, lane) · `g1.review`(stop "DỪNG: GV duyệt mọi lỗi") · `g1.05_profiler`(llm 05 "code: Elo · LLM: knowledge_state") · `g1.commit`(commit "② 1 transaction") | attempt, mistake, skill_event, skill_state, misconception_log, session |
| G2 | `g2.split`(code latex.py) · `g2.06_tagger`(llm 06, lane) · `g2.02_rubric`(llm 02, lane) · `g2.review`(stop) · `g2.commit` | problem, problem_kc, rubric, kc.embedding |
| G3 | `g3.pair`(code "ghép cặp cùng KC ~10/bài") · `g3.07_difficulty`(llm 07 "hỏi (A,B) và (B,A)") · `g3.bt_fit`(code bt.py) · `g3.review`(stop) · `g3.commit` | problem_pair, problem.bt_score/delta |
| G4 | `g4.read_state`(code) · `g4.select`(code select.py) · `g4.08_recommender`(llm 08) · `g4.review`(stop "ghi data/out/*.md") · `g4.commit` | recommendation |
| G5 | `g5.facts`(code facts.py) · `g5.insights`(code) · `g5.09_reporter`(llm 09) · `g5.audit`(code audit.py) · `g5.review`(stop) · `g5.commit` | report |

## 4. `settings`

```js
settings: {
  reco: { ratios:{ review:0.4, zpd:0.5, challenge:0.1 }, n_problems:6, no_repeat_days:30, min_kc_mix:3, zpd_window:[-0.5, 0.5] },
  elo: { K:0.3, theta0:0 },                          // read-only in UI (spec §8)
  misconception: { resolve_streak:2 },               // read-only
  review: { low_confidence:0.6 },                    // † assumption: spec does not set the threshold
  report: { low_pass_rate:0.5 },                     // † assumption: "kết quả thấp" threshold
  models: { '01':'claude-opus-5-5', '02':'claude-opus-5-5', ..., '09':'claude-opus-5-5' },
  budget_usd_month: 30,                              // † "chưa chốt" (gen_docx §10.1)
  price_assumption: { input_per_mtok:5, output_per_mtok:25, cache_read_per_mtok:0.5, note:'đơn giá giả định cho bản nháp' },  // † not real pricing
  privacy: { send_code_only:true, status:'đề xuất, chờ chốt' },
  backup_dir: 'data/backup/'
}
```

---

## 5. `db` — tutor.db (approved rows only)

Cardinalities are targets for the generator; exact showcase rows in §8.

| key | fields (schema names) | † extras | rows | used by |
|---|---|---|---|---|
| `kc` | id, code, name, description, parent_id (int\|null), embed_model (str\|null), created_at | `lop` (8\|9, from kc.csv), `embedding_stale` (bool; stands for the BLOB) | 74 = 10 groups (parent null) + 64 leaves, kc.csv row order, BOM stripped | catalog, bank, students, recommend, session |
| `kc_prereq` | kc_id, prereq_id | — | 74 (kc_prereq.csv, codes → ids) | catalog, bank, recommend |
| `error_code` | code, category, description, example (str\|null), active (0\|1) | — | 18 seed rows verbatim from schema.sql; `example` set for 13, null for `computational.propagated`, `conceptual.invalid_assumption`, `notational.symbol`, `presentation.units`, `other.unclear`; all active=1 | catalog, session, students, logs |
| `problem` | id, ref, statement_latex, solution_latex, source, bt_score, delta, n_comparisons, difficulty_approved_at, created_at | `topic_file`, `lop`, `solution_steps` [{idx (1-based), latex}], `expected_kc` [code], `expected_difficulty` (1–5) | 279 = refs 001–031 of 9 files (all except `8-ham-so-bac-nhat.tex`, whose 31 live in the G2 thread) | bank, session, recommend, students, report |
| `problem_kc` | problem_id, kc_id, step_idx, evidence_latex, approved_at | — | for the 279: one row per expected KC k (0-based) at step_idx = min(k+1, n_steps) | bank, recommend, session, catalog |
| `rubric` | id, problem_id, version, items_json [{item_id:'r1', text, points}], max_score, approved_at | — | 276 (v1; none for 8DS-PT1-017, 9DS-PT2-019, 9DS-CAN-019) + 1 v2 (9DS-PT2-002, teacher edit of r3 text). Items = one per solution paragraph, the final "Đáp số" paragraph merged into the last item, 1 point each (9DS-PT2-002 → 5 items) | bank, session, recommend |
| `problem_pair` | id, problem_a, problem_b (a<b), harder_ab ('a'\|'b'), harder_ba ('a'\|'b'), created_at | — | ≈1 240 (8 δ-approved files × 5 per problem = 155, ~10 comparisons per problem; ~8% with harder_ab≠harder_ba = hoà) | bank |
| `student` | id, name, grade, note, created_at, archived_at | `code` = `'HS-' + pad2(id)` (the API code) | 6 (§8.1) | all |
| `session` | id, student_id, held_on, source_path, source_kind ('tex'\|'pdf'), source_sha256 (64 hex), transcript_latex, knowledge_state, thread_id, status ('running'\|'awaiting_review'\|'committed'\|'failed'), created_at, committed_at | `review_seconds` (int\|null) | ≈42: §8.2 schedule | session, students, today, review, ops, logs, report |
| `attempt` | id, session_id, seq, problem_id, rubric_id, solution_latex, steps_json [{idx, latex, pos:[start,end]}], flags_json [Flag], grade_json [{item_id, passed, evidence_latex}], score, max_score, supersedes_id, created_at | — | 3–4 per committed session (≈125) | session, students, report, recommend |
| `mistake` | id, attempt_id, step_idx, code, kc_id (int\|null), description, evidence_latex, confidence, verifier_verdict ('agree'\|'disagree'\|'wrong_code'\|null), verifier_reason, status ('confirmed'\|'edited'\|'rejected'\|'added'), llm_json (object\|null), teacher_note, supersedes_id, reviewed_at, created_at | — | ≈150; status mix ≈70/12/13/5 %; verdict mix ≈75/12/13 % (null when added); `llm_json === null` ⇔ status 'added' | session, students, catalog, logs, report |
| `skill_event` | id, student_id, kc_id, attempt_id, outcome (0\|1), p_expected, theta_before, theta_after, delta, created_at | — | derived (§6) | students, session, report |
| `skill_state` | student_id, kc_id, theta, n_attempts, correct_streak, last_seen, updated_at | — | derived | students, recommend, today, catalog |
| `misconception_log` | student_id, code, kc_id, first_seen, last_seen, count, resolved_at | — | derived | students, recommend, report, today |
| `recommendation` | id, student_id, for_date, problem_id, kc_id, bucket ('review'\|'zpd'\|'challenge'\|null), reason, status ('approved'\|'rejected'\|'added'), reviewed_at | — | 6 per list; lists for_date = every committed 2026-10 held_on, plus HS-01 `2026-10-21`, HS-06 `2026-10-19`; ~1 rejected + 1 added in a third of lists | recommend, students, today |
| `report` | id, student_id, month, facts_json [Fact], text_md, audit_json [Sentence], approved_at | — | 4: month 2026-09 for HS-01, HS-03, HS-05, HS-06 | report, students |

Shared shapes:
```js
Flag     = { type:'low_match'|'mismatch'|'no_rubric'|'alt_method', detail:'…', step_idx?:int, transcript?:'…', text_layer?:'…', resolved:bool }
Fact     = { fact_id:'F01', kind:'count'|'sessions'|'rate'|'delta_theta'|'top_code'|'recurring'|'resolved', label:'Số bài đã làm', value:number|string, unit?:'%'|'bài'|'buổi'|'lần', kc_id?:int, code?:str, insight?:'trend'|'change_point'|'outlier'|'majority', sql:'SELECT …' }
Sentence = { idx:int, text:'… [F02]', fact_ids:['F02'], result:'pass'|'rewritten'|'dropped', reason:str|null, first_draft:str|null, tone_flag?:bool }
```
`problem` status is derived, not stored — `ctx.lookup.problemStatus(problem)` returns `'ready'` (≥1 problem_kc, rubric, difficulty_approved_at) · `'thieu_rubric'` · `'cho_do_kho'` (tagged + rubric, δ null) · `'cho_duyet_tag'` (only in a G2 thread).
δ-approved files: the 8 files other than `9-ham-so-y-ax2.tex` (δ null, G3 pending) and `8-ham-so-bac-nhat.tex` (G2 pending).

## 6. Derivation rules (`window.TutorCalc`, defined in mock.js, re-exported as `ctx.calc`)

```js
TutorCalc = {
  elo(theta, delta, X, K)            // → { P: 1/(1+Math.exp(-(theta-delta))), thetaAfter: theta + K*(X-P) }
  xFor(attempt, kcId, mistakes)      // 0 if a current mistake (status≠'rejected', not superseded) on attempt has kc_id===kcId, else 1
  replay(db, studentId)              // → { skill_event:[], skill_state:[], misconception_log:[] } from committed attempts in (held_on, seq) order
  deltaVsPrevious(db, sessionId)     // → [{kc_id, theta_before, theta_after, d}] + { repeat:[code], new:[code], gone:[code], resolved:[{code,kc_id}] }
  passRate(attempts)                 // Σscore / Σmax_score
  audit(sentence, facts)             // → { ok, reason } — see below
  selectRecommendations(db, settings, studentId, forDate)  // → { kc_selection, candidates, picks } — see below
}
```

- **Elo** (spec §8, gen_docx §5.1): θ0 = 0; KCs of an attempt = distinct `problem_kc.kc_id` of its problem; δ = `problem.delta`; store 4 decimals. Worked example to show in popovers: θ=0.10, δ=0.35, X=0 → P=0.44, θ=−0.03.
- **skill_state** = last event per (student, kc): `n_attempts` = event count, `correct_streak` = trailing X=1 run, `last_seen` = held_on.
- **misconception_log**: from current mistakes with kc_id; key (student, code, kc); `count` = number of attempts with that pair; `resolved_at` = held_on where the KC reaches `resolve_streak` consecutive X=1 after `last_seen`; recurrence clears `resolved_at`, count+1.
- **Δθ vs previous**: per KC touched in the session: θ after this session − θ before its first event in the session. Codes: repeat = in both last two committed sessions, new = only this one, gone = only the previous one (gen_docx §5.3).
- **δ for the mock**: δ = round((expected_difficulty − 3) × 0.6 + noise(±0.15), 2); `bt_score = δ / 0.6`. † The real BT→δ conversion is an open point (gen_docx §10.4).
- **Recommendation select** (select.py): split `n_problems` by ratios with largest-remainder rounding (6 → 2/3/1); review KCs = KCs with unresolved misconceptions by count desc; zpd = KCs with a candidate where θ−δ ∈ `zpd_window`, by min |θ−δ|; challenge = KC whose prereqs all have θ ≥ 0 (†) with the smallest δ−θ > 0.5. Candidate filter: has `problem_kc` for the KC, has rubric, δ approved, not attempted by the student within `no_repeat_days` before `forDate`; excluded candidates keep `excluded:'đã làm 2026-10-01 (< 30 ngày)'|'chưa có rubric'|'δ chưa duyệt'`. Enforce ≥ `min_kc_mix` distinct KCs (swap the weakest pick for the next KC).
- **Audit** (audit.py): sentence must contain ≥1 `[F\d+]`; every number matched by `/-?\d+(?:[.,]\d+)?%?/` (ignoring the fact ids themselves) must equal a value of a cited fact within 0.005 after normalising `,`→`.` and `%` (68% ≡ 0.68). Fail → reason `'không trích fact_id'` or `'số 70% không khớp F02 = 68%'`.

The generator in mock.js uses these same functions to build skill_event / skill_state / misconception_log and all report facts, so "Dựng lại trạng thái từ lịch sử" always matches.

---

## 7. `checkpoints.threads` — data/checkpoints.db

```js
Thread = {
  thread_id:'g1-hs03-20261020', graph:'G1'|'G2'|'G3'|'G4'|'G5',
  subject:'HS-03 · buổi 20/10/2026',       // display string
  student_id:int|null, session_id:int|null,
  started_at:ISO, status:'running'|'awaiting_review'|'committed'|'failed',   // same enum as session.status
  current_node:NodeId, interrupted_at:NodeId|null, error:str|null,
  checkpoints:[ { node:NodeId, lane?:int /*attempt seq*/, at:ISO, ms:int, tokens_in:int, tokens_out:int } ],
  demo_run:str|null,                       // key in MOCK.ui.demo_runs played when running/resumed
  state:{ ...per graph below }
}
```
The review queue = threads with `status==='awaiting_review'`. `locked` is computed by the shell, never stored: a G1 thread is locked when the same student has another awaiting G1 thread with an earlier `held_on`.
Committed history threads (one per committed session / approved list / approved report / bank run, `status:'committed'`) exist so `ops` can list and "Dọn" them.

Per-graph `state` and proposal kinds (`kind ∈ mistake | kc_tag | rubric | difficulty | recommendation | report`):

```js
// G1
state = { source:{path, kind, sha256}, transcript_latex, attempts:[PendingAttempt], proposals:[MistakeProposal],
          decisions:{ [pid]: Decision }, context_mistake_ids:[int] /*5 recent approved, from SQL*/, profile:null }
PendingAttempt = { seq, problem_id:int|null, match:{ method:'id'|'llm', score:num|null, candidates:[{problem_id, score}] },
                   rubric_id:int|null, rubric_draft:{ items_json, max_score }|null, steps_json, flags_json:[Flag],
                   grade_json, score, max_score }
MistakeProposal = { pid:'p1', kind:'mistake', attempt_seq, step_idx, code, kc_id:int|null, description, evidence_latex, confidence,
                    verifier:{ verdict:'agree'|'disagree'|'wrong_code', reason, suggested_code:str|null } }
Decision = { action:'accept'|'edit'|'reject'|'add', code?, kc_id?, step_idx?, description?, evidence_latex?, teacher_note?, at }
// commit mapping → db.mistake: accept→'confirmed' (proposal fields); edit→'edited' (decision fields);
// reject→'rejected'; add→'added' (llm_json null, verifier fields null). llm_json = proposal minus `verifier`.
// verifier_verdict/verifier_reason copied from proposal.verifier. reviewed_at = now. Rubric approved at stop 1 is written in the same commit.

// G2
state = { bank_file, problems:[{ ref, topic_file, lop, statement_latex, solution_latex, solution_steps, expected_kc, expected_difficulty }],
          proposals:[KcTagProposal | RubricProposal], decisions:{ [pid]: {kc_ids:[int]} | {items_json, max_score} }, done:{ [ref]: bool } }
KcTagProposal = { pid, kind:'kc_tag', problem_ref, step_idx /*0 = cả bài*/, step_latex,
                  candidates:[ { kc_id, cosine, llm_rank /*1..5*/, evidence_latex, prereq_warning:str|null } ] /*exactly 5*/ }
RubricProposal = { pid, kind:'rubric', problem_ref, version:1, items_json, max_score, alt_methods:str|null }

// G3
state = { kc_group:'9DS-HSB2', proposals:[DifficultyProposal] /*one per KC*/, decisions:{ [pid]: {ranking:[problem_id]} } }
DifficultyProposal = { pid, kind:'difficulty', kc_id, pairs:[{problem_a, problem_b, harder_ab, harder_ba}],
                       ranking:[{ problem_id, bt_score, delta, n_comparisons, teacher_adjusted:false }] }

// G4
state = { student_id, for_date, ratios, kc_selection:[{kc_id, bucket, theta, reason}],
          candidates:[{ problem_id, kc_id, gap /*θ−δ*/, last_done:str|null, rubric_version:int|null, excluded:str|null }],
          proposals:[RecoProposal] /*6*/, decisions:{ [pid]: {action:'approve'|'reject'|'replace', replacement_problem_id?} },
          added:[{problem_id, kc_id}], out_path:'data/out/recommend-HS-02-2026-10-23.md' }
RecoProposal = { pid, kind:'recommendation', problem_id, kc_id, bucket, reason /*08, 1 line*/, theta, delta, last_done, rubric_version }

// G5
state = { student_id, month, proposals:[ReportProposal] /*1*/, decisions:{} , out_path:'data/out/report-HS-02-2026-09.md' }
ReportProposal = { pid, kind:'report', facts_json:[Fact], audit_json:[Sentence], text_md,
                   tone:{ low_results:bool, pass_rate:number, threshold:number } }
```

## 8. Showcase records (exact; everything else generated)

### 8.1 Students

| id | code | name | grade | note |
|---|---|---|---|---|
| 1 | HS-01 | Nguyễn Minh An | 9 | Ôn thi vào 10 |
| 2 | HS-02 | Trần Gia Bảo | 9 | Hay nhầm dấu khi tính Δ |
| 3 | HS-03 | Lê Thu Hà | 9 | — |
| 4 | HS-04 | Phạm Đức Khang | 8 | Mới học từ tháng 9, nền yếu |
| 5 | HS-05 | Võ Ngọc Lan | 8 | — |
| 6 | HS-06 | Đặng Quốc Huy | 8 | Nộp PDF thay vì .tex |

Grade-9 students only get 9DS problems; grade-8 only 8DS. Names are fictional and stay local (never in prompts, NFR7).

### 8.2 Sessions and threads

Committed `held_on` (weekly): HS-01 09-02, 09-09, 09-16, 09-23, 10-07, 10-14 · HS-02 09-03, 09-10, 09-17, 09-24, 10-01, 10-08, 10-15 · HS-03 09-04, 09-11, 09-18, 09-25, 10-06, 10-13 · HS-04 09-05, 09-12, 09-19, 09-26, 10-03, 10-10 · HS-05 09-06, 09-13, 09-20, 09-27, 10-04, 10-11 · HS-06 09-05, 09-19, 10-03, 10-12. `source_path = data/inbox/hs0N-YYYY-MM-DD.tex` (HS-06 `.pdf`).

Non-committed (also present in `db.session` — ① writes the row at start):

| thread_id | graph | status | stage / node | notes |
|---|---|---|---|---|
| `g1-hs03-20261020` | G1 | awaiting_review | `g1.review` | 4 attempts, 6 proposals (§8.3) |
| `g1-hs05-20261017` | G1 | awaiting_review | `g1.review` | 3 attempts, 3 proposals |
| `g1-hs05-20261020` | G1 | awaiting_review | `g1.review` | locked by 17/10; 3 attempts, 2 proposals |
| `g1-hs04-20261020` | G1 | awaiting_review | `g1.confirm_match` | PDF; flags §8.4; proposals empty; `demo_run:'hs04-after-confirm'` |
| `g1-hs06-20261019` | G1 | failed | `g1.03_diagnoser` lane 3 | `error:'APITimeoutError: hết thời gian chờ sau 3 lần thử (lane 3 · 8DS-PS-005)'`; lanes 1–2 done; `demo_run:'hs06-resume'` |
| `g1-hs01-20261021` | G1 | running | `g1.02_grader` | `demo_run:'hs01-1021'` (plays on open) |
| `g2-8-ham-so-bac-nhat` | G2 | awaiting_review | `g2.review` | 31 problems 8DS-HSBN-001…031; step-level kc_tag proposals for 001, 003, 005; step_idx 0 for the other 28; 31 rubric proposals |
| `g3-9DS-HSB2` | G3 | awaiting_review | `g3.review` | 4 DifficultyProposals (9DS-HSB2-01…04; each problem under its first expected KC), ≈155 pairs |
| `g4-hs02-20261023` | G4 | awaiting_review | `g4.review` | §8.5 |
| `g5-hs02-2026-09` | G5 | awaiting_review | `g5.review` | 6 sentences: 4 pass, 1 rewritten (first draft "70%" vs fact 68%-style), 1 dropped ("không trích fact_id") |
| `g5-hs04-2026-09` | G5 | awaiting_review | `g5.review` | generator guarantees HS-04 Sep pass rate < 0.5 → `tone.low_results:true`; one sentence `tone_flag:true` (praise) dropped |

Queue at load: 9 awaiting (1 locked) → review badge 9, ops badge 1.

### 8.3 `g1-hs03-20261020` (main review demo)

Attempts: seq 1 `9DS-PT2-002` · seq 2 `9DS-PT2-007` · seq 3 `9DS-CAN-007` (02 flag `alt_method`: ẩn phụ t = √x) · seq 4 `9DS-HPT-002` (no mistakes, full score).
Student steps for seq 1 (verbatim):
```latex
1  x(2x - 3) = 2(x + 1) + 1 \Leftrightarrow 2x^2 - 3x = 2x + 3
2  2x^2 - 5x - 3 = 0,\quad a = 2,\ b = -5,\ c = -3
3  \Delta = (-5)^2 - 4 \cdot 2 \cdot (-3) = 25 - 24 = 1
4  x_1 = \dfrac{5 + 1}{4} = \dfrac{3}{2},\quad x_2 = \dfrac{5 - 1}{4} = 1
5  \text{Vậy } S = \left\{1;\ \dfrac{3}{2}\right\}
```
Seq 2: correct Δ' and part a; step 3 uses Viète without stating Δ' ≥ 0; step 6 "Vậy $m = 2$ hoặc $m = -6$". Seq 3: step 1 "Đặt $t = \sqrt{x}\ (t \ge 0)$"; step 2 rewrites $\frac{7t+3}{9-t^2} = \frac{-(7t+3)}{(t-3)(t+3)}$ (correct); step 4 cancels $(t-3)$ without noting $t \ne 3$; step 5 concludes "$P = \frac{3t}{t+3}$" (still in t); part b correct.

| pid | seq | step | code | KC | conf | 04 verdict | 04 reason / suggested |
|---|---|---|---|---|---|---|---|
| p1 | 1 | 3 | computational.intermediate_calc | 9DS-PT2-02 | 0.58 | wrong_code | "−4·2·(−3) = +24; HS đổi dấu" → `notational.operator_swap` |
| p2 | 3 | 2 | computational.copy_error | 9DS-CAN-05 | 0.47 | disagree | "Bước 2 đổi dấu mẫu và tử cùng lúc — biến đổi đúng, không phải chép sai" |
| p3 | 2 | 6 | conceptual.theorem_misapplied | 9DS-PT2-03 | 0.55 | agree | "Nhận m = −6 khi Δ' < 0" |
| p4 | 1 | 4 | computational.propagated | 9DS-PT2-02 | 0.81 | agree | "Sai theo Δ ở bước 3" |
| p5 | 3 | 4 | presentation.missing_justification | 9DS-CAN-05 | 0.88 | agree | "Rút gọn (t − 3) mà không nêu t ≠ 3 (x ≠ 9)" |
| p6 | 3 | 5 | presentation.variable_misnamed | null | 0.64 | agree | "Kết luận theo t, đề hỏi theo x" |

Display order: p1, p2 (disputed) → p3 (< 0.6) → p4, p6, p5 (rest, by seq then step). Rubric seq 1 = `9DS-PT2-002` v2, grade r1 ✓ r2 ✓ r3 ✗ r4 ✗ r5 ✗.
`context_mistake_ids`: 5 latest approved HS-03 mistakes (generator picks).

### 8.4 `g1-hs04-20261020` (stop 1)

| seq | match | flags |
|---|---|---|
| 1 | `8DS-PTNT-007` by id | `mismatch` step 2: transcript `x^2(2x - 1) - 4(2x - 1)` vs text layer `x^2(2x - 1) - 4(2x + 1)` |
| 2 | llm: `8DS-PS-005` 0.71 · `8DS-PS-003` 0.64 · `8DS-PS-014` 0.41 | `low_match` |
| 3 | `8DS-PT1-017` by id | `no_rubric` + `rubric_draft` (one item per solution step) |

### 8.5 `g4-hs02-20261023`

| pid | bucket | KC | problem |
|---|---|---|---|
| r1 | review | 9DS-PT2-02 | 9DS-PT2-003 |
| r2 | review | 9DS-CAN-01 | 9DS-CAN-002 |
| r3 | zpd | 9DS-HPT-03 | 9DS-HPT-013 |
| r4 | zpd | 9DS-BPT-03 | 9DS-BPT-004 |
| r5 | zpd | 9DS-CAN-03 | 9DS-CAN-008 |
| r6 | challenge | 9DS-PT2-06 | 9DS-PT2-008 |

Generator constraints so this is consistent: HS-02 has unresolved misconceptions (`notational.operator_swap`, 9DS-PT2-02, count ≥ 3) and (any code, 9DS-CAN-01); HS-02 did none of the six problems after 2026-09-23; excluded examples in `candidates`: `9DS-PT2-002` "đã làm … (< 30 ngày)", `9DS-PT2-019` "chưa có rubric", `9DS-HSB2-028` "δ chưa duyệt".

### 8.6 Other fixed facts

- Bank files (`files.bank`, 10): path `data/inbox/bank/<file>.tex`, `topic_vi`, `kc_group`, `lop`, `n_blocks:31`, `status` ('ready' 8 · 'cho_do_kho' 9-ham-so-y-ax2 · 'cho_duyet_tag' 8-ham-so-bac-nhat).
- Problem LaTeX: extracted at build time from `data/dummy/bank/*.tex` — all refs `…-001`…`…-031` (the bank is complete; the generator asserts every file has exactly these), `\begin{problem}[ref] … \end{problem}` blocks after `\begin{document}`; solution = the `solution` env; steps = paragraphs split on blank lines; metadata from `% kc_du_kien:` / `% do_kho_du_kien:` comments.
- `files.inbox`: `hs02-2026-10-21.tex` (new → `demo_run:'hs02-1021'`), `hs03-2026-10-20.tex`, `hs04-2026-10-20.pdf`, `hs01-2026-10-21.tex` (all three duplicates of existing sessions → duplicate toast).

---

## 9. `files` and `ui`

```js
files: {
  inbox:   [ { path, student_id, held_on, kind:'tex'|'pdf', sha256, demo_run:str|null } ],
  bank:    [ { path, file, topic_vi, kc_group, lop, n_blocks, status } ],
  out:     [ { path, kind:'recommend'|'report', student_id, key /*for_date or month*/, text } ],     // .md of approved items
  backups: [ { path:'data/backup/tutor-2026-10-15.db', at:ISO, size_kb:int } ],                       // 5 rows, newest first
  llm_log: [ LlmCall ]          // ≈ 4 100 rows, generated at load per run (G1: 01×1, 02×n, 03×2n (2 passes), 04×#proposals, 05×1; G2: 06+02 per problem; G3: 07 per pair×2; G4: 08×1; G5: 09×1–2).
                                 // Bank runs of the 8 δ-approved files are dated 2026-08-25…31 (outside the mock months); G3 9DS-HSB2 2026-10-18; G2 8-ham-so-bac-nhat 2026-10-19.
}
LlmCall = { ts:ISO, agent:'01'…'09', graph:'G1'…'G5', thread_id, student_code:'HS-03'|null, prompt_version:'03-v4', model:'claude-opus-5-5',
            tokens_in:int, tokens_out:int, cache_read_tokens:int, ms:int, cost_usd:number /*from price_assumption*/,
            result:'ok'|'retry'|'schema_error', output_summary:str }

ui: {
  activity: [ { at:ISO, text, graph:str|null, agent:str|null, table:str|null } ],      // 12 seeded, newest first; ctx.receipt prepends
  demo_runs: {                                                                          // played by session (G1) runs
    'hs02-1021' | 'hs01-1021' | 'hs06-resume' | 'hs04-after-confirm':
      { attempts:[PendingAttempt], proposals:[MistakeProposal], node_timings:[{node, lane?, ms, tokens_in, tokens_out}], llm_calls:[LlmCall] },
    'g4-new': { reason_templates:{ review:'Ôn {kc}: lỗi {code} chưa hết ({count} lần).', zpd:'Vừa sức: θ − δ = {gap}.', challenge:'Thử thách: đã vững KC tiên quyết {prereq}.' } },
    'g5-new': { sentence_templates:[...], rewrite_example:{...}, drop_example:{...} }
  },
  agent_quality: { '06': { top5_hit:0.92, top1_match:0.41, n:279 } },                  // † other metrics are computed from db
  prompt_versions: [ { agent:'03', version:'03-v4', changed_at:ISO, stability:{ status:'passed'|'not_run', runs:3, pass3:bool, changed_criteria_pct:number } } ],  // 9 rows
  api_payload_samples: { '01'|'02'|'03'|'04'|'06'|'08'|'09': { cached_system:str, untrusted:str /*contains {code}*/, schema:str } },
  catalog_import_preview: { kc_added:[], kc_changed:[{ code:'9DS-PT2-03', field:'description', old, new }], prereq_added:[], prereq_removed:[] }
}
```

`demo_runs` proposals for new runs: `hs02-1021` = 3 attempts / 4 proposals (1 wrong_code, 1 low conf); `hs01-1021` = 3 / 3; `hs06-resume` = lane 3 only + earlier lanes' proposals (3 total); `hs04-after-confirm` = 3 proposals (incl. `computational.copy_error` on seq 1 step 2 if text layer chosen).

---

## 10. Shell API (`window.App`, shell.js)

```js
App.registerTab(id, { title, render(root, ctx) })   // render may return a cleanup fn; called on every nav to the tab
App.start()                                         // builds shell, parses hash, renders
App.tour                                            // { start(), next(), prev(), stop() } — steps in IA §3.11
```

Routing: `#/<tabId>?k=v&k2=v2`. Unknown tab → `today`. Each render clears `#view`, sets `#view[data-tab=<id>]`, scrolls top. Shell wraps `render` in try/catch and shows an error box (one broken tab never kills the app).

`ctx` passed to `render`:

| member | signature | does |
|---|---|---|
| `data` | `window.MOCK` | mutable; tabs mutate rows directly, then call `ctx.refresh()` |
| `params` | `{}` | parsed hash params (strings) |
| `nav` | `(tabId, params?)` | sets hash → re-render |
| `rerender` | `()` | re-render current tab with same params |
| `refresh` | `()` | recompute badges, gauges, cost meter (no tab re-render) |
| `toast` | `(msg, {kind:'info'\|'ok'\|'warn'\|'error'}?)` | 4 s toast in `#toasts` |
| `receipt` | `(title, rows:[[table, n\|'cập nhật']], {graph, backup?:bool})` | if `backup` first toasts "Đã sao lưu data/backup/tutor-<today>.db" and prepends `files.backups`; then receipt toast "1 transaction · +n table …"; prepends `ui.activity`; `refresh()` |
| `modal` | `({title, body: Node\|string\|(el)=>void, actions:[{label, kind, onClick(close), noAutoclick}], wide})` → `{close}` | in `#modal-root`; close button `[data-modal-close]`; Esc closes |
| `confirm` | `(msg)` → `Promise<boolean>` | modal-based |
| `drawer` | `({title, body})` → `{close}` | right side panel in `#drawer-root` |
| `tex` | `(el)` → `Promise` | `MathJax.typesetPromise([el])`; no-op if MathJax missing |
| `calc` | `window.TutorCalc` | §6 |
| `lookup` | `student(id)`, `studentByCode(code)`, `kc(id)`, `kcByCode(code)`, `problem(id)`, `problemByRef(ref)`, `errorCode(code)`, `rubricFor(problemId)` (latest version), `problemStatus(problem)`, `thread(id)`, `sessionByThread(id)` | O(1) maps rebuilt on `refresh()` |
| `queue` | `list({graph?, student_id?})` → threads sorted (G1 by student + held_on, then interrupted_at) with computed `locked`, `lock_reason`, `blocker`; `count()`; `open(threadId)` routes per IA §3.2; `resolve(threadId)` → status 'committed', `refresh()`, unlock dependants; `add(thread)` | badge source |
| `threads` | `resume(id)` (failed → running → 1.2 s → awaiting_review, merges `ui.demo_runs[thread.demo_run]`, session status synced, toast, refresh) · `fail(id, node, error)` · `cancel(id)` | shared by today, review, session, ops |
| `explain` | `boolean` | current "Chú thích hệ thống" state |
| `ui` | helpers below | — |

`ctx.ui` helpers (all return DOM nodes; `h` is the base):

| helper | signature |
|---|---|
| `h` | `(tag, attrs?, ...children)` — attrs: `class`, `style`, `on*` handlers, `data-*`; strings become text nodes |
| `button` | `(label, onClick, {kind:'primary'\|'secondary'\|'danger'\|'ghost', cli?, privacy?:code, disabledReason?, noAutoclick?, title?})` — always `<button type="button">`; `disabledReason` → disabled + visible reason; `cli` → `>_` line under it; `privacy` → chip "gửi API dưới mã HS-03" |
| `table` | `({columns:[{key, label, render?(row), align?}], rows, empty?, onRow?, rowClass?(row)})` — wrapped in a horizontally scrollable box |
| `chip` | `(text, kind?)` — kinds: neutral, info, ok, warn, danger, G1…G5, agent01…agent09 |
| `status` | `(value)` — pill for every enum: running, awaiting_review, committed, failed, confirmed, edited, rejected, added, approved, waiting, locked, pass, rewritten, dropped, ready, thieu_rubric, cho_do_kho, cho_duyet_tag |
| `store` | `(kind: 'checkpoint'\|'db'\|'file')` — badge "checkpoints.db" / "tutor.db" / "data/" |
| `prov` | `(kind: 'llm'\|'code'\|'gv', label?)` — provenance mark |
| `annot` | `(tags:[str])` — explain-mode chips; tag forms `'G1'`, `'agent:03'`, `'table:mistake'`, `'cli:tutor review'`, `'file:checkpoints.db'` |
| `why` | `(content: Node\|()=>Node)` — "?" button opening "Con số này từ đâu?" popover |
| `cli` | `(cmd)` — mono line `>_ cmd` |
| `graphStrip` | `(graphId, {current?, done?:[nodeId], failed?, lanes?:[{seq, label, done:[nodeId], failed?}], compact?})` |
| `animateGraph` | `(stripEl, steps:[{node, lane?, ms}], {stepMs=350})` → `Promise` |
| `segmented` | `(options:[{id, label}], value, onChange)` — in-page sub-tabs (buttons) |
| `sparkline` | `(values:[number], {w=80, h=20})` — inline SVG |
| `bar` | `(value, max, {signed?:bool, kind?})` — horizontal bar; signed centres at 0 |
| `lineChart` | `(points:[{x:label, y:number}], {h=160, yLabel})` — inline SVG, axis + dots |
| `rubricEditor` | `(rubric:{items_json, max_score}, {onChange, readOnly})` — rows text + points, add/remove (buttons), total auto |
| `latex` | `(src, {block?})` — element with raw TeX; call `ctx.tex` after insert |
| `kv` | `(pairs:[[label, value]])` — definition list |
| `empty` | `(text, action?:Node)` |
| `payloadModal` | `(agentId, studentCode)` — "Xem nội dung gửi API" from `ui.api_payload_samples` |
| `download` | `(filename, text)` — Blob link; callers set `noAutoclick` |
| `fmt` | `date(d)`, `month(m)`, `dt(ts)`, `num(x, d=2)`, `signed(x)`, `pct(x)`, `usd(x)`, `ago(ts)` |

---

## 11. DOM conventions (test robot relies on these)

- Nav links: `<a data-tab-link="<id>">` in `#sidebar` (also top-bar shortcuts use the same attribute).
- View root: `#view` (`data-tab` = current id). Modals in `#modal-root`, drawers in `#drawer-root`, toasts in `#toasts`.
- **Every action is a `<button type="button">`** — no clickable divs/spans, no `<a>` for actions (links only for nav).
- Buttons that must not be auto-clicked carry `data-no-autoclick`: downloads, "Đặt lại dữ liệu mẫu", tour start, "Huỷ thread", "Giả lập lỗi giữa chừng", anything that reloads the page.
- Disabled buttons use the `disabled` attribute and show their reason in a sibling `.reason` element.
- Every button handler must be safe to click repeatedly and in any order (idempotent or guarded; never throws on missing state).
- Keyboard shortcuts only on `session` step 4; ignored when focus is in `input`, `textarea`, `select`.
- No `alert()`, `prompt()`, `confirm()` — use `ctx.modal` / `ctx.confirm`.
- No network calls except the MathJax script.
- `localStorage` only for per-viewer conveniences (explain mode, last sub-tab), always in try/catch.

## 12. Styling (styles.css owned by shell)

- Colour tokens on `:root`, dark overrides under `@media (prefers-color-scheme: dark)` with `:root:not([data-theme="light"])` and `:root[data-theme="dark"]`; `body` has an explicit background.
- Data-state classes: `.st-pending` (amber, dashed border — checkpoints.db), `.st-db` (green solid — tutor.db), `.st-rejected` (grey, strike-through), `.st-file` (grey square). Provenance: `.pv-llm` (rounded), `.pv-code` (square), `.pv-gv` (dashed).
- Graph colours: `--g1`…`--g5`; agent colours `--a01`…`--a09` (same everywhere).
- Layout: sidebar 232 px; under 720 px it collapses behind a "Menu" button; 16 px side gutter; no horizontal page scroll; tables scroll inside `.table-wrap`.
- Explain mode: `body.explain .annot { display:inline-flex }`, hidden otherwise.
- Font: system UI stack with Vietnamese support (or one Google Font, e.g. "Be Vietnam Pro").
