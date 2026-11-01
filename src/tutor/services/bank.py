"""Read KC / level labels and rubric v1 from a bank .tex (P5-T02)."""

from dataclasses import dataclass

from tutor.services import latex

LEVEL_DELTA = {"dễ": -0.6, "vừa": 0.0, "khó": 0.6}


@dataclass
class BankItem:
    ref: str | None
    statement: str
    solution: str
    tags: list[tuple[int, int, str]]  # (kc_id, step_idx, evidence_latex)
    delta: float | None
    rubric_items: list[dict]
    needs: list[str]  # subset of ["kc", "level"]: labels the teacher must still pick
    unknown_label: bool  # a kc_du_kien code is not in the catalog
    invalid: str | None


def rubric_v1(paragraphs: list[str]) -> list[dict]:
    """One item per paragraph, the final "Đáp số" paragraph merged into the item before it."""
    texts = list(paragraphs)
    if len(texts) > 1:
        texts[-2:] = [f"{texts[-2]}\n\n{texts[-1]}"]
    return [{"item_id": f"r{i}", "text": t, "points": 1} for i, t in enumerate(texts, 1)]


def level_delta(level: str | None) -> float | None:
    if level is None:
        return None
    if level not in LEVEL_DELTA:
        raise ValueError(f"unknown level {level!r}")
    return LEVEL_DELTA[level]


def rubric_items(raw: object) -> list[dict]:
    """Teacher-edited [{text, points}] → items with item_id r1…rn."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("rubric needs at least one item")
    out = []
    for i, it in enumerate(raw, 1):
        text, points = (it.get("text"), it.get("points")) if isinstance(it, dict) else (None, None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"item {i}: text is empty")
        if isinstance(points, bool) or not isinstance(points, int | float) or points <= 0:
            raise ValueError(f"item {i}: points must be a number > 0")
        out.append({"item_id": f"r{i}", "text": text, "points": points})
    return out


def read_bank(tex: str, kc_ids: dict[str, int]) -> list[BankItem]:
    out, seen = [], set()
    for p in latex.split_problems(tex):
        sol = p.solutions[0] if p.solutions else None
        steps = latex.split_steps(tex, sol.pos, sol.pos_end, by="paragraph") if sol else []
        if p.ref is None:
            invalid = "thiếu mã bài"
        elif not steps:
            invalid = "thiếu lời giải"
        elif p.ref in seen:
            invalid = "trùng mã trong file"
        else:
            invalid = None
        seen.add(p.ref)
        codes = [c.strip() for c in p.meta.get("kc_du_kien", "").split(",") if c.strip()]
        tags = []
        for k, c in enumerate(codes):
            if c in kc_ids and steps:
                # contract §5: k-th expected KC (0-based) tagged at step min(k+1, n_steps)
                j = min(k + 1, len(steps))
                tags.append((kc_ids[c], j, steps[j - 1].latex))
        d = p.meta.get("do_kho_du_kien", "")
        delta = round((int(d) - 3) * 0.6, 2) if d in ("1", "2", "3", "4", "5") else None
        needs = [n for n, missing in (("kc", not any(c in kc_ids for c in codes)), ("level", delta is None)) if missing]
        out.append(
            BankItem(
                ref=p.ref,
                statement=p.statement,
                solution=tex[sol.pos : sol.pos_end].strip() if sol else "",
                tags=tags,
                delta=delta,
                rubric_items=rubric_v1([s.latex for s in steps]),
                needs=needs,
                unknown_label=any(c not in kc_ids for c in codes),
                invalid=invalid,
            )
        )
    return out
