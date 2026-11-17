# Hướng dẫn Trợ lý gia sư Toán

Có hai thư mục, đừng nhầm:

- `GiaSuToan-app` là thư mục chương trình, lấy từ file zip.
- `GiaSuToan` là thư mục dữ liệu, nằm trong thư mục cá nhân của thầy/cô. App tự tạo thư mục này lần đầu.
- Trong Finder, bấm ⇧⌘H để mở thư mục cá nhân.

## 1. Cài đặt lần đầu

Cần Mac chip Apple (M1 trở lên).

1. Giải nén `GiaSuToan-app.zip`. Kéo thư mục `GiaSuToan-app` vào thư mục cá nhân (bấm ⇧⌘H trong Finder). Đừng đặt vào Tài liệu. macOS bảo vệ thư mục đó, nên Terminal sẽ hỏi quyền truy cập.
2. Bấm đúp file `Mo-tro-ly.command` trong thư mục đó. Cửa sổ Terminal mở ra.
3. Lần đầu máy cần mạng và chờ vài phút. Đừng đóng cửa sổ Terminal.
4. Trình duyệt tự mở app. Nếu không, gõ `http://127.0.0.1:8000/` vào thanh địa chỉ.
5. Bấm chuột phải vào `Mo-tro-ly.command`, chọn **Tạo bí danh** (Make Alias). Kéo bí danh ra Desktop hoặc Dock để lần sau bấm đúp ở đó.
6. Bấm ⚙ ở góc trên bên phải, chọn **Cài đặt**. Dán khoá người cài gửi vào ô **Khoá OpenAI**, rồi bấm **Lưu cài đặt**. Nếu app ghi tên nhà cung cấp khác, dán vào ô đó.
7. Hỏi trợ lý một câu để thử. Nếu thấy "Trợ lý chưa có khoá API" hoặc "Khoá API sai, hết hạn, chưa có hoặc tài khoản hết hạn mức", bấm **Mở Cài đặt** và làm lại bước 6.

Nếu macOS không cho mở file, mở Cài đặt hệ thống › Quyền riêng tư & Bảo mật, kéo xuống rồi bấm **Vẫn mở**. Nhập mật khẩu máy nếu được hỏi.

Nếu Terminal hiện lỗi, chụp màn hình gửi người cài.

## 2. Thêm học sinh

1. Mở tab **Học sinh**, bấm **+ Thêm học sinh**.
2. Ở ô **Họ và tên**, gõ đủ họ và tên, ít nhất 2 chữ. Một chữ thì app không nhận.
3. Ở ô **Lớp**, chọn lớp của em, 8 hoặc 9. Trợ lý dùng lớp này để chấm bài và soạn phiếu.
4. Bấm **Thêm học sinh**.
5. Khi hỏi trợ lý về một em, gõ `@` rồi chọn em trong danh sách, hoặc gõ đủ họ và tên.
6. Họ và tên đầy đủ được thay bằng mã của em trước khi gửi đi. Tên gọi một chữ, như `Lan`, được gửi đúng như đã gõ.

## 3. Chấm bài

1. Chép file bài làm vào `GiaSuToan/inbox`. Trợ lý chỉ chấm file LaTeX đánh máy, đuôi `.tex`.
2. Mỗi bài làm của em nằm giữa `\begin{problem}[mã bài]` và `\end{problem}`. Ví dụ:

   ```
   \begin{problem}[8DS-HDT-001]
   $(x + 3)^2 = x^2 + 6x + 9$
   Đáp số: $x^2 + 6x + 9$
   \end{problem}
   ```

3. File không có `\begin{problem}` bị từ chối ngay. File cũng phải lưu dạng UTF-8.
4. Nên đặt tên file `hsNN-yyyy-mm-dd.tex`, ví dụ `hs01-2026-11-03.tex`. `NN` là số thứ tự của em: em thêm đầu tiên là `01`, em thứ hai là `02`.
5. Tên khác cũng được. Trợ lý sẽ hỏi em nào, ngày nào.
6. Mở tab **Trợ lý**, bấm 📎, bấm **Chọn** cạnh file, rồi bấm **Gửi**.
7. Nếu trợ lý hỏi em và ngày học, chọn xong bấm **Chấm bài này**.
8. Nếu bài làm không ghi mã bài, chọn bài đúng rồi bấm **Đúng bài này**. Muốn bỏ bài đó, bấm **Bỏ bài này, không chấm**.
9. Với mỗi lỗi trợ lý tìm ra, bấm **Đúng**, **Sửa** hoặc **Bỏ**.
10. Đọc phần **Xem trước tiến bộ**, rồi bấm **Lưu kết quả**. Chưa bấm thì chưa có gì được lưu. App tự sao lưu trước khi lưu.
11. Nộp nhầm file: bấm **Huỷ buổi chấm** trên thẻ chấm bài, trước khi bấm **Lưu kết quả**. Bài làm và các lỗi đã duyệt bị bỏ. Nộp lại file đó được.

## 4. Soạn phiếu

1. Trong tab **Trợ lý**, gõ yêu cầu. Ví dụ: `Gợi ý 6 bài cho @tên em buổi thứ Bảy`. Gõ `@` để chọn em.
2. Khung **Phiếu nháp** hiện ra. Đổi **Buổi học** nếu cần.
3. Dùng ↑ và ↓ để đổi thứ tự bài. Dùng × để bỏ bài. Gõ mã bài vào ô rồi bấm **Thêm** để thêm bài.
4. Bấm **Tạo phiếu**. Chưa bấm thì chưa lưu gì.
5. Bấm **Tải .tex** hoặc **In PDF**.
6. Không dùng bản nháp nữa thì bấm **Bỏ phiếu nháp**.
7. Sau khi lưu kết quả chấm, bấm **Soạn phiếu buổi sau** để soạn phiếu tiếp.

## 5. Báo cáo theo kỳ

1. Mở tab **Báo cáo**.
2. Chọn em, chọn kỳ **Ngày**, **Tuần** hoặc **Tháng**, rồi chọn buổi, tuần hoặc tháng cụ thể.
3. Bấm **Tạo báo cáo**. Chờ bản nháp hiện ở mục **Bản nháp chờ duyệt**.
4. Câu gạch chân vàng cần xem lại. Bấm **Sửa** hoặc **Bỏ** ở câu đó. Bấm **+ Thêm câu** để thêm.
5. Bấm **Duyệt báo cáo**. Chưa bấm thì chưa lưu vào hồ sơ. Mỗi kỳ của một em chỉ duyệt một lần.
6. Sau khi duyệt, bấm **Tải PDF** để lấy bản PDF.
7. Không dùng bản nháp nữa thì bấm **Bỏ bản nháp**.

## 6. Nạp ngân hàng bài

1. Bộ bài mẫu có sẵn trong `GiaSuToan-app/data/dummy/bank` và `GiaSuToan-app/data/dummy/bank-mo-rong`. Chép các file `.tex` trong hai thư mục đó vào `GiaSuToan/inbox/bank`, rồi làm tiếp từ bước 10. Mỗi file nạp riêng: với từng file, bấm **Nạp bài mới**, **Đọc file**, rồi **Lưu vào ngân hàng**.
2. Soạn bài trong file `.tex`. Mỗi bài có dạng sau:

   ```
   % Hằng đẳng thức đáng nhớ, lớp 8
   \begin{problem}[8DS-HDT-001]
   % lop: 8
   % kc_du_kien: 8DS-HDT-01, 8DS-HDT-02
   % do_kho_du_kien: 1
   Khai triển $(x + 3)^2$.

   \begin{solution}
   Áp dụng bình phương của một tổng: $(x + 3)^2 = x^2 + 6x + 9$.

   Đáp số: $\boxed{x^2 + 6x + 9}$
   \end{solution}
   \end{problem}
   ```

3. Dòng đầu file bắt đầu bằng `%` là tên bộ bài, hiện trong danh sách.
4. Mã bài (`8DS-HDT-001`) không dấu, không trùng, không đổi và không dùng lại.
5. Mỗi bước lời giải là một đoạn. Các bước cách nhau một dòng trống. Dòng cuối ghi `Đáp số:`.
6. `kc_du_kien` là mã kỹ năng. Tra mã trong file `GiaSuToan-app/data/dummy/bank/kc.csv`. Cột đầu là mã, cột hai là tên kỹ năng.
7. `do_kho_du_kien` là số từ 1 đến 5.
8. Bài thiếu mã bài hoặc thiếu lời giải bị bỏ qua.
9. Chép file vào `GiaSuToan/inbox/bank`.
10. Mở tab **Ngân hàng bài**, bấm **Nạp bài mới**, rồi bấm **Đọc file**.
11. Bài có nhãn kỹ năng và mức thì đã sẵn sàng. Bài không nhãn thì chọn kỹ năng, và mức nếu thiếu, ở bước xem trước. Để trống mức thì tính là mức vừa.
12. Khi hết bài cần chọn, bấm **Lưu vào ngân hàng**.

## 7. Sao lưu và khôi phục

1. App tự sao lưu trước mỗi lần bấm **Lưu kết quả**.
2. Muốn sao lưu thêm: bấm ⚙, chọn **Sao lưu**, rồi bấm **Sao lưu ngay**.
3. Muốn quay về một bản: bấm ⚙, chọn **Sao lưu**, bấm **Khôi phục** ở dòng đó, rồi bấm **Khôi phục** để xác nhận. Dữ liệu quay về đúng lúc của bản đó. Bản hiện tại được sao lưu trước.
4. Nếu app báo còn việc chưa xong, bấm **Bỏ các việc này rồi khôi phục**. Phần đã làm dở trong các việc đó sẽ mất.
5. Muốn có bản sao đủ ra ổ khác: tắt app, rồi chép cả thư mục `GiaSuToan`.
6. Thư mục `GiaSuToan` có file khoá `.env` chứa khoá API. Hãy giữ bản chép ở nơi riêng tư và đừng gửi cho ai.

## 8. Tắt app

- Đóng cửa sổ Terminal. Nếu Terminal hỏi có kết thúc không, chọn đồng ý.
- Đóng cửa sổ trình duyệt thì app vẫn chạy.

## 9. Cập nhật

1. Ở đầu tab **Trợ lý**, mục **Việc đang chờ thầy/cô** không được còn việc nào. Duyệt hoặc bỏ hết các việc đang chờ.
2. Đóng cửa sổ Terminal để tắt app.
3. Đừng xoá bản cũ. Đổi tên thư mục `GiaSuToan-app` thành `GiaSuToan-app-cu` và để nguyên đó. Đây là đường lùi.
4. Giải nén bản mới, đặt thư mục `GiaSuToan-app` mới vào đúng chỗ cũ.
5. Giữ nguyên thư mục `GiaSuToan`. Dữ liệu và khoá nằm ở đó.
6. Bấm đúp lại `Mo-tro-ly.command`. Nếu macOS chặn, làm lại cách ở mục 1.
7. Lần đầu sau cập nhật, chờ vài phút và cần mạng.
8. App tự sao lưu trước. Các cuộc trò chuyện của bản mới nằm trong file riêng trong `GiaSuToan`, nên bản cũ vẫn mở được dữ liệu.
9. Nếu bản mới trục trặc: đóng cửa sổ Terminal. Đổi tên thư mục `GiaSuToan-app` thành `GiaSuToan-app-hong`, đổi `GiaSuToan-app-cu` lại thành `GiaSuToan-app`, rồi bấm đúp `Mo-tro-ly.command` như cũ. Bản cũ vẫn mở được các cuộc trò chuyện và phiếu tạo bằng bản mới. Chỉ các thẻ xin duyệt của bản mới không hiện, và những việc đang chờ duyệt trong đó không làm tiếp được. Hãy duyệt hoặc bỏ hết trước khi lùi.
10. Dùng bản mới ổn vài tuần thì mới xoá `GiaSuToan-app-cu`.

## 10. Dành cho người cài

Tạo gói zip từ thư mục dự án, sau khi đã commit:

```
git archive --format=zip --prefix=GiaSuToan-app/ -o ~/Desktop/GiaSuToan-app.zip HEAD \
  Mo-tro-ly.command HUONG-DAN.md pyproject.toml uv.lock .python-version src app \
  data/dummy/bank data/dummy/bank-mo-rong
unzip -l ~/Desktop/GiaSuToan-app.zip
```

- Cần Mac chip Apple (M1 trở lên).
- Mặc định mọi agent chạy trên `openai:gpt-5.6-sol`. Muốn dùng model khác, thêm khối `models` vào `GiaSuToan/settings.json`, khoá từ `00` đến `04` và `09`. Ví dụ: `{"models": {"00": "openai:gpt-5.6-sol"}}`.
- Muốn thử hoặc trình diễn, giải nén zip rồi chạy từ `GiaSuToan-app`. Đừng bấm đúp `Mo-tro-ly.command` trong thư mục dự án, vì file `.env` của dự án sẽ thắng khoá đã lưu trong **Cài đặt**.
- Lần đầu launcher cài `uv`, Python 3.12 và thư viện, nên máy cần mạng.
- Launcher đặt dữ liệu ở `~/GiaSuToan`. Biến `TUTOR_DATA` đổi được chỗ này.
- Khoá lấy theo thứ tự: biến môi trường của shell, rồi file `.env` trong thư mục đang chạy app, rồi file `.env` trong thư mục dữ liệu.
- Với launcher, thư mục đang chạy app là `GiaSuToan-app`.
- Hai nguồn đầu thắng khoá lưu trong **Cài đặt**. Trên máy gia sư sạch, hai nguồn đó không có.
- Khi app không mở được, đóng app rồi khôi phục bằng lệnh. Tên bản sao lưu xem trong `~/GiaSuToan/backup`:

```
cd ~/GiaSuToan-app
TUTOR_DATA="$HOME/GiaSuToan" uv run --frozen --no-dev tutor restore tutor-2026-10-20-093000.db
```

- Thêm `--drop-unfinished` để bỏ các việc chưa xong. Phần làm dở trong đó sẽ mất.
