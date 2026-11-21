# a08 · Bước 2: Environment

## Dùng chung

- `agents.trials` dựng thế giới `assistant_fix.world`: ngân hàng `data/dummy/bank` và vài buổi học. `components.evaluate_08` đưa vào một
  `FakeLLM` không có handler, nên mọi lời gọi model lỡ xảy ra đều lỗi ngay.

## Riêng cho 08

`components._rank_08` dựng một hồ sơ:

- Thêm một học sinh mới `Eval <id>` với lớp của hồ sơ.
- Đặt `theta` cho từng kỹ năng, ghi lỗi lặp vào `misconception_log`, ghi bài đã làm với ngày `today` trừ `days_ago`.
- Gọi `select.rank_problems` với `config.defaults()["reco"]`. Hàm này chỉ đọc DB, không gọi model.
- Với câu tìm, `Toolbox.run("search_problems", ...)` chạy trên DB của run 1 qua kết nối chỉ đọc.

## Check "sạch, không rò"

- Mỗi hồ sơ có học sinh riêng, nên hồ sơ này không ảnh hưởng hồ sơ khác.
- Nhãn `relevant` và `must_not` không vào DB, chỉ vào grader.
- `tests/eval/test_components.py::test_08_runs_without_any_model_call`.
- Fixture `no_real_llm` (autouse) chặn mọi lời gọi API thật trong test.
