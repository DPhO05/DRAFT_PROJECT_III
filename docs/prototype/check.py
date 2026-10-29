#!/usr/bin/env python3
"""Robot test for dist/app-draft.html: errors, dead buttons, 390px overflow, screenshots.

Run: uv run --quiet --with playwright python check.py [--tabs id1 id2] [--shots]
Exit 1 on any page error (uncaught exception) or console error from the app.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PAGE = (Path(os.environ.get("PROTO_DIST", ROOT / "dist")) / "app-draft.html").as_uri()
SHOTS = Path(os.environ.get("PROTO_SHOTS", ROOT / "shots"))
DESK = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
CAP = 60
# Network noise (offline fonts/CDN) is not an app bug.
NET_NOISE = ("Failed to load resource", "net::ERR_")

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


def exercise(page, tab: str, rep: dict) -> None:
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
            rep["click_failures"].append(f'{c["scope"]}: {c["label"]} ({str(e).splitlines()[0][:120]})')
            continue
        n += 1
        page.wait_for_timeout(300)
        mut, toasts = page.evaluate("[window.__robotMut, window.__robotToasts]")
        now = page.evaluate("document.querySelector('#view').dataset.tab")
        if now != tab:
            rep["navigated"].append(f'{c["label"]} -> {now}')
            page.evaluate("document.querySelectorAll('#modal-root .modal-back, #drawer-root .drawer-back').forEach(e => e.remove())")
            goto_tab(page, tab)
        elif mut == 0 and toasts == 0:
            rep["dead"].append(f'{c["scope"]}: {c["label"]}')
    rep["clicks"] = n
    if n >= CAP:
        rep["notes"].append(f"click cap {CAP} reached")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tabs", nargs="*")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    report = {"page": PAGE, "tabs": []}
    fatal = False
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=DESK)
        errs: list[str] = []
        perrs: list[str] = []
        page.on("console", lambda m: m.type == "error" and not m.text.startswith(NET_NOISE) and errs.append(m.text[:300]))
        page.on("pageerror", lambda e: perrs.append(str(e)[:300]))
        page.goto(PAGE)
        page.wait_for_function("window.App && App.started", timeout=10000)
        tabs = args.tabs or page.evaluate("[...document.querySelectorAll('#sidebar [data-tab-link]')].map(a => a.dataset.tabLink)")
        registered = page.evaluate("App.registered()")
        report["boot"] = {"console_errors": errs[:], "page_errors": perrs[:], "registered": registered}
        fatal |= bool(errs or perrs)
        if args.shots:
            SHOTS.mkdir(parents=True, exist_ok=True)
        for tab in tabs:
            errs.clear()
            perrs.clear()
            rep = {"tab": tab, "registered": tab in registered, "clicks": 0, "dead": [], "navigated": [],
                   "click_failures": [], "notes": [], "shots": []}
            page.set_viewport_size(DESK)
            page.emulate_media(color_scheme="light")
            page.goto(PAGE)
            page.wait_for_function("window.App && App.started", timeout=10000)
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
                        out = SHOTS / f"{tab}-{vp_name}-{scheme}.png"
                        page.screenshot(path=str(out), full_page=True)
                        rep["shots"].append(str(out))
            page.set_viewport_size(DESK)
            page.emulate_media(color_scheme="light")
            rep["tex_errors"] = page.evaluate(JS_TEX_ERRORS)
            exercise(page, tab, rep)
            page.wait_for_timeout(1500)  # let timers (resume, animations) finish so late errors land on this tab
            rep["console_errors"] = errs[:]
            rep["page_errors"] = perrs[:]
            fatal |= bool(errs or perrs)
            report["tabs"].append(rep)
        browser.close()
    report["summary"] = {
        "tabs": len(report["tabs"]),
        "page_errors": sum(len(t["page_errors"]) for t in report["tabs"]),
        "console_errors": sum(len(t["console_errors"]) for t in report["tabs"]),
        "dead_buttons": sum(len(t["dead"]) for t in report["tabs"]),
        "overflow_tabs": [t["tab"] for t in report["tabs"] if t.get("overflow_390", {}).get("overflow")],
        "tex_errors": sum(len(t["tex_errors"]) for t in report["tabs"]),
        "ok": not fatal,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
