"""Check a bank folder: kc.csv / kc_prereq.csv integrity and every *.tex against the bank conventions.

usage: python bankcheck.py <folder> [--min N] [--only file.tex ...]
Exit 1 on any error. Test-only labels checked: % kc_du_kien:, % do_kho_du_kien:
"""
import csv
import glob
import os
import re
import sys
from collections import Counter

from pylatexenc import macrospec
from pylatexenc.latexwalker import LatexCommentNode, LatexEnvironmentNode, LatexWalker, get_default_latex_context_db

args = sys.argv[1:]
folder = args[0]
min_n = int(args[args.index("--min") + 1]) if "--min" in args else 1
only = args[args.index("--only") + 1:] if "--only" in args else None
errors, warns = [], []

# ---------------------------------------------------------------- CSV
kc = list(csv.DictReader(open(os.path.join(folder, "kc.csv"), encoding="utf-8-sig")))
codes = [r["code"] for r in kc]
for c, n in Counter(codes).items():
    if n > 1:
        errors.append(f"kc.csv: mã trùng {c}")
cs = set(codes)
leaf = {r["code"] for r in kc if r["parent_code"]}
for r in kc:
    if not r["name"].strip() or not r["description"].strip():
        errors.append(f"kc.csv: {r['code']} thiếu name/description")
    if r["parent_code"] and r["parent_code"] not in cs:
        errors.append(f"kc.csv: {r['code']} có parent_code lạ {r['parent_code']}")
    if not r["lop"].isdigit():
        errors.append(f"kc.csv: {r['code']} lop không phải số")
graph = {}
for r in csv.DictReader(open(os.path.join(folder, "kc_prereq.csv"), encoding="utf-8-sig")):
    if r["kc_code"] not in cs or r["prereq_code"] not in cs or r["kc_code"] == r["prereq_code"]:
        errors.append(f"kc_prereq.csv: dòng sai {r}")
    graph.setdefault(r["kc_code"], []).append(r["prereq_code"])
state = {}
def dfs(n):
    state[n] = 1
    for p in graph.get(n, []):
        if state.get(p) == 1:
            errors.append(f"kc_prereq.csv: chu trình qua {n} -> {p}")
        elif p not in state:
            dfs(p)
    state[n] = 2
for n in list(graph):
    if n not in state:
        dfs(n)

# ---------------------------------------------------------------- TEX
db = get_default_latex_context_db()
db.add_context_category("tutor", environments=[macrospec.EnvironmentSpec("problem", "["),
                                                macrospec.EnvironmentSpec("solution", "[")], prepend=True)

def walk(ns):
    for n in ns or []:
        yield n
        yield from walk(getattr(n, "nodelist", None))

def balance(pid, s):
    s = re.sub(r"(?<!\\)%.*", "", s)  # comments may mention \begin{problem} etc.
    s = s.replace("\\\\", " ")  # line break \\[2mm] is not a display-math opener
    t = s.replace("\\{", "").replace("\\}", "").replace("\\$", "").replace("\\%", "")
    if t.count("{") != t.count("}"):
        errors.append(f"{pid}: ngoặc nhọn lệch ({t.count('{')} vs {t.count('}')})")
    if t.count("\\[") != t.count("\\]"):
        errors.append(f"{pid}: \\[ và \\] lệch")
    if t.count("$") % 2:
        errors.append(f"{pid}: số dấu $ lẻ")
    for env in set(re.findall(r"\\begin\{(\w+\*?)\}", t)):
        if t.count(f"\\begin{{{env}}}") != t.count(f"\\end{{{env}}}"):
            errors.append(f"{pid}: \\begin/\\end{{{env}}} lệch")

ID = re.compile(r"(\d{1,2}[A-Z]{2}-[A-Z0-9]+)-\d{3}")
all_ids, used_kc, diff = [], Counter(), Counter()
files = sorted(glob.glob(os.path.join(folder, "*.tex")))
if only:
    files = [f for f in files if os.path.basename(f) in only]
for path in files:
    src = open(path, encoding="utf-8").read()
    balance(os.path.basename(path), src)
    nodes, _, _ = LatexWalker(src, latex_context=db, tolerant_parsing=True).get_latex_nodes()
    probs = [n for n in walk(nodes) if isinstance(n, LatexEnvironmentNode) and n.environmentname == "problem"]
    topics = set()
    fdiff = Counter()
    for p in probs:
        if not p.nodeargd.argnlist or p.nodeargd.argnlist[0] is None:
            errors.append(f"{os.path.basename(path)}: problem thiếu [id] ở vị trí {p.pos}")
            continue
        pid = p.nodeargd.argnlist[0].latex_verbatim()[1:-1]
        all_ids.append(pid)
        m = ID.fullmatch(pid)
        if not m:
            errors.append(f"{pid}: id sai dạng")
            continue
        topics.add(m.group(1))
        if m.group(1) not in cs:
            errors.append(f"{pid}: chủ đề {m.group(1)} không có trong kc.csv")
        balance(pid, src[p.pos: p.pos + p.len])
        meta = {}
        for c in p.nodelist:
            if isinstance(c, LatexCommentNode) and ":" in c.comment:
                k, v = c.comment.split(":", 1)
                meta[k.strip()] = v.strip()
        for k in ("nguon", "lop", "kc_du_kien", "do_kho_du_kien"):
            if k not in meta:
                errors.append(f"{pid}: thiếu % {k}:")
        for k in [x.strip() for x in meta.get("kc_du_kien", "").split(",") if x.strip()]:
            if k not in leaf:
                errors.append(f"{pid}: kc_du_kien {k} không phải KC lá trong kc.csv")
            used_kc[k] += 1
        d = meta.get("do_kho_du_kien", "")
        if d not in {"1", "2", "3", "4", "5"}:
            errors.append(f"{pid}: do_kho_du_kien phải là 1..5")
        else:
            fdiff[d] += 1
            diff[d] += 1
        if meta.get("lop") and not pid.startswith(meta["lop"]):
            errors.append(f"{pid}: % lop: {meta['lop']} không khớp id")
        sols = [c for c in p.nodelist if isinstance(c, LatexEnvironmentNode) and c.environmentname == "solution"]
        if not sols:
            errors.append(f"{pid}: không có solution")
        stmt_end = sols[0].pos if sols else p.pos + p.len
        if len(src[p.pos: stmt_end].strip()) < 40:
            errors.append(f"{pid}: đề quá ngắn")
        for s in sols:
            if not s.nodelist:
                errors.append(f"{pid}: solution rỗng")
                continue
            body = src[s.nodelist[0].pos: s.nodelist[-1].pos + s.nodelist[-1].len]
            steps = [t.strip() for t in re.split(r"\n\s*\n", body) if t.strip()]
            if len(steps) < 3:
                errors.append(f"{pid}: lời giải < 3 bước")
            if not (steps[-1].startswith("Đáp số:") and "\\boxed" in steps[-1]):
                errors.append(f"{pid}: bước cuối phải là 'Đáp số: ... \\boxed{{...}}'")
    if len(topics) != 1:
        errors.append(f"{os.path.basename(path)}: phải đúng 1 chủ đề, thấy {sorted(topics)}")
    if len(probs) < min_n:
        errors.append(f"{os.path.basename(path)}: chỉ có {len(probs)} bài (< {min_n})")
    print(f"{os.path.basename(path):40s} {len(probs):3d} bài  độ khó {dict(sorted(fdiff.items()))}")
    for t in topics:
        unused = sorted(c for c in leaf if c.startswith(t + "-") and used_kc[c] == 0)
        if unused:
            warns.append(f"{os.path.basename(path)}: KC chưa có bài nào: {', '.join(unused)}")
for pid, n in Counter(all_ids).items():
    if n > 1:
        errors.append(f"id trùng: {pid}")

print(f"\nTổng: {len(files)} file, {len(all_ids)} bài, độ khó {dict(sorted(diff.items()))}, "
      f"{len(kc)} dòng KC, {sum(len(v) for v in graph.values())} tiên quyết")
for w in warns:
    print("WARN ", w)
for e in errors:
    print("ERROR", e)
print("OK" if not errors else f"{len(errors)} lỗi")
sys.exit(1 if errors else 0)
