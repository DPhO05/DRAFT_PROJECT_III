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
    ingest: dict  # agents.a01_ingest.ingest.IngestResult; apply_match fills chosen refs and resolves flags
    rubric_drafts: dict  # str(seq) -> 02 draft {items, max_score, alt_methods} | None
    match_decisions: object  # last answers at confirm_match: {str(seq): {problem_ref?, rubric_items?, note?}}
    approved_rubrics: dict  # str(seq) -> {items, max_score}: approved at step 3, written by commit ② (C-16)
    lanes: Annotated[list, operator.add]  # one per attempt: {seq, problem_id, rubric, grade, diagnosis, mistakes}
    proposals: list  # mistake cards in review order (P2-T04)
    review: dict  # answers at gate_review: {cards: {pid: Decision}, review_seconds} (contract §7, C-09)
    profile: dict  # 05: elo.profile result for this session over `profile_prior`; commit ② writes exactly it
    profile_prior: dict  # the repo.profile_prior 05 used; a different one at confirm_commit sends the graph back to 05
    preview: dict  # the tutor-facing preview of `profile` (P4-T06)
    receipt: dict  # commit ②: rows added + backup file name
    committed: bool  # runner marks the thread committed


class LaneState(TypedDict, total=False):
    """One problem's 02 → 03 → 04 subgraph. Only `lanes` flows back into SessionState."""

    lane: dict  # {seq, problem_id, steps, rubric, student_id, session_id}
    lane_grade: dict
    lane_diag: dict
    lanes: Annotated[list, operator.add]


class BankState(TypedDict, total=False):
    file: str  # relative to the data dir: inbox/bank/<name>.tex
    items: list[dict]  # one per problem: ref, statement_latex, solution_latex, tags, delta, rubric_items, needs, ...
    decisions: dict  # answers at gate_confirm_import: {items: {ref: {kc_ids?, level?, rubric_items?}}}
    receipt: dict  # commit: {added, skipped_existing}
    committed: bool  # runner marks the thread committed


class WorksheetState(TypedDict, total=False):
    student_id: int
    for_date: str
    refs: list[str]  # the proposal, upper case; a saved decision's refs replace it
    reasons: dict  # ref -> {bucket, reason}; a ref missing here was added by the teacher
    warnings: list[str]  # from rank_problems
    note: str | None
    decisions: dict | None  # answers at gate_worksheet: {for_date, refs, replace}; None = the proposal as it is
    receipt: dict  # commit: {for_date, n_problems, replaced}
    committed: bool  # runner marks the thread committed


class ReportState(TypedDict, total=False):
    student_id: int
    period_kind: str  # day / week / month (C-44)
    period_start: str
    today: str  # H7: start's day; write's Toolbox uses it, never the wall clock
    draft: dict  # reporter.run: facts, insights, low, dates, sentences, audit (the writer's rows); write adds
    # plan facts and dates, sessions [{text, facts}], plan [{text, facts}], plan_title
    decisions: dict | None  # answers at gate_report: {sentences: [{text, facts}], plan?: [..]}; None = the draft's
    receipt: dict  # commit: {report_id, approved_at}
    committed: bool  # runner marks the thread committed
