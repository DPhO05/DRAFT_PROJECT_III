"""Load data/dummy/bank into tutor.db for dev / test only (P1-T05, C-32): tags and δ come from the author's labels."""

from pathlib import Path

from tutor.db import repo
from tutor.services import bank


def seed(conn, bank_dir: Path) -> dict:
    kcs, pre = repo.read_catalog(
        (bank_dir / "kc.csv").read_text("utf-8-sig"), (bank_dir / "kc_prereq.csv").read_text("utf-8-sig")
    )
    repo.import_catalog(conn, kcs, pre, apply=True)
    kc_id = {k["code"]: k["id"] for k in repo.list_kc(conn)}
    added = 0
    for f in sorted(bank_dir.glob("*.tex")):
        src = f.read_text(encoding="utf-8")
        for it in bank.read_bank(src, kc_id):
            if it.invalid:
                continue
            pid = repo.add_bank_problem(
                conn,
                ref=it.ref,
                statement=it.statement,
                solution=it.solution,
                source=f"dummy:{f.name}",
                delta=it.delta,
                tags=it.tags,
                rubric_items=it.rubric_items,
            )
            added += pid is not None
    return {"problems_added": added, **repo.row_counts(conn)}
