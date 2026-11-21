# G1 · Bước 2: Environment

`run.evaluate` dựng một thế giới mới cho mỗi run. Đây là vòng riêng của G1, cùng ý với `agents.trials`.

- Thư mục `work/run<k>/data`: `tutor.db` mới (`repo.init_db`), seed ngân hàng `data/dummy/bank`.
- File bài chép vào `inbox` của run. Nhãn ở ngoài thư mục dữ liệu.
- Mỗi file một học sinh mới (`run._one`), nên lịch sử lỗi rỗng. Buổi học ghi ngày 2026-10-20.
- `Runner` thật với graph G1 (`session.build`), như app. Backend dựng một lần ở run 1.
- Cổng `gate_confirm_match` được trả lời theo nhãn (`run._answer`): cờ `low_match` nhận mã đúng; cờ `no_rubric` nhận rubric
  nháp của 02.

## Check "sạch, không rò"

- `tests/eval/test_harness.py::test_each_run_starts_from_a_new_world`.
- `tests/eval/test_harness.py::test_labels_never_enter_the_trial_data`: không file nào trong thư mục dữ liệu của trial chứa nhãn.
- Giới hạn: các file trong một run dùng chung một DB. Mỗi file có học sinh riêng, nên lỗi của file này không vào lịch
  sử của file khác.
