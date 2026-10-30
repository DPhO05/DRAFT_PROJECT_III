#!/usr/bin/env python3
"""Build docs/prototype/app-user.html (teacher app mock, 4 tabs) from the sources in this folder.

  python3 build.py          concatenate shell.html + app.css + *.js + data.js
  python3 build.py --data   first re-derive data.js from ../src/mock.js (the developer mock)

data.js is a friendly snapshot of the developer mock: levels as words, mistakes as words, no θ/δ, codes or ids.
"""
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "app-user.html"
MOCK = HERE.parent / "src" / "mock.js"
WS_DATE = "2026-10-24"
JS_ORDER = ["data.js", "core.js", "chat.js", "students.js", "reports.js", "bank.js", "main.js"]
# Strings that must never reach the teacher app (design §2 anti-goals, §12).
FORBIDDEN = re.compile(r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear|g[1-5]-hs")


def load_mock() -> dict:
    # mock.js fills some fields (attempt steps) in JS after the JSON literal, so evaluate it with node.
    # rank_problems (§7) comes from the mock's own TutorCalc.selectRecommendations, for the next Saturday.
    js = (f"global.window={{}};require({json.dumps(str(MOCK))});const M=window.MOCK;"
          f"M._picks={{}};M.db.student.forEach(s=>{{M._picks[s.id]=window.TutorCalc.selectRecommendations(M.db,M.settings,s.id,{json.dumps(WS_DATE)}).picks}});"
          "process.stdout.write(JSON.stringify(M))")
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(res.stdout)


def level_word(theta: float) -> str:
    return "chua" if theta < -0.5 else ("vung" if theta > 0.5 else "dang")


def change_word(d: float) -> str:
    return "up" if d >= 0.05 else ("down" if d <= -0.05 else "keep")


def pos(theta: float) -> int:
    # Display scale only (0–100, bands at 33/67); the app never shows it as a number.
    return max(0, min(100, round((theta + 1.5) / 3 * 100)))


def diff_level(d) -> str | None:
    if d is None:
        return None
    return "de" if d <= 2 else ("vua" if d == 3 else "kho")


def derive(M: dict) -> dict:
    D = M["db"]
    kc = {k["id"]: k for k in D["kc"]}
    kc_by_code = {k["code"]: k for k in D["kc"]}
    kinds = {e["code"]: i + 1 for i, e in enumerate(D["error_code"])}
    probs = {p["id"]: p for p in D["problem"]}
    rubric = {}
    for r in sorted(D["rubric"], key=lambda r: r["version"]):
        rubric[r["problem_id"]] = r
    rubric_by_id = {r["id"]: r for r in D["rubric"]}
    sessions = {s["id"]: s for s in D["session"]}

    def kind_of(code):
        return kinds.get(code, kinds["other.unclear"])

    out = {"today": M["meta"]["today"]}
    out["students"] = [
        {"id": s["id"], "name": s["name"], "short": s["name"].split()[-1], "grade": s["grade"],
         "note": s["note"] or "", "since": s["created_at"][:10], "archived": bool(s["archived_at"])}
        for s in D["student"]
    ]
    out["topics"] = [{"id": k["id"], "name": k["name"], "grade": k["lop"]} for k in D["kc"] if not k["parent_id"]]
    out["skills"] = [{"id": k["id"], "name": k["name"], "topic": k["parent_id"], "grade": k["lop"]}
                     for k in D["kc"] if k["parent_id"]]
    out["kinds"] = [{"id": i + 1, "label": e["description"], "group": e["category"]} for i, e in enumerate(D["error_code"])]

    def skills_of(p):
        ids = [kc_by_code[c]["id"] for c in (p.get("expected_kc") or []) if c in kc_by_code]
        return ids

    def rubric_items(r):
        return [{"text": i["text"], "pts": i["points"]} for i in r["items_json"]] if r else None

    def topic_of(skill_ids, ref):
        for s in skill_ids:
            if kc[s]["parent_id"]:
                return kc[s]["parent_id"]
        prefix = "-".join(ref.split("-")[:2])
        return kc_by_code[prefix]["id"] if prefix in kc_by_code else None

    def problem_out(p, pid=None):
        sk = skills_of(p)
        return {"id": pid or p["id"], "ref": p["ref"], "grade": p["lop"], "topic": topic_of(sk, p["ref"]), "skills": sk,
                "level": diff_level(p.get("expected_difficulty")), "statement": p["statement_latex"],
                "solution": [s["latex"] for s in p.get("solution_steps") or []] or [p["solution_latex"]],
                "rubric": rubric_items(rubric.get(p["id"])) if pid is None else None,
                "source": "Tự soạn" if "dummy" in (p.get("source") or "dummy") else p["source"]}

    out["problems"] = [problem_out(p) for p in D["problem"]]

    # ---- graded sessions (approved) ----
    superseded_m = {m["supersedes_id"] for m in D["mistake"] if m["supersedes_id"]}
    m_by_attempt = defaultdict(list)
    for m in D["mistake"]:
        if m["status"] != "rejected" and m["id"] not in superseded_m:
            m_by_attempt[m["attempt_id"]].append(m)
    a_by_session = defaultdict(list)
    for a in D["attempt"]:
        a_by_session[a["session_id"]].append(a)

    def mistake_out(m, seq=None):
        return {"kind": kind_of(m["code"]), "skill": m["kc_id"], "step": m["step_idx"],
                "desc": m["description"], "evidence": m["evidence_latex"], "note": m.get("teacher_note") or "",
                **({"seq": seq} if seq is not None else {})}

    out["sessions"] = []
    for s in sorted(D["session"], key=lambda s: s["held_on"]):
        if s["status"] != "committed":
            continue
        probs_out = []
        for a in sorted(a_by_session[s["id"]], key=lambda a: a["seq"]):
            probs_out.append({"pid": a["problem_id"], "score": a["score"], "max": a["max_score"],
                              "steps": [x["latex"] for x in a["steps_json"]],
                              "mistakes": [mistake_out(m) for m in sorted(m_by_attempt[a["id"]], key=lambda m: m["step_idx"])]})
        out["sessions"].append({"id": s["id"], "student": s["student_id"], "date": s["held_on"], "problems": probs_out})

    # ---- levels, changes, series ----
    att_session = {a["id"]: a["session_id"] for a in D["attempt"]}
    events = sorted(D["skill_event"], key=lambda e: (sessions[att_session[e["attempt_id"]]]["held_on"], e["id"]))
    out["levels"], out["series"] = {}, {}
    for st in D["student"]:
        sid = st["id"]
        evs = [e for e in events if e["student_id"] == sid]
        dates = sorted({sessions[att_session[e["attempt_id"]]]["held_on"] for e in evs})
        theta, series_all, by_skill = {}, [], defaultdict(list)
        last_change, last_seen, n_seen = {}, {}, defaultdict(int)
        for d in dates:
            day = [e for e in evs if sessions[att_session[e["attempt_id"]]]["held_on"] == d]
            moved = defaultdict(float)
            for e in day:
                theta[e["kc_id"]] = e["theta_after"]
                moved[e["kc_id"]] += e["theta_after"] - e["theta_before"]
                n_seen[e["kc_id"]] += 1
            for k, v in moved.items():
                last_change[k], last_seen[k] = v, d
            series_all.append(pos(sum(theta.values()) / len(theta)))
            for k in kc:
                by_skill[k].append(pos(theta[k]) if k in theta else None)
        out["levels"][sid] = {k: {"lv": level_word(theta[k]), "ch": change_word(last_change[k]), "n": n_seen[k],
                                  "last": last_seen[k]} for k in theta}
        out["series"][sid] = {"dates": dates, "all": series_all,
                              "skills": {k: v for k, v in by_skill.items() if any(x is not None for x in v)}}
        out.setdefault("_theta", {})[sid] = theta  # used below only, stripped before output

    out["recurring"] = defaultdict(list)
    for m in D["misconception_log"]:
        out["recurring"][m["student_id"]].append({"kind": kind_of(m["code"]), "skill": m["kc_id"], "count": m["count"],
                                                  "first": m["first_seen"], "last": m["last_seen"],
                                                  "resolved": m["resolved_at"]})

    # ---- worksheets given ----
    ws = defaultdict(list)
    for r in sorted(D["recommendation"], key=lambda r: r["position"]):
        if r["status"] in ("approved", "added"):
            ws[(r["student_id"], r["for_date"])].append({"pid": r["problem_id"], "why": r["reason"] or "Thầy/cô tự thêm"})
    out["worksheets"] = [{"student": k[0], "date": k[1], "items": v} for k, v in sorted(ws.items(), key=lambda x: x[0][1])]

    # ---- approved reports per period (re-worded: no %, no θ, no fact ids) ----
    span = {"day": "buổi này", "week": "tuần", "month": "tháng"}

    def report_sentences(facts, kind, flag_extra=None):
        f = {x.get("insight") if x["kind"] in ("delta_theta", "top_code") else x["kind"]: x for x in facts}
        out_s = []
        out_s.append({"t": f"Trong buổi này, em làm {f['count']['value']} bài." if kind == "day" else
                      f"Trong {span[kind]}, em học {f['sessions']['value']} buổi và làm {f['count']['value']} bài."})
        rate = f["rate"]["value"]
        out_s.append({"t": "Em làm đúng phần lớn các bước giải." if rate >= 0.8 else
                      ("Em làm đúng khá nhiều bước, còn vài chỗ cần cẩn thận hơn." if rate >= 0.6 else
                       "Em còn sai ở khá nhiều bước, cần luyện thêm.")})
        if "trend" in f and f["trend"]["value"] > 0:
            out_s.append({"t": f"Tiến bộ rõ nhất ở phần “{kc[f['trend']['kc_id']]['name']}”."})
        if "majority" in f:
            lab = D["error_code"][kind_of(f["majority"]["code"]) - 1]["description"].lower()
            out_s.append({"t": f"Lỗi em hay gặp nhất là “{lab}” ({f['majority']['value']} lần)."})
        if "outlier" in f:
            out_s.append({"t": f"Cần ôn thêm phần “{kc[f['outlier']['kc_id']]['name']}”."})
        rec = f["recurring"]["value"]
        out_s.append({"t": f"Còn {rec} lỗi hay lặp lại, thầy/cô sẽ cho em ôn ở các buổi tới." if rec else
                      "Không còn lỗi nào lặp lại."})
        if f.get("resolved") and f["resolved"]["value"]:
            out_s.append({"t": f"Có {f['resolved']['value']} lỗi em đã sửa được trong {span[kind]}."})
        if flag_extra:
            out_s.append(flag_extra)
        return out_s

    out["reports"] = [{"id": r["id"], "student": r["student_id"], "kind": r["period_kind"], "start": r["period_start"],
                       "approved": r["approved_at"][:10], "sentences": report_sentences(r["facts_json"], r["period_kind"])}
                      for r in D["report"]]
    threads = {t["thread_id"]: t for t in M["checkpoints"]["threads"]}
    out["reportDrafts"] = []
    for tid, extra in (("g5-hs02-20260901", {"t": "Em làm đúng hết 6 bài ở buổi cuối tháng.", "flag": "num",
                                              "why": "Con số này không khớp với dữ liệu đã duyệt."}),
                       ("g5-hs04-20260901", {"t": "Em đã nắm rất vững kiến thức, kết quả rất đáng khen.", "flag": "tone",
                                              "why": "Câu khen hơi quá so với kết quả trong tháng."}),
                       ("g5-hs01-20261012", None)):
        t = threads[tid]
        st, prop = t["state"], t["state"]["proposals"][0]
        nums = sorted({str(x["value"]) for x in prop["facts_json"] if isinstance(x["value"], int)})
        out["reportDrafts"].append({"id": 100 + t["student_id"], "student": t["student_id"], "kind": st["period_kind"],
                                    "start": st["period_start"], "created": t["started_at"][:10],
                                    "nums": nums, "sentences": report_sentences(prop["facts_json"], st["period_kind"], extra)})

    # ---- pending grading jobs (G1 at a stop) and new inbox files ----
    def job_from(attempts, proposals, student, date, file, jid, status, match_override=None):
        probs_j = []
        for a in attempts:
            r = rubric_by_id.get(a.get("rubric_id")) or rubric.get(a["problem_id"])
            mt = (match_override or {}).get(a["seq"]) or a.get("match") or {}
            cands = [c["problem_id"] for c in mt.get("candidates", [])]
            probs_j.append({"seq": a["seq"], "pid": a["problem_id"], "score": a.get("score"), "max": a.get("max_score"),
                            "steps": [x["latex"] for x in a["steps_json"]],
                            "confirm": cands if mt.get("method") == "llm" else None,
                            "rubricDraft": any(f.get("type") == "no_rubric" for f in a.get("flags_json") or []),
                            "rubric": rubric_items(r)})
        ms = []
        for i, p in enumerate(proposals):
            v = p.get("verifier") or {}
            check = None
            if v.get("verdict") == "disagree":
                check = "Kiểm tra lại thấy có thể không phải lỗi: " + v["reason"].rstrip(".") + "."
            elif v.get("verdict") == "wrong_code" and v.get("suggested_code"):
                lab = D["error_code"][kind_of(v["suggested_code"]) - 1]["description"].lower()
                check = f"Kiểm tra lại thấy có thể là loại “{lab}”."
            ms.append({"id": f"{jid}-m{i + 1}", "seq": p["attempt_seq"], "step": p["step_idx"], "kind": kind_of(p["code"]),
                       "skill": p["kc_id"], "desc": p["description"], "evidence": p["evidence_latex"],
                       "unsure": (p.get("confidence") or 1) < 0.6, "check": check,
                       "suggest": kind_of(v["suggested_code"]) if v.get("suggested_code") else None})
        return {"id": jid, "student": student, "date": date, "file": file, "status": status,
                "problems": probs_j, "mistakes": ms}

    demo = M["ui"]["demo_runs"]
    jobs = []
    an_match = {3: {"method": "llm", "candidates": [{"problem_id": probs_id} for probs_id in
                                                     [p["id"] for p in D["problem"] if p["ref"] in ("9DS-CAN-009", "9DS-CAN-012", "9DS-CAN-021")]]}}
    jobs.append(job_from(demo["hs01-1021"]["attempts"], demo["hs01-1021"]["proposals"], 1, "2026-10-21",
                         "hs01-2026-10-21.tex", "j-an", "new", an_match))
    jobs.append(job_from(demo["hs02-1021"]["attempts"], demo["hs02-1021"]["proposals"], 2, "2026-10-21",
                         "hs02-2026-10-21.tex", "j-bao", "new"))
    for tid, jid in (("g1-hs03-20261020", "j-ha"), ("g1-hs05-20261020", "j-lan20"), ("g1-hs05-20261017", "j-lan17")):
        t = threads[tid]
        jobs.append(job_from(t["state"]["attempts"], t["state"]["proposals"], t["student_id"],
                             sessions[t["session_id"]]["held_on"], Path(t["state"]["source"]["path"]).name, jid, "review"))
    # Khang: stopped at "is this the right problem?"; after confirm the demo run has the grades + mistakes.
    t = threads["g1-hs04-20261020"]
    kh = job_from(demo["hs04-after-confirm"]["attempts"], demo["hs04-after-confirm"]["proposals"], 4, "2026-10-20",
                  "hs04-2026-10-20.pdf", "j-khang", "match")
    kh["problems"][1]["confirm"] = [c["problem_id"] for c in t["state"]["attempts"][1]["match"]["candidates"]]
    jobs.append(kh)
    t = threads["g1-hs06-20261019"]
    hu = job_from(t["state"]["attempts"], demo["hs06-resume"]["proposals"], 6, "2026-10-19", "hs06-2026-10-19.pdf",
                  "j-huy", "failed")
    for p in hu["problems"]:
        if p["score"] is None:
            p["score"], p["max"] = 4, 6
    jobs.append(hu)
    for j in jobs:
        for p in j["problems"]:
            if p["score"] is None and p["rubric"]:
                p["max"] = sum(i["pts"] for i in p["rubric"])
                p["score"] = p["max"]
    out["jobs"] = jobs
    out["inbox"] = [{"file": "hs01-2026-10-21.tex", "student": 1, "date": "2026-10-21", "job": "j-an"},
                    {"file": "hs02-2026-10-21.tex", "student": 2, "date": "2026-10-21", "job": "j-bao"}]

    # ---- worksheet draft waiting (Bảo, Saturday 24/10) ----
    g4 = threads["g4-hs02-20261024"]["state"]
    short = {"review": "on", "zpd": "vua", "challenge": "thu"}
    out["wsDraft"] = {"student": g4["student_id"], "date": g4["for_date"],
                      "items": [{"pid": p["problem_id"], "why": p["reason"], "b": short[p["bucket"]]}
                                for p in sorted(g4["proposals"], key=lambda p: p["position"])]}

    # ---- rank_problems per student, worded like the mock's recommendation.reason template ----
    def pick_why(sid, p):
        name = kc[p["kc_id"]]["name"]
        if p["bucket"] == "review":
            return f"Ôn lại “{name}”: còn {p['codeDesc'][0].lower() + p['codeDesc'][1:]} ({p['count']} lần)."
        if p["bucket"] == "zpd":
            seen = p["kc_id"] in out["_theta"][sid]
            return f"Vừa sức: “{name}”" + ("." if seen else " chưa có dữ liệu, bắt đầu bằng bài mức vừa.")
        if p.get("fallback"):
            return f"Thử thách: chưa có bài khó hơn, lấy bài khó nhất còn lại của “{name}”."
        return f"Thử thách: kỹ năng nền đã vững, thử “{name}” ở mức khó hơn."

    out["suggest"] = {sid: [{"pid": p["problem_id"], "b": short[p["bucket"]], "why": pick_why(int(sid), p)} for p in picks]
                      for sid, picks in M["_picks"].items()}
    del out["_theta"]

    # ---- bank inbox: 8-ham-so-bac-nhat.tex (G2 thread); labels missing in the file stay empty for the teacher ----
    g2 = threads["g2-8-ham-so-bac-nhat"]["state"]
    items = {b["problem_ref"]: b for b in g2["proposals"]}
    newp = []
    for i, p in enumerate(g2["problems"]):
        q = problem_out(p, pid=1000 + i)
        q["topic"] = kc_by_code["8DS-HSBN"]["id"]
        q["unknownLabel"] = bool(items[p["ref"]]["unknown_kc"])
        newp.append(q)
    out["bankInbox"] = [
        {"file": "8-ham-so-bac-nhat.tex", "title": "Hàm số bậc nhất (lớp 8)", "problems": newp},
        {"file": "de-on-tap-chua-dat-ten.tex", "title": "Đề ôn tập", "problems": [],
         "error": "Không tìm thấy bài nào trong file (chưa có dòng \\begin{problem})."},
        {"file": "9-can-thuc.tex", "title": "Căn bậc hai và căn bậc ba (lớp 9)", "imported": "2026-08-26", "problems": []},
    ]
    out["backups"] = [{"at": b["at"][:16].replace("T", " "), "kb": b["size_kb"]} for b in M["files"]["backups"]]
    out["settings"] = {"n": M["settings"]["reco"]["n_problems"], "noRepeat": M["settings"]["reco"]["no_repeat_days"],
                       "budget": M["settings"]["budget_usd_month"]}
    out["cost"] = {"month": "10/2026", "total": 4.2, "parts": [["Chấm bài", 2.6], ["Trợ lý", 0.9], ["Báo cáo", 0.5],
                                                              ["Khác", 0.2]]}
    return out


def write_data() -> None:
    data = derive(load_mock())
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    bad = FORBIDDEN.findall(blob)
    if bad:
        sys.exit(f"build: data contains forbidden strings: {sorted(set(bad))[:10]}")
    (HERE / "data.js").write_text("/* generated by build.py --data from ../src/mock.js — do not edit */\n"
                                  f"window.APP = {blob};\n", encoding="utf-8")
    print(f"data.js: {len(blob) / 1024:.0f} KB, {len(data['problems'])} problems, {len(data['sessions'])} sessions")


def main() -> None:
    if "--data" in sys.argv:
        write_data()
    shell = (HERE / "shell.html").read_text(encoding="utf-8")
    css = (HERE / "app.css").read_text(encoding="utf-8")
    js = []
    for name in JS_ORDER:
        src = (HERE / name).read_text(encoding="utf-8")
        if re.search(r"</script", src, re.I):
            sys.exit(f"build: {name} contains </script")
        js.append(f"/* {name} */\n{src}")
    for mark in ("/*__CSS__*/", "/*__JS__*/"):
        if shell.count(mark) != 1:
            sys.exit(f"build: shell.html needs {mark} once")
    html = shell.replace("/*__CSS__*/", css).replace("/*__JS__*/", "\n</script>\n<script>\n".join(js))
    OUT.write_text(html, encoding="utf-8")
    print(f"build: {OUT} ({len(html.encode()) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
