#!/usr/bin/env python3
"""Robot UI check for the 4-tab app at /v3/ (P5-T05).

Run: .venv/bin/python tests/ui/check_v3.py [--url http://127.0.0.1:8000/] [--data] [--shots]
Opens /v3/ at 1440 px and 390 px; walks the 4 tabs, the ⚙ menu and light/dark.
Exit 1 on any page error, app console error, dead button, horizontal overflow at 390 px or forbidden text on screen.
Without --url it starts `tutor app` on a free port with a temp data dir; --data seeds dummy bank and students.
"""

import argparse
import json
import re
import sys

# shortcut: generic helpers are imported from check.py; P8-T03 deletes check.py and they move into this file.
from check import DESK, JS_OBSERVE, JS_OVERFLOW, NET_NOISE, PHONE, SHOTS, close_overlay, tutor_app
from playwright.sync_api import sync_playwright

TABS = ("tro-ly", "hoc-sinh", "bao-cao", "ngan-hang")
# docs/prototype/app-user/build.py FORBIDDEN, plus the word "node"
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b"
)
SOON = "Sắp có"
JS_TAB = """t => document.getElementById('tab-' + t).getAttribute('aria-selected') === 'true'
  && !document.getElementById('panel-' + t).hidden && location.hash === '#' + t"""
JS_THEME = """() => ({
  attr: document.documentElement.getAttribute('data-theme'),
  stored: localStorage.getItem('gs-theme'),
  pressed: [...document.querySelectorAll('[data-theme-opt][aria-pressed=true]')].map(b => b.dataset.themeOpt),
  bg: getComputedStyle(document.body).backgroundColor,
})"""
JS_TABBAR = """() => {
  const r = document.querySelector('.tabs').getBoundingClientRect(); return [r.top, r.bottom, innerHeight];
}"""


def press(page, rep: dict, sel: str, label: str) -> None:
    """Click and record a dead button when the DOM does not change."""
    page.evaluate(JS_OBSERVE)
    try:
        page.click(sel, timeout=3000)
    except Exception as e:  # noqa: BLE001
        rep["missing"].append(f"click {label}: {str(e).splitlines()[0][:120]}")
        return
    page.wait_for_timeout(100)
    if not page.evaluate("window.__robotMut + window.__robotToasts"):
        rep["dead"].append(label)


def see(page, rep: dict, where: str, phone: bool) -> None:
    """Forbidden words on screen, and horizontal overflow at 390 px."""
    rep["forbidden"] += [f"{where}: {m.group(0)}" for m in FORBIDDEN.finditer(page.inner_text("body"))]
    if phone:
        o = page.evaluate(JS_OVERFLOW)
        if o["overflow"]:
            rep["overflow"].append(f"{where}: {o['offenders']}")


def shoot(page, rep: dict, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    for scheme in ("light", "dark"):
        page.emulate_media(color_scheme=scheme)
        page.wait_for_timeout(100)
        out = SHOTS / f"v3-{name}-{scheme}.png"
        page.screenshot(path=str(out), full_page=True)
        rep["shots"].append(str(out))
    page.emulate_media(color_scheme="light")


def walk_tabs(page, rep: dict, phone: bool, shots: bool) -> None:
    ids = page.evaluate("[...document.querySelectorAll('[role=tab]')].map(t => t.dataset.tab)")
    if ids != list(TABS):
        rep["missing"].append(f"tabs in the page are {ids}, robot expects {list(TABS)}")
    if not page.evaluate(JS_TAB, "tro-ly"):
        rep["missing"].append("first tab is not Trợ lý")
    if not page.inner_text("#tb-date").strip():
        rep["missing"].append("topbar date is empty")
    top, bottom, height = page.evaluate(JS_TABBAR)
    if phone and bottom < height - 1 or not phone and top > 60:
        rep["missing"].append(f"tab bar is not {'at the bottom' if phone else 'in the top bar'} ({top}, {bottom})")
    for tab in [*list(TABS)[1:], "tro-ly"]:  # each click leaves a different tab
        press(page, rep, f"#tab-{tab}", f"tab {tab}")
        if not page.evaluate(JS_TAB, tab):
            rep["missing"].append(f"tab {tab} did not open")
        if SOON not in page.inner_text(f"#panel-{tab}"):
            rep["missing"].append(f"{tab}: no '{SOON}'")
        see(page, rep, tab, phone)
        if shots:
            shoot(page, rep, f"{tab}-{'phone' if phone else 'desktop'}")
    page.focus("#tab-tro-ly")
    page.keyboard.press("ArrowRight")
    if not page.evaluate(JS_TAB, "hoc-sinh"):
        rep["missing"].append("ArrowRight did not move to the next tab")
    press(page, rep, ".brand", "brand")
    if not page.evaluate(JS_TAB, "tro-ly"):
        rep["missing"].append("brand did not go to Trợ lý")


def walk_gear(page, rep: dict, phone: bool) -> None:
    keys = page.evaluate("[...document.querySelectorAll('[data-sys]')].map(b => b.dataset.sys)")
    if len(keys) != 4:
        rep["missing"].append(f"gear menu has {len(keys)} items, expected 4")
    for key in keys:
        press(page, rep, "#gear-btn", "gear")
        if not page.is_visible(f'[data-sys="{key}"]'):
            rep["missing"].append(f"gear menu did not show {key}")
            continue
        press(page, rep, f'[data-sys="{key}"]', f"gear item {key}")
        if SOON not in page.inner_text("#modal-root"):
            rep["missing"].append(f"gear {key}: no '{SOON}'")
        see(page, rep, f"gear {key}", phone)
        if not close_overlay(page):
            rep["missing"].append(f"gear {key}: modal did not close")


def walk_theme(page, rep: dict, base: str) -> None:
    got = {}
    for opt in ("dark", "light", "system"):
        if not page.is_visible(f'[data-theme-opt="{opt}"]'):
            press(page, rep, "#gear-btn", "gear")
        press(page, rep, f'[data-theme-opt="{opt}"]', f"theme {opt}")
        s = got[opt] = page.evaluate(JS_THEME)
        if (s["attr"], s["stored"], s["pressed"]) != (None if opt == "system" else opt, opt, [opt]):
            rep["missing"].append(f"theme {opt}: page state is {s}")
        if opt == "dark":  # the choice survives a reload
            page.reload()
            s = page.evaluate(JS_THEME)
            if (s["attr"], s["pressed"]) != ("dark", ["dark"]):
                rep["missing"].append(f"theme dark lost after reload: {s}")
    if got["dark"]["bg"] == got["light"]["bg"]:
        rep["missing"].append("dark and light look the same")
    page.emulate_media(color_scheme="dark")
    if page.evaluate(JS_THEME)["bg"] != got["dark"]["bg"]:
        rep["missing"].append("theme system does not follow a dark system")
    page.emulate_media(color_scheme="light")
    page.goto(f"{base}?theme=dark#bao-cao")
    if not page.evaluate(JS_TAB, "bao-cao") or page.evaluate(JS_THEME)["attr"] != "dark":
        rep["missing"].append("?theme=dark#bao-cao did not open Báo cáo in dark")


def walk(browser, base: str, vp_name: str, vp: dict, shots: bool) -> dict:
    rep = {"viewport": vp_name, "console_errors": [], "page_errors": [], "dead": [], "missing": [], "forbidden": [],
           "overflow": [], "shots": []}  # fmt: skip
    phone = vp is PHONE
    page = browser.new_context(viewport=vp, color_scheme="light").new_page()
    page.on(
        "console",
        lambda m: m.type == "error" and not m.text.startswith(NET_NOISE) and rep["console_errors"].append(m.text[:300]),
    )
    page.on("pageerror", lambda e: rep["page_errors"].append(str(e)[:300]))
    page.goto(base)
    if page.title() != "Trợ lý gia sư Toán":
        rep["missing"].append(f"page title is {page.title()!r}")
    if page.evaluate("U.api.get('/health')").get("status") != "ok":
        rep["missing"].append("U.api.get('/health') is not ok")
    walk_tabs(page, rep, phone, shots)
    walk_gear(page, rep, phone)
    walk_theme(page, rep, base)
    page.wait_for_timeout(500)  # late errors
    page.context.close()
    return rep


def check(url: str, args: argparse.Namespace) -> int:
    base = f"{url}v3/"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        views = [walk(browser, base, name, vp, args.shots) for name, vp in (("desktop", DESK), ("phone", PHONE))]
        browser.close()
    keys = ("console_errors", "page_errors", "dead", "missing", "forbidden", "overflow")
    summary = {k: sum(len(v[k]) for v in views) for k in keys}
    summary["ok"] = not any(summary.values())
    print(json.dumps({"page": base, "views": views, "summary": summary}, ensure_ascii=False, indent=1))
    return 0 if summary["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="app already running (its root URL); default: start one")
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--data", action="store_true", help="seed dummy bank, 2 students, 3 inbox files, 4 G1 sessions")
    args = ap.parse_args()
    if args.url:
        return check(args.url, args)
    with tutor_app(args.data) as url:
        return check(url, args)


if __name__ == "__main__":
    sys.exit(main())
