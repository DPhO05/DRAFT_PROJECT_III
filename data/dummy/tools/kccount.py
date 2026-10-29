"""Per leaf KC: problems where it is the main KC (first in kc_du_kien) / problems tagged with it."""
import collections, csv, glob, re, sys
B = sys.argv[1]
only = sys.argv[2:]  # optional topic group codes, e.g. 8DS-HDT
leaves = [r["code"] for r in csv.DictReader(open(f"{B}/kc.csv", encoding="utf-8-sig")) if r["parent_code"]]
tot, main = collections.Counter(), collections.Counter()
for f in glob.glob(f"{B}/*.tex"):
    for m in re.finditer(r"% kc_du_kien: (.*)", open(f, encoding="utf-8").read()):
        cs = [c.strip() for c in m.group(1).split(",")]
        tot.update(cs)
        main[cs[0]] += 1
grp = collections.defaultdict(list)
for c in leaves:
    grp[c.rsplit("-", 1)[0]].append(c)
for g, cs in grp.items():
    if not only or g in only:
        print(g, "  ".join(f"{c[-2:]}:{main[c]}/{tot[c]}" for c in cs))
