-- P7-T01 (C-44): a report covers a day, a week or a month. Old rows were months: month 'yyyy-mm' becomes 'yyyy-mm-01'.
CREATE TABLE report_new (
  id           INTEGER PRIMARY KEY,
  student_id   INTEGER NOT NULL REFERENCES student(id),
  period_kind  TEXT    NOT NULL CHECK (period_kind IN ('day','week','month')),
  period_start TEXT    NOT NULL,
  facts_json   TEXT    NOT NULL,
  text_md      TEXT    NOT NULL,
  audit_json   TEXT    NOT NULL,
  approved_at  TEXT    NOT NULL,
  UNIQUE (student_id, period_kind, period_start)
);

INSERT INTO report_new (id, student_id, period_kind, period_start, facts_json, text_md, audit_json, approved_at)
SELECT id, student_id, 'month', month || '-01', facts_json, text_md, audit_json, approved_at
  FROM report;

DROP TABLE report;
ALTER TABLE report_new RENAME TO report;
