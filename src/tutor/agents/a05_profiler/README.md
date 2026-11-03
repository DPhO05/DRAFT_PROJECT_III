# 05 Profiler

05 chỉ là code, không gọi LLM (C-36). Code ở `src/tutor/services/elo.py` (`profile`, `update`, `level`, `trend`) và node `profile` của G1 trong `src/tutor/graphs/session.py`.
Code ở lại `services/` vì `db/repo.py` và `services/` đều dùng `elo`, mà luật lớp cấm `db` và `services` import `agents` (`tests/test_architecture.py`).
