-- C-10: lớp của KC (8 | 9), lấy từ kc.csv
ALTER TABLE kc ADD COLUMN lop INTEGER CHECK (lop BETWEEN 1 AND 12);
-- C-09: thời gian GV duyệt buổi (giây), cộng dồn qua Tạm dừng
ALTER TABLE session ADD COLUMN review_seconds INTEGER CHECK (review_seconds >= 0);
