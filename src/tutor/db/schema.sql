-- tutor.db: SQLite schema (bản thiết kế; sơ đồ: 12-database-erd.excalidraw)
--
-- Quy tắc:
--   1. Chỉ commit node của Orchestrator ghi file này (single writer).
--   2. Đề xuất LLM đang chờ giáo viên duyệt nằm trong checkpoints.db (LangGraph),
--      không nằm ở đây. Ở đây chỉ có dữ liệu đã duyệt.
--   3. attempt, mistake, skill_event chỉ thêm. Sửa = dòng mới + supersedes_id.
--   4. skill_state, misconception_log là bản tóm tắt, dựng lại được từ skill_event / mistake.
--   5. Thời gian: TEXT ISO-8601 UTC. Ngày: 'YYYY-MM-DD'. Tháng: 'YYYY-MM'.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =========================================================== A. Ngân hàng bài
CREATE TABLE kc (
  id           INTEGER PRIMARY KEY,
  code         TEXT    NOT NULL UNIQUE,              -- mã do giáo viên đặt
  name         TEXT    NOT NULL,
  description  TEXT    NOT NULL,                     -- định nghĩa, đem đi embedding (06)
  parent_id    INTEGER REFERENCES kc(id),
  embedding    BLOB,                                 -- float32[]; NULL tới khi 06 chạy
  embed_model  TEXT,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE kc_prereq (
  kc_id      INTEGER NOT NULL REFERENCES kc(id),
  prereq_id  INTEGER NOT NULL REFERENCES kc(id),
  PRIMARY KEY (kc_id, prereq_id),
  CHECK (kc_id <> prereq_id)
);

CREATE TABLE error_code (                            -- taxonomy §6, giáo viên sửa được
  code         TEXT    PRIMARY KEY,                  -- '<category>.<sub>'
  category     TEXT    NOT NULL CHECK (category IN
                 ('computational','conceptual','notational','presentation','other')),
  description  TEXT    NOT NULL,
  example      TEXT,                                 -- 1 ví dụ cho prompt 03 (FERMAT)
  active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE TABLE problem (
  id              INTEGER PRIMARY KEY,
  ref             TEXT    NOT NULL UNIQUE,           -- id trong \begin{problem}[ref]
  statement_latex TEXT    NOT NULL,
  solution_latex  TEXT    NOT NULL,
  source          TEXT,
  bt_score        REAL,                              -- 07: Bradley-Terry thô
  delta           REAL,                              -- 07: δ thang Elo, cố định sau khi duyệt
  n_comparisons   INTEGER NOT NULL DEFAULT 0,
  difficulty_approved_at TEXT,
  created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE problem_kc (                            -- chỉ tag giáo viên đã chọn (06)
  problem_id     INTEGER NOT NULL REFERENCES problem(id),
  kc_id          INTEGER NOT NULL REFERENCES kc(id),
  step_idx       INTEGER NOT NULL DEFAULT 0,         -- bước của lời giải mẫu; 0 = cả bài
  evidence_latex TEXT,
  approved_at    TEXT    NOT NULL,
  PRIMARY KEY (problem_id, kc_id, step_idx)
);

CREATE TABLE rubric (                                -- 02 sinh từ lời giải mẫu, GV duyệt
  id          INTEGER PRIMARY KEY,
  problem_id  INTEGER NOT NULL REFERENCES problem(id),
  version     INTEGER NOT NULL,
  items_json  TEXT    NOT NULL,                      -- [{item_id, text, points}]
  max_score   REAL    NOT NULL,
  approved_at TEXT    NOT NULL,
  UNIQUE (problem_id, version)
);

CREATE TABLE problem_pair (                          -- 07: so sánh độ khó, giữ để fit lại BT
  id          INTEGER PRIMARY KEY,
  problem_a   INTEGER NOT NULL REFERENCES problem(id),
  problem_b   INTEGER NOT NULL REFERENCES problem(id),
  harder_ab   TEXT    NOT NULL CHECK (harder_ab IN ('a','b')),  -- hỏi theo thứ tự (A, B)
  harder_ba   TEXT    NOT NULL CHECK (harder_ba IN ('a','b')),  -- hỏi theo thứ tự (B, A)
  created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (problem_a < problem_b)
);

-- =========================================================== B. Học sinh & buổi học
CREATE TABLE student (
  id          INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  grade       INTEGER CHECK (grade BETWEEN 1 AND 12),
  note        TEXT,
  created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  archived_at TEXT
);

CREATE TABLE session (
  id               INTEGER PRIMARY KEY,
  student_id       INTEGER NOT NULL REFERENCES student(id),
  held_on          TEXT    NOT NULL,                 -- ngày học
  source_path      TEXT    NOT NULL,                 -- data/inbox/...
  source_kind      TEXT    NOT NULL CHECK (source_kind IN ('tex','pdf')),
  source_sha256    TEXT    NOT NULL,
  transcript_latex TEXT,                             -- .tex gốc hoặc bản 01 chép từ PDF
  knowledge_state  TEXT,                             -- 05: ≤150 từ, viết từ số liệu
  thread_id        TEXT    NOT NULL UNIQUE,          -- LangGraph thread trong checkpoints.db
  status           TEXT    NOT NULL CHECK (status IN
                     ('running','awaiting_review','committed','failed')),
  created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  committed_at     TEXT,
  UNIQUE (student_id, source_sha256)                 -- chặn nộp trùng một file
);

CREATE TABLE attempt (
  id             INTEGER PRIMARY KEY,
  session_id     INTEGER NOT NULL REFERENCES session(id),
  seq            INTEGER NOT NULL,                   -- thứ tự bài trong file
  problem_id     INTEGER NOT NULL REFERENCES problem(id),
  rubric_id      INTEGER NOT NULL REFERENCES rubric(id),
  solution_latex TEXT    NOT NULL,
  steps_json     TEXT    NOT NULL,                   -- [{idx, latex, pos}]
  flags_json     TEXT    NOT NULL DEFAULT '[]',      -- mismatch, low_match, ...
  grade_json     TEXT    NOT NULL,                   -- [{item_id, passed, evidence_latex}]
  score          REAL    NOT NULL,
  max_score      REAL    NOT NULL,
  supersedes_id  INTEGER REFERENCES attempt(id),
  created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE mistake (
  id               INTEGER PRIMARY KEY,
  attempt_id       INTEGER NOT NULL REFERENCES attempt(id),
  step_idx         INTEGER NOT NULL,                 -- bước trong bài HS (attempt.steps_json)
  code             TEXT    NOT NULL REFERENCES error_code(code),
  kc_id            INTEGER REFERENCES kc(id),        -- 03 chọn trong problem_kc của bài; NULL = lỗi trình bày chung
  description      TEXT    NOT NULL,
  evidence_latex   TEXT    NOT NULL,
  confidence       REAL    CHECK (confidence BETWEEN 0 AND 1),
  verifier_verdict TEXT    CHECK (verifier_verdict IN ('agree','disagree','wrong_code')),
  verifier_reason  TEXT,
  status           TEXT    NOT NULL CHECK (status IN ('confirmed','edited','rejected','added')),
  llm_json         TEXT,                             -- đề xuất gốc của 03; NULL khi 'added'
  teacher_note     TEXT,
  supersedes_id    INTEGER REFERENCES mistake(id),
  reviewed_at      TEXT    NOT NULL,
  created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK ((status = 'added') = (llm_json IS NULL))
);

-- =========================================================== C. Trạng thái học sinh (05 Profiler)
CREATE TABLE skill_event (                           -- lịch sử Elo, 1 dòng / (attempt, KC)
  id           INTEGER PRIMARY KEY,
  student_id   INTEGER NOT NULL REFERENCES student(id),
  kc_id        INTEGER NOT NULL REFERENCES kc(id),
  attempt_id   INTEGER NOT NULL REFERENCES attempt(id),
  outcome      INTEGER NOT NULL CHECK (outcome IN (0,1)),  -- X
  p_expected   REAL    NOT NULL,                     -- P trước cập nhật
  theta_before REAL    NOT NULL,
  theta_after  REAL    NOT NULL,
  delta        REAL    NOT NULL,                     -- δ của bài tại thời điểm đó
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE (attempt_id, kc_id)
);

CREATE TABLE skill_state (                           -- = dòng skill_event mới nhất mỗi KC
  student_id     INTEGER NOT NULL REFERENCES student(id),
  kc_id          INTEGER NOT NULL REFERENCES kc(id),
  theta          REAL    NOT NULL DEFAULT 0,
  n_attempts     INTEGER NOT NULL DEFAULT 0,
  correct_streak INTEGER NOT NULL DEFAULT 0,         -- luật ≥ 2 đúng liên tiếp
  last_seen      TEXT    NOT NULL,
  updated_at     TEXT    NOT NULL,
  PRIMARY KEY (student_id, kc_id)
);

CREATE TABLE misconception_log (                     -- chỉ lỗi có kc_id
  student_id  INTEGER NOT NULL REFERENCES student(id),
  code        TEXT    NOT NULL REFERENCES error_code(code),
  kc_id       INTEGER NOT NULL REFERENCES kc(id),
  first_seen  TEXT    NOT NULL,                      -- session.held_on
  last_seen   TEXT    NOT NULL,
  count       INTEGER NOT NULL DEFAULT 1,
  resolved_at TEXT,
  PRIMARY KEY (student_id, code, kc_id)
);

-- =========================================================== D. Đầu ra
CREATE TABLE recommendation (
  id          INTEGER PRIMARY KEY,
  student_id  INTEGER NOT NULL REFERENCES student(id),
  for_date    TEXT    NOT NULL,                      -- ngày buổi học sau
  problem_id  INTEGER NOT NULL REFERENCES problem(id),
  kc_id       INTEGER NOT NULL REFERENCES kc(id),
  bucket      TEXT    CHECK (bucket IN ('review','zpd','challenge')),  -- NULL khi GV tự thêm
  reason      TEXT,                                  -- 08: lý do 1 dòng
  status      TEXT    NOT NULL CHECK (status IN ('approved','rejected','added')),
  reviewed_at TEXT    NOT NULL,
  UNIQUE (student_id, for_date, problem_id)
);

CREATE TABLE report (
  id          INTEGER PRIMARY KEY,
  student_id  INTEGER NOT NULL REFERENCES student(id),
  month       TEXT    NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'),
  facts_json  TEXT    NOT NULL,                      -- [{fact_id, kind, value}] do SQL tính
  text_md     TEXT    NOT NULL,                      -- bản GV đã duyệt; mỗi câu kèm [fact_id]
  audit_json  TEXT    NOT NULL,                      -- từng câu: đạt / viết lại / bỏ
  approved_at TEXT    NOT NULL,
  UNIQUE (student_id, month)
);

-- =========================================================== Index + view
CREATE INDEX ix_session_student   ON session(student_id, held_on);
CREATE INDEX ix_attempt_session   ON attempt(session_id);
CREATE INDEX ix_attempt_problem   ON attempt(problem_id);
CREATE INDEX ix_mistake_attempt   ON mistake(attempt_id);
CREATE INDEX ix_problem_kc_kc     ON problem_kc(kc_id);
CREATE INDEX ix_skill_event_hist  ON skill_event(student_id, kc_id, created_at);
CREATE INDEX ix_reco_student      ON recommendation(student_id, for_date);

CREATE VIEW attempt_current AS
SELECT a.* FROM attempt a
WHERE NOT EXISTS (SELECT 1 FROM attempt b WHERE b.supersedes_id = a.id);

CREATE VIEW mistake_current AS                       -- lỗi đang có hiệu lực
SELECT m.* FROM mistake m
JOIN attempt_current a ON a.id = m.attempt_id
WHERE m.status <> 'rejected'
  AND NOT EXISTS (SELECT 1 FROM mistake n WHERE n.supersedes_id = m.id);

-- =========================================================== Seed taxonomy (§6)
INSERT INTO error_code (code, category, description) VALUES
 ('computational.final_answer',       'computational', 'Đáp số cuối sai dù các bước trước đúng'),
 ('computational.intermediate_calc',  'computational', 'Tính sai ở bước trung gian'),
 ('computational.copy_error',         'computational', 'Chép sai số hoặc biểu thức từ đề / dòng trước'),
 ('computational.propagated',         'computational', 'Sai kéo theo từ một lỗi trước đó'),
 ('conceptual.theorem_misapplied',    'conceptual',    'Dùng định lý sai hoặc khi chưa đủ điều kiện'),
 ('conceptual.misread_question',      'conceptual',    'Hiểu sai yêu cầu của đề'),
 ('conceptual.invalid_assumption',    'conceptual',    'Thêm giả thiết đề không cho'),
 ('conceptual.wrong_fact',            'conceptual',    'Dùng một tính chất / kiến thức sai'),
 ('conceptual.formula_misuse',        'conceptual',    'Dùng sai công thức'),
 ('notational.symbol',                'notational',    'Dùng sai ký hiệu'),
 ('notational.operator_swap',         'notational',    'Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)'),
 ('notational.parentheses',           'notational',    'Thiếu hoặc đặt sai ngoặc'),
 ('presentation.format',              'presentation',  'Trình bày sai quy cách'),
 ('presentation.logic_gap',           'presentation',  'Nhảy bước, thiếu mắt xích lập luận'),
 ('presentation.variable_misnamed',   'presentation',  'Tên biến không nhất quán'),
 ('presentation.units',               'presentation',  'Thiếu hoặc sai đơn vị'),
 ('presentation.missing_justification','presentation', 'Kết luận không nêu lý do'),
 ('other.unclear',                    'other',         'Không xác định được loại lỗi');
