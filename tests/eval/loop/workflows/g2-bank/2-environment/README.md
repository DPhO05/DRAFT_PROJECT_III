# G2 · Bước 2: Environment

- Fixture `paths` và `conn` của `tests/conftest.py`: thư mục dữ liệu và DB tạm mới cho mỗi test.
- Fixture `no_real_llm` xoá khoá API và cài `FakeLLM`, dù G2 không gọi model.
- Check "sạch, không rò": mỗi test có `tmp_path` riêng.
