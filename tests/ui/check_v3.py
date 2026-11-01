#!/usr/bin/env python3
"""Robot UI check for the 4-tab app at /v3/ (P5-T05).

Run: .venv/bin/python tests/ui/check_v3.py [--url http://127.0.0.1:8000/] [--data] [--shots]
Opens /v3/ at 1440 px and 390 px; walks the 4 tabs, the Ngân hàng bài tab (filters, view, edit, import), ⚙ menu,
light/dark.
Exit 1 on any page error, app console error, dead button, horizontal overflow at 390 px or forbidden text on screen.
Without --url it starts `tutor app` on a free port with a temp data dir; --data seeds dummy bank and students and
checks the bank tab against that tutor.db and imports tests/fixtures/bank/import-mix.tex (needs no --url).
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
# holds back the first-page answer to a level filter by 1 s, so Xem thêm can be clicked meanwhile
JS_DELAY_FILTER = """() => { window.__get = U.api.get;
  const late = r => new Promise(ok => setTimeout(() => ok(r), 1000));
  const first = p => p.includes('offset=0') && p.includes('level=');
  U.api.get = p => { const r = window.__get(p); return first(p) ? late(r) : r; }; }"""
# every bank list request of a new page waits 2.5 s, so the teacher can type before the first answer
JS_SLOW_LIST = """(() => { let a; Object.defineProperty(window, 'api', { configurable: true, get: () => a, set: v => {
  a = v; const g = v.get, wait = () => new Promise(r => setTimeout(r, 2500));
  v.get = p => p.includes('view=teacher') ? wait().then(() => g(p)) : g(p); } }); })();"""
JS_ROOT_HAS = "t => document.getElementById('modal-root').innerText.includes(t)"
JS_ENABLED = (
    """() => { const b = document.querySelector('#modal-foot [data-act="imp-save"]'); return !!b && !b.disabled; }"""
)
JS_HEAD_TOTAL = "n => document.getElementById('b-head').innerText.startsWith(n + ' bài ·')"
JS_ROWS_N = "n => document.querySelectorAll('#modal-body .imp-row').length === n"
# a second tab filled the last gaps first: the save is refused with 409 undecided_items
JS_RACE_RESUME = """() => { window.__send = U.api.send;
  const e = Object.assign(new Error('x'), {status: 409, code: 'undecided_items', detail: {n: 2}});
  U.api.send = (m, p, b) => p.endsWith('/resume') ? Promise.reject(e) : window.__send(m, p, b); }"""
GRADE9 = "CAST(ref AS INTEGER) = 9"
EASY = "difficulty_approved_at IS NOT NULL AND delta < -0.3"
HARD = "difficulty_approved_at IS NOT NULL AND delta > 0.3"
NO_LEVEL = "difficulty_approved_at IS NULL OR delta IS NULL"
IN_TOPIC = (
    "id IN (SELECT pk.problem_id FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id WHERE COALESCE(k.parent_id, k.id) = ?)"
)
HAS_KC = "id IN (SELECT problem_id FROM problem_kc WHERE kc_id = ?)"
MIX = Path(__file__).resolve().parents[1] / "fixtures" / "bank" / "import-mix.tex"
ONE_PROBLEM = (
    "% Bài <u>thử</u>\n\\begin{problem}[8DS-BAD-001]\nCho $x = 1$.\n\n"
    "\\begin{solution}\nĐáp số: $x = 1$.\n\\end{solution}\n\\end{problem}\n"
)
SUMMARY = "5 bài · 1 đã có kỹ năng và mức · 3 cần chọn"
SAVE = '#modal-foot [data-act="imp-save"]'


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
    grade9_none = (
        f"({GRADE9}) AND ({NO_LEVEL})"  # Lớp 9 is still set; an earlier import may have left lớp 8 without a level
    )
    bank_level(page, rep, data_dir, "none", grade9_none)
    if not problems(data_dir, grade9_none) and NO_MATCH not in page.inner_text("#panel-ngan-hang"):
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


def bank_races(page, rep: dict, data_dir: str) -> None:
    """Xem thêm while a newer filter or search is still loading must not mix two result sets."""
    total, easy = problems(data_dir), problems(data_dir, EASY)
    clear = ('[data-act="b-clear"]', "bank Xoá lọc", JS_COUNT_IS, total)
    press(page, rep, *clear)
    page.evaluate(JS_DELAY_FILTER)
    page.click('[data-act="b-level"][data-v="dễ"]')
    page.click('[data-act="b-more"]')
    expect(page, rep, JS_COUNT_IS, f"bank: dễ should match {easy}", easy)
    page.wait_for_timeout(300)
    cards = page.locator("#b-grid .bcard").all_inner_texts()
    if len(cards) != min(12, easy) or any("dễ" not in t for t in cards):
        rep["missing"].append(f"bank: Xem thêm during a level filter left {len(cards)} cards, not {min(12, easy)} dễ")
    page.evaluate("() => { U.api.get = window.__get; }")
    press(page, rep, *clear)
    page.fill("#b-q", "9DS-HPT")
    page.click('[data-act="b-more"]')
    n = problems(data_dir, "ref LIKE ?", "9DS-HPT%")
    expect(page, rep, JS_COUNT_IS, f"bank: ref prefix 9DS-HPT should match {n}", n)
    page.wait_for_timeout(300)
    refs = page.locator("#b-grid .bcard .ref").all_inner_texts()
    if len(refs) != min(12, n) or not all(r.startswith("9DS-HPT") for r in refs):
        rep["missing"].append(f"bank: Xem thêm during a search left {len(refs)} cards, not {min(12, n)} for 9DS-HPT")
    press(page, rep, *clear)
    topics = scalar(
        data_dir, "SELECT count(DISTINCT COALESCE(k.parent_id, k.id)) FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
    )
    late = page.context.new_page()
    late.on("pageerror", lambda e: rep["page_errors"].append(str(e)[:300]))
    late.add_init_script(JS_SLOW_LIST)
    late.goto(f"{page.url.split('#')[0]}#ngan-hang", wait_until="commit")
    late.fill("#b-q", "zzz")
    expect(late, rep, JS_COUNT_IS, "bank: typing before the first answer should end at 0 bài khớp", 0)
    if f"{total} bài · {topics} chủ đề" not in late.inner_text("#panel-ngan-hang .page-head"):
        rep["missing"].append("bank: typing before the first answer left a wrong head")
    late.close()


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


def bank_inbox(data_dir: str, phone: bool) -> tuple[str, str]:
    """Put this viewport's two import files in data/inbox/bank/ and return their names: one to import, one to break.

    The phone gets its own refs because the desktop import leaves import-mix.tex fully imported."""
    folder = Path(data_dir, "inbox", "bank")
    folder.mkdir(parents=True, exist_ok=True)
    mix, bad = ("import-mix-2.tex", "bad<i>-2.tex") if phone else ("import-mix.tex", "bad<i>.tex")
    text = MIX.read_text(encoding="utf-8")
    (folder / mix).write_text(text.replace("8DS-NEW-", "8DS-NEX-") if phone else text, encoding="utf-8")
    (folder / bad).write_text(ONE_PROBLEM, encoding="utf-8")
    return mix, bad


def bank_import(page, rep: dict, phone: bool, data_dir: str, reqs: list, files: tuple[str, str]) -> None:
    mix, bad = files
    ref = lambda n: f"8DS-{'NEX' if phone else 'NEW'}-{n:03d}"  # noqa: E731
    row = lambda r: f'#modal-body [data-row="{r}"]'  # noqa: E731
    file_row = lambda name: f'#modal-body .file-row:has-text("{name}")'  # noqa: E731
    before, start = problems(data_dir), len(rep["missing"])
    press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới", JS_ROOT_HAS, mix)
    if len(rep["missing"]) > start:  # no point in the later steps
        return
    if "<u>thử</u>" not in (listed := page.inner_text("#modal-body")) or bad not in listed:
        rep["missing"].append("bank import: a file name or title with HTML is not shown as plain text")
    see(page, rep, "bank import files", phone)
    Path(data_dir, "inbox", "bank", bad).write_text("% Hỏng\nkhông còn bài nào\n", encoding="utf-8")
    press(page, rep, f'{file_row(bad)} [data-act="imp-read"]', f"bank đọc {bad}", JS_ROOT_HAS, f"Không nạp được {bad}")
    if not page.locator("#modal-body .callout-crit").count():
        rep["missing"].append("bank import: a refused file has no red box")
    see(page, rep, "bank import refused", phone)
    press(page, rep, '[data-act="imp-back"]', "bank Chọn file khác", JS_ROOT_HAS, mix)
    press(page, rep, f'{file_row(mix)} [data-act="imp-read"]', f"bank đọc {mix}", JS_ROOT_HAS, SUMMARY)
    if len(rep["missing"]) > start:
        return
    modal = page.inner_text("#modal-root")
    rep["missing"] += [
        f"bank import: no '{w}'"
        for w in ("Còn 2 bài chưa chọn kỹ năng", "Nhãn kỹ năng ghi trong file không có trong danh mục")
        if w not in modal
    ]
    if not page.locator(SAVE).is_disabled(timeout=2000):
        rep["missing"].append("bank import: Lưu vào ngân hàng is on while 2 bài lack a skill")
    see(page, rep, "bank import preview", phone)
    expect(page, rep, JS_ROWS_N, "bank import: Cần chọn should list 3 rows", 3)
    press(page, rep, '[data-act="imp-only"][data-v="0"]', "bank import Tất cả", JS_ROWS_N, 8)
    rep["missing"] += [
        f"bank import: Tất cả has no '{w}'"
        for w in ("thiếu lời giải", "đã có")
        if w not in page.inner_text("#modal-body")
    ]
    see(page, rep, "bank import all", phone)
    press(page, rep, '[data-act="imp-only"][data-v="1"]', "bank import Cần chọn", JS_ROWS_N, 3)
    seen = len(reqs)
    pick = lambda n, i: page.select_option(f"{row(ref(n))} select", index=i)  # noqa: E731
    pick(2, 1)
    expect(page, rep, JS_ROOT_HAS, "bank import: no 'Còn 1 bài chưa chọn kỹ năng'", "Còn 1 bài chưa chọn kỹ năng")
    pick(3, 1)
    press(page, rep, f'{row(ref(4))} [data-act="imp-level"][data-v="vừa"]', "bank import mức vừa", JS_ENABLED)
    want = {
        ref(2): {"kc_ids": [int(page.input_value(f"{row(ref(2))} select"))]},
        ref(3): {"kc_ids": [int(page.input_value(f"{row(ref(3))} select"))]},
        ref(4): {"level": "vừa"},
    }  # fmt: skip
    puts = [json.loads(b) for m, _, b in reqs[seen:] if m == "PUT"]
    if len(puts) != 2 or puts[-1] != {"items": want}:
        rep["missing"].append(f"bank import: decisions sent are {puts}, want 2 debounced PUTs ending in {want}")
    page.evaluate(JS_RACE_RESUME)
    press(page, rep, SAVE, "bank Lưu khi server báo còn thiếu", JS_ROOT_HAS, "Còn 2 bài chưa chọn kỹ năng")
    if not page.locator(SAVE).is_disabled(timeout=2000):
        rep["missing"].append("bank import: a 409 left Lưu vào ngân hàng on")
    page.evaluate("() => { U.api.send = window.__send; }")
    pick(2, 2)
    expect(page, rep, JS_ENABLED, "bank import: a new choice did not bring the count back")
    press(page, rep, SAVE, "bank Lưu vào ngân hàng", JS_ROOT_HAS, "Đã thêm 4 bài vào ngân hàng")
    resumes = [u for m, u, _ in reqs if m == "POST" and u.endswith("/resume")]
    if len(resumes) != 1:
        rep["missing"].append(f"bank import: {len(resumes)} resume calls, want 1")
    if (added := problems(data_dir) - before) != 4:
        rep["missing"].append(f"bank import: tutor.db has {added} new problems, receipt says 4")
    if not problems(data_dir, "ref = ? AND delta = 0 AND difficulty_approved_at IS NOT NULL", ref(4)):
        rep["missing"].append(f"bank import: {ref(4)} is not vừa in tutor.db")
    if "1 bài đã có trong ngân hàng" not in page.inner_text("#modal-body"):
        rep["missing"].append("bank import: the receipt does not say 1 bài đã có")
    see(page, rep, "bank import saved", phone)
    press(page, rep, '[data-act="imp-show"]', "bank Xem các bài mới", JS_NO_MODAL)
    if not (tid := page.input_value("#b-topic")):
        rep["missing"].append("bank import: Xem các bài mới left the topic filter empty")
    else:
        n = problems(data_dir, IN_TOPIC, int(tid))
        expect(page, rep, JS_COUNT_IS, f"bank import: topic {tid} should match {n}", n)
    expect(page, rep, JS_HEAD_TOTAL, f"bank import: head should say {problems(data_dir)} bài", problems(data_dir))
    press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới lần 2", JS_ROOT_HAS, mix)
    if len(rep["missing"]) > start:
        return
    done = page.locator(f"{file_row(mix)} button")
    if done.inner_text(timeout=2000).strip() != "Đã nạp" or not done.is_disabled():
        rep["missing"].append(f"bank import: {mix} is not a disabled Đã nạp after the import")
    if page.locator(f"{file_row(bad)} button").inner_text(timeout=2000).strip() != "Không có bài":
        rep["missing"].append(f"bank import: the broken {bad} is not Không có bài")
    see(page, rep, "bank import files after", phone)
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "bank import: Esc did not close")
    if page.evaluate("document.activeElement.dataset.act") != "b-import":
        rep["missing"].append("bank import: focus did not return to Nạp bài mới")


def walk_bank(page, rep: dict, phone: bool, data_dir: str | None, files: tuple[str, str] | None) -> None:
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
        bank_races(page, rep, data_dir)
        bank_edit(page, rep, phone, data_dir, reqs)
        bank_import(page, rep, phone, data_dir, reqs, files)
    elif loaded and not data_dir and ("0 bài khớp" not in text or NO_MATCH not in text):
        rep["missing"].append(f"bank: an empty bank should say '0 bài khớp' and '{NO_MATCH}'")
    if loaded and not data_dir:
        press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới", JS_ROOT_HAS, "Chưa có file .tex nào")
        page.keyboard.press("Escape")
        expect(page, rep, JS_NO_MODAL, "bank import: Esc did not close")


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
    files = bank_inbox(data_dir, phone) if data_dir else None
    page.goto(base)
    if page.title() != "Trợ lý gia sư Toán":
        rep["missing"].append(f"page title is {page.title()!r}")
    if page.evaluate("U.api.get('/health')").get("status") != "ok":
        rep["missing"].append("U.api.get('/health') is not ok")
    walk_tabs(page, rep, phone, shots)
    walk_bank(page, rep, phone, data_dir, files)
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
