-- P6-T07 (C-45): a sheet keeps its order (position) and a date can hold a new sheet beside a rejected one.
-- UNIQUE moves from the table to the live rows only.
CREATE TABLE recommendation_new (
  id          INTEGER PRIMARY KEY,
  student_id  INTEGER NOT NULL REFERENCES student(id),
  for_date    TEXT    NOT NULL,
  problem_id  INTEGER NOT NULL REFERENCES problem(id),
  kc_id       INTEGER NOT NULL REFERENCES kc(id),
  bucket      TEXT    CHECK (bucket IN ('review','zpd','challenge')),
  reason      TEXT,
  status      TEXT    NOT NULL CHECK (status IN ('approved','rejected','added')),
  reviewed_at TEXT    NOT NULL,
  position    INTEGER
);

INSERT INTO recommendation_new (id, student_id, for_date, problem_id, kc_id, bucket, reason, status, reviewed_at, position)
SELECT id, student_id, for_date, problem_id, kc_id, bucket, reason, status, reviewed_at,
       row_number() OVER (PARTITION BY student_id, for_date ORDER BY id)
  FROM recommendation;

DROP TABLE recommendation;
ALTER TABLE recommendation_new RENAME TO recommendation;

CREATE INDEX ix_reco_student ON recommendation(student_id, for_date);
CREATE UNIQUE INDEX ux_reco_live ON recommendation(student_id, for_date, problem_id) WHERE status <> 'rejected';
