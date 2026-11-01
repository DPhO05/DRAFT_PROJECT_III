-- P5-T01: tìm bài bằng FTS5, bỏ dấu (C-49). unicode61 không gộp "đ" thành "d" nên view gộp trước khi vào chỉ mục.
CREATE VIRTUAL TABLE problem_fts USING fts5(statement, solution, skills, tokenize = 'unicode61 remove_diacritics 2');

CREATE VIEW problem_fts_src AS
SELECT p.id AS id,
       replace(replace(p.statement_latex, 'đ', 'd'), 'Đ', 'D') AS statement,
       replace(replace(p.solution_latex, 'đ', 'd'), 'Đ', 'D') AS solution,
       replace(replace((SELECT group_concat(k.name || ' ' || k.description, ' ') FROM kc k
                         WHERE k.id IN (SELECT kc_id FROM problem_kc WHERE problem_id = p.id)), 'đ', 'd'), 'Đ', 'D') AS skills
  FROM problem p;

CREATE TRIGGER problem_fts_ai AFTER INSERT ON problem BEGIN
  DELETE FROM problem_fts WHERE rowid = new.id;
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src WHERE id = new.id;
END;

CREATE TRIGGER problem_fts_au AFTER UPDATE OF statement_latex, solution_latex ON problem BEGIN
  DELETE FROM problem_fts WHERE rowid = new.id;
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src WHERE id = new.id;
END;

CREATE TRIGGER problem_fts_ad AFTER DELETE ON problem BEGIN
  DELETE FROM problem_fts WHERE rowid = old.id;
END;

CREATE TRIGGER problem_kc_fts_ai AFTER INSERT ON problem_kc BEGIN
  DELETE FROM problem_fts WHERE rowid = new.problem_id;
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src WHERE id = new.problem_id;
END;

CREATE TRIGGER problem_kc_fts_au AFTER UPDATE ON problem_kc BEGIN
  DELETE FROM problem_fts WHERE rowid IN (old.problem_id, new.problem_id);
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src WHERE id IN (old.problem_id, new.problem_id);
END;

CREATE TRIGGER problem_kc_fts_ad AFTER DELETE ON problem_kc BEGIN
  DELETE FROM problem_fts WHERE rowid = old.problem_id;
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src WHERE id = old.problem_id;
END;

CREATE TRIGGER kc_fts_au AFTER UPDATE OF name, description ON kc BEGIN
  DELETE FROM problem_fts WHERE rowid IN (SELECT problem_id FROM problem_kc WHERE kc_id = new.id);
  INSERT INTO problem_fts (rowid, statement, solution, skills)
    SELECT id, statement, solution, skills FROM problem_fts_src
     WHERE id IN (SELECT problem_id FROM problem_kc WHERE kc_id = new.id);
END;

INSERT INTO problem_fts (rowid, statement, solution, skills) SELECT id, statement, solution, skills FROM problem_fts_src;
