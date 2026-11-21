# a08 · Bước 4: Graders

## Hôm nay

- Grader là `assert` trong `tests/services/test_select.py`.
- Mức: outcome và component có, trong các `assert` đó. Trajectory không áp dụng: một hàm, không có bước trung gian.

## Chưa có

- Task 16: `passed_08`: đủ n bài hoặc có cảnh báo, không bài nào trong `must_not`.
- Task 16: `score_08`: `p_at_n`, `recall_at_n`, `must_not_hits`.
- Dùng P@n và recall@n vì phiếu là một tập bài. Thứ tự trên phiếu là thứ tự nhóm, nên MRR không hợp (design mục
  5.8).
- Check "khớp với người chấm": nhãn liên quan cần chủ dự án duyệt trước khi tin số.
