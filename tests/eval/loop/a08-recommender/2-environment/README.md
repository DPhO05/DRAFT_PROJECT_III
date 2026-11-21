# a08 · Bước 2: Environment

## Hôm nay

- Fixture `conn` của `tests/conftest.py`: DB tạm mới cho mỗi test. Test dựng `assistant_fix.world` trên DB đó.
- 08 chỉ đọc DB: `skill_state`, lỗi lặp, bài đã làm trong cửa sổ không lặp. Không gọi model.

## Chưa có

- Task 16: `agents.trials` với `FakeLLM` rỗng, để mọi lời gọi model lỡ xảy ra đều lỗi ngay.
- Thế giới seed ngân hàng `data/dummy/bank`, thêm `skill_state` và lỗi lặp theo hồ sơ.
