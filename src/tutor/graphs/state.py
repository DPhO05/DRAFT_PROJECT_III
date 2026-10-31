"""Graph states: plain JSON-able dicts so checkpoints stay readable (agent outputs stored as model_dump())."""

import operator
from typing import Annotated, TypedDict


class SessionState(TypedDict, total=False):
    session_id: int
    student_id: int
    held_on: str
    source_path: str  # relative to the data dir: inbox/<file>
    source_kind: str
    transcript: str  # the .tex as submitted (FR1: never corrected)
    ingest: dict  # agents.ingest.IngestResult; apply_match fills chosen refs and resolves flags
    rubric_drafts: dict  # str(seq) -> 02 draft {items, max_score, alt_methods} | None
    match_decisions: object  # last answers at confirm_match: {str(seq): {problem_ref?, rubric_items?, note?}}
    approved_rubrics: dict  # str(seq) -> {items, max_score}: approved at step 3, written by commit ② (C-16)
    lanes: Annotated[list, operator.add]  # one per attempt: {seq, problem_id, rubric, grade, diagnosis, mistakes}
    proposals: list  # mistake cards in review order (P2-T04)
    review: dict  # answers at gate_review: {cards: {pid: Decision}, review_seconds} (contract §7, C-09)
    profile: dict  # 05: elo.profile result for this session over `profile_prior`; commit ② writes exactly it
    profile_prior: dict  # the repo.profile_prior 05 used; a different one at confirm_commit sends the graph back to 05
    preview: dict  # the tutor-facing preview of `profile` (P4-T05)
    receipt: dict  # commit ②: rows added + backup file name
    committed: bool  # runner marks the thread committed


class LaneState(TypedDict, total=False):
    """One problem's 02 → 03 → 04 subgraph. Only `lanes` flows back into SessionState."""

    lane: dict  # {seq, problem_id, steps, rubric, student_id, session_id}
    lane_grade: dict
    lane_diag: dict
    lanes: Annotated[list, operator.add]
