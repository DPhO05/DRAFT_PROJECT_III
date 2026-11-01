"""/api/assistant: the writes agent 00's tools may start. Same functions as the matching routes (C-38)."""

from contextlib import closing
from datetime import date

from tutor.agents.tools import Starters
from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs import bank, session, worksheet
from tutor.graphs.runner import Runner, ThreadNotFound


def _dm(day: str) -> str:
    return f"{date.fromisoformat(day):%d/%m}"


def make_starters(paths: DataPaths, runner: Runner) -> Starters:
    """start_* wrappers around `runner.start`; a domain error becomes a ValueError with words for the tutor (R20)."""

    def start_grading(student_id: int, file: str, held_on: str) -> dict:
        try:
            return session.submit(paths, runner, student_id=student_id, held_on=held_on, rel_path=file)
        except repo.DuplicateSubmission as e:
            with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
                done = repo.session_detail(conn, e.session_id)["held_on"]
            raise ValueError(f"Bài này đã nộp cho {student_code(student_id)} rồi (buổi {_dm(done)}).") from e
        except repo.DateOrderLocked as e:
            raise ValueError(f"Ngày học sớm hơn buổi đã lưu {_dm(e.last_committed)}, không chấm được.") from e
        except repo.NotFound as e:
            raise ValueError(f"Không có học sinh {student_code(student_id)}") from e

    def propose_worksheet(
        student_id: int, for_date: str, items: list[dict], note: str | None, warnings: list[str]
    ) -> dict:
        try:
            return worksheet.propose(
                paths, runner, student_id=student_id, for_date=for_date, items=items, note=note, warnings=warnings
            )
        except repo.NotFound as e:
            raise ValueError(f"Không có học sinh {student_code(student_id)}") from e

    def add_to_worksheet(thread_id: str, refs: list[str]) -> dict:
        try:
            return worksheet.add_refs(paths, runner, thread_id, refs)
        except ThreadNotFound as e:
            raise ValueError("Không có phiếu nháp để thêm bài") from e

    return Starters(
        start_grading=start_grading,
        start_bank_import=lambda file: bank.start_import(paths, runner, file=file),
        propose_worksheet=propose_worksheet,
        add_to_worksheet=add_to_worksheet,
    )
