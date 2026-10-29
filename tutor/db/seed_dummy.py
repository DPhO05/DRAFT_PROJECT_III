"""Load data/dummy/bank into tutor.db for dev / test only (P1-T05, C-32): tags and δ come from the author's labels."""

from pathlib import Path

from tutor.db import repo
from tutor.services import latex


def seed(conn, bank_dir: Path) -> dict:
    kcs, pre = repo.read_catalog(
        (bank_dir / "kc.csv").read_text("utf-8-sig"), (bank_dir / "kc_prereq.csv").read_text("utf-8-sig")
    )
    repo.import_catalog(conn, kcs, pre, apply=True)
    kc_id = {k["code"]: k["id"] for k in repo.list_kc(conn)}
    added = 0
    for f in sorted(bank_dir.glob("*.tex")):
        src = f.read_text(encoding="utf-8")
        for p in latex.split_problems(src):
            sol = p.solutions[0]
            steps = latex.split_steps(src, sol.pos, sol.pos_end, by="paragraph")
            codes = [c.strip() for c in p.meta.get("kc_du_kien", "").split(",") if c.strip()]
            # contract §5: k-th expected KC (0-based) tagged at step min(k+1, n_steps)
            tags = [
                (kc_id[c], min(k + 1, len(steps)), steps[min(k + 1, len(steps)) - 1].latex) for k, c in enumerate(codes)
            ]
            # rubric v1: one item per paragraph, the final "Đáp số" paragraph merged into the last item
            texts = [s.latex for s in steps[:-1]]
            texts[-1] += "\n\n" + steps[-1].latex
            items = [{"item_id": f"r{i}", "text": t, "points": 1} for i, t in enumerate(texts, 1)]
            diff = p.meta.get("do_kho_du_kien")
            pid = repo.add_bank_problem(
                conn,
                ref=p.ref,
                statement=p.statement,
                solution=src[sol.pos : sol.pos_end].strip(),
                source=f"dummy:{f.name}",
                delta=round((int(diff) - 3) * 0.6, 2) if diff else None,
                tags=tags,
                rubric_items=items,
            )
            added += pid is not None
    return {"problems_added": added, **repo.row_counts(conn)}
