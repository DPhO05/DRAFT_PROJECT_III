# G4 · Bước 2: Environment

- Fixture của `tests/conftest.py`: thư mục dữ liệu và DB tạm mới cho mỗi test. `no_real_llm` chặn mọi lời gọi API thật.
- Check "sạch, không rò": mỗi test có `tmp_path` riêng.
