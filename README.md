# DRAFT_PROJECT_III

Bản nháp giao diện **app gia sư** của PROJECT_III — trợ lý chấm bài và theo dõi tiến bộ cho gia sư Toán dạy từng học sinh.
Dữ liệu giả, chưa nối backend; dùng để xem và góp ý trước khi build thật.

## Mở

Mở `app-user.html` bằng trình duyệt (Chrome / Edge / Safari). Cần mạng để tải font và MathJax (công thức).

## 4 tab

| Tab | Việc |
|---|---|
| Trợ lý | Chat với trợ lý: chấm bài học sinh (duyệt từng lỗi), tìm bài theo mã hoặc mô tả, soạn phiếu bài tập, hỏi đáp về học sinh |
| Học sinh | Tiến bộ từng học sinh bằng lời (vững / đang hình thành / chưa vững), lỗi hay lặp lại, các buổi đã chấm |
| Báo cáo | Báo cáo theo ngày / tuần / tháng, sửa câu, duyệt, tải PDF |
| Ngân hàng bài | Xem bài theo chủ đề / lớp / mức, nạp file `.tex` bài mới |

Menu ⚙ góc trên: sao lưu, danh mục kỹ năng và loại lỗi, cài đặt, chi phí tháng.

## Thư mục

| Đường dẫn | Nội dung |
|---|---|
| `app-user.html` | Bản build, mở trực tiếp |
| `app-user/*.js`, `app.css`, `shell.html` | Mã nguồn giao diện |
| `app-user/data.js` | Dữ liệu giả (đã sinh sẵn) |
| `app-user/build.py` | Ghép mã nguồn thành `app-user.html`: `python3 app-user/build.py` (Python ≥ 3.10) |
| `app-user/check.py` | Robot kiểm tra (Playwright): `python3 app-user/check.py <thư-mục-ảnh>` |

`build.py --data` (sinh lại `data.js`) chỉ chạy trong repo dự án chính, vì cần dữ liệu gốc `src/mock.js`.
