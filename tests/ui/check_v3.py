#!/usr/bin/env python3
"""Robot UI check for the 4-tab app at /v3/ (P5-T05).

Run: .venv/bin/python tests/ui/check_v3.py [--url http://127.0.0.1:8000/] [--data] [--shots]
Opens /v3/ at 1440 px and 390 px; walks the 4 tabs, the Trợ lý chat tab (reminders, @, stream, cards, 📎, retry,
the G1 grading card, the G4 worksheet panel), the Ngân hàng bài tab (filters, view, edit, import), ⚙ menu, light/dark.
Exit 1 on any page error, app console error, dead button, horizontal overflow at 390 px or forbidden text on screen.
Without --url it starts `tutor app` on a free port with a temp data dir; --data seeds dummy bank and students and
checks the chat and bank tabs against that tutor.db and imports tests/fixtures/bank/import-mix.tex (needs no --url).
It also prints db_changes (tutor.db row counts around each step; only commit-button steps may change them) and
scans llm.jsonl and the chat logs for student names.
"""

import argparse
import functools
import json
import re
import sqlite3
import sys
import unicodedata
from contextlib import closing, contextmanager
from pathlib import Path

# shortcut: generic helpers are imported from check.py; P8-T03 deletes check.py and they move into this file.
from check import (
    DESK,
    FIX,
    JS_OBSERVE,
    JS_OVERFLOW,
    NET_NOISE,
    PHONE,
    PREVIEW_TID,
    SHOTS,
    api,
    close_overlay,
    tutor_app,
)
from playwright.sync_api import sync_playwright

from tutor.db.repo import TABLES

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
        real = tab in ("tro-ly", "ngan-hang")
        if (SOON in page.inner_text(f"#panel-{tab}")) == real:
            rep["missing"].append(f"{tab}: '{SOON}' {'still' if real else 'missing'}")
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


PEOPLE = ("Nguyễn Văn An", "Trần Thị Bình")
ARCHIVED = "Lê Văn Cường"  # HS-03, archived: its code still shows as the name
HS_CODE = re.compile(r"\bHS-\d")
NO_WORK = "Không có việc nào đang chờ thầy/cô."
SAVED_NOTHING = "Mình chưa lưu gì cả"
ERR_BUBBLE = "Chưa trả lời được, thử lại"
STOPPED = "Mình dừng sau 8 lượt tra cứu, thầy/cô hỏi hẹp hơn giúp mình nhé."
SEND = '[data-act="c-send"]'
MSGS = "**/api/assistant/messages"
JS_REPLIED = """n => document.querySelectorAll('#chat-msgs .msg').length > n
  && !document.querySelector('.asst.is-busy')"""
JS_LAST_BOT = """() => { const b = [...document.querySelectorAll('#chat-msgs .msg-bot .bubble')];
  return b.length ? b.at(-1).innerText : ''; }"""
JS_LIST_HAS = "() => document.querySelectorAll('#conv-list .conv-item').length > 0"
JS_IDLE = "() => !document.querySelector('.asst.is-busy')"
JS_RETRY = "() => !!document.querySelector('#chat-msgs .bubble-err [data-act=\"c-retry\"]')"
JS_SOL_OPEN = "() => !document.querySelector('#chat-msgs .pcard .sol').hidden"
JS_TWO_TEX = "() => document.querySelectorAll('#chat-msgs .pcard mjx-container').length >= 2"
JS_CARDS_OPEN = "() => !!document.querySelector('.remind-cards')"
JS_SUGGEST = "() => !!document.querySelector('.suggest')"
JS_DRAWER = "() => !!document.querySelector('.convs.open')"
JS_FILES = "() => document.querySelectorAll('#modal-body .file-row').length >= 5"
JS_POP = "() => document.querySelectorAll('#mention-pop .mention-opt').length > 0"
JS_N_MSGS = "n => document.querySelectorAll('#chat-msgs .msg').length === n"
# the stream is fed by hand: the page shows only what the robot emits
JS_FEED = """() => { window.__ndjson = U.ndjson;
  U.ndjson = (path, body, onEvent) => new Promise(done => { window.__emit = onEvent; window.__end = done; }); }"""
JS_UNFEED = "() => { U.ndjson = window.__ndjson; }"
JS_ASK_GRADE = """() => { const c = document.querySelector('.ask-grade'); if (!c) return null;
  const s = c.querySelector('select');
  return [s.options[s.selectedIndex].text, c.querySelector('input[type=date]').value,
    c.querySelector('[data-act="c-grade"]').disabled]; }"""
NOT_FOUND = {"error": {"code": "not_ready", "message": "x", "detail": {"reason": "x"}}}
# G1 threads of the seeded sessions (check.add_students) and of the file 📎 grades for real on the desktop
G_S01, G_S06, G_S04, G_NEW = "g1-hs01-20261020", "g1-hs01-20261022", "g1-hs02-20261023", "g1-hs01-20261025"
LOCKED = f"Duyệt buổi 20/10 của {PEOPLE[0]} trước (tiến bộ tính theo thứ tự ngày)"
LEFT_5 = "Còn 5 lỗi chưa chọn Đúng / Sửa / Bỏ"
SIG_CHANGED = "Kết quả xem trước vừa thay đổi, xem lại rồi bấm Lưu kết quả"
FAILED_WORDS = "Mất kết nối khi đang chấm bài 3. Bài làm vẫn còn nguyên, chưa có gì được lưu."
GONE = "Việc này đã xong"
NEW_CODE, NEW_KIND = "computational.copy_error", "Chép sai số hoặc biểu thức từ đề / dòng trước"
ADDED = "robot: quên đổi dấu khi chuyển vế"
OPEN_FORM = "Bấm Thêm lỗi hoặc Thôi trước"
EVIL = r"$\href{javascript:alert(1)}{x}$"  # student LaTeX; only MathJax's safe extension stops \href
# the model only ever sees HS-xx, so its text can hold one; boxes show the name, PUTs carry the code (C-40)
CODED, NAMED = "Em HS-01 quên đổi dấu ở bước cuối", f"Em {PEOPLE[0]} quên đổi dấu ở bước cuối"
JS_HOST_SEL = """([t, s]) => !!document.querySelector(`.card-host[data-thread="${t}"] ${s}`)"""
JS_HOST_HAS = """([t, w]) => { const h = document.querySelector(`.card-host[data-thread="${t}"]`);
  return !!h && h.innerText.includes(w); }"""
JS_HOST_NO = """([t, s]) => !document.querySelector(`.card-host[data-thread="${t}"] ${s}`)"""
JS_ON = "s => { const b = document.querySelector(s); return !!b && !b.disabled; }"
JS_OFF = "s => { const b = document.querySelector(s); return !!b && b.disabled; }"
JS_TOAST_HAS = "t => document.getElementById('toasts').innerText.includes(t)"
JS_TOAST_NO = "t => !document.getElementById('toasts').innerText.includes(t)"
JS_PRESSED = "s => document.querySelector(s)?.getAttribute('aria-pressed') === 'true'"
JS_BOXES = "els => els.map(e => e.value)"
JS_HREF_READY = r"() => MathJax.tex2svgPromise('\\href{x}{y}').then(() => true)"
JS_LIVE_LINKS = """() => document.querySelectorAll(
  '#panel-tro-ly [href^="javascript:" i], #panel-tro-ly [*|href^="javascript:" i]').length"""


def last_bot(page) -> str:
    return page.evaluate(JS_LAST_BOT)


def msgs(page) -> int:
    return page.locator("#chat-msgs .msg").count()


def posts(reqs: list) -> list:
    return [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/api/assistant/messages")]


def say(page, rep: dict, text: str) -> str:
    """Type a plain message, press Enter, wait for the finished answer; returns its text."""
    n = msgs(page)
    page.fill("#chat-input", text)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, f"chat: no answer to {text!r}", n)
    return last_bot(page)


def pick_mention(page, rep: dict, before: str, query: str, who: str) -> None:
    """Type `before@query`, ArrowDown, Enter: the box must then start with `before@who`."""
    page.fill("#chat-input", f"{before}@{query}")
    expect(page, rep, JS_POP, "chat: @ shows no list")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    if not page.input_value("#chat-input").startswith(f"{before}@{who}"):
        rep["missing"].append(f"chat: @ pick left {page.input_value('#chat-input')!r}, want @{who}")


def db_state(data_dir: str) -> tuple:
    """Rows in every tutor.db table, and the saved decisions of every thread (checkpoints.db)."""
    rows = [scalar(data_dir, f"SELECT count(*) FROM {t}") for t in TABLES]
    with closing(sqlite3.connect(f"{Path(data_dir, 'checkpoints.db').as_uri()}?mode=ro", uri=True)) as con:
        return rows, con.execute("SELECT thread_id, decisions_json FROM tutor_thread ORDER BY 1").fetchall()


# Row counts of every tutor.db table around each walk step (db_changes). A step changes nothing, bar `may` = table ->
# the exact row delta (Chấm bài này starts grading: transaction ① adds one session row, status running).
# A commit-button step may change the tables of its `commit` list, all taken from the backend's writes
# (UPDATEs of existing rows are not row counts).
# `last` = the counts when the previous step ended, so a change between two steps is caught too.
LEDGER: dict = {"dir": None, "log": [], "last": None, "depth": 0}
START_GRADING = {"session": 1}  # repo.commit_session_start, db/repo.py:748
SAVE_RESULT = ("rubric", "attempt", "mistake", "skill_event", "skill_state", "misconception_log")
# Lưu kết quả -> repo.commit_session (session.py:545): rubric db/repo.py:922, attempt :928, mistake :803 (via
# _insert_mistake), _write_profile skill_event :870, skill_state :876, misconception_log :884; session is only
# UPDATEd :940
SAVE_SHEET = ("recommendation",)  # Tạo phiếu -> repo.commit_worksheet (worksheet.py:248): UPDATE :976, INSERT :979
SAVE_LABELS = ("problem_kc", "rubric")
# bank Lưu thay đổi -> PATCH -> repo.update_problem_labels (api/bank.py:85): problem_kc :612-614, rubric :625;
# problem is only UPDATEd :620
SAVE_IMPORT = ("problem", "problem_kc", "rubric")
# bank Lưu vào ngân hàng -> repo.import_bank (graphs/bank.py:236) -> _insert_problem: problem :479, problem_kc :484,
# rubric :488
SEED_LOG = FIX.parent / "llm.jsonl"  # check.seed() copies it to logs/llm.jsonl: the app's own calls come after it
# steps that must move rows, or the counts are blind (the Sửa save of a bank problem may only update a row)
MOVES_ROWS = {"chat_attach", "grade_save", "ws_create", "ws_replace", "bank_import"}


def counts(data_dir: str) -> dict:
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


def moved(a: dict, b: dict) -> dict:
    return {t: [a[t], b[t]] for t in TABLES if a[t] != b[t]}


@contextmanager
def step(rep: dict, name: str, commit: tuple = (), may: dict | None = None):
    if not LEDGER["dir"] or LEDGER["depth"]:  # no --data, or a step inside a step: the outer one counts
        yield
        return
    before = counts(LEDGER["dir"])
    if gap := moved(LEDGER["last"], before):
        rep["missing"].append(f"db: rows changed before {name}, outside any step: {gap}")
    LEDGER["depth"] = 1
    try:
        yield
    finally:
        LEDGER["depth"] = 0
        LEDGER["last"] = after = counts(LEDGER["dir"])
        changed = moved(before, after)
        LEDGER["log"].append({"view": rep["viewport"], "step": name, "commit": bool(commit), "changed": changed})
        extra = {t: v for t, v in changed.items() if t not in commit and (may or {}).get(t) != v[1] - v[0]}
        if extra:
            rep["missing"].append(f"db: {name} changed rows beyond its button ({list(commit)}, {may or {}}): {extra}")


def counted(commit: tuple = (), may: dict | None = None):
    """Run a walk step (page, rep, ...) inside `step`, named after the function."""

    def wrap(fn):
        @functools.wraps(fn)
        def run(page, rep, *args, **kw):
            with step(rep, fn.__name__, commit, may):
                return fn(page, rep, *args, **kw)

        return run

    return wrap


def see_chat(page, rep: dict, where: str, phone: bool) -> None:
    see(page, rep, where, phone)
    rep["forbidden"] += [f"{where}: {m.group(0)}" for m in HS_CODE.finditer(page.inner_text("#panel-tro-ly"))]
    boxes = page.eval_on_selector_all("#panel-tro-ly textarea, #panel-tro-ly input", JS_BOXES)  # inner_text skips them
    rep["forbidden"] += [f"{where} (box): {m.group(0)}" for v in boxes for m in HS_CODE.finditer(v)]


def new_chat(page, rep: dict, phone: bool) -> None:
    """Mới sits in the conversation list, which is a drawer on the phone."""
    if phone:
        press(page, rep, "#conv-toggle", "chat ☰ Hội thoại", JS_DRAWER)
    press(page, rep, '[data-act="c-new"]', "chat Mới", JS_SUGGEST)


@counted()
def chat_basics(page, rep: dict, phone: bool, data_dir: str | None, root: str) -> bool:
    """Reminders, badge, welcome buttons; False when the tab has no chat to walk."""
    js = "() => (document.getElementById('remind') || {innerText: ''}).innerText.trim() !== ''"
    if not expect(page, rep, js, "chat: no reminder area"):
        return False
    badge = page.locator("#badge-tro-ly")
    if not data_dir:
        if NO_WORK not in page.inner_text("#remind"):
            rep["missing"].append(f"chat: an empty queue should say '{NO_WORK}'")
        if not badge.is_hidden():
            rep["missing"].append("chat: the Trợ lý badge shows with nothing waiting")
    else:
        n = api(root, "GET", "/assistant/pending")["counts"]["assistant"]
        if (page.locator(".remind-cards").count() == 0) != phone:
            rep["missing"].append(f"chat: reminder cards should be {'folded' if phone else 'open'} at first")
        if phone:
            press(page, rep, '[data-act="c-remind"]', "chat Xem việc chờ", JS_CARDS_OPEN)
        text = page.inner_text("#remind")
        rep["missing"] += [f"chat: reminder has no '{w}'" for w in PEOPLE if w not in text]
        if HS_CODE.search(text):
            rep["missing"].append("chat: a reminder shows an HS code")
        if not n or badge.inner_text().strip() != str(n):
            rep["missing"].append(f"chat: badge says {badge.inner_text()!r}, pending.counts.assistant is {n}")
    want = 6 if data_dir else 2
    if page.locator(".suggest .btn").count() != want:
        rep["missing"].append(f"chat: a new conversation should offer {want} suggestion buttons")
    see_chat(page, rep, "chat start", phone)
    return True


@counted()
def chat_cut_code(page, rep: dict, phone: bool) -> None:
    """A code cut between deltas or by a lost stream, and an archived code, never show raw (Review Focus 1).

    The stream is fed by hand, so Gửi and Enter can also be checked while the answer is still coming."""
    page.evaluate(JS_FEED)
    page.fill("#chat-input", "thử")
    page.press("#chat-input", "Enter")
    page.fill("#chat-input", "x")  # typed while the answer comes: Gửi stays off and Enter sends nothing
    if not page.locator(SEND).is_disabled():
        rep["missing"].append("chat: Gửi stayed on while the answer comes")
    page.press("#chat-input", "Enter")
    if page.input_value("#chat-input") != "x":
        rep["missing"].append("chat: Enter sent a second message while the answer comes")
    page.fill("#chat-input", "")
    emit = lambda ev: page.evaluate("ev => window.__emit(ev)", ev)  # noqa: E731
    emit({"type": "start", "conversation_id": "2026-01-01-1", "message_id": "m2"})
    emit({"type": "text", "delta": "Hồ sơ của HS-"})
    if "HS-" in last_bot(page):
        rep["missing"].append(f"chat: a code cut after 'HS-' shows: {last_bot(page)!r}")
    emit({"type": "text", "delta": "03 và HS-0"})
    if "HS-" in last_bot(page) or ARCHIVED not in last_bot(page):
        rep["missing"].append(f"chat: archived HS-03 or a cut HS-0 is not a name: {last_bot(page)!r}")
    emit({"type": "text", "delta": "1 có 2 buổi."})
    emit({"type": "done", "stopped": "max_tool_turns"})
    page.evaluate("window.__end()")
    final = last_bot(page)
    if f"{ARCHIVED} và {PEOPLE[0]} có 2 buổi." not in final or "HS-" in final:
        rep["missing"].append(f"chat: cut codes did not end as names: {final!r}")
    if STOPPED not in final:
        rep["missing"].append("chat: done.stopped max_tool_turns has no message")
    expect(page, rep, JS_IDLE, "chat: the fed answer left the tab busy")
    page.fill("#chat-input", "lại")  # a stream that dies right after a half code, with no `done`
    page.press("#chat-input", "Enter")
    emit({"type": "start", "conversation_id": "2026-01-01-1", "message_id": "m4"})
    emit({"type": "text", "delta": "Hồ sơ HS-0"})
    page.evaluate("window.__end()")
    expect(page, rep, JS_RETRY, "chat: a stream cut before done shows no red bubble with Gửi lại")
    if ERR_BUBBLE not in last_bot(page) or "HS-" in last_bot(page):
        rep["missing"].append(
            f"chat: a stream cut after 'HS-0' should be a red bubble with no code: {last_bot(page)!r}"
        )
    page.evaluate(JS_UNFEED)
    see_chat(page, rep, "chat cut code", phone)
    new_chat(page, rep, phone)


@counted()
def chat_mentions(page, rep: dict, phone: bool, data_dir: str, reqs: list) -> None:
    """@ picks a name on screen, the wire message holds the code; a made-up number is marked."""
    page.fill("#chat-input", "")
    page.type("#chat-input", "@")
    names = page.locator("#mention-pop .mention-opt b").all_inner_texts()
    if names != list(PEOPLE):
        rep["missing"].append(f"chat: @ lists {names}, want only {list(PEOPLE)}")
    seen = len(posts(reqs))
    pick_mention(page, rep, "Tháng này ", "", PEOPLE[0])
    page.keyboard.type("yếu gì?")
    if (got := page.input_value("#chat-input")) != f"Tháng này @{PEOPLE[0]} yếu gì?":
        rep["missing"].append(f"chat: the box holds {got!r}")
    n = msgs(page)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, "chat: no answer to the @ question", n)
    answer = last_bot(page)
    if PEOPLE[0] not in answer or HS_CODE.search(answer) or "Nguồn:" not in answer:
        rep["missing"].append(f"chat: answer should name {PEOPLE[0]}, hide HS-01 and cite a source: {answer!r}")
    sent = posts(reqs)[seen:]
    if len(sent) != 1 or sent[0]["text"] != "Tháng này @HS-01 yếu gì?" or sent[0]["mentions"] != [1]:
        rep["missing"].append(f"chat: wire message is {sent}, want '@HS-01' and mentions [1]")
    if any("Nguyễn" in json.dumps(b, ensure_ascii=False) for b in sent):
        rep["missing"].append("chat: a student name went to /api/assistant")
    see_chat(page, rep, "chat answer", phone)
    pick_mention(page, rep, "bịa số cho ", "Trần", PEOPLE[1])
    n = msgs(page)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, "chat: no answer to the made-up number", n)
    if page.locator("#chat-msgs .msg-bot:last-child .uncheck").count() != 1 or "Số chưa kiểm: 97" not in last_bot(page):
        rep["missing"].append(f"chat: no underlined sentence + 'Số chưa kiểm: 97': {last_bot(page)!r}")
    see_chat(page, rep, "chat warning", phone)


@counted()
def chat_codes(page, rep: dict, phone: bool, data_dir: str) -> None:
    """Bank codes alone are answered by code: 2 problem cards with formulas, no model call."""
    logs = Path(data_dir, "logs", "llm.jsonl")
    lines = len(logs.read_text(encoding="utf-8").splitlines())
    say(page, rep, "8DS-PT1-001, 8DS-PT1-002")
    expect(page, rep, JS_TWO_TEX, "chat: the two bank codes did not show 2 problem cards with mjx-container")
    if (cards := page.locator("#chat-msgs .pcard").count()) != 2:
        rep["missing"].append(f"chat: {cards} problem cards, want 2")
    if len(logs.read_text(encoding="utf-8").splitlines()) != lines:
        rep["missing"].append("chat: bank codes called the model (llm.jsonl grew)")
    press(page, rep, '#chat-msgs .pcard [data-act="c-sol"]', "chat Xem lời giải", JS_SOL_OPEN)
    see_chat(page, rep, "chat problem cards", phone)


@counted()
def chat_ask(page, rep: dict, phone: bool) -> None:
    """A bank search and the all-students question run their tools; the answers cite a source and show no code."""
    if "tìm được" not in say(page, rep, "Tìm bài đổi dấu"):
        rep["missing"].append(f"chat: 'Tìm bài đổi dấu' got {last_bot(page)!r}")
    see_chat(page, rep, "chat search", phone)
    answer = say(page, rep, "Ai còn sai dấu khi chuyển vế?")
    if "so sánh lỗi lặp" not in answer or "Nguồn:" not in answer:
        rep["missing"].append(f"chat: 'Ai còn sai dấu khi chuyển vế?' got {answer!r}, want a comparison and 'Nguồn:'")
    see_chat(page, rep, "chat compare", phone)


@counted()
def chat_keys(page, rep: dict, reqs: list) -> None:
    """Shift+Enter breaks the line, Enter sends, Gửi is off when the box is empty."""
    page.fill("#chat-input", "")
    if not page.locator(SEND).is_disabled():
        rep["missing"].append("chat: Gửi is on with an empty box")
    seen = len(posts(reqs))
    page.type("#chat-input", "a")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("b")
    page.wait_for_timeout(300)
    if page.input_value("#chat-input") != "a\nb" or len(posts(reqs)) != seen or page.locator(SEND).is_disabled():
        rep["missing"].append(f"chat: Shift+Enter did not just break the line: {page.input_value('#chat-input')!r}")
    say(page, rep, "xin chào")
    if len(posts(reqs)) != seen + 1:
        rep["missing"].append(f"chat: {len(posts(reqs)) - seen} messages sent, want 1")
    if page.input_value("#chat-input") != "":
        rep["missing"].append("chat: the box kept the text after a good answer")


@counted()
def chat_retry(page, rep: dict, phone: bool) -> None:
    """A lost network or a 409: red bubble + Gửi lại, the text stays, Gửi lại then answers (Review Focus 5)."""
    for how in ("abort", "409"):
        if how == "abort":
            page.route(MSGS, lambda r: r.abort())
        else:
            page.route(
                MSGS, lambda r: r.fulfill(status=409, content_type="application/json", body=json.dumps(NOT_FOUND))
            )
        mine = page.locator("#chat-msgs .msg-me").count()
        page.fill("#chat-input", f"thử lại {how}")
        page.press("#chat-input", "Enter")
        expect(page, rep, JS_RETRY, f"chat {how}: no red bubble with Gửi lại")
        if how == "abort" and ERR_BUBBLE not in page.inner_text("#chat-msgs .bubble-err"):
            rep["missing"].append(f"chat: the red bubble does not say '{ERR_BUBBLE}'")
        if page.input_value("#chat-input") != f"thử lại {how}" or page.locator(SEND).is_disabled():
            rep["missing"].append(
                f"chat {how}: the text left the box or Gửi stayed off: {page.input_value('#chat-input')!r}"
            )
        see_chat(page, rep, f"chat {how}", phone)
        page.unroute(MSGS)
        shown = msgs(page)
        press(page, rep, '[data-act="c-retry"]', f"chat Gửi lại ({how})", JS_REPLIED, shown - 1)
        if page.locator(".bubble-err").count() or page.locator("#chat-msgs .msg-me").count() != mine + 1:
            rep["missing"].append(f"chat {how}: Gửi lại left the red bubble or added a second tutor bubble")
        if page.input_value("#chat-input") != "":
            rep["missing"].append(f"chat {how}: the box kept the text after Gửi lại worked")


@counted()
def chat_reload(page, rep: dict, phone: bool) -> None:
    """After a reload the conversation is in the list and opens with every message; the phone gets a drawer."""
    count = page.locator("#chat-msgs .msg").count()
    page.reload()
    expect(page, rep, JS_LIST_HAS, "chat: no conversation in the list after a reload")
    if phone:
        press(page, rep, "#conv-toggle", "chat ☰ Hội thoại", JS_DRAWER)
        see_chat(page, rep, "chat drawer", phone)
    elif page.locator(".convs").is_hidden():
        rep["missing"].append("chat: the conversation list is hidden at desktop width")
    item = '#conv-list .conv-item:has-text("Tháng này @Nguyễn Văn An") >> nth=0'
    press(page, rep, item, "chat mở hội thoại", JS_N_MSGS, count)
    text = page.inner_text("#chat-msgs")
    rep["missing"] += [
        f"chat: reopened conversation has no '{w}'"
        for w in ("Số chưa kiểm: 97", "Nguồn:", SAVED_NOTHING)
        if w not in text
    ]
    if page.locator(".convs.open").count():
        rep["missing"].append("chat: opening a conversation left the drawer open")
    see_chat(page, rep, "chat reopened", phone)


def llm_lines(data_dir: str, agent: str) -> int:
    """Lines of llm.jsonl from one agent; the seeded log ends in a cut line, so no JSON parse."""
    text = Path(data_dir, "logs", "llm.jsonl").read_text(encoding="utf-8")
    return len(re.findall(rf'^\{{"agent": "{agent}"', text, re.M))


@counted(may=START_GRADING)
def chat_attach(page, rep: dict, phone: bool, data_dir: str, reqs: list, before: tuple) -> None:
    """📎 lists data/inbox/; the chosen file rides with the message; ask_grading pre-fills the guess.

    The desktop then grades the file for real (the grading walk uses its card); the phone has its own file and day."""
    day = 26 if phone else 25
    fname = f"hs01-2026-10-{day}.tex"
    inbox = Path(data_dir, "inbox")
    (inbox / fname).write_bytes((FIX / "s01.tex").read_bytes() + f"\n% robot {day}\n".encode())  # new sha: not graded
    (inbox / "bai-scan.pdf").write_bytes(b"%PDF-1.4\n")
    new_chat(page, rep, phone)
    press(page, rep, '[data-act="c-attach"]', "chat 📎", JS_MODAL)
    expect(page, rep, JS_FILES, "chat 📎: the inbox is not listed")
    modal = page.inner_text("#modal-body")
    rep["missing"] += [
        f"chat 📎: no '{w}'"
        for w in (f"Bài của {PEOPLE[0]} · {day}/10/2026", "Chưa rõ học sinh, ngày học")
        if w not in modal
    ]
    for name, label in (("s01.tex", "đã chấm"), ("bai-scan.pdf", "chưa nhận PDF")):
        b = page.locator(f'#modal-body .file-row:has-text("{name}") button')
        if b.inner_text().strip() != label or not b.is_disabled():
            rep["missing"].append(f"chat 📎: {name} should be a disabled '{label}'")
    see_chat(page, rep, "chat 📎", phone)
    press(page, rep, f'#modal-body .file-row:has-text("{fname}") button', "chat Chọn bài", JS_NO_MODAL)
    if fname not in page.inner_text("#attach-row") or page.locator(SEND).is_disabled():
        rep["missing"].append("chat 📎: the chosen file is not a chip on the box, or Gửi is off")
    seen, n = len(posts(reqs)), msgs(page)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, "chat 📎: no answer to the file", n)
    sent = posts(reqs)[seen:]
    if len(sent) != 1 or sent[0]["attachment"] != {"path": fname} or sent[0]["held_on"] != f"2026-10-{day}":
        rep["missing"].append(f"chat 📎: sent {sent}, want attachment {fname} + held_on 2026-10-{day}")
    if page.locator("#attach-row .file-chip").count():
        rep["missing"].append("chat 📎: the chip stayed after sending")
    if (form := page.evaluate(JS_ASK_GRADE)) != [PEOPLE[0], f"2026-10-{day}", False]:
        rep["missing"].append(f"chat ask_grading: form is {form}, want {PEOPLE[0]}, 2026-10-{day}, button on")
    see_chat(page, rep, "chat ask_grading", phone)
    if db_state(data_dir) != before:
        rep["missing"].append("chat: the walk changed tutor.db or the saved decisions")
    if phone:
        page.route(MSGS, lambda r: r.abort())  # only the message is read: grading would start a thread
    seen, n, routers = len(posts(reqs)), msgs(page), llm_lines(data_dir, "00")
    page.click('.ask-grade [data-act="c-grade"]')
    if phone:
        page.wait_for_timeout(300)
        page.unroute(MSGS)
    else:
        expect(page, rep, JS_REPLIED, "chat ask_grading: no answer to Chấm bài này", n)
        expect(page, rep, JS_HOST_SEL, "chat ask_grading: Chấm bài này shows no grading card", [G_NEW, ".gcard-head"])
        if llm_lines(data_dir, "00") != routers:
            rep["missing"].append("chat ask_grading: Chấm bài này called the assistant model (agent 00 in llm.jsonl)")
    sent = posts(reqs)[seen:]
    if len(sent) != 1 or sent[0]["mentions"] != [1] or "@HS-01" not in sent[0]["text"]:
        rep["missing"].append(f"chat ask_grading: Chấm bài này sent {sent}, want @HS-01 and mentions [1]")
    elif sent[0]["held_on"] != f"2026-10-{day}" or sent[0]["attachment"] != {"path": fname}:
        rep["missing"].append(f"chat ask_grading: Chấm bài này sent {sent}, want the file and held_on")


def walk_chat(page, rep: dict, phone: bool, data_dir: str | None, root: str) -> None:
    """The Trợ lý tab (the app is on it already). With --data the walk must leave tutor.db and the decisions alone."""
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    before = db_state(data_dir) if data_dir else None
    if not chat_basics(page, rep, phone, data_dir, root):
        return
    if data_dir:
        chat_cut_code(page, rep, phone)
        chat_mentions(page, rep, phone, data_dir, reqs)
    saved = db_state(data_dir) if data_dir else None
    with step(rep, "chat ok"):
        if SAVED_NOTHING not in say(page, rep, "ok"):
            rep["missing"].append(f"chat: 'ok' should answer '{SAVED_NOTHING}'")
    if data_dir:
        if db_state(data_dir) != saved:
            rep["missing"].append("chat: 'ok' changed tutor.db or the saved decisions")
        chat_codes(page, rep, phone, data_dir)
        chat_ask(page, rep, phone)
    chat_keys(page, rep, reqs)
    chat_retry(page, rep, phone)
    if data_dir:
        chat_reload(page, rep, phone)
        chat_attach(page, rep, phone, data_dir, reqs, before)


def host(tid: str) -> str:
    return f'.card-host[data-thread="{tid}"]'


def decisions(data_dir: str, tid: str) -> dict:
    with closing(sqlite3.connect(f"{Path(data_dir, 'checkpoints.db').as_uri()}?mode=ro", uri=True)) as con:
        row = con.execute("SELECT decisions_json FROM tutor_thread WHERE thread_id = ?", (tid,)).fetchone()
    return json.loads(row[0]) if row and row[0] else {}


def mistakes(data_dir: str, tid: str) -> list:
    """(attempt seq, status, code, description) of the committed mistakes of one G1 thread."""
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(
            "SELECT a.seq, m.status, m.code, m.description FROM mistake m JOIN attempt a ON a.id = m.attempt_id"
            " JOIN session s ON s.id = a.session_id WHERE s.thread_id = ? ORDER BY 1, 2",
            (tid,),
        ).fetchall()


def open_card(page, rep: dict, phone: bool, tid: str, label: str, js: str, arg) -> None:
    """Mở on the reminder of thread `tid` (folded on the phone after a reload)."""
    if not page.locator(".remind-cards").count():
        press(page, rep, '[data-act="c-remind"]', "chat Xem việc chờ", JS_CARDS_OPEN)
    press(page, rep, f'#remind [data-act="c-open"][data-tid="{tid}"]', label, js, arg)


@counted()
def grade_confirm(page, rep: dict, data_dir: str) -> None:
    """s04 has a problem with no ref: the candidates are formulas; Bỏ bài này sends skip and grading goes on."""
    open_card(page, rep, False, G_S04, "grading Mở bài cần xác nhận", JS_HOST_SEL, [G_S04, ".match-opt mjx-container"])
    see_chat(page, rep, "grading confirm", False)
    skip, saved = f'{host(G_S04)} [data-act="g-skip"]', [G_S04, "[data-act=g-save]"]
    press(page, rep, skip, "grading Bỏ bài này", JS_HOST_SEL, saved)
    if not any(isinstance(d, dict) and d.get("skip") is True for d in decisions(data_dir, G_S04).values()):
        rep["missing"].append(f"grading confirm: decisions_json of s04 is {decisions(data_dir, G_S04)}, want a skip")


def other_sig(route) -> None:
    """The poll of a thread at preview answers another preview_sig: another session of the student was saved."""
    r = route.fetch()
    j = r.json()
    if j["card"]["stage"] == "preview":
        j["card"]["preview_sig"] = "robot"
    route.fulfill(response=r, json=j)


def resumes(reqs: list, tid: str) -> int:
    return sum(m == "POST" and u.endswith(f"/threads/{tid}/resume") for m, u, _ in reqs)


@counted()
def grade_changed(page, rep: dict, reqs: list) -> None:
    """s04 at review, every mistake Bỏ: the preview changes under Lưu kết quả, so one resume and a toast (R7)."""
    h, save = host(G_S04), f'{host(G_S04)} [data-act="g-save"]'
    reject = f"{h} [data-act=g-dec][data-v=reject]"
    if not (n := page.locator(reject).count()):
        rep["missing"].append("grading s04: no mistake to Bỏ at review")
        return
    for i in range(n):
        press(page, rep, f"{reject} >> nth={i}", f"grading Bỏ lỗi {i + 1} của s04")
    if not expect(page, rep, JS_ON, "grading s04: Lưu kết quả did not turn on after every Bỏ", save):
        return
    expect(page, rep, JS_HOST_SEL, "grading s04: no preview table", [G_S04, ".preview-tbl"])
    poll = re.compile(rf"/api/threads/{G_S04}\?view=teacher$")
    page.route(poll, other_sig)
    seen = resumes(reqs, G_S04)  # the confirm step resumed once already
    press(page, rep, save, "grading Lưu kết quả khi xem trước đổi", JS_TOAST_HAS, SIG_CHANGED)
    page.wait_for_timeout(1500)
    if (n := resumes(reqs, G_S04) - seen) != 1:
        rep["missing"].append(f"grading s04: a changed preview_sig gave {n} resumes, want 1")
    page.unroute(poll)


def coded(route) -> None:
    """Mistake p2 of s01 as the model may write it: with the student's code. Evidence and a step hold EVIL."""
    r = route.fetch()
    j = r.json()
    for a in j["card"]["attempts"]:
        for st in a["steps"][:1]:
            st["latex"] += f" {EVIL}"
        for m in a["mistakes"]:
            if m["pid"] == "p2":
                m["description"] = CODED
            if m["pid"] == "p1":
                m["evidence_latex"] = EVIL
    route.fulfill(response=r, json=j)


@counted()
def grade_review(page, rep: dict, data_dir: str, reqs: list) -> bool:
    """s06 waits for s01 (date lock); in s01 each choice is a PUT and tutor.db stays as it is until Lưu kết quả.

    False when a step failed: the later ones stand on it."""
    start = len(rep["missing"])
    ok = lambda: len(rep["missing"]) == start  # noqa: E731
    open_card(page, rep, False, G_S06, "grading Mở buổi bị khoá", JS_HOST_HAS, [G_S06, LOCKED])
    see_chat(page, rep, "grading locked", False)
    poll = re.compile(rf"/api/threads/{G_S01}\?view=teacher$")
    page.evaluate(JS_HREF_READY)  # MathJax autoloads \href; typeset at once, runs break each other
    page.route(poll, coded)
    press(page, rep, f'{host(G_S06)} [data-act="g-open"]', "grading Mở buổi 20/10", JS_HOST_SEL, [G_S01, ".mistake"])
    h, save = host(G_S01), f'{host(G_S01)} [data-act="g-save"]'
    if not ok() or not page.locator(save).count():
        rep["missing"].append("grading review: the s01 card has no Lưu kết quả")
        return False
    if page.locator(save).is_enabled() or LEFT_5 not in page.inner_text(h):
        rep["missing"].append(f"grading review: Lưu kết quả should be off with '{LEFT_5}'")
    rows = db_state(data_dir)[0]
    dec = lambda pid, v: f'{h} [data-act="g-dec"][data-pid="{pid}"][data-v="{v}"]'  # noqa: E731
    press(page, rep, dec("p1", "accept"), "grading Đúng", JS_PRESSED, dec("p1", "accept"))
    press(page, rep, dec("p2", "edit"), "grading Sửa", JS_HOST_SEL, [G_S01, ".edit-form select[data-f=code]"])
    if not ok():
        return False
    box = f"{h} .edit-form textarea"
    if HS_CODE.search(shown := page.input_value(box)) or PEOPLE[0] not in shown:
        rep["missing"].append(f"grading review: the Sửa box shows {shown!r}, want the name and no code")
    page.select_option(f"{h} .edit-form select[data-f=code]", NEW_CODE)
    page.fill(box, NAMED)  # the tutor types the name: the PUT must carry the code
    press(page, rep, f'{h} [data-act="g-edit-done"]', "grading Sửa xong", JS_HOST_NO, [G_S01, ".edit-form"])
    if NEW_KIND not in " ".join(page.locator(f'{h} .mistake[data-pid="p2"]').all_inner_texts()):
        rep["missing"].append(f"grading review: the edited mistake does not say '{NEW_KIND}'")
    for pid in ("p3", "p4", "p5"):
        press(page, rep, dec(pid, "reject"), f"grading Bỏ {pid}", JS_PRESSED, dec(pid, "reject"))
    press(page, rep, f'{h} [data-act="g-add"][data-seq="1"]', "grading + Thêm lỗi", JS_HOST_SEL, [G_S01, ".add-form"])
    if not ok():
        return False
    page.fill(f"{h} .add-form textarea", ADDED)
    press(page, rep, f'{h} [data-act="g-add-ok"]', "grading Thêm lỗi", JS_HOST_HAS, [G_S01, "Thầy/cô thêm"])
    expect(page, rep, JS_ON, "grading review: Lưu kết quả did not turn on after every choice", save)
    expect(page, rep, JS_HOST_SEL, "grading review: no preview table", [G_S01, ".preview-tbl"])
    # a mistake still being typed in + Thêm lỗi must hold Lưu kết quả back, or the save drops it
    add = f'{h} [data-act="g-add"][data-seq="1"]'
    press(page, rep, add, "grading + Thêm lỗi nửa chừng", JS_HOST_SEL, [G_S01, ".add-form"])
    page.fill(f"{h} .add-form textarea", ADDED)
    expect(page, rep, JS_OFF, "grading review: Lưu kết quả stayed on over a mistake still being typed", save)
    if OPEN_FORM not in page.inner_text(h):
        rep["missing"].append(f"grading review: no '{OPEN_FORM}' while the Thêm lỗi form holds text")
    press(page, rep, f'{h} [data-act="g-add-cancel"]', "grading Thôi", JS_ON, save)
    puts = [json.loads(b) for m, u, b in reqs if m == "PUT" and u.endswith(f"/threads/{G_S01}/decisions")]
    p2 = puts[-1]["cards"].get("p2", {}).get("description") if puts else None
    if p2 != CODED or any(PEOPLE[0] in json.dumps(b, ensure_ascii=False) for b in puts):
        rep["missing"].append(f"grading review: the last PUT has p2 {p2!r}, want {CODED!r} and no name in any PUT")
    if db_state(data_dir)[0] != rows:
        rep["missing"].append("grading review: a choice changed tutor.db before Lưu kết quả")
    see_chat(page, rep, "grading review", False)
    # EVIL in the evidence and in a step is typeset, and leaves no javascript: link
    work = f'{h} [data-act="g-work"][data-seq="1"]'
    press(page, rep, work, "grading Xem bài làm có EVIL", JS_HOST_SEL, [G_S01, ".wstep"])
    sels = ('.mistake[data-pid="p1"]', ".wstep:nth-child(2)")  # the evidence, the first step
    typeset = [
        expect(page, rep, JS_HOST_SEL, f"grading review: EVIL not typeset in {s}", [G_S01, f"{s} mjx-container"])
        for s in sels
    ]
    if all(typeset) and (n := page.evaluate(JS_LIVE_LINKS)):
        rep["missing"].append(f"grading review: {n} javascript: links on screen after MathJax drew student LaTeX")
    press(page, rep, work, "grading Ẩn bài làm có EVIL", JS_HOST_NO, [G_S01, ".wstep"])
    page.unroute(poll)
    return ok()


@counted(commit=SAVE_RESULT)
def grade_save(page, rep: dict, data_dir: str, reqs: list) -> None:
    """Lưu kết quả at review: PUT, resume 1, the same preview, resume 2 on its own; a double click is still 1 chain."""
    h, save = host(G_S01), f'{host(G_S01)} [data-act="g-save"]'
    seen = resumes(reqs, G_S01)
    page.dblclick(save)
    expect(page, rep, JS_HOST_HAS, "grading save: no 'Đã lưu' after one click at review", [G_S01, "Đã lưu"])
    if (n := resumes(reqs, G_S01) - seen) != 2:
        rep["missing"].append(f"grading save: a double click at review sent {n} resumes, want 2 (one chain)")
    rep["missing"] += [f"grading saved: no '{w}'" for w in ("Đã sao lưu trước khi lưu", "Xem hồ sơ",
                       "Soạn phiếu buổi sau") if w not in page.inner_text(h)]  # fmt: skip
    got = [(seq, st) for seq, st, _, _ in mistakes(data_dir, G_S01)]
    want = [(1, "added"), (1, "confirmed"), (2, "edited"), (3, "rejected"), (4, "rejected"), (5, "rejected")]
    if got != want:
        rep["missing"].append(f"grading saved: mistake rows are {got}, want {want}")
    rows = {st: (code, text) for _, st, code, text in mistakes(data_dir, G_S01)}
    if rows.get("edited") != (NEW_CODE, CODED) or rows.get("added", ("", ""))[1] != ADDED:
        rep["missing"].append(f"grading saved: edited / added rows are {rows}")
    if not scalar(data_dir, "SELECT COALESCE(review_seconds, 0) FROM session WHERE thread_id = ?", G_S01):
        rep["missing"].append("grading saved: session.review_seconds is not > 0")
    see_chat(page, rep, "grading saved", False)
    press(page, rep, f'{h} [data-act="g-profile"]', "grading Xem hồ sơ")
    if not page.evaluate(JS_TAB, "hoc-sinh"):
        rep["missing"].append("grading saved: Xem hồ sơ did not open Học sinh")
    press(page, rep, "#tab-tro-ly", "tab tro-ly")


@counted()
def grade_stale(page, rep: dict, reqs: list) -> None:
    """Commit ② refused (StaleProfile, session.py:548): the thread is back at the same preview, Lưu kết quả is on again.

    The resume is stubbed, so the server row never moves: the card must still give up waiting."""
    h, save = host(PREVIEW_TID), f'{host(PREVIEW_TID)} [data-act="g-save"]'
    again = re.compile(rf"/api/threads/{PREVIEW_TID}/resume$")
    expect(page, rep, JS_TOAST_NO, "grading stale: an earlier toast did not go away", SIG_CHANGED)
    open_card(page, rep, False, PREVIEW_TID, "grading Mở bài chờ lưu", JS_ON, save)
    page.route(again, lambda r: r.fulfill(status=202, json={"thread_id": PREVIEW_TID, "status": "running"}))
    seen = resumes(reqs, PREVIEW_TID)
    press(page, rep, save, "grading Lưu kết quả khi lưu bị trả lại", JS_TOAST_HAS, SIG_CHANGED)
    expect(page, rep, JS_ON, "grading stale: Lưu kết quả stayed off after the commit came back", save)
    if (n := resumes(reqs, PREVIEW_TID) - seen) != 1:
        rep["missing"].append(f"grading stale: {n} resumes, want 1")
    see_chat(page, rep, "grading stale", False)
    page.unroute(again)
    # an open card does not poll while the Trợ lý tab is behind another one
    press(page, rep, "#tab-hoc-sinh", "tab hoc-sinh", JS_TAB, "hoc-sinh")
    page.wait_for_timeout(300)  # a poll already in the air lands
    seen = len(reqs)
    page.wait_for_timeout(2500)
    if n := sum(m == "GET" and "view=teacher" in u for m, u, _ in reqs[seen:]):
        rep["missing"].append(f"grading hidden: {n} card polls while the Trợ lý tab was hidden")
    press(page, rep, "#tab-tro-ly", "tab tro-ly", JS_TAB, "tro-ly")
    if "Đã lưu" in " ".join(page.locator(h).all_inner_texts()):
        rep["missing"].append("grading stale: the card says Đã lưu")


@counted()
def grade_routes(page, rep: dict, reqs: list) -> None:
    """A failed thread offers Chấm lại (one resume); a thread gone (404) in a reopened conversation stops polling."""
    h, poll = host(G_NEW), re.compile(rf"/api/threads/{G_NEW}\?view=teacher$")
    again = re.compile(rf"/api/threads/{G_NEW}/resume$")

    def failed(route) -> None:
        r = route.fetch()
        j = r.json()
        j["status"] = "failed"
        j["card"] |= {"stage": "failed", "error_words": FAILED_WORDS, "lock": None}
        route.fulfill(response=r, json=j)

    page.route(poll, failed)
    page.route(again, lambda r: r.fulfill(status=202, json={"thread_id": G_NEW, "status": "running"}))
    expect(page, rep, JS_HOST_SEL, "grading failed: no red box", [G_NEW, ".callout-crit"])
    if FAILED_WORDS not in " ".join(page.locator(h).all_inner_texts()):
        rep["missing"].append("grading failed: the red box does not show error_words")
    see_chat(page, rep, "grading failed", False)
    seen = len(reqs)
    press(page, rep, f'{h} [data-act="g-retry"]', "grading Chấm lại")
    page.wait_for_timeout(500)
    if (n := sum(m == "POST" and again.search(u) is not None for m, u, _ in reqs[seen:])) != 1:
        rep["missing"].append(f"grading failed: Chấm lại sent {n} resumes, want 1")
    # the poll still says failed, as if the retry failed again before any poll saw it run
    retry = f'{h} [data-act="g-retry"]'
    expect(page, rep, JS_ON, "grading failed: Chấm lại stayed off after the retry failed again", retry)
    page.unroute(poll)
    page.unroute(again)
    new_chat(page, rep, False)  # the old card goes first, so only the reopened one can show the 404
    gone = {"error": {"code": "not_found", "message": "x", "detail": None}}
    page.route(poll, lambda r: r.fulfill(status=404, json=gone))
    item = '#conv-list .conv-item:has-text("Chấm bài này") >> nth=0'
    press(page, rep, item, "grading mở lại hội thoại có thẻ chấm", JS_HOST_HAS, [G_NEW, GONE])
    page.wait_for_timeout(300)
    seen = len(reqs)
    page.wait_for_timeout(2500)
    if any(poll.search(u) for _, u, _ in reqs[seen:]):
        rep["missing"].append("grading gone: the card kept polling after a 404")
    see_chat(page, rep, "grading gone", False)
    page.unroute(poll)


def walk_grading(page, rep: dict, phone: bool, data_dir: str) -> None:
    """The G1 card in the chat. The phone only looks at one (s06, under review once s01 is saved)."""
    if phone:
        with step(rep, "grading phone"):
            open_card(page, rep, phone, G_S06, "grading Mở bài chờ duyệt", JS_HOST_SEL, [G_S06, ".mistake"])
            press(page, rep, f"{host(G_S06)} [data-act=g-work] >> nth=0", "grading Xem đề & bài làm", JS_HOST_SEL,
                  [G_S06, ".wstep.hit"])  # fmt: skip
            see_chat(page, rep, "grading phone", phone)
        return
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    grade_confirm(page, rep, data_dir)
    grade_changed(page, rep, reqs)
    if grade_review(page, rep, data_dir, reqs):
        grade_save(page, rep, data_dir, reqs)
    grade_stale(page, rep, reqs)
    grade_routes(page, rep, reqs)


WS_ASK = "Gợi ý 6 bài cho "
NEED_ONE = "Phiếu cần ít nhất 1 bài"
SELF_ADDED = "Thầy/cô tự thêm"
WS_MADE = "Đã tạo phiếu"
REPLACE = "Ngày này đã có phiếu 2 bài. Phiếu cũ vẫn giữ để tra cứu."
CREATE = '#draft [data-act="ws-create"]'
WS_CODE = "#draft .ws-code"
JS_WS_REFS = "() => [...document.querySelectorAll('#draft .draft-item .ref')].map(e => e.innerText.trim())"
JS_WS_REFS_ARE = """want => JSON.stringify([...document.querySelectorAll('#draft .draft-item .ref')]
  .map(e => e.innerText.trim())) === JSON.stringify(want)"""
JS_WS_N = "n => document.querySelectorAll('#draft .draft-item').length === n"
JS_WS_HAS = "t => !!document.getElementById('draft') && document.getElementById('draft').innerText.includes(t)"
JS_WS_TEX = "() => document.querySelectorAll('#draft .draft-item mjx-container').length > 0"
JS_WS_TID = "() => CHAT.worksheetThread ? CHAT.worksheetThread() : null"
JS_WS_OPEN = "() => (document.getElementById('draft')?.getBoundingClientRect().height || 0) > 0"
JS_WS_SHUT = "() => document.getElementById('draft')?.getBoundingClientRect().height === 0"
JS_STATUS = "u => fetch(u).then(r => r.status)"
JS_NO_PRINT = "() => { window.__printed = 0; window.print = () => { window.__printed++; }; }"
BAD_CODE, BAD_WHY = "9ZZ-ZZZ-999", "Bỏ mã không hợp lệ trước khi tạo phiếu"  # P8
# PUTs of the G4 drafts reach the server `ms` late; only g4- threads, the grading cards keep their own PUTs
JS_SLOW_PUT = """ms => { window.__wsSend = U.api.send;
  const late = (m, p, b) => new Promise(r => setTimeout(r, ms)).then(() => window.__wsSend(m, p, b));
  U.api.send = (m, p, b) => m === 'PUT' && p.startsWith('/threads/g4-') ? late(m, p, b) : window.__wsSend(m, p, b); }"""
JS_FAST_PUT = "() => { U.api.send = window.__wsSend; }"
JS_CARD_REFS = "t => U.api.get('/threads/' + t + '?view=teacher').then(r => r.card.items.map(i => i.ref))"


def recs(data_dir: str, where: str = "1", *args) -> int:
    return scalar(data_dir, f"SELECT count(*) FROM recommendation WHERE {where}", *args)


def sheet(data_dir: str, sid: int) -> list:
    """(ref, position) of the student's live sheet rows, in position order."""
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(
            "SELECT p.ref, r.position FROM recommendation r JOIN problem p ON p.id = r.problem_id"
            " WHERE r.student_id = ? AND r.status <> 'rejected' ORDER BY r.position",
            (sid,),
        ).fetchall()


@counted()
def ws_propose(page, rep: dict, phone: bool, who: str = PEOPLE[1]) -> str | None:
    """'Gợi ý 6 bài cho @<who> buổi thứ Bảy' opens the draft panel with 6 problems; returns its thread."""
    new_chat(page, rep, phone)
    pick_mention(page, rep, WS_ASK, who.split()[0], who)
    page.keyboard.type("buổi thứ Bảy")
    n = msgs(page)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, "worksheet: no answer to the suggestion", n)
    if not expect(page, rep, JS_WS_N, "worksheet: the draft panel did not show 6 problems", 6):
        return None
    return page.evaluate(JS_WS_TID)


@counted()
def ws_edit(page, rep: dict, data_dir: str, reqs: list, tid: str) -> list:
    """↑ ↓ × and Thêm theo mã redraw from the server card; nothing reaches tutor.db; Enter in the code box adds."""
    r = page.evaluate(JS_WS_REFS)
    counts = page.inner_text("#draft .ws-counts")
    if sum(map(int, re.findall(r"\d+", counts))) != 6 or not all(
        w in counts for w in ("ôn lại", "vừa sức", "thử thách", "thầy/cô thêm")
    ):
        rep["missing"].append(f"worksheet: the count line {counts!r} should name 4 groups adding up to 6")
    whys = page.locator("#draft .draft-item .why").all_inner_texts()
    if len(whys) != 6 or not all(w.strip() for w in whys):
        rep["missing"].append(f"worksheet: every problem needs a reason in words: {whys}")
    expect(page, rep, JS_WS_TEX, "worksheet: the statements are not typeset")
    up = '#draft [data-act="ws-move"][data-i="1"][data-d="-1"]'
    press(page, rep, up, "worksheet ↑ bài 2", JS_WS_REFS_ARE, [r[1], r[0], *r[2:]])
    drop = '#draft [data-act="ws-del"][data-i="2"]'
    press(page, rep, drop, "worksheet × bài 3", JS_WS_REFS_ARE, [r[1], r[0], *r[3:]])
    if not page.locator(WS_CODE).count():
        rep["missing"].append("worksheet: the draft has no Thêm theo mã box")
        return []
    page.fill(WS_CODE, "9DS-PT2-001")
    page.press(WS_CODE, "Enter")
    want = [r[1], r[0], *r[3:], "9DS-PT2-001"]
    expect(page, rep, JS_WS_REFS_ARE, "worksheet: Enter in Thêm theo mã did not add 9DS-PT2-001 last", want)
    if SELF_ADDED not in " ".join(page.locator("#draft .draft-item").all_inner_texts()[-1:]):
        rep["missing"].append(f"worksheet: the added problem does not say '{SELF_ADDED}'")
    page.fill(WS_CODE, BAD_CODE)
    page.press(WS_CODE, "Enter")
    expect(page, rep, JS_WS_HAS, f"worksheet: Thêm {BAD_CODE} shows no invalid line", f"{BAD_CODE}: không có")
    if not page.locator(CREATE).is_disabled() or BAD_WHY not in page.inner_text("#draft"):
        rep["missing"].append(f"worksheet: an invalid code should turn Tạo phiếu off with '{BAD_WHY}' (P8)")
    press(page, rep, '#draft [data-act="ws-bad-del"]', f"worksheet × {BAD_CODE}", JS_ON, CREATE)
    if recs(data_dir) or resumes(reqs, tid):
        rep["missing"].append("worksheet: an edit or Enter in Thêm theo mã wrote recommendation rows or resumed")
    return want


@counted()
def ws_chat_enter(page, rep: dict, data_dir: str, reqs: list, tid: str, want: list) -> None:
    """Review Focus 2: Enter in the chat box, empty or 'ok', makes no sheet; a code typed there joins the draft."""
    page.fill("#chat-input", "")
    seen = len(posts(reqs))
    page.press("#chat-input", "Enter")
    page.wait_for_timeout(300)
    if len(posts(reqs)) != seen:
        rep["missing"].append("worksheet: Enter in an empty chat box sent a message")
    if SAVED_NOTHING not in say(page, rep, "ok"):
        rep["missing"].append(f"worksheet: 'ok' should answer '{SAVED_NOTHING}'")
    page.wait_for_timeout(500)
    if recs(data_dir) or resumes(reqs, tid) or page.locator(CREATE).count() != 1:
        rep["missing"].append("worksheet: Enter in the chat box made a sheet (Review Focus 2)")
    page.evaluate(JS_SLOW_PUT, 400)  # Important 1: the PUT of a panel change lands after the chat added a code
    page.click('#draft [data-act="ws-move"][data-i="0"][data-d="1"]')
    say(page, rep, "8DS-PT1-001")
    want = [want[1], want[0], *want[2:], "8DS-PT1-001"]
    expect(page, rep, JS_WS_REFS_ARE, "worksheet: a code typed in the chat did not join (C-43)", want)
    page.wait_for_timeout(2500)
    page.evaluate(JS_FAST_PUT)
    if page.evaluate(JS_WS_REFS) != want or page.evaluate(JS_CARD_REFS, tid) != want:
        rep["missing"].append("worksheet: a code typed in the chat right after ↓ left the panel or the server")
    if posts(reqs)[-1]["context"]["worksheet_thread_id"] != tid:
        rep["missing"].append(f"worksheet: the chat sent context {posts(reqs)[-1]['context']}, want the draft {tid}")
    if recs(data_dir):
        rep["missing"].append("worksheet: a code typed in the chat wrote recommendation rows")


@counted(commit=SAVE_SHEET)
def ws_create(page, rep: dict, data_dir: str, reqs: list, tid: str) -> None:
    """× hết turns Tạo phiếu off; 2 codes back, one ↑, Enter in the date box makes the sheet in screen order."""
    while (n := page.locator("#draft .draft-item").count()) and len(rep["missing"]) < 50:
        press(page, rep, '#draft [data-act="ws-del"] >> nth=0', f"worksheet × ({n} left)", JS_WS_N, n - 1)
    if not page.locator(CREATE).is_disabled() or NEED_ONE not in page.inner_text("#draft"):
        rep["missing"].append(f"worksheet: an empty sheet should turn Tạo phiếu off with '{NEED_ONE}'")
    for k, ref in enumerate(("8DS-PT1-001", "9DS-PT2-001"), 1):
        page.fill(WS_CODE, ref)
        press(page, rep, '#draft [data-act="ws-add"]', f"worksheet Thêm {ref}", JS_WS_N, k)
    up = '#draft [data-act="ws-move"][data-i="1"][data-d="-1"]'
    press(page, rep, up, "worksheet ↑ again", JS_WS_REFS_ARE, ["9DS-PT2-001", "8DS-PT1-001"])
    expect(page, rep, JS_ON, "worksheet: Tạo phiếu did not turn on with 2 problems", CREATE)
    page.press("#draft .ws-date", "Enter")
    expect(page, rep, JS_WS_HAS, "worksheet: Enter in the date box did not make the sheet", WS_MADE)
    if (n := resumes(reqs, tid)) != 1:
        rep["missing"].append(f"worksheet: Tạo phiếu sent {n} resumes, want 1")
    if (got := sheet(data_dir, 2)) != [("9DS-PT2-001", 1), ("8DS-PT1-001", 2)]:
        rep["missing"].append(f"worksheet: recommendation rows are {got}, want the panel order")
    href = page.get_attribute("#draft .ws-tex", "href") if page.locator("#draft .ws-tex").count() else None
    if not href or page.evaluate(JS_STATUS, href) != 200:
        rep["missing"].append(f"worksheet: Tải .tex ({href}) does not answer 200")
    page.evaluate(JS_NO_PRINT)
    press(page, rep, '#draft [data-act="ws-pdf"]', "worksheet In PDF", "() => window.__printed === 1")
    if page.locator("#print-root li").count() != 2 or page.locator("#print-root li .tex-block").count() != 2:
        rep["missing"].append("worksheet: In PDF did not put the 2 statements in #print-root")


@counted(commit=SAVE_SHEET)
def ws_replace(page, rep: dict, phone: bool, data_dir: str, reqs: list) -> None:
    """A second sheet the same day asks to replace; Tạo phiếu mới marks the old rows rejected."""
    if not (tid := ws_propose(page, rep, phone)):
        return
    press(page, rep, CREATE, "worksheet Tạo phiếu lần 2", JS_MODAL)
    if REPLACE not in page.inner_text("#modal-root") or "Tạo phiếu mới thay thế?" not in page.inner_text("#modal-root"):
        rep["missing"].append(f"worksheet: the replace question does not say '{REPLACE}'")
    press(page, rep, '#modal-root [data-act="confirm-ok"]', "worksheet Tạo phiếu mới", JS_WS_HAS, WS_MADE)
    live = len(sheet(data_dir, 2))
    if (n := recs(data_dir, "student_id = 2 AND status = 'rejected'")) != 2 or live != 6:
        rep["missing"].append(f"worksheet: replace left {n} rejected rows and {live} live, want 2 and 6")
    if resumes(reqs, tid) != 1:
        rep["missing"].append(f"worksheet: the replace sent {resumes(reqs, tid)} resumes, want 1")


@counted()
def ws_switch(page, rep: dict, phone: bool) -> None:
    """Important 2: another student's draft replaces the panel while the last one's PUT is in the air."""
    if not ws_propose(page, rep, phone):
        return
    page.evaluate(JS_SLOW_PUT, 1500)
    page.click('#draft [data-act="ws-move"][data-i="0"][data-d="1"]')
    ws_propose(page, rep, phone, PEOPLE[0])
    page.wait_for_timeout(2500)  # the slow PUT of the first draft has come back
    page.evaluate(JS_FAST_PUT)
    if PEOPLE[0] not in (head := page.inner_text("#draft h2")) or PEOPLE[1] in head:
        rep["missing"].append(f"worksheet: the panel head says {head!r} over the draft of {PEOPLE[0]}")


@counted()
def ws_retry(page, rep: dict) -> None:
    """Thử lại on a failed draft whose poll still says failed (it failed again at once) comes back."""
    if not (tid := page.evaluate(JS_WS_TID)):
        rep["missing"].append("worksheet retry: no draft on screen")
        return
    poll, again = re.compile(rf"/api/threads/{tid}\?view=teacher$"), re.compile(rf"/api/threads/{tid}/resume$")

    def failed(route) -> None:
        r = route.fetch()
        j = r.json()
        j["status"] = "failed"
        j["card"]["stage"] = "failed"
        route.fulfill(response=r, json=j)

    page.route(poll, failed)
    page.route(again, lambda r: r.fulfill(status=202, json={"thread_id": tid, "status": "running"}))
    retry = '#draft [data-act="ws-retry"]'
    if expect(page, rep, JS_ON, "worksheet retry: a failed draft has no Thử lại", retry):
        press(page, rep, retry, "worksheet Thử lại")
        expect(page, rep, JS_ON, "worksheet retry: Thử lại stayed off after the retry failed again", retry)
    page.unroute(poll)
    page.unroute(again)
    expect(page, rep, JS_ON, "worksheet retry: the draft did not come back", CREATE)


def walk_worksheet(page, rep: dict, phone: bool, data_dir: str) -> None:
    """The G4 draft panel beside the chat; a sheet at 390 px. Each desktop step stands on the one before."""
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    if phone:
        if ws_propose(page, rep, phone):
            with step(rep, "worksheet phone"):
                see_chat(page, rep, "worksheet phone open", phone)
                press(page, rep, '#draft [data-act="ws-close"]', "worksheet đóng tấm trượt", JS_WS_SHUT)
                toggle = page.locator("#draft-toggle")
                if not toggle.is_visible() or toggle.inner_text().strip() != "Phiếu nháp (6)":
                    rep["missing"].append("worksheet phone: no 'Phiếu nháp (6)' button once the sheet is closed")
                press(page, rep, "#draft-toggle", "worksheet Phiếu nháp (6)", JS_WS_OPEN)
                see_chat(page, rep, "worksheet phone sheet", phone)
        return
    if recs(data_dir):
        rep["missing"].append("worksheet: recommendation has rows before the walk")
    start = len(rep["missing"])
    if not (tid := ws_propose(page, rep, phone)):
        return
    see_chat(page, rep, "worksheet draft", phone)
    ok = lambda: len(rep["missing"]) == start  # noqa: E731
    want = ws_edit(page, rep, data_dir, reqs, tid)
    if ok():
        ws_chat_enter(page, rep, data_dir, reqs, tid, want)
        see_chat(page, rep, "worksheet edited", phone)
    if ok():
        ws_create(page, rep, data_dir, reqs, tid)
        see_chat(page, rep, "worksheet saved", phone)
    if ok():
        ws_replace(page, rep, phone, data_dir, reqs)
    if ok():
        ws_switch(page, rep, phone)
    if ok():
        ws_retry(page, rep)


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
# the import's poll answers "failed" (a killed app, a commit that broke); `__late` = it got past reading.
# Only G2 threads: the chat's grading cards keep polling their own threads meanwhile.
JS_FAIL_POLL = """() => { window.__get = U.api.get; window.__send = U.api.send;
  window.__resumes = 0; window.__cancels = 0; window.__late = false;
  const mine = p => p.startsWith('/threads/g2-') && p.includes('view=teacher');
  U.api.get = p => mine(p) ? Promise.resolve({thread_id: 't', graph: 'G2', status: 'failed',
    card: {kind: 'bank_import', stage: 'failed', items: window.__late ? [{}] : []}}) : window.__get(p);
  U.api.send = (m, p, b) => p.endsWith('/resume') ? (window.__resumes++, Promise.resolve({}))
    : p.endsWith('/cancel') ? (window.__cancels++, Promise.resolve({})) : window.__send(m, p, b); }"""
JS_UNFAIL = "() => { U.api.get = window.__get; U.api.send = window.__send; }"
JS_RESUMES_IS = "n => window.__resumes === n"
JS_CANCELS_IS = "n => window.__cancels === n"
JS_FILE_LIST = (
    "() => !document.querySelector('[data-act=\"imp-retry\"]') && !!document.querySelector('#modal-body .file-row')"
)
# the saved picks of a kept import thread cannot be read: the request fails, or the JSON is broken
JS_SAVED_BROKEN = """() => { window.__get = U.api.get; window.__mode = 'reject';
  const bad = Object.assign(new Error('x'), {status: 500});
  U.api.get = p => /^\\/threads\\/[^?]+$/.test(p)
    ? (window.__mode === 'reject' ? Promise.reject(bad) : Promise.resolve({decisions_json: '{nope'}))
    : window.__get(p); }"""
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
TYPO = "typo-label.tex"
TYPO_TEX = (
    "% Nhãn lạ\n\\begin{problem}[8DS-TYP-001]\n% kc_du_kien: 8DS-HSBN-01, 8DS-KHONG-CO\n% do_kho_du_kien: 2\n"
    "Cho $x = 1$.\n\n\\begin{solution}\nĐáp số: $x = 1$.\n\\end{solution}\n\\end{problem}\n"
)
UNKNOWN_LABEL = "Nhãn kỹ năng ghi trong file không có trong danh mục"
LEAF = "Kỹ năng lẻ"  # a skill with no topic over it, as the old catalog tab could make
SUMMARY = "5 bài · 1 đã có kỹ năng và mức · 3 cần chọn"
SAVE = '#modal-foot [data-act="imp-save"]'


def scalar(data_dir: str, sql: str, *args) -> int:
    """One number from the app's tutor.db, opened read-only while the app runs."""
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(sql, args).fetchone()[0]


def problems(data_dir: str, where: str = "1", *args) -> int:
    return scalar(data_dir, f"SELECT count(*) FROM problem WHERE {where}", *args)


def tag_rows(data_dir: str, pid: str) -> list:
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(
            "SELECT kc_id, step_idx FROM problem_kc WHERE problem_id = ? ORDER BY 1, 2", (pid,)
        ).fetchall()


def tag_own_topic(data_dir: str, pid: str) -> int:
    """Tag the problem with the KC of its own topic, a tag the Sửa form used to hide; returns that KC id."""
    with closing(sqlite3.connect(Path(data_dir, "tutor.db"))) as con, con:
        topic = con.execute(
            "SELECT COALESCE(k.parent_id, k.id) FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
            " WHERE pk.problem_id = ? ORDER BY k.id LIMIT 1",
            (pid,),
        ).fetchone()[0]
        con.execute(
            "INSERT OR IGNORE INTO problem_kc (problem_id, kc_id, step_idx, approved_at)"
            " VALUES (?, ?, 1, '2026-01-01T00:00:00Z')",
            (pid, topic),
        )
    return topic


def bank_level(page, rep: dict, data_dir: str, level: str, where: str) -> None:
    n = problems(data_dir, where)
    press(page, rep, f'[data-act="b-level"][data-v="{level}"]', f"bank level {level}", JS_COUNT_IS, n)


@counted()
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


@counted()
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


@counted(commit=SAVE_LABELS)
def bank_edit(page, rep: dict, phone: bool, data_dir: str, reqs: list) -> None:
    bank_level(page, rep, data_dir, "dễ", EASY)
    card = page.locator("#b-grid .bcard").first
    pid, ref = card.get_attribute("data-pid"), card.locator(".ref").first.inner_text()
    one = f'#b-grid .bcard[data-pid="{pid}"]'
    topic_kc = tag_own_topic(data_dir, pid)
    tags = tag_rows(data_dir, pid)
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
    if not page.locator(f'#modal-body [data-sk="{topic_kc}"]:checked').count():
        rep["missing"].append(f"bank edit: the topic-level skill {topic_kc} tagged on {ref} is not shown checked")
    boxes, rows = page.locator("#modal-body [data-sk]").count(), page.locator("#modal-body [data-rt]").count()
    press(page, rep, '[data-act="e-all"]', "bank hiện kỹ năng chủ đề khác", JS_CHECKS_GT, boxes)
    if not page.locator("#modal-body .skill-checks label", has_text=LEAF).count():
        rep["missing"].append("bank edit: a skill with no topic is not in Hiện kỹ năng chủ đề khác")
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
    if (now := tag_rows(data_dir, pid)) != tags:
        rep["missing"].append(f"bank edit: a level-only save changed the skill tags of {ref} from {tags} to {now}")
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
    (folder / TYPO).write_text(TYPO_TEX, encoding="utf-8")
    return mix, bad


def import_failed(page, rep: dict, phone: bool, mix: str, file_row) -> None:
    """A failed import thread (killed app, failed commit) offers Thử lại, and one click sends one resume.

    Bỏ drops the thread with one cancel and returns to the file list."""
    page.evaluate(JS_FAIL_POLL)
    for n, (late, said) in enumerate(
        ((False, "Không đọc được nội dung file"), (True, "Chưa lưu được vào ngân hàng")), 1
    ):
        page.evaluate("l => { window.__late = l; }", late)
        press(page, rep, f'{file_row(mix)} [data-act="imp-read"]', f"bank đọc {mix} khi lỗi", JS_ROOT_HAS, said)
        shown = page.inner_text("#modal-root")
        rep["missing"] += [
            f"bank import failed: no '{w}'" for w in ("Thử lại", "Bỏ", "Chọn file khác") if w not in shown
        ]
        see(page, rep, "bank import failed", phone)
        press(page, rep, '[data-act="imp-retry"]', "bank Thử lại", JS_RESUMES_IS, n)
        expect(page, rep, JS_ROOT_HAS, f"bank import failed: no '{said}' after Thử lại", said)
        press(page, rep, '[data-act="imp-back"]', "bank Chọn file khác", JS_ROOT_HAS, mix)
    press(page, rep, f'{file_row(mix)} [data-act="imp-read"]', f"bank đọc {mix} khi lỗi", JS_ROOT_HAS, "Thử lại")
    press(page, rep, '[data-act="imp-drop"]', "bank Bỏ", JS_FILE_LIST)
    expect(page, rep, JS_CANCELS_IS, "bank import failed: Bỏ should send exactly 1 cancel", 1)
    page.evaluate(JS_UNFAIL)


def import_typo(page, rep: dict, phone: bool, file_row) -> None:
    """A known skill next to a misspelt one: the row still warns and offers the picker, and Lưu stays on."""
    press(page, rep, f'{file_row(TYPO)} [data-act="imp-read"]', f"bank đọc {TYPO}", JS_ROOT_HAS, UNKNOWN_LABEL)
    expect(page, rep, JS_ENABLED, "bank import: a row with a known skill and a misspelt one cannot be saved")
    if page.locator("#modal-body .imp-row").count() != 1 or "thiếu" in page.inner_text("#modal-body .imp-row"):
        rep["missing"].append("bank import: the misspelt-label row should be one row that lacks nothing")
    if not page.locator("#modal-body [data-imp-kc] option", has_text=LEAF).count():
        rep["missing"].append("bank import: a skill with no topic is not in the skill picker")
    if not page.locator("#b-skill option", has_text=LEAF).count():
        rep["missing"].append("bank: a skill with no topic is not in the Kỹ năng filter")
    see(page, rep, "bank import misspelt label", phone)
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "bank import: Esc did not close")
    press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới", JS_ROOT_HAS, "Đọc file")


def import_reopen(page, rep: dict, phone: bool, mix: str, file_row, reqs: list) -> None:
    """Close with one pick saved. If that pick cannot be read back, the reopen must stop: a PUT would erase it."""
    read = f'{file_row(mix)} [data-act="imp-read"]'
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "bank import: Esc did not close")
    page.evaluate(JS_SAVED_BROKEN)
    for mode in ("reject", "json"):
        page.evaluate("m => { window.__mode = m; }", mode)
        press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới lại", JS_ROOT_HAS, mix)
        seen = len(reqs)
        press(page, rep, read, f"bank đọc lại {mix}", JS_ROOT_HAS, "Không đọc được lựa chọn đã lưu")
        if page.locator(SAVE).count() or any(m == "PUT" for m, _, _ in reqs[seen:]):
            rep["missing"].append(f"bank import: an unreadable saved pick ({mode}) went on to the preview")
        see(page, rep, f"bank import reopen {mode}", phone)
        page.keyboard.press("Escape")
        expect(page, rep, JS_NO_MODAL, "bank import: Esc did not close")
    page.evaluate("() => { U.api.get = window.__get; }")
    press(page, rep, '[data-act="b-import"]', "bank Nạp bài mới lại", JS_ROOT_HAS, mix)
    press(page, rep, read, f"bank đọc lại {mix}", JS_ROOT_HAS, "Còn 1 bài chưa chọn kỹ năng")


@counted(commit=SAVE_IMPORT)
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
    import_failed(page, rep, phone, mix, file_row)
    import_typo(page, rep, phone, file_row)
    start = len(rep["missing"])  # the steps below stand on their own
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
    first = int(page.input_value(f"{row(ref(2))} select"))
    import_reopen(page, rep, phone, mix, file_row, reqs)
    if len(rep["missing"]) > start:
        return
    pick(3, 1)
    press(page, rep, f'{row(ref(4))} [data-act="imp-level"][data-v="vừa"]', "bank import mức vừa", JS_ENABLED)
    want = {
        ref(2): {"kc_ids": [first]},
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
    pick(3, 2)
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
    walk_chat(page, rep, phone, data_dir, base.removesuffix("v3/"))
    if data_dir:
        walk_grading(page, rep, phone, data_dir)
        walk_worksheet(page, rep, phone, data_dir)
    walk_bank(page, rep, phone, data_dir, files)
    walk_gear(page, rep, phone)
    walk_theme(page, rep, base)
    page.wait_for_timeout(500)  # late errors
    with step(rep, "walk end"):  # catches rows changed since the last step
        pass
    page.context.close()
    return rep


def fold(text: str) -> str:
    """Lowercase, no diacritics; đ has no decomposition, so it is mapped by hand."""
    plain = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in plain if not unicodedata.combining(c)).replace("đ", "d")


NAMES = tuple(fold(n) for n in (*PEOPLE, ARCHIVED))  # every student the walk creates


def finish(data_dir: str) -> dict:
    """After both walks: no student name in llm.jsonl or the chat logs (C-40), and the row counts saw the saves.

    A missing, empty or seed-only log would pass the scan, so it fails it."""
    rep = {k: [] for k in ("console_errors", "page_errors", "dead", "missing", "forbidden", "overflow", "shots")}
    logs = Path(data_dir, "logs")
    files = [logs / "llm.jsonl", *sorted(logs.glob("chat/*.jsonl"))]
    texts = {f.name: f.read_text(encoding="utf-8") if f.is_file() else "" for f in files}
    rep |= {"viewport": "end", "scanned": {name: len(text) for name, text in texts.items()}}
    if len(files) < 2:
        rep["missing"].append("log scan: no chat log in data/logs/chat/")
    seed = SEED_LOG.read_text(encoding="utf-8")
    made = texts[files[0].name].removeprefix(seed)
    if not re.search(r'^\{"agent": "00"', made, re.M):  # the seed has agents 01-03 only
        rep["missing"].append("log scan: llm.jsonl holds no agent 00 call after the seed, the app logged nothing")
    for name, text in texts.items():
        if not text.strip():
            rep["missing"].append(f"log scan: {name} is missing or empty")
        rep["missing"] += [f"log scan: '{n}' is in {name}" for n in NAMES if n in fold(text)]
    if lost := MOVES_ROWS - {e["step"] for e in LEDGER["log"] if e["changed"]}:
        rep["missing"].append(f"db: steps {sorted(lost)} changed no rows, so the row counts see nothing")
    return rep


def check(url: str, args: argparse.Namespace) -> int:
    base = f"{url}v3/"
    data_dir = getattr(url, "data_dir", None) if args.data else None
    if data_dir:
        api(url, "POST", "/catalog/kc", {"code": "ROBOT-LE-01", "name": LEAF, "description": "robot", "lop": 8})
        api(url, "POST", f"/students/{api(url, 'POST', '/students', {'name': ARCHIVED, 'grade': 7})['id']}/archive")
        LEDGER.update(dir=data_dir, last=counts(data_dir))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        views = [walk(browser, base, n, vp, args.shots, data_dir) for n, vp in (("desktop", DESK), ("phone", PHONE))]
        browser.close()
    if data_dir:
        views.append(finish(data_dir))
    keys = ("console_errors", "page_errors", "dead", "missing", "forbidden", "overflow")
    summary = {k: sum(len(v[k]) for v in views) for k in keys}
    summary["ok"] = not any(summary.values())
    print(json.dumps({"page": base, "views": views, "db_changes": LEDGER["log"], "summary": summary},
                     ensure_ascii=False, indent=1))  # fmt: skip
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
