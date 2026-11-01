#!/usr/bin/env python3
"""Robot UI check for the 4-tab app at /v3/ (P5-T05).

Run: .venv/bin/python tests/ui/check_v3.py [--url http://127.0.0.1:8000/] [--data] [--shots]
Opens /v3/ at 1440 px and 390 px; walks the 4 tabs, the Ngân hàng bài tab (filters, view, edit), ⚙ menu, light/dark.
Exit 1 on any page error, app console error, dead button, horizontal overflow at 390 px or forbidden text on screen.
Without --url it starts `tutor app` on a free port with a temp data dir; --data seeds dummy bank and students and
checks the bank tab against that tutor.db (needs no --url).
"""

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

# shortcut: generic helpers are imported from check.py; P8-T03 deletes check.py and they move into this file.
from check import DESK, JS_OBSERVE, JS_OVERFLOW, NET_NOISE, PHONE, SHOTS, close_overlay, tutor_app
from playwright.sync_api import sync_playwright

TABS = ("tro-ly", "hoc-sinh", "bao-cao", "ngan-hang")
# docs/prototype/app-user/build.py FORBIDDEN, plus the word "node" and skill codes like 8DS-HSBN-02
# (problem refs end in 3 digits and may show)
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b|\b\d[A-Z]{2}-[A-Z0-9]+-\d\d\b"
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


def press(page, rep: dict, sel: str, label: str, until: str | None = None, arg=None) -> None:
    """Click and record a dead button when the DOM does not change; `until` (JS) is the result to wait for."""
    page.evaluate(JS_OBSERVE)
    try:
        page.click(sel, timeout=3000)
    except Exception as e:  # noqa: BLE001
        rep["missing"].append(f"click {label}: {str(e).splitlines()[0][:120]}")
        return
    if until:
        expect(page, rep, until, f"{label}: result did not show", arg)
    else:
        page.wait_for_timeout(100)
    if not page.evaluate("window.__robotMut + window.__robotToasts"):
        rep["dead"].append(label)


def expect(page, rep: dict, js: str, what: str, arg=None) -> bool:
    try:
        page.wait_for_function(js, arg=arg, timeout=5000)
    except Exception:  # noqa: BLE001
        rep["missing"].append(what)
        return False
    return True


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
        if (SOON in page.inner_text(f"#panel-{tab}")) == (tab == "ngan-hang"):
            rep["missing"].append(f"{tab}: '{SOON}' {'still' if tab == 'ngan-hang' else 'missing'}")
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
    for key, how in [(k, h) for k in keys for h in ("Esc", "×")]:
        label = f"gear {key} closed by {how}"
        press(page, rep, "#gear-btn", "gear")
        if not page.is_visible(f'[data-sys="{key}"]'):
            rep["missing"].append(f"gear menu did not show {key}")
            continue
        press(page, rep, f'[data-sys="{key}"]', f"gear item {key}")
        if SOON not in page.inner_text("#modal-root"):
            rep["missing"].append(f"gear {key}: no '{SOON}'")
        see(page, rep, f"gear {key}", phone)
        if how == "Esc":
            closed = close_overlay(page)
        else:
            press(page, rep, "#modal-root .icon-btn", f"modal × for {key}")
            closed = page.evaluate("!document.querySelector('#modal-root .modal')")
        if not closed:
            rep["missing"].append(f"{label}: modal did not close")
        elif (focus := page.evaluate("document.activeElement.id")) != "gear-btn":
            rep["missing"].append(f"{label}: focus is on {focus or 'the page'}, not the ⚙ button")


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


BANK_LABELS = ("Tìm", "Chủ đề", "Lớp", "Kỹ năng", "Mức", "Xoá lọc")
BANK_LEVELS = ("Tất cả", "dễ", "vừa", "khó", "chưa có mức")
NO_MATCH = "Không có bài nào khớp bộ lọc"
SAVED = "Áp dụng cho các lần chấm từ nay"
JS_COUNT_IS = "n => document.getElementById('b-count').innerText.trim() === n + ' bài khớp'"
JS_CARDS_IS = "n => document.querySelectorAll('#b-grid .bcard').length === n"
JS_LOADED = "() => (document.getElementById('b-count') || {innerText: ''}).innerText.trim() !== ''"
JS_MODAL = "() => !!document.querySelector('#modal-root .modal')"
JS_NO_MODAL = "() => !document.querySelector('#modal-root .modal')"
JS_CHECKS_GT = "n => document.querySelectorAll('#modal-body [data-sk]').length > n"
JS_ROWS_IS = "n => document.querySelectorAll('#modal-body [data-rt]').length === n"
JS_EDIT_OPEN = f"() => document.getElementById('modal-body').innerText.includes('{SAVED}')"
JS_HARD_ON = """() => document.querySelector('#modal-body [data-act="e-level"][data-v="khó"]')
  .getAttribute('aria-pressed') === 'true'"""
JS_ERR = (
    """() => { const e = document.getElementById('e-err'); return !!e && !e.hidden && e.innerText.trim() !== ''; }"""
)
# a save the server refuses with a 422 whose detail names a skill code
JS_FAIL_SAVE = """() => { window.__send = U.api.send;
  const e = Object.assign(new Error('x'), {status: 422, code: 'validation_error', detail: 'KC 8DS-HSBN-02 sai'});
  U.api.send = () => Promise.reject(e); }"""
# holds back the answer to the search "zzzq" by 1 s so a newer answer arrives first
JS_DELAY_SEARCH = """() => { window.__get = U.api.get;
  const late = p => new Promise(r => setTimeout(r, 1000)).then(() => window.__get(p));
  U.api.get = p => p.includes('q=zzzq') ? late(p) : window.__get(p); }"""
GRADE9 = "CAST(ref AS INTEGER) = 9"
EASY = "difficulty_approved_at IS NOT NULL AND delta < -0.3"
HARD = "difficulty_approved_at IS NOT NULL AND delta > 0.3"
NO_LEVEL = "difficulty_approved_at IS NULL OR delta IS NULL"
IN_TOPIC = (
    "id IN (SELECT pk.problem_id FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id WHERE COALESCE(k.parent_id, k.id) = ?)"
)
HAS_KC = "id IN (SELECT problem_id FROM problem_kc WHERE kc_id = ?)"


def scalar(data_dir: str, sql: str, *args) -> int:
    """One number from the app's tutor.db, opened read-only while the app runs."""
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(sql, args).fetchone()[0]


def problems(data_dir: str, where: str = "1", *args) -> int:
    return scalar(data_dir, f"SELECT count(*) FROM problem WHERE {where}", *args)


def bank_level(page, rep: dict, data_dir: str, level: str, where: str) -> None:
    n = problems(data_dir, where)
    press(page, rep, f'[data-act="b-level"][data-v="{level}"]', f"bank level {level}", JS_COUNT_IS, n)


def bank_filters(page, rep: dict, data_dir: str, reqs: list) -> None:
    total = problems(data_dir)
    topics = scalar(
        data_dir, "SELECT count(DISTINCT COALESCE(k.parent_id, k.id)) FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
    )
    clear = ('[data-act="b-clear"]', "bank Xoá lọc", JS_COUNT_IS, total)
    expect(page, rep, JS_COUNT_IS, f"bank: the list should say {total} bài khớp", total)
    if f"{total} bài · {topics} chủ đề" not in page.inner_text("#panel-ngan-hang .page-head"):
        rep["missing"].append(f"bank: head does not say '{total} bài · {topics} chủ đề'")
    if page.locator("#b-topic option").count() != topics + 1:
        rep["missing"].append(f"bank: topic filter should list {topics} topics")
    expect(page, rep, JS_CARDS_IS, "bank: first page is not 12 cards", 12)
    press(page, rep, '[data-act="b-more"]', "bank Xem thêm", JS_CARDS_IS, 24)
    page.select_option("#b-grade", "9")
    n = problems(data_dir, GRADE9)
    expect(page, rep, JS_COUNT_IS, f"bank: Lớp 9 should match {n}", n)
    bank_level(page, rep, data_dir, "dễ", f"({GRADE9}) AND ({EASY})")
    off = [t for t in page.locator("#b-grid .bcard").all_inner_texts() if "lớp 9" not in t or "dễ" not in t]
    if off:
        rep["missing"].append(f"bank: {len(off)} cards are not Lớp 9 + dễ")
    bank_level(page, rep, data_dir, "none", NO_LEVEL)
    if not problems(data_dir, NO_LEVEL) and NO_MATCH not in page.inner_text("#panel-ngan-hang"):
        rep["missing"].append(f"bank: no '{NO_MATCH}'")
    press(page, rep, *clear)
    if [page.input_value(f"#b-{k}") for k in ("q", "grade", "topic", "skill")] != [""] * 4:
        rep["missing"].append("bank: Xoá lọc left a filter set")
    page.select_option("#b-topic", index=1)
    tid = int(page.input_value("#b-topic"))
    n = problems(data_dir, IN_TOPIC, tid)
    expect(page, rep, JS_COUNT_IS, f"bank: topic {tid} should match {n}", n)
    page.select_option("#b-skill", index=1)
    kid = int(page.input_value("#b-skill"))
    n = problems(data_dir, HAS_KC, kid)
    expect(page, rep, JS_COUNT_IS, f"bank: skill {kid} should match {n}", n)
    press(page, rep, *clear)
    seen = len(reqs)
    page.type("#b-q", "zzz", delay=60)
    page.wait_for_timeout(900)
    sent = [u for _, u, _ in reqs[seen:] if "/api/bank/problems?" in u]
    if len(sent) != 1 or "q=zzz" not in sent[0]:
        rep["missing"].append(f"bank: typing 3 letters sent {len(sent)} searches, want 1 after the pause")
    expect(page, rep, JS_COUNT_IS, "bank: 'zzz' should match 0", 0)
    page.fill("#b-q", "9DS-HPT")
    n = problems(data_dir, "ref LIKE ?", "9DS-HPT%")
    expect(page, rep, JS_COUNT_IS, f"bank: ref prefix 9DS-HPT should match {n}", n)
    press(page, rep, *clear)
    page.evaluate(JS_DELAY_SEARCH)
    page.fill("#b-q", "zzzq")
    page.wait_for_timeout(450)
    press(page, rep, *clear)
    page.wait_for_timeout(1300)
    if page.inner_text("#b-count").strip() != f"{total} bài khớp":
        rep["missing"].append("bank: a late answer overwrote the newer list")
    page.evaluate("() => { U.api.get = window.__get; }")


def bank_edit(page, rep: dict, phone: bool, data_dir: str, reqs: list) -> None:
    bank_level(page, rep, data_dir, "dễ", EASY)
    card = page.locator("#b-grid .bcard").first
    pid, ref = card.get_attribute("data-pid"), card.locator(".ref").first.inner_text()
    one = f'#b-grid .bcard[data-pid="{pid}"]'
    press(page, rep, f"{one} .ref", f"bank open {ref}", JS_MODAL)
    try:
        page.wait_for_selector("#modal-root mjx-container", timeout=20000)
    except Exception:  # noqa: BLE001
        rep["missing"].append("bank view: no mjx-container, MathJax did not run")
    page.click("#modal-root summary")
    modal = page.inner_text("#modal-root")
    rep["missing"] += [
        f"bank view: no '{w}'"
        for w in (ref, "Đề bài", "Lời giải", "Cách chấm", "Ý 1", "Tổng", "Nguồn")
        if w not in modal
    ]
    if page.locator("#modal-root mjx-merror, #modal-root [data-mjx-error]").count():
        rep["missing"].append("bank view: MathJax error on screen")
    see(page, rep, f"bank view {ref}", phone)
    press(page, rep, '[data-act="b-edit"]', "bank Sửa", JS_EDIT_OPEN)
    boxes, rows = page.locator("#modal-body [data-sk]").count(), page.locator("#modal-body [data-rt]").count()
    press(page, rep, '[data-act="e-all"]', "bank hiện kỹ năng chủ đề khác", JS_CHECKS_GT, boxes)
    press(page, rep, '[data-act="e-radd"]', "bank Thêm ý", JS_ROWS_IS, rows + 1)
    press(page, rep, f'[data-act="e-rdel"][data-i="{rows}"]', "bank × ý", JS_ROWS_IS, rows)
    press(page, rep, '[data-act="e-level"][data-v="khó"]', "bank mức khó", JS_HARD_ON)
    see(page, rep, f"bank edit {ref}", phone)
    page.evaluate(JS_FAIL_SAVE)
    press(page, rep, '[data-act="e-save"]', "bank Lưu khi server từ chối", JS_ERR)
    err = page.evaluate("() => (document.getElementById('e-err') || {innerText: ''}).innerText")
    if any(w in err for w in ("KC", "8DS", "validation")):
        rep["missing"].append("bank edit: a server error shows its code or detail")
    page.evaluate("() => { U.api.send = window.__send; }")
    press(page, rep, '[data-act="e-save"]', "bank Lưu thay đổi", JS_NO_MODAL)
    patches = [(u, b) for m, u, b in reqs if m == "PATCH"]
    if [(u.rsplit("/", 1)[-1], json.loads(b)) for u, b in patches] != [(pid, {"level": "khó"})]:
        rep["missing"].append(f"bank edit: PATCH requests are {patches}, want only level for {pid}")
    expect(page, rep, f"() => document.querySelector('{one}').innerText.includes('khó')", "bank edit: card is not khó")
    expect(
        page, rep, f"() => document.getElementById('toasts').innerText.includes('{SAVED}')", f"bank edit: no '{SAVED}'"
    )
    if problems(data_dir, f"id = ? AND ({HARD})", pid) != 1:
        rep["missing"].append(f"bank edit: tutor.db does not have {ref} as khó")
    see(page, rep, f"bank after save {ref}", phone)
    press(page, rep, "#b-grid .bcard:nth-child(2) .ref", "bank open 2nd", JS_MODAL)
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "bank view: Esc did not close")
    if "ref" not in page.evaluate("document.activeElement.className"):
        rep["missing"].append("bank view: focus did not return to the card")


def walk_bank(page, rep: dict, phone: bool, data_dir: str | None) -> None:
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    press(page, rep, "#tab-ngan-hang", "tab ngan-hang")
    loaded = expect(page, rep, JS_LOADED, "bank: the list did not load")
    text = page.inner_text("#panel-ngan-hang")
    rep["missing"] += [f"bank: no filter '{w}'" for w in BANK_LABELS if w not in text]
    rep["missing"] += [f"bank: no level '{w}'" for w in BANK_LEVELS if w not in text]
    see(page, rep, "ngan-hang", phone)
    if data_dir and loaded:
        bank_filters(page, rep, data_dir, reqs)
        bank_edit(page, rep, phone, data_dir, reqs)
    elif loaded and not data_dir and ("0 bài khớp" not in text or NO_MATCH not in text):
        rep["missing"].append(f"bank: an empty bank should say '0 bài khớp' and '{NO_MATCH}'")


def walk(browser, base: str, vp_name: str, vp: dict, shots: bool, data_dir: str | None) -> dict:
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
    walk_bank(page, rep, phone, data_dir)
    walk_gear(page, rep, phone)
    walk_theme(page, rep, base)
    page.wait_for_timeout(500)  # late errors
    page.context.close()
    return rep


def check(url: str, args: argparse.Namespace) -> int:
    base = f"{url}v3/"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        data_dir = getattr(url, "data_dir", None) if args.data else None
        views = [walk(browser, base, n, vp, args.shots, data_dir) for n, vp in (("desktop", DESK), ("phone", PHONE))]
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
