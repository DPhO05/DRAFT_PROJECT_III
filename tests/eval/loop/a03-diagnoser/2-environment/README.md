# a03 · Bước 2: Environment

Môi trường của G1, dựng trong `run.evaluate`. Xem `tests/eval/loop/workflows/g1-session/2-environment/README.md`.

- Mỗi file bài có một học sinh mới (`run._one`), nên lịch sử lỗi của học sinh rỗng.
- Trong production 03 còn nhận 5 lỗi gần nhất của học sinh. Trong eval danh sách này rỗng. Đây là một chỗ eval khác
  production (design mục 5.4).
- Bảng mã lỗi là các mã đang bật trong DB mới của run (`repo.error_codes`). Đổi bảng mã thì `prompt_version` của 03
  đổi (`diagnoser.prompt_version`).
- Nhãn không vào thư mục dữ liệu của trial: `tests/eval/test_harness.py::test_labels_never_enter_the_trial_data`.
