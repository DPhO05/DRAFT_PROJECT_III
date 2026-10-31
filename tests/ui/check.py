#!/usr/bin/env python3
"""Robot UI check (P0-T08): page/console errors, dead buttons, 390px overflow, screenshots.

Run: uv run python tests/ui/check.py [--url http://127.0.0.1:8000/] [--tabs id1 id2] [--shots] [--data]
Without --url it starts `tutor app` on a free port with a temp data dir.
Exit 1 on any page error, app console error, dead button or horizontal overflow at 390px.
Ported from docs/prototype/check.py (file:// mock draft -> running app).
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
DESK = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
CAP = 60
# Network noise (offline fonts/CDN) is not an app bug.
NET_NOISE = ("Failed to load resource", "net::ERR_")
# A 1 s ticking clock (review timer) changes the DOM every second and would hide dead buttons.
NO_CLOCKS = "const _si = window.setInterval; window.setInterval = (f, ms, ...a) => ms === 1000 ? 0 : _si(f, ms, ...a);"
# Extra routes walked with --data: step 4 of the seeded HS-01 session, step 5 preview of the seeded HS-02 session
# (neither reachable from the tab's first view).
PREVIEW_TID = "g1-hs02-20261023-2"
DATA_ROUTES = {"session": ["session?thread=g1-hs01-20261020", f"session?thread={PREVIEW_TID}"]}
# route -> the preview must offer `button`, show every `text`, and after the click show every `after` (the receipt).
EXPECT = {
    f"session?thread={PREVIEW_TID}": {
        "button": "Lưu kết quả",
        "text": ["Sẽ ghi (1 transaction)"],
        "after": ["Đã ghi 1 transaction", "lượt cập nhật kỹ năng"],
    }
}
# Table names and maths symbols stay off the teacher's screen (R-F).
BANNED = ("skill_event", "skill_state", "misconception_log", "θ", "δ")

JS_CANDIDATES = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
    const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const modal = [...document.querySelectorAll('#modal-root .modal')].pop();
  const drawer = document.querySelector('#drawer-root .drawer');
  const [scope, root] = modal ? ['modal', modal] : drawer ? ['drawer', drawer] : ['view', document.querySelector('#view')];
  document.querySelectorAll('[data-robot]').forEach(e => e.removeAttribute('data-robot'));
  const out = [], seen = {};
  root.querySelectorAll('button').forEach(b => {
    if (b.disabled || b.closest('[data-no-autoclick]') || b.matches('[data-modal-close], .seg-btn[aria-pressed="true"]') || !vis(b)) return;
    const label = (b.getAttribute('aria-label') || b.textContent || b.title || '').replace(/\s+/g, ' ').trim().slice(0, 70);
    const k = scope + '|' + label; seen[k] = (seen[k] || 0) + 1;
    const id = String(out.length); b.setAttribute('data-robot', id);
    out.push({ id, sig: k + '#' + seen[k], label, scope });
  });
  return { scope, items: out };
}
"""

JS_OBSERVE = r"""
() => {
  if (window.__robotObs) window.__robotObs.disconnect();
  window.__robotMut = 0; window.__robotToasts = 0;
  const inToasts = n => { const e = n && (n.nodeType === 1 ? n : n.parentElement); return !!(e && e.closest('#toasts')); };
  window.__robotObs = new MutationObserver(list => {
    for (const m of list) {
      if (m.type === 'attributes' && m.attributeName === 'data-robot') continue;
      if (inToasts(m.target) && m.removedNodes.length && !m.addedNodes.length) continue;  // old toasts expiring
      if (m.target.id === 'toasts' && m.addedNodes.length) window.__robotToasts++;
      window.__robotMut++;
    }
  });
  window.__robotObs.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
}
"""

JS_OVERFLOW = r"""
() => {
  const W = document.documentElement.clientWidth, sw = document.documentElement.scrollWidth;
  const offenders = [];
  if (sw > W + 1) {
    const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
    document.querySelectorAll('body *').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.right <= W + 1 || !r.width) return;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') return;
      }
      offenders.push(desc(el) + ' right=' + Math.round(r.right));
    });
  }
  return { width: W, scrollWidth: sw, overflow: sw > W + 1, offenders: offenders.slice(0, 8) };
}
"""

JS_TEX_ERRORS = r"""
() => [...document.querySelectorAll('#view [data-mjx-error], #view mjx-merror')]
  .map(e => e.getAttribute('data-mjx-error') || e.textContent).slice(0, 8)
"""


def wait_tex(page) -> str:
    try:
        page.wait_for_function("window.App && App.texReady()", timeout=20000)
    except Exception:
        return "mathjax-not-loaded"
    try:
        return page.evaluate("App.texDone()")
    except Exception as e:  # noqa: BLE001
        return f"tex-error: {e}"


def goto_tab(page, tab: str) -> None:
    page.click(f'#sidebar [data-tab-link="{tab}"]', timeout=5000)
    page.wait_for_timeout(150)


def close_overlay(page) -> bool:
    sel = "#modal-root .modal-back:last-child [data-modal-close], #drawer-root [data-modal-close]"
    if page.locator(sel).count():
        try:
            page.locator(sel).first.click(timeout=2000)
        except Exception:  # noqa: BLE001
            page.keyboard.press("Escape")
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    return page.evaluate("!document.querySelector('#modal-root .modal, #drawer-root .drawer')")


def view_text(page) -> str:
    return page.evaluate("document.querySelector('#view').innerText")


def exercise(page, tab: str, rep: dict, want: dict | None = None) -> None:
    clicked, n, closes = set(), 0, 0
    while n < CAP:
        page.evaluate("document.querySelectorAll(':popover-open').forEach(p => p.hidePopover())")
        cand = page.evaluate(JS_CANDIDATES)
        todo = [c for c in cand["items"] if c["sig"] not in clicked]
        if not todo:
            if cand["scope"] in ("modal", "drawer"):
                closes += 1
                if not close_overlay(page) and closes > 20:
                    rep["notes"].append("overlay would not close")
                    break
                continue
            break
        c = todo[0]
        clicked.add(c["sig"])
        page.evaluate(JS_OBSERVE)
        try:
            page.click(f'[data-robot="{c["id"]}"]', timeout=3000)
        except Exception as e:  # noqa: BLE001
            rep["click_failures"].append(f"{c['scope']}: {c['label']} ({str(e).splitlines()[0][:120]})")
            continue
        n += 1
        if want and c["label"] == want["button"]:
            try:
                page.wait_for_function(
                    "ts => ts.every(t => document.querySelector('#view').innerText.includes(t))",
                    arg=want["after"],
                    timeout=10000,
                )
            except Exception:  # noqa: BLE001
                rep["missing"].append(f"after {want['button']}: no {want['after']}")
            text = view_text(page)
            rep["missing"] += [f"banned on screen: {b}" for b in BANNED if b in text]
            want = {**want, "button": None}  # checked once
        page.wait_for_timeout(300)
        mut, toasts = page.evaluate("[window.__robotMut, window.__robotToasts]")
        now = page.evaluate("document.querySelector('#view').dataset.tab")
        if now != tab:
            rep["navigated"].append(f"{c['label']} -> {now}")
            page.evaluate(
                "document.querySelectorAll('#modal-root .modal-back, #drawer-root .drawer-back').forEach(e => e.remove())"
            )
            goto_tab(page, tab)
        elif mut == 0 and toasts == 0:
            rep["dead"].append(f"{c['scope']}: {c['label']}")
    rep["clicks"] = n
    if want and want["button"]:
        rep["missing"].append(f"never clicked: {want['button']}")
    if n >= CAP:
        rep["notes"].append(f"click cap {CAP} reached")


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "submissions"


def seed(exe: str, data: str) -> None:
    """Dummy bank + inbox files; students are added over the API once the app is up."""
    subprocess.run([exe, "seed-dummy", "--dev", "--data-dir", data], check=True, capture_output=True, timeout=120)
    inbox = Path(data) / "inbox"
    for name in ("s01.tex", "s04.tex", "s06.tex"):
        (inbox / name).write_bytes((FIX / name).read_bytes())
    logs = Path(data) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "llm.jsonl").write_bytes((FIX.parent / "llm.jsonl").read_bytes())


def api(url: str, method: str, path: str, body: object = None) -> object:
    req = urllib.request.Request(f"{url}api{path}", None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"X-Tutor": "1", "Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def wait_idle(url: str, tid: str) -> None:
    for _ in range(300):
        if api(url, "GET", f"/threads/{tid}")["status"] != "running":
            return
        time.sleep(0.1)


def add_students(url: str) -> None:
    """2 students, 4 G1 sessions: HS-01 s01 (review gate) + s06 two days later (date-locked behind s01, C-28);
    HS-02 s04 (step 3: low_match) + s01 the same day (every card accepted, parked at gate_confirm_commit = step 5 preview).
    s04 is listed first, so the robot's walk opens step 3, resumes, then sees step 4."""
    students = ({"name": "Nguyễn Văn An", "grade": 8}, {"name": "Trần Thị Bình", "grade": 9})
    s1, s2 = [api(url, "POST", "/students", b)["id"] for b in students]
    tids = [api(url, "POST", "/sessions", {"student_id": sid, "held_on": day, "path": f})["thread_id"]
            for sid, day, f in ((s1, "2026-10-20", "s01.tex"), (s1, "2026-10-22", "s06.tex"),
                                (s2, "2026-10-23", "s04.tex"), (s2, "2026-10-23", "s01.tex"))]  # fmt: skip
    if tids[3] != PREVIEW_TID:
        raise RuntimeError(f"preview thread is {tids[3]}, robot expects {PREVIEW_TID}")
    for tid in tids:
        wait_idle(url, tid)
    cards = {
        p["pid"]: {"action": "accept"}
        for p in api(url, "GET", f"/threads/{PREVIEW_TID}?include=state")["state"]["proposals"]
    }
    api(url, "PUT", f"/threads/{PREVIEW_TID}/decisions", {"cards": cards, "review_seconds": 60})
    api(url, "POST", f"/threads/{PREVIEW_TID}/resume")
    wait_idle(url, PREVIEW_TID)
    if api(url, "GET", f"/threads/{PREVIEW_TID}")["node"] != "gate_confirm_commit":
        raise RuntimeError("preview thread did not stop at gate_confirm_commit")


@contextmanager
def tutor_app(with_data: bool = False):
    """`tutor app` on a free port with a throwaway data dir; yields its URL."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    with tempfile.TemporaryDirectory() as tmp:
        exe = str(Path(sys.executable).with_name("tutor"))
        if with_data:
            seed(exe, f"{tmp}/data")
        # --fake-llm + no ANTHROPIC_* env: the robot never reaches the real API (C-34)
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC")}
        proc = subprocess.Popen([exe, "app", "--no-browser", "--port", str(port), "--data-dir", f"{tmp}/data",
                                 "--fake-llm"], env=env)  # fmt: skip
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"{url}api/health", timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.1)
            if with_data:
                add_students(url)
            yield url
        finally:
            proc.terminate()
            proc.wait(10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="app already running; default: start one")
    ap.add_argument("--tabs", nargs="*")
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--data", action="store_true", help="seed dummy bank, 2 students, 3 inbox files, 4 G1 sessions")
    args = ap.parse_args()
    if args.url:
        return check(args.url, args)
    with tutor_app(args.data) as url:
        return check(url, args)


def check(page_url: str, args: argparse.Namespace) -> int:
    report = {"page": page_url, "tabs": []}
    fatal = False
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=DESK)
        page.add_init_script(NO_CLOCKS)
        errs: list[str] = []
        perrs: list[str] = []
        page.on(
            "console", lambda m: m.type == "error" and not m.text.startswith(NET_NOISE) and errs.append(m.text[:300])
        )
        page.on("pageerror", lambda e: perrs.append(str(e)[:300]))
        page.goto(page_url)
        page.wait_for_function("window.App && App.started", timeout=10000)
        tabs = args.tabs or page.evaluate(
            "[...document.querySelectorAll('#sidebar [data-tab-link]')].map(a => a.dataset.tabLink)"
        )
        registered = page.evaluate("App.registered()")
        report["boot"] = {"console_errors": errs[:], "page_errors": perrs[:], "registered": registered}
        fatal |= bool(errs or perrs)
        if args.shots:
            SHOTS.mkdir(parents=True, exist_ok=True)
        # routes first: later walks (ops › Huỷ) may cancel the seeded threads
        walks = [(t, r) for t in tabs if args.data for r in DATA_ROUTES.get(t, [])] + [(t, None) for t in tabs]
        for tab, route in walks:
            errs.clear()
            perrs.clear()
            rep = {
                "tab": tab + (f"#{route}" if route else ""),
                "registered": tab in registered,
                "clicks": 0,
                "dead": [],
                "missing": [],
                "navigated": [],
                "click_failures": [],
                "notes": [],
                "shots": [],
            }
            page.set_viewport_size(DESK)
            page.emulate_media(color_scheme="light")
            page.goto(page_url + (f"#{route}" if route else ""))
            page.wait_for_function("window.App && App.started", timeout=10000)
            if route:
                page.wait_for_timeout(1500)  # thread state loads after the first paint
            else:
                goto_tab(page, tab)
            rep["tex"] = wait_tex(page)
            for vp_name, vp in (("desktop", DESK), ("phone", PHONE)):
                page.set_viewport_size(vp)
                for scheme in ("light", "dark") if args.shots else ("light",):
                    page.emulate_media(color_scheme=scheme)
                    page.wait_for_timeout(150)
                    if vp_name == "phone" and scheme == "light":
                        rep["overflow_390"] = page.evaluate(JS_OVERFLOW)
                    if args.shots:
                        out = SHOTS / f"{tab}{'-route' if route else ''}-{vp_name}-{scheme}.png"
                        page.screenshot(path=str(out), full_page=True)
                        rep["shots"].append(str(out))
            page.set_viewport_size(DESK)
            page.emulate_media(color_scheme="light")
            rep["tex_errors"] = page.evaluate(JS_TEX_ERRORS)
            want = EXPECT.get(route)
            if want:
                text = view_text(page)
                rep["missing"] += [f"text: {t}" for t in want["text"] if t not in text]
                rep["missing"] += [f"banned on screen: {b}" for b in BANNED if b in text]
                if not page.locator("#view button:not([disabled])", has_text=want["button"]).count():
                    rep["missing"].append(f"button: {want['button']}")
            exercise(page, tab, rep, want)
            page.wait_for_timeout(1500)  # let timers (resume, animations) finish so late errors land on this tab
            rep["console_errors"] = errs[:]
            rep["page_errors"] = perrs[:]
            fatal |= bool(errs or perrs or rep["dead"] or rep["missing"] or rep.get("overflow_390", {}).get("overflow"))
            report["tabs"].append(rep)
        browser.close()
    report["summary"] = {
        "tabs": len(report["tabs"]),
        "page_errors": sum(len(t["page_errors"]) for t in report["tabs"]),
        "console_errors": sum(len(t["console_errors"]) for t in report["tabs"]),
        "dead_buttons": sum(len(t["dead"]) for t in report["tabs"]),
        "missing": sum(len(t["missing"]) for t in report["tabs"]),
        "overflow_tabs": [t["tab"] for t in report["tabs"] if t.get("overflow_390", {}).get("overflow")],
        "tex_errors": sum(len(t["tex_errors"]) for t in report["tabs"]),
        "ok": not fatal,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
