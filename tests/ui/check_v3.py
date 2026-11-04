#!/usr/bin/env python3
"""Robot UI check for the 4-tab app at / (P5-T05).

Run: .venv/bin/python tests/ui/check_v3.py [--url http://127.0.0.1:8000/] [--data] [--shots]
Opens / at 1440 px and 390 px; walks the 4 tabs, the Trợ lý chat tab (reminders, @, stream, cards, 📎, retry,
the G1 grading card, the G4 worksheet panel), the Báo cáo tab (draft, edit, approve, PDF), the Học sinh tab (list,
add / edit / archive, profile with chart, windows), the Ngân hàng bài tab (filters, view, edit, import), ⚙ menu,
light/dark.
Exit 1 on any page error, app console error, dead button, horizontal overflow at 390 px or forbidden text on screen.
Without --url it starts `tutor app` on a free port with a temp data dir; --data seeds dummy bank and students and
checks the chat and bank tabs against that tutor.db and imports tests/fixtures/bank/import-mix.tex (needs no --url).
It also prints db_changes (tutor.db row counts around each step; only commit-button steps may change them) and
scans llm.jsonl and the chat logs for student names.
"""

import argparse
import functools
import json
import math
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from tutor.db.repo import TABLES

SHOTS = Path(__file__).resolve().parent / "shots"
DESK = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

# Network noise (offline fonts/CDN) is not an app bug.
NET_NOISE = ("Failed to load resource", "net::ERR_")

# the seeded HS-02 session parked at gate_confirm_commit (add_students)
PREVIEW_TID = "g1-hs02-20261023-2"

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


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "submissions"
BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"
KEY_VARS = ("ANTHROPIC", "OPENAI")
# what `tutor` does at start: load ./.env, then see which API-key variables the process holds (names only, never values)
KEY_PROBE = (
    "import os; from tutor import config; config.load_env(config.ENV_FILE); "
    f"print(*[k for k in os.environ if k.startswith({KEY_VARS})])"
)


def keys_seen(env: dict, cwd: str) -> list[str]:
    """Names of the API-key variables a `tutor` process started with `env` in `cwd` would hold."""
    run = subprocess.run([sys.executable, "-c", KEY_PROBE], env=env, cwd=cwd, capture_output=True, text=True,
                         check=True, timeout=30)  # fmt: skip
    return run.stdout.split()


def seed(exe: str, data: str, env: dict) -> None:
    """Dummy bank + inbox files; students are added over the API once the app is up."""
    subprocess.run([exe, "seed-dummy", "--dev", "--bank", str(BANK), "--data-dir", data], check=True,
                   capture_output=True, timeout=120, env=env, cwd=Path(data).parent)  # fmt: skip
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


class AppUrl(str):
    """The app's root URL; `data_dir` is its throwaway data dir."""

    data_dir: str


@contextmanager
def tutor_app(with_data: bool = False):
    """`tutor app` on a free port with a throwaway data dir; yields its URL (an AppUrl)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = AppUrl(f"http://127.0.0.1:{port}/")
    with tempfile.TemporaryDirectory() as tmp:
        url.data_dir = f"{tmp}/data"
        exe = str(Path(sys.executable).absolute().with_name("tutor"))
        # --fake-llm, no ANTHROPIC* / OPENAI* env, and a cwd with no .env (the CLI loads ./.env): the robot
        # never reaches a real API (C-34)
        env = {k: v for k, v in os.environ.items() if not k.startswith(KEY_VARS)}
        if leaked := keys_seen(env, tmp):
            raise RuntimeError(f"the robot's app would hold API keys: {leaked}")
        if with_data:
            seed(exe, f"{tmp}/data", env)
        proc = subprocess.Popen([exe, "app", "--no-browser", "--port", str(port), "--data-dir", f"{tmp}/data",
                                 "--fake-llm"], env=env, cwd=tmp)  # fmt: skip
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
        if SOON in page.inner_text(f"#panel-{tab}"):
            rep["missing"].append(f"{tab}: '{SOON}' still on the tab")
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


JS_CATALOG = """() => ({
  topics: document.querySelectorAll('#modal-body details').length,
  open: document.querySelectorAll('#modal-body details[open]').length,
  kinds: document.querySelectorAll('#modal-body .cat-kinds li').length,
})"""
CATALOG_NOTE = "Danh mục chỉ xem ở đây; người cài đổi được bằng file."


def walk_catalog(page, rep: dict, phone: bool, data: bool) -> None:
    """⚙ Danh mục is read-only: topics fold open on their skills, active error codes by description."""
    kcs = page.evaluate("U.api.get('/catalog/kc')")
    active = [c for c in page.evaluate("U.api.get('/catalog/error-codes')") if c["active"]]
    topics = [k for k in kcs if k["parent_id"] is None]
    got = page.evaluate(JS_CATALOG)
    text = page.inner_text("#modal-body")
    if CATALOG_NOTE not in text:
        rep["missing"].append("gear catalog: the read-only note is missing")
    if (got["topics"], got["open"], got["kinds"]) != (len(topics), 0, len(active)) or len(active) != 18:
        rep["missing"].append(f"gear catalog: page shows {got}, API has {len(topics)} topics, {len(active)} codes (18)")
    first = next((t for t in topics if any(k["parent_id"] == t["id"] for k in kcs)), None)
    if not first:
        rep["missing"].append("gear catalog: no topic with skills")
        return
    kids = [k["name"] for k in kcs if k["parent_id"] == first["id"]]
    summary = f"#modal-body details >> nth={topics.index(first)} >> summary"
    press(page, rep, summary, "gear catalog topic")
    shown = page.evaluate("[...document.querySelectorAll('#modal-body details[open] li')].map(l => l.innerText)")
    if shown != kids or f"lớp {first['lop']} · {len(kids)} kỹ năng" not in page.inner_text(summary):
        rep["missing"].append(f"gear catalog: topic {first['name']!r} shows {shown}, expected {kids}")
    if any(k["code"] in page.inner_text("#modal-body") for k in kcs):
        rep["missing"].append("gear catalog: a skill code is on screen")


JS_BK_ROWS = "() => [...document.querySelectorAll('#modal-body tbody tr')].map(r => [...r.cells].map(c => c.innerText))"
JS_N_ROWS = "n => document.querySelectorAll('#modal-body tbody tr').length === n"
JS_RELOADED = "() => window.__robotLoaded === undefined"
JS_NO_RUNNING = "() => U.api.get('/threads').then(r => !r.some(t => t.running || t.status === 'running'))"
BK_WHEN = re.compile(r"\d\d/\d\d/\d{4} \d\d:\d\d")
BK_SIZE = re.compile(r"\d+,\d MB")
NO_BACKUPS = "Chưa có bản sao lưu."
RESTORE_API = "**/api/backup/restore"
CORRUPT = "Bản sao lưu này bị hỏng, không khôi phục được."
REFUSED = json.dumps({"error": {"code": "validation_error", "message": CORRUPT, "detail": None}})
SAFETY_WORDS = (  # (file the server names in detail.safety_backup, what the page says instead)
    ("tutor-2026-10-20-093000.db", "bản sao lưu lúc 20/10/2026 09:30"),
    ("tutor.db.broken-20261020-093000", "bản lưu tạm của dữ liệu cũ"),
)
UNFINISHED = ("G1", "bài chấm"), ("G4", "phiếu nháp"), ("G2", "lần nạp bài"), ("G5", "báo cáo nháp")
OPEN_STATES = ("running", "awaiting_review", "failed")


def backup_when(name: str) -> str:
    """tutor-2026-10-20-093000.db -> 20/10/2026 09:30, as the Sao lưu table shows it."""
    y, mo, d, hm = re.match(r"tutor-(\d{4})-(\d\d)-(\d\d)-(\d{4})", name).groups()
    return f"{d}/{mo}/{y} {hm[:2]}:{hm[2:]}"


def walk_backup(page, rep: dict, phone: bool, data: bool) -> None:
    """⚙ Sao lưu: the data folder, then every file of data/backup/ as When · Size · Khôi phục (or the empty line)."""
    if not expect(page, rep, JS_ROOT_HAS, "gear backup: the list did not open", "Thư mục dữ liệu:"):
        return
    info = page.evaluate("U.api.get('/backup')")
    text, rows = page.inner_text("#modal-body"), page.evaluate(JS_BK_ROWS)
    if f"Thư mục dữ liệu: {info['data_dir']}" not in text:
        rep["missing"].append(f"gear backup: the data folder {info['data_dir']} is not on screen")
    want = [backup_when(b["name"]) for b in info["backups"]]
    if [r[0] for r in rows] != want or not all(BK_SIZE.fullmatch(r[1]) and r[2] == "Khôi phục" for r in rows):
        rep["missing"].append(f"gear backup: the table shows {rows}, the folder has {want}")
    if not all(BK_WHEN.fullmatch(w) for w in want) or (NO_BACKUPS in text) != (not rows):
        rep["missing"].append(f"gear backup: wrong dates or empty line ({rows}, {NO_BACKUPS!r})")


def backup_names(page) -> list:
    return [b["name"] for b in page.evaluate("U.api.get('/backup')")["backups"]]


def backup_restore(page, rep: dict, phone: bool) -> None:
    """Sao lưu ngay adds one row; Khôi phục of that row asks again, then the page reloads (nothing is unfinished)."""
    before = backup_names(page)
    press(page, rep, "#gear-btn", "gear")
    press(page, rep, '[data-sys="backup"]', "gear item backup", JS_ROOT_HAS, "Sao lưu ngay")
    with step(rep, "backup_restore", commit=TABLES):
        press(page, rep, '[data-act="backup-now"]', "backup Sao lưu ngay", JS_TOAST_HAS, "Đã sao lưu dữ liệu.")
        expect(page, rep, JS_N_ROWS, "backup: Sao lưu ngay did not add a row", len(before) + 1)
        new = sorted(set(backup_names(page)) - set(before))
        if len(new) != 1:
            rep["missing"].append(f"backup: Sao lưu ngay added {new}, expected one file")
            return
        see(page, rep, "gear backup", phone)
        ask = f'[data-act="backup-restore"][data-name="{new[0]}"]'
        # a damaged file: the page shows the server's own words and stays where it is
        page.route(RESTORE_API, lambda r: r.fulfill(status=422, content_type="application/json", body=REFUSED))
        press(page, rep, ask, "backup Khôi phục (hỏng)", JS_ROOT_HAS, "Khôi phục bản sao lưu?")
        press(page, rep, '[data-act="confirm-ok"]', "backup Khôi phục (hỏng, hỏi lại)", JS_TOAST_HAS, CORRUPT)
        page.unroute(RESTORE_API)
        # a failure after tutor.db was touched: the toast says when / what the old data is, never a file name (C-01)
        for safety, words in SAFETY_WORDS:
            press(page, rep, "#gear-btn", "gear")
            press(page, rep, '[data-sys="backup"]', "gear item backup", JS_ROOT_HAS, "Sao lưu ngay")
            failed = json.dumps(
                {
                    "error": {
                        "code": "restore_failed",
                        "message": f"Chưa khôi phục được. Dữ liệu trước khi khôi phục nằm ở {safety}.",
                        "detail": {"safety_backup": safety},
                    }
                }
            )
            page.route(
                RESTORE_API, lambda r, _, body=failed: r.fulfill(status=500, content_type="application/json", body=body)
            )
            press(page, rep, ask, "backup Khôi phục (lỗi)", JS_ROOT_HAS, "Khôi phục bản sao lưu?")
            press(
                page, rep, '[data-act="confirm-ok"]', "backup Khôi phục (lỗi, hỏi lại)", JS_TOAST_HAS, f"nằm ở {words}."
            )
            page.unroute(RESTORE_API)
            if ".db" in page.inner_text("#toasts"):
                rep["missing"].append(f"backup: the failure toast shows a file name: {page.inner_text('#toasts')!r}")
        press(page, rep, "#gear-btn", "gear")
        press(page, rep, '[data-sys="backup"]', "gear item backup", JS_ROOT_HAS, "Sao lưu ngay")
        press(page, rep, ask, "backup Khôi phục", JS_ROOT_HAS, "Khôi phục bản sao lưu?")
        if f"Dữ liệu sẽ quay về lúc {backup_when(new[0])}." not in page.inner_text("#modal-body"):
            rep["missing"].append("backup: the question does not name the backup's time")
        page.evaluate("window.__robotLoaded = 1")
        press(
            page,
            rep,
            '[data-act="confirm-ok"]',
            "backup Khôi phục (hỏi lại)",
            JS_TOAST_HAS,
            f"Đã khôi phục bản {backup_when(new[0])}",
        )
        expect(page, rep, JS_RELOADED, "backup: the page did not reload after Khôi phục")
        if page.evaluate("U.api.get('/health')").get("status") != "ok":
            rep["missing"].append("backup: the app is not ok after Khôi phục")
        if len(backup_names(page)) != len(before) + 2:  # the new file, and the safety copy of the data before it
            rep["missing"].append("backup: Khôi phục did not leave a copy of the data it replaced")


FAKE_KEY = "sk-robot-" + "x" * 30  # only ever typed into the robot's own app, which writes it to <its data>/.env
FAKE_KEY2 = "sk-robot-" + "y" * 30  # the key typed while settings.json is broken
BAD_SETTINGS = "File cài đặt bị hỏng, nhờ người cài sửa."
KEY_SAVED = "Đã lưu khoá."
KEY_VAR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
PROVIDER = {"anthropic": "Anthropic", "openai": "OpenAI"}
KEY_HINT = {True: "Đã có khoá. Để trống nếu không đổi.", False: "Chưa có khoá: dán khoá người cài gửi."}
SAVED_SETTINGS = "Đã lưu cài đặt."
BAD_KEY = "Khoá không đúng dạng"
JS_SET_FORM = """() => ({
  nums: ['set-n', 'set-norep', 'set-budget'].map(id => {
    const i = document.getElementById(id); return [i.type, i.min, i.max, i.value]; }),
  keys: [...document.querySelectorAll('#modal-body input[type=password]')].map(i => [i.id, i.autocomplete, i.value]),
})"""
JS_TEXT_HAS = "([id, t]) => document.getElementById(id).innerText.includes(t)"
JS_NOKEY_ON = "() => { const n = document.getElementById('nokey'); return !!n && !n.hidden; }"
JS_PUT_BAD = """p => fetch('/api/settings/key', {
  method: 'PUT', headers: { 'X-Tutor': '1', 'Content-Type': 'application/json' },
  body: JSON.stringify({ provider: p, key: 'sk bad' }) }).then(r => r.text())"""


def settings_now(page) -> dict:
    return page.evaluate("U.api.get('/settings')")


def save_settings(page, rep: dict, label: str, fields: dict) -> None:
    """Type into the boxes and press Lưu cài đặt; the toast says it was saved."""
    page.evaluate("document.getElementById('toasts').innerHTML = ''")
    for sel, text in fields.items():
        page.fill(sel, text)
    press(page, rep, '[data-act="settings-save"]', f"settings {label}", JS_TOAST_HAS, SAVED_SETTINGS)


def reopen_settings(page, rep: dict) -> None:
    close_overlay(page)
    press(page, rep, "#gear-btn", "gear")
    press(page, rep, '[data-sys="settings"]', "gear item settings", JS_ROOT_HAS, "Lưu cài đặt")


def modal_text(page) -> str:
    return page.evaluate("document.getElementById('modal-body')?.innerText ?? ''")


def leaks(home: str, shown: str, key: str = FAKE_KEY) -> list[str]:
    """Where `key` must not be: the page, settings.json, app.log. Names the places that hold it."""
    places = {"the page": shown}
    for name in ("settings.json", "logs/app.log", "logs/llm.jsonl"):
        f = Path(home, name)
        places[name] = f.read_text(encoding="utf-8") if f.is_file() else ""
    return [w for w, text in places.items() if key in text]


def walk_settings(page, rep: dict, phone: bool, home: str | None) -> None:
    """⚙ Cài đặt: three numbers and one password box per provider in use. With `home` (the app the robot started) it
    also saves: 6 -> 8 -> 6, 13 refused, a key typed in goes to <home>/.env (0600) and nowhere else."""
    if not expect(page, rep, JS_ROOT_HAS, "gear settings: the form did not open", "Lưu cài đặt"):
        return
    now, form, text = settings_now(page), page.evaluate(JS_SET_FORM), page.inner_text("#modal-body")
    want = [
        ["number", "3", "12", str(now["reco"]["n_problems"])],
        ["number", "0", "120", str(now["reco"]["no_repeat_days"])],
        ["number", "0", "", str(now["budget_usd_month"])],
    ]
    if form["nums"] != want:
        rep["missing"].append(f"gear settings: the three numbers are {form['nums']}, expected {want}")
    if [k[0] for k in form["keys"]] != [f"set-key-{p}" for p in now["keys"]] or any(
        k[1:] != ["off", ""] for k in form["keys"]
    ):
        rep["missing"].append(f"gear settings: key boxes are {form['keys']}, API has {now['keys']}")
    for p, has in now["keys"].items():
        if f"Khoá {PROVIDER[p]}" not in text or KEY_HINT[has] not in text:
            rep["missing"].append(f"gear settings: no 'Khoá {PROVIDER[p]}' box with '{KEY_HINT[has]}'")
    if "Giao diện" in text:
        rep["missing"].append("gear settings: the theme switch is repeated in Cài đặt (it stays in the ⚙ menu)")
    if not home:
        return
    n0, box = now["reco"]["n_problems"], f"#set-key-{next(iter(now['keys']))}"
    pv = box.removeprefix("#set-key-")
    with step(rep, "gear_settings"):  # writes settings.json and <data>/.env, never tutor.db
        save_settings(page, rep, "6 to 8", {"#set-n": "8"})
        if settings_now(page)["reco"]["n_problems"] != 8:
            rep["missing"].append("gear settings: Lưu cài đặt did not save 8 (GET /api/settings)")
        reopen_settings(page, rep)
        if page.input_value("#set-n") != "8":
            rep["missing"].append(f"gear settings: reopened with {page.input_value('#set-n')!r}, expected 8")
        page.fill("#set-n", "13")
        press(
            page, rep, '[data-act="settings-save"]', "settings 13", JS_TEXT_HAS, ["set-n-err", "Nhập số từ 3 đến 12."]
        )
        if settings_now(page)["reco"]["n_problems"] != 8:
            rep["missing"].append("gear settings: 13 was saved")
        see(page, rep, "gear settings error", phone)
        save_settings(page, rep, "back to the first value", {"#set-n": str(n0)})  # the next walk drafts sheets of n0
        if settings_now(page)["reco"]["n_problems"] != n0 or page.inner_text("#set-n-err"):
            rep["missing"].append(f"gear settings: the number is not back to {n0}, or the error stayed")
        # a bad key: refused under its box, and the 422 body does not hold it
        page.fill(box, "sk bad")
        press(page, rep, '[data-act="settings-save"]', "settings bad key", JS_TEXT_HAS, [f"{box[1:]}-err", BAD_KEY])
        if "sk bad" in page.evaluate(JS_PUT_BAD, pv):
            rep["missing"].append("gear settings: the 422 for a bad key holds the key")
        if settings_now(page)["keys"] != now["keys"]:
            rep["missing"].append("gear settings: a bad key changed the keys")
        save_settings(page, rep, "key", {box: FAKE_KEY})
        after = settings_now(page)
        if after["keys"] != dict.fromkeys(now["keys"], True) or page.input_value(box) != "":
            rep["missing"].append(
                f"gear settings: after the key keys are {after['keys']}, box {page.input_value(box)!r}"
            )
        if KEY_HINT[True] not in page.inner_text("#modal-body"):
            rep["missing"].append("gear settings: the box does not say there is a key now")
        if placed := leaks(home, page.inner_text("body") + page.evaluate("document.documentElement.outerHTML")):
            rep["missing"].append(f"gear settings: the key is in {placed}")
        if FAKE_KEY in json.dumps(after):
            rep["missing"].append("gear settings: GET /api/settings holds the key")
        env = Path(home, ".env")
        lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if ln.startswith(KEY_VAR[pv])]
        if lines != [f"{KEY_VAR[pv]}={FAKE_KEY}"] or env.stat().st_mode & 0o777 != 0o600:
            rep["missing"].append(
                f"gear settings: .env has {len(lines)} key lines, mode {oct(env.stat().st_mode & 0o777)}"
            )
        file = Path(home, "settings.json")
        if not set(json.loads(file.read_text(encoding="utf-8"))) <= {"reco", "budget_usd_month"}:
            rep["missing"].append("gear settings: settings.json holds more than the tutor changed")
        # settings.json breaks while the app runs: the numbers are refused, the key (it lives in .env) still saves
        good = file.read_bytes()
        file.write_bytes(b"{oops")
        try:
            reopen_settings(page, rep)
            page.evaluate("document.getElementById('toasts').innerHTML = ''")
            page.fill("#set-n", "7")
            page.fill(box, FAKE_KEY2)
            press(page, rep, '[data-act="settings-save"]', "settings broken file and key", JS_TOAST_HAS, KEY_SAVED)
            if not page.evaluate(JS_TOAST_HAS, BAD_SETTINGS):
                rep["missing"].append("gear settings: no word about the broken file next to the saved key")
            lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if ln.startswith(KEY_VAR[pv])]
            if lines != [f"{KEY_VAR[pv]}={FAKE_KEY2}"] or page.input_value(box) != "":
                rep["missing"].append(f"gear settings: broken file: the key did not save ({len(lines)} lines in .env)")
            if file.read_bytes() != b"{oops" or settings_now(page)["reco"]["n_problems"] != n0:
                rep["missing"].append("gear settings: broken file: the number or the file changed")
            if placed := leaks(
                home, page.inner_text("body") + page.evaluate("document.documentElement.outerHTML"), FAKE_KEY2
            ):
                rep["missing"].append(f"gear settings: the second key is in {placed}")
        finally:
            file.write_bytes(good)


def walk_nokey(page, rep: dict, phone: bool) -> None:
    """R15: 'Trợ lý chưa có khoá API.' tops the Trợ lý tab only when a provider has no key and the app is not
    --fake-llm; Mở Cài đặt opens ⚙ Cài đặt, and Lưu cài đặt draws the line again. health and settings are stubbed."""
    state = {"fake": False, "keys": {"openai": False}}

    def health(route) -> None:
        r = route.fetch()
        route.fulfill(response=r, json=r.json() | {"fake_llm": state["fake"]})

    def settings(route) -> None:
        if route.request.method != "GET":
            return route.continue_()
        r = route.fetch()
        return route.fulfill(response=r, json=r.json() | {"keys": state["keys"]})

    page.route("**/api/health", health)
    page.route("**/api/settings", settings)
    try:
        for fake, keys, shown in (
            (False, {"openai": False}, True),
            (False, {"openai": True}, False),
            (True, {"openai": False}, False),
            (False, {"anthropic": True, "openai": False}, True),
            (False, {"openai": False}, True),
        ):
            state.update(fake=fake, keys=keys)
            page.evaluate("location.hash = '#tro-ly'")
            try:
                with page.expect_response(lambda r: r.url.endswith("/api/settings"), timeout=3000):
                    page.reload()
            except Exception:  # noqa: BLE001
                rep["missing"].append("nokey: the Trợ lý tab did not ask for /api/settings")
            page.wait_for_timeout(150)
            if page.evaluate(JS_NOKEY_ON) != shown:
                rep["missing"].append(
                    f"nokey: fake_llm {fake}, keys {keys}: the line should be {'shown' if shown else 'hidden'}"
                )
        # the last state shows the line: it is the tab's first child, and its button opens Cài đặt
        if page.evaluate("document.querySelector('.chat').firstElementChild.id") != "nokey":
            rep["missing"].append("nokey: the line is not the first thing in the tab")
        line = page.evaluate("document.getElementById('nokey')?.innerText ?? ''")
        if "Trợ lý chưa có khoá API." not in line:
            rep["missing"].append(f"nokey: the line says {line!r}")
        see(page, rep, "nokey", phone)
        press(page, rep, '#nokey [data-act="c-keys"]', "nokey Mở Cài đặt", JS_ROOT_HAS, "Lưu cài đặt")
        if "Khoá OpenAI" not in modal_text(page) or KEY_HINT[False] not in modal_text(page):
            rep["missing"].append("nokey: Mở Cài đặt did not open the form with a 'Khoá OpenAI' box")
        state["keys"] = {"openai": True}  # the key is there now: Lưu cài đặt draws the line again
        press(page, rep, '[data-act="settings-save"]', "nokey Lưu cài đặt", JS_TOAST_HAS, SAVED_SETTINGS)
        expect(
            page,
            rep,
            "() => !document.getElementById('nokey') || document.getElementById('nokey').hidden",
            "nokey: the line stayed after Lưu cài đặt",
        )
    finally:
        page.unroute("**/api/health")
        page.unroute("**/api/settings")
    close_overlay(page)
    page.reload()


GEAR_OPENS = {"backup": "Sao lưu ngay", "catalog": "Loại lỗi", "settings": "Lưu cài đặt", "cost": "USD"}
COST_API = "**/api/logs/cost*"
COST_LABELS = ["Chấm bài", "Trợ lý", "Báo cáo", "Khác"]
COST_LINE = re.compile(r"Khoảng (\d+),(\d+) USD trên (\S+) USD \(giả định\)")
COST_ROW = re.compile(r"(\d+),(\d+) USD")
NEAR = "Đã dùng hơn 80 % ngân sách tháng."
OVER = "Đã vượt ngân sách tháng. App vẫn chạy bình thường."
NO_BUDGET = "Chưa đặt ngân sách tháng."
JS_BAR = """() => { const b = document.querySelector('#modal-body [role=progressbar]');
  return b && [Number(b.getAttribute('aria-valuenow')), b.firstElementChild.style.width]; }"""
JS_STRAY = """() => {
  document.body.insertAdjacentHTML('beforeend', '<button id="stray" data-act="sys" data-sys="nope">x</button>');
  document.getElementById('stray').click(); document.getElementById('stray').remove();
}"""
JS_TOAST_N = "t => [...document.querySelectorAll('#toasts .toast')].filter(x => x.innerText.includes(t)).length"
JS_SOON_IN_SCRIPTS = """s => Promise.all([...document.scripts].filter(x => x.src.startsWith(location.origin)).map(
  x => fetch(x.src).then(r => r.text()).then(t => t.includes(s) ? x.src : null))).then(r => r.filter(Boolean))"""


def walk_cost(page, rep: dict, phone: bool) -> None:
    """⚙ Chi phí tháng: the sentence with the USD total and budget, a % bar, one row per task; no per-call figures."""
    c = page.evaluate("U.api.get('/logs/cost')")
    text, rows = modal_text(page), page.evaluate(JS_BK_ROWS)
    m = COST_LINE.search(text)
    if not m or m[3] != str(c["budget_usd"]).replace(".", ",") or abs(float(f"{m[1]}.{m[2]}") - c["total_usd"]) > 0.05:
        rep["missing"].append(
            f"gear cost: no 'Khoảng … USD trên {c['budget_usd']} USD (giả định)' for {c['total_usd']}"
        )
    got = [(r[0], COST_ROW.fullmatch(r[1])) for r in rows]
    if [g[0] for g in got] != COST_LABELS or not all(g[1] for g in got):
        rep["missing"].append(f"gear cost: the table shows {rows}, expected {COST_LABELS} with USD")
    elif any(abs(float(f"{g[1][1]}.{g[1][2]}") - p["usd"]) > 0.05 for g, p in zip(got, c["parts"], strict=True)):
        rep["missing"].append(f"gear cost: the table {rows} does not match the API {c['parts']}")
    pct = min(100, round(c["pct"] * 100))
    if page.evaluate(JS_BAR) != [pct, f"{pct}%"]:
        rep["missing"].append(f"gear cost: the bar is {page.evaluate(JS_BAR)}, expected {pct} %")
    if (NEAR in text or OVER in text) != bool(c["warning"]):
        rep["missing"].append(f"gear cost: a warning on screen does not match warning {c['warning']!r}")
    if re.search(r"lời gọi|calls|phiên|session", text, re.I):
        rep["missing"].append("gear cost: per-call or per-session wording on screen")


def walk_cost_warning(page, rep: dict, phone: bool) -> None:
    """R14: /api/logs/cost is stubbed with each warning: ⚙ Chi phí says it, and one toast says it when the app opens
    (opening ⚙ Chi phí adds none). A budget of 0 says it is not set and draws no bar. A real answer (warning null)
    opens the app with no toast."""
    state = {"patch": {}}

    def stub(route) -> None:
        r = route.fetch()
        route.fulfill(response=r, json=r.json() | state["patch"])

    page.route(COST_API, stub)
    try:
        for warn, words in (("near", NEAR), ("over", OVER)):
            state["patch"] = {"warning": warn}
            page.reload()
            if expect(page, rep, JS_TOAST_HAS, f"cost {warn}: no toast when the app opened", words):
                page.wait_for_timeout(300)
                if (n := page.evaluate(JS_TOAST_N, words)) != 1:
                    rep["missing"].append(f"cost {warn}: {n} toasts say it, expected 1")
            press(page, rep, "#gear-btn", "gear")
            press(page, rep, '[data-sys="cost"]', f"gear item cost ({warn})", JS_ROOT_HAS, words)
            if (n := page.evaluate(JS_TOAST_N, words)) != 1:
                rep["missing"].append(f"cost {warn}: opening ⚙ Chi phí left {n} toasts, expected the 1 from the load")
            see(page, rep, f"gear cost {warn}", phone)
            close_overlay(page)
        state["patch"] = {"budget_usd": 0, "pct": None, "warning": None}
        press(page, rep, "#gear-btn", "gear")
        press(page, rep, '[data-sys="cost"]', "gear item cost (no budget)", JS_ROOT_HAS, NO_BUDGET)
        if page.query_selector("#modal-body [role=progressbar]"):
            rep["missing"].append("cost: a budget of 0 still draws the bar")
        close_overlay(page)
    finally:
        page.unroute(COST_API)
    page.reload()
    page.wait_for_timeout(600)
    if shown := page.evaluate("document.getElementById('toasts').innerText.trim()"):
        rep["missing"].append(f"cost: the app opened with a toast {shown!r} and no warning")


def walk_gear(page, rep: dict, phone: bool, data: bool, home: str | None) -> None:
    keys = page.evaluate("[...document.querySelectorAll('[data-sys]')].map(b => b.dataset.sys)")
    if len(keys) != 4:
        rep["missing"].append(f"gear menu has {len(keys)} items, expected 4")
    for key, how in [(k, h) for k in keys for h in ("Esc", "×")]:
        label = f"gear {key} closed by {how}"
        press(page, rep, "#gear-btn", "gear")
        if not page.is_visible(f'[data-sys="{key}"]'):
            rep["missing"].append(f"gear menu did not show {key}")
            continue
        press(page, rep, f'[data-sys="{key}"]', f"gear item {key}", JS_ROOT_HAS, GEAR_OPENS[key])
        if SOON in page.inner_text("#modal-root"):
            rep["missing"].append(f"gear {key}: still '{SOON}'")
        elif how == "Esc" and key == "settings":
            walk_settings(page, rep, phone, home)
        elif how == "Esc" and key == "cost":
            walk_cost(page, rep, phone)
        elif how == "Esc":
            (walk_catalog if key == "catalog" else walk_backup)(page, rep, phone, data)
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
    if left := page.evaluate(JS_SOON_IN_SCRIPTS, SOON):
        rep["missing"].append(f"gear: '{SOON}' is still in {left}")
    # a ⚙ item with no handler must not throw (a page error would fail the run)
    page.evaluate(JS_STRAY)
    walk_cost_warning(page, rep, phone)
    if not data:
        backup_restore(page, rep, phone)


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
FACT_ID = re.compile(r"\bF\d\d\b")
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
# G1 threads of the seeded sessions (add_students) and of the file 📎 grades for real on the desktop
G_S01, G_S06, G_S04, G_NEW = "g1-hs01-20261020", "g1-hs01-20261022", "g1-hs02-20261023", "g1-hs01-20261025"
LOCKED = f"Duyệt buổi 20/10 của {PEOPLE[0]} trước (tiến bộ tính theo thứ tự ngày)"
LEFT_5 = "Còn 5 lỗi chưa chọn Đúng / Sửa / Bỏ"
SIG_CHANGED = "Kết quả xem trước vừa thay đổi, xem lại rồi bấm Lưu kết quả"
FAILED_WORDS = "Mất kết nối khi đang chấm bài 3. Bài làm vẫn còn nguyên, chưa có gì được lưu."
GONE = "Việc này đã xong"
NEW_CODE, NEW_KIND = "computational.copy_error", "Chép sai số hoặc biểu thức từ đề / dòng trước"
ADDED = "robot: quên đổi dấu khi chuyển vế"
OPEN_FORM = "Bấm Thêm lỗi hoặc Thôi trước"
# student LaTeX; the tab splits the scheme, so MathJax's safe regex misses it
EVIL = "$\\href{javascript:alert(1)}{y}$ $\\href{java\tscript:alert(1)}{x}$"
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
JS_ACTIVE = "() => document.activeElement.id"
JS_IN_DRAFT = "() => !!document.activeElement.closest('#draft')"
JS_NO_DRAWER = "() => !document.querySelector('.convs.open')"
JS_HREF_READY = r"() => MathJax.tex2svgPromise('\\href{x}{y}').then(() => true)"
JS_LIVE_LINKS = """() => document.querySelectorAll(
  'mjx-container a[*|href], [*|href*="script" i]').length"""


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
SEED_LOG = FIX.parent / "llm.jsonl"  # seed() copies it to logs/llm.jsonl: the app's own calls come after it
# steps that must move rows, or the counts are blind (the Sửa save of a bank problem may only update a row)
MOVES_ROWS = {
    "chat_attach",
    "grade_save",
    "ws_create",
    "ws_replace",
    "bank_import",
    "rep_approve",
    "rep_resumed",
    "rep_hidden",
    "stu_add",
    "restore",
}


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
    # the whole page: toasts and the modal sit outside the panel
    rep["forbidden"] += [f"{where}: {m.group(0)}" for m in HS_CODE.finditer(page.inner_text("body"))]
    boxes = page.eval_on_selector_all("textarea, input", JS_BOXES)  # inner_text skips them
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
def chat_drawer(page, rep: dict) -> None:
    """Esc closes the conversation drawer and the focus goes back to ☰ Hội thoại."""
    press(page, rep, "#conv-toggle", "chat ☰ Hội thoại", JS_DRAWER)
    page.keyboard.press("Escape")
    if expect(page, rep, JS_NO_DRAWER, "chat: Esc did not close the conversation drawer") and (
        (on := page.evaluate(JS_ACTIVE)) != "conv-toggle"
    ):
        rep["missing"].append(f"chat: the focus is on {on!r} after the drawer closed, want conv-toggle")


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
    if phone:
        chat_drawer(page, rep)
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
    cancel_btn(page, rep, G_S04, "confirm")
    skip, saved = f'{host(G_S04)} [data-act="g-skip"]', [G_S04, "[data-act=g-save]"]
    press(page, rep, skip, "grading Bỏ bài này", JS_HOST_SEL, saved)
    if not any(isinstance(d, dict) and d.get("skip") is True for d in decisions(data_dir, G_S04).values()):
        rep["missing"].append(f"grading confirm: decisions_json of s04 is {decisions(data_dir, G_S04)}, want a skip")


def cancel_btn(page, rep: dict, tid: str, stage: str, want: bool = True) -> None:
    """Huỷ buổi chấm sits on the card at confirm, review, preview, failed and locked, not once it is saved."""
    if bool(page.locator(f'{host(tid)} [data-act="g-cancel"]').count()) != want:
        rep["missing"].append(f"grading {stage}: Huỷ buổi chấm should be {'on the card' if want else 'gone'}")


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
    if expect(page, rep, JS_HOST_SEL, "grading s04: no preview table", [G_S04, ".preview-tbl"]):
        cancel_btn(page, rep, G_S04, "preview")
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
    cancel_btn(page, rep, G_S06, "locked")
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
    cancel_btn(page, rep, G_S01, "review")
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
    # EVIL in the evidence and in a step is typeset, and leaves no link and no dialog on a click
    work = f'{h} [data-act="g-work"][data-seq="1"]'
    press(page, rep, work, "grading Xem bài làm có EVIL", JS_HOST_SEL, [G_S01, ".wstep"])
    sels = ('.mistake[data-pid="p1"]', ".wstep:nth-child(2)")  # the evidence, the first step
    typeset = [
        expect(page, rep, JS_HOST_SEL, f"grading review: EVIL not typeset in {s}", [G_S01, f"{s} mjx-container"])
        for s in sels
    ]
    if all(typeset):
        popups: list = []

        def on_dialog(d) -> None:
            popups.append(d.message)
            d.dismiss()

        page.on("dialog", on_dialog)
        for sel in sels:
            for box in page.locator(f"{h} {sel} mjx-container").all():
                box.click()
        page.wait_for_timeout(300)
        page.remove_listener("dialog", on_dialog)
        if n := page.evaluate(JS_LIVE_LINKS):
            rep["missing"].append(f"grading review: {n} links on screen after MathJax drew student LaTeX")
        if popups:
            rep["missing"].append(f"grading review: clicking student LaTeX raised dialogs {popups}")
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
    cancel_btn(page, rep, G_S01, "saved", False)
    press(page, rep, f'{h} [data-act="g-profile"]', "grading Xem hồ sơ")
    if not page.evaluate(JS_TAB, "hoc-sinh"):
        rep["missing"].append("grading saved: Xem hồ sơ did not open Học sinh")
    expect(
        page, rep, JS_STU_PROFILE, f"grading saved: Xem hồ sơ did not open the profile of {PEOPLE[0]} (R6)", PEOPLE[0]
    )
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
    cancel_btn(page, rep, G_NEW, "failed")
    seen = len(reqs)
    press(page, rep, f'{h} [data-act="g-retry"]', "grading Chấm lại")
    expect(
        page, rep, JS_OFF, "grading failed: Huỷ buổi chấm stayed on while Chấm lại ran", f'{h} [data-act="g-cancel"]'
    )
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
    if page.locator('#draft [data-act="ws-drop"]').count():
        rep["missing"].append("worksheet: Bỏ phiếu nháp stayed on a sheet that is made")
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
        if not page.locator('#draft [data-act="ws-drop"]').count():
            rep["missing"].append("worksheet retry: a failed draft has no Bỏ phiếu nháp")
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
                if not page.evaluate(JS_IN_DRAFT):
                    rep["missing"].append("worksheet phone: the sheet took no focus when it opened")
                press(page, rep, '#draft [data-act="ws-close"]', "worksheet đóng tấm trượt", JS_WS_SHUT)
                if (on := page.evaluate(JS_ACTIVE)) != "draft-toggle":
                    rep["missing"].append(f"worksheet phone: the focus is on {on!r} after ×, want draft-toggle")
                toggle = page.locator("#draft-toggle")
                if not toggle.is_visible() or toggle.inner_text().strip() != "Phiếu nháp (6)":
                    rep["missing"].append("worksheet phone: no 'Phiếu nháp (6)' button once the sheet is closed")
                press(page, rep, "#draft-toggle", "worksheet Phiếu nháp (6)", JS_WS_OPEN)
                see_chat(page, rep, "worksheet phone sheet", phone)
                if not page.evaluate(JS_IN_DRAFT):
                    rep["missing"].append("worksheet phone: the sheet took no focus when the toggle opened it")
                page.keyboard.press("Escape")
                expect(page, rep, JS_WS_SHUT, "worksheet phone: Esc did not close the sheet")
                if (on := page.evaluate(JS_ACTIVE)) != "draft-toggle":
                    rep["missing"].append(f"worksheet phone: the focus is on {on!r} after Esc, want draft-toggle")
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


CANCEL_FILE = "hs02-2026-10-26.tex"
CANCEL_ASK = "Huỷ buổi chấm này?"
CANCEL_WORDS = "Bài làm và các lỗi đã duyệt sẽ bỏ, chưa có gì được lưu. Nộp lại file này được."
CANCELLED = "Đã huỷ buổi chấm."
DROP_ASK = "Bỏ phiếu nháp này?"
DROPPED = "Đã bỏ phiếu nháp."
CANCEL_BUSY = "Đang chạy, chờ xong rồi huỷ."
TUTOR = {"X-Tutor": "1"}
NOT_READY = {"error": {"code": "not_ready", "message": "x", "detail": None}}
JS_BADGE_TL = """n => { const b = document.getElementById('badge-tro-ly');
  return n === '0' ? b.hidden : !b.hidden && b.textContent === n; }"""


def listed(root: str, tid: str) -> bool:
    """The thread is in the reminders (GET /api/assistant/pending)."""
    return any(i["thread_id"] == tid for i in api(root, "GET", "/assistant/pending")["items"])


def waiting(root: str) -> str:
    """The number the Trợ lý badge must show (pending.counts.assistant)."""
    return str(api(root, "GET", "/assistant/pending")["counts"]["assistant"])


def ask_cancel(page, rep: dict, root: str, tid: str, button: str, what: str, title: str) -> None:
    """The button asks first (Thôi leaves the thread), and a 409 not_ready answer is a toast, not a lost card."""
    press(page, rep, button, f"{what} (hỏi lại)", JS_MODAL)
    if title not in page.inner_text("#modal-root"):
        rep["missing"].append(f"{what}: the question does not say '{title}'")
    press(page, rep, '#modal-root [data-act="modal-close"]', f"{what} Thôi", JS_NO_MODAL)
    if (n := page.request.get(f"{root}api/threads/{tid}").status) != 200:
        rep["missing"].append(f"{what}: Thôi left GET /api/threads/{tid} at {n}, want 200")
    route = re.compile(rf"/api/threads/{tid}/cancel$")
    page.route(route, lambda r: r.fulfill(status=409, json=NOT_READY))
    press(page, rep, button, f"{what} (đang chạy)", JS_MODAL)
    press(page, rep, '#modal-root [data-act="confirm-ok"]', f"{what} đồng ý (đang chạy)", JS_TOAST_HAS, CANCEL_BUSY)
    page.unroute(route)
    expect(page, rep, JS_ON, f"{what}: the button went after a 409 not_ready", button)
    press(page, rep, button, f"{what} (lần cuối)", JS_MODAL)


@counted(commit=("session",))
def cancel_grading(page, rep: dict, data_dir: str, root: str) -> None:
    """Huỷ buổi chấm (R8): the session row goes, the thread 404s, the same file can be sent again."""
    Path(data_dir, "inbox", CANCEL_FILE).write_bytes((FIX / "s01.tex").read_bytes() + b"\n% robot cancel\n")
    body, sessions = {"student_id": 2, "held_on": "2026-10-26", "path": CANCEL_FILE}, "SELECT count(*) FROM session"
    base = scalar(data_dir, sessions)
    r = page.request.post(f"{root}api/sessions", data=body, headers=TUTOR)
    if r.status != 202:
        rep["missing"].append(f"cancel: POST /api/sessions answered {r.status}, want 202")
        return
    tid = r.json()["thread_id"]
    wait_idle(root, tid)
    if (st := api(root, "GET", f"/threads/{tid}")["status"]) != "awaiting_review":
        rep["missing"].append(f"cancel: the thread is {st}, want awaiting_review")
        return
    new_chat(page, rep, False)
    page.evaluate("t => CHAT.openThread(t, 'grading')", tid)
    button = f'{host(tid)} [data-act="g-cancel"]'
    if not expect(page, rep, JS_ON, "cancel: the grading card has no Huỷ buổi chấm", button):
        return
    see_chat(page, rep, "cancel card", False)
    ask_cancel(page, rep, root, tid, button, "cancel Huỷ buổi chấm", CANCEL_ASK)
    if CANCEL_WORDS not in page.inner_text("#modal-root"):
        rep["missing"].append(f"cancel: the question lacks '{CANCEL_WORDS}'")
    press(page, rep, '#modal-root [data-act="confirm-ok"]', "cancel đồng ý", JS_HOST_HAS, [tid, CANCELLED])
    page.wait_for_timeout(1500)  # the next poll (1 s) meets the 404 and must not flip the card
    if CANCELLED not in (text := page.inner_text(host(tid))) or GONE in text:
        rep["missing"].append(f"cancel: a poll later the card says {text!r}, want '{CANCELLED}' and not '{GONE}'")
    see_chat(page, rep, "cancel done", False)
    if (n := page.request.get(f"{root}api/threads/{tid}").status) != 404:
        rep["missing"].append(f"cancel: GET /api/threads/{tid} answered {n}, want 404")
    if (n := scalar(data_dir, sessions)) != base:
        rep["missing"].append(f"cancel: {n} session rows after Huỷ buổi chấm, want {base}")
    expect(page, rep, JS_BADGE_TL, "cancel: the Trợ lý badge is stale", waiting(root))
    r = page.request.post(f"{root}api/sessions", data=body, headers=TUTOR)  # the same file goes again
    if r.status != 202:
        rep["missing"].append(f"cancel: sending the file again answered {r.status}, want 202")
        return
    tid = r.json()["thread_id"]
    wait_idle(root, tid)  # a running thread cannot be cancelled (409)
    if (n := page.request.post(f"{root}api/threads/{tid}/cancel", headers=TUTOR).status) != 200:
        rep["missing"].append(f"cancel: dropping the second thread answered {n}, want 200")
    elif (n := scalar(data_dir, sessions)) != base:
        rep["missing"].append(f"cancel: {n} session rows after dropping the second thread, want {base}")


@counted()
def cancel_draft(page, rep: dict, data_dir: str, root: str) -> None:
    """Bỏ phiếu nháp (R8): asks first, the thread goes, the reminder goes, no recommendation row changes."""
    if not (tid := ws_propose(page, rep, False)):
        return
    before = recs(data_dir)
    if not listed(root, tid):
        rep["missing"].append("cancel draft: the draft is not in the reminders before Bỏ phiếu nháp")
    button = '#draft [data-act="ws-drop"]'
    if not expect(page, rep, JS_ON, "cancel draft: the draft panel has no Bỏ phiếu nháp", button):
        return
    ask_cancel(page, rep, root, tid, button, "cancel draft Bỏ phiếu nháp", DROP_ASK)
    press(page, rep, '#modal-root [data-act="confirm-ok"]', "cancel draft đồng ý", JS_WS_HAS, DROPPED)
    page.wait_for_timeout(1500)  # the next poll (1 s) meets the 404 and must not flip the panel
    if DROPPED not in (text := page.inner_text("#draft")) or GONE in text:
        rep["missing"].append(f"cancel draft: a poll later the panel says {text!r}, want '{DROPPED}' and not '{GONE}'")
    see_chat(page, rep, "cancel draft done", False)
    if (n := page.request.get(f"{root}api/threads/{tid}").status) != 404:
        rep["missing"].append(f"cancel draft: GET /api/threads/{tid} answered {n}, want 404")
    if (n := recs(data_dir)) != before:
        rep["missing"].append(f"cancel draft: {n} recommendation rows after Bỏ phiếu nháp, want {before}")
    if listed(root, tid):
        rep["missing"].append("cancel draft: the draft is still in the reminders")
    expect(page, rep, JS_BADGE_TL, "cancel draft: the Trợ lý badge is stale", waiting(root))


REP_DAY, REP_WEEK, REP_MONTH = "2026-10-20", "2026-10-19", "2026-10-01"
REP_FILE = "baocao-HS-01-day-2026-10-20.md"
REP_45 = "Số “45” không có trong dữ liệu đã duyệt."
REP_ADDED = "Em đã cố gắng nhiều."
REP_CODED = "HS-01 và HS-03 cùng cố gắng nhiều."
REP_OPEN_BOX = "Lưu hoặc bỏ câu đang sửa trước"
REP_AGAIN = "Mỗi kỳ chỉ duyệt một lần."
REP_EMPTY = "Chọn một báo cáo bên trái, hoặc tạo báo cáo mới"
REP_NOT_READY = "chưa có buổi nào đã duyệt"
REP_WAITING = "(bài 23/10 còn chờ duyệt)"
REP_BUSY = "Báo cáo đang được xử lý. Thử lại sau giây lát."
REP_STALE = "Có buổi mới được duyệt trong kỳ này. Bỏ bản nháp rồi tạo lại."
REP_GONE = "Việc này đã xong"
REP_NEED_ONE = "Cần ít nhất một câu."
REP_FACTS, REP_FACTS_CLEAN = "Em làm tốt (F01, F03) và F02 rất đều.", "Em làm tốt và rất đều."
REP_TYPED = "câu gõ dở chưa lưu"
REP_FAILED_CHIP = "chưa làm xong"
MAKE = '[data-act="rep-make"]'
APPROVE = '[data-act="rep-approve"]'
SENT_EDIT = '#rep-doc [data-act="sent-edit"], #rep-doc [data-act="sent-del"], #rep-doc [data-act="sent-add"]'
JS_REP_HAS = "t => document.getElementById('rep-doc').innerText.includes(t)"
JS_REP_LEFT_HAS = "t => document.getElementById('panel-bao-cao').innerText.includes(t)"
JS_REP_FORM = "() => !!document.getElementById('rep-student') && !!document.getElementById('rep-start')"
JS_REP_OPT = 'v => !!document.querySelector(`#rep-start option[value="${v}"]`)'
JS_REP_DRAFT = "n => document.querySelectorAll('#rep-doc .rep-doc.is-draft .sent').length >= n"
JS_REP_DONE = "() => !!document.querySelector('#rep-doc .rep-doc.is-approved')"
JS_REP_BOX = "i => !!document.getElementById('sent-' + i)"
JS_NO_BOX = "i => !document.getElementById('sent-' + i)"
JS_REP_ROWS = (
    "n => !document.getElementById('sent-' + (n - 1)) && document.querySelectorAll('#rep-doc .sent').length >= n"
)
JS_REP_FLAGS = "() => document.querySelectorAll('#rep-doc .sent .uncheck').length"
JS_REP_COLS = "() => getComputedStyle(document.querySelector('.rep-layout')).gridTemplateColumns.split(' ').length"
JS_REP_SENTS = "() => [...document.querySelectorAll('#rep-doc .rep-s')].map(e => e.innerText.trim())"
JS_REP_ITEM = 't => !!document.querySelector(`.rep-item[data-tid="${t}"]`)'
JS_REP_NO_ITEM = 't => !document.querySelector(`.rep-item[data-tid="${t}"]`)'
JS_REP_NAME = """n => { const s = document.getElementById('rep-student');
  return !!s && !s.disabled && s.selectedOptions[0]?.textContent === n; }"""
JS_REP_KIND_FOCUS = "() => document.activeElement?.dataset?.act === 'rep-kind'"
JS_FOCUS_ACT = "a => document.activeElement?.dataset?.act === a"
JS_REP_ITEM_HAS = 'a => !!document.querySelector(`.rep-item[data-tid="${a[0]}"]`)?.innerText.includes(a[1])'
JS_REP_BOX_TEXT = "i => document.getElementById('sent-' + i)?.value ?? null"
JS_TOASTS_CLEAR = "() => { document.getElementById('toasts').innerHTML = ''; }"
REP_POLL = re.compile(r"/api/threads/[^/?]+\?view=teacher$")
REP_LIST = re.compile(r"/api/reports$")
JS_REP_DELS = "n => document.querySelectorAll('#rep-doc [data-act=\"sent-del\"]').length === n"
JS_PRINT_HAS = "t => document.getElementById('print-root').textContent.includes(t)"
JS_PRINTED = "() => window.__printed > 0"
# POST /api/reports answers "no session in the week, bài 23/10 waits" (the form's weeks slide with today's date)
REP_WAIT_BODY = {
    "error": {"code": "not_ready", "message": "x", "detail": {"reason": "no_committed_session",
              "pending": [{"thread_id": "g1-hs02-20261023", "held_on": "2026-10-23"}] * 2, "previous_start": None}}
}  # fmt: skip


def see_rep(page, rep: dict, where: str, phone: bool) -> None:
    """see(), plus: no student code on the tab, and one column at 390 px."""
    see(page, rep, where, phone)
    if codes := HS_CODE.findall(page.inner_text("#panel-bao-cao")):
        rep["missing"].append(f"{where}: a student code is on screen {codes}")
    if phone and (n := page.evaluate(JS_REP_COLS)) != 1:
        rep["missing"].append(f"{where}: {n} columns at 390 px, want 1")


def rep_form(page, rep: dict, kind: str, start: str | None = None) -> bool:
    """Kỳ `kind`, then the period `start` when given; False when the period is not in the list."""
    on = f'[data-act="rep-kind"][data-kind="{kind}"]'
    press(page, rep, on, f"report Kỳ {kind}", JS_PRESSED, on)
    if start is None:
        return True
    if not expect(page, rep, JS_REP_OPT, f"report: no period {start} in the {kind} list", start):
        return False
    page.select_option("#rep-start", start)
    return True


def rep_open(page, rep: dict) -> bool:
    press(page, rep, "#tab-bao-cao", "tab bao-cao")
    return expect(page, rep, JS_REP_FORM, "report: the form has no student and period boxes")


def sent_puts(reqs: list, tid: str) -> list:
    return [json.loads(b) for m, u, b in reqs if m == "PUT" and u.endswith(f"/threads/{tid}/decisions")]


@counted()
def rep_make(page, rep: dict, phone: bool) -> bool:
    """Tạo báo cáo ngày 20/10 của An: a yellow draft with sentences; tutor.db stays as it is."""
    if not rep_open(page, rep):
        return False
    if REP_EMPTY not in page.inner_text("#rep-doc"):
        rep["missing"].append(f"report: nothing is chosen yet, the right side should say '{REP_EMPTY}'")
    page.select_option("#rep-student", label=PEOPLE[0])
    if not rep_form(page, rep, "day", REP_DAY):
        return False
    press(page, rep, MAKE, "report Tạo báo cáo", JS_REP_DRAFT, 1)
    for w in ("Bản nháp — chưa duyệt", "+ Thêm câu", "Bỏ bản nháp", "Duyệt báo cáo", "Sửa"):
        if w not in page.inner_text("#rep-doc"):
            rep["missing"].append(f"report draft: no '{w}'")
    see_rep(page, rep, "report draft", phone)
    return page.locator("#rep-doc .rep-doc.is-draft").count() == 1


@counted()
def rep_edit(page, rep: dict, reqs: list, phone: bool) -> bool:
    """Sửa câu 1 (a number the data lacks), + Thêm câu (two kinds); an open box holds Duyệt báo cáo back."""
    tid = page.get_attribute("#rep-doc .rep-doc", "data-thread")
    sent = "#rep-doc .sent"
    press(page, rep, '[data-act="sent-edit"][data-i="0"]', "report Sửa câu 1", JS_REP_BOX, 0)
    page.fill("#sent-0", page.input_value("#sent-0") + " 45 lần")
    press(page, rep, '[data-act="sent-save"][data-i="0"]', "report Lưu câu 1", JS_REP_HAS, REP_45)
    if page.locator(f"{sent} >> nth=0").locator(".uncheck").count() != 1:
        rep["missing"].append("report edit: sentence 1 is not underlined after 45")
    for text in (REP_ADDED, REP_FACTS, REP_CODED):
        n = page.locator(sent).count()
        press(page, rep, '[data-act="sent-add"]', "report + Thêm câu", JS_REP_BOX, n)
        page.fill(f"#sent-{n}", text)
        press(page, rep, f'[data-act="sent-save"][data-i="{n}"]', "report Lưu câu mới", JS_REP_ROWS, n + 1)
        if text == REP_FACTS and (REP_FACTS_CLEAN not in (now := page.inner_text("#rep-doc")) or FACT_ID.search(now)):
            rep["missing"].append(
                f"report edit: typed fact ids are on screen right after Lưu câu (C-44): {now[-90:]!r}"
            )
    shown = page.inner_text("#rep-doc")
    if REP_ADDED not in shown or f"{PEOPLE[0]} và {ARCHIVED} cùng cố gắng nhiều." not in shown:
        rep["missing"].append("report edit: the added sentences are not on screen, with names for HS-01 and HS-03")
    if (flags := page.evaluate(JS_REP_FLAGS)) < 1 or REP_ADDED in " ".join(
        page.locator(f"{sent} .uncheck").all_inner_texts()
    ):
        rep["missing"].append(f"report edit: {flags} underlined sentences, want 45 flagged and '{REP_ADDED}' not")
    put = sent_puts(reqs, tid)
    if len(put) < 3 or [s["text"] for s in put[-1]["sentences"]][-1] != REP_CODED:
        rep["missing"].append(f"report edit: the last PUT is {put[-1:]}, want the codes HS-01 and HS-03 as typed")
    if any(s["text"] != s["text"].strip() or "[F" in s["text"] for b in put for s in b["sentences"]):
        rep["missing"].append("report edit: a PUT carries a loose or [F sentence")
    seen = resumes(reqs, tid)
    press(page, rep, '[data-act="sent-edit"][data-i="1"]', "report Sửa câu 2", JS_REP_BOX, 1)
    press(page, rep, APPROVE, "report Duyệt khi ô sửa mở", JS_TOAST_HAS, REP_OPEN_BOX)
    page.wait_for_timeout(500)
    if (n := resumes(reqs, tid) - seen) != 0:
        rep["missing"].append(f"report edit: Duyệt báo cáo over an open box sent {n} resumes, want 0")
    press(page, rep, '[data-act="sent-cancel"][data-i="1"]', "report Thôi", JS_NO_BOX, 1)
    press(page, rep, '[data-act="sent-edit"][data-i="0"]', "report Sửa câu 1 lần nữa", JS_REP_BOX, 0)
    page.fill("#sent-0", REP_TYPED)
    for act, i in (("sent-edit", 1), ("sent-add", None)):  # another box never replaces the open one
        page.evaluate(JS_TOASTS_CLEAR)
        sel = f'[data-act="{act}"]' + (f'[data-i="{i}"]' if i is not None else "")
        press(page, rep, sel, f"report {act} khi ô sửa mở", JS_TOAST_HAS, REP_OPEN_BOX)
        if (kept := page.evaluate(JS_REP_BOX_TEXT, 0)) != REP_TYPED or page.locator("#rep-doc textarea").count() != 1:
            rep["missing"].append(f"report edit: {act} over an open box left {kept!r} in box 1, want {REP_TYPED!r}")
    press(page, rep, '[data-act="sent-cancel"][data-i="0"]', "report Thôi câu 1", JS_NO_BOX, 0)
    for _ in range(3):  # a box the bug left open must not hold Duyệt báo cáo back
        if page.locator("#rep-doc textarea").count():
            page.click('#rep-doc [data-act="sent-cancel"] >> nth=0')
    see_rep(page, rep, "report edited", phone)
    return True


@counted(commit=("report",))
def rep_approve(page, rep: dict, data_dir: str, reqs: list, phone: bool) -> bool:
    """Duyệt báo cáo with flags: "Vẫn duyệt?", one `report` row, the .md file, then read-only."""
    tid = page.get_attribute("#rep-doc .rep-doc", "data-thread")
    before = scalar(data_dir, "SELECT count(*) FROM report")
    puts = len(sent_puts(reqs, tid))
    press(page, rep, APPROVE, "report Duyệt báo cáo", JS_ROOT_HAS, "Vẫn duyệt?")
    press(page, rep, '[data-act="confirm-ok"]', "report Vẫn duyệt", JS_REP_DONE)
    if not page.locator("#rep-doc .rep-doc.is-approved").count():
        return False
    if (n := scalar(data_dir, "SELECT count(*) FROM report") - before) != 1:
        rep["missing"].append(f"report approve: {n} new report rows, want 1")
    if not Path(data_dir, "out", REP_FILE).is_file():
        rep["missing"].append(f"report approve: no data/out/{REP_FILE}")
    if not re.search(r"Đã duyệt \d\d/\d\d/\d{4}", page.inner_text("#rep-doc")) or page.locator(SENT_EDIT).count():
        rep["missing"].append("report approve: want 'Đã duyệt dd/mm/yyyy' and no Sửa / Bỏ / + Thêm câu")
    if len(sent_puts(reqs, tid)) != puts + 1:
        rep["missing"].append("report approve: Duyệt should PUT the sentences once, then resume")
    if "Tải PDF" not in page.inner_text("#rep-doc"):
        rep["missing"].append("report approve: no Tải PDF")
    see_rep(page, rep, "report approved", phone)
    return True


@counted()
def rep_pdf(page, rep: dict, phone: bool) -> None:
    """Tải PDF: the print page holds the name and the sentences, no [F and no HS-0 (Focus 3)."""
    page.evaluate(JS_NO_PRINT)
    sents = page.evaluate(JS_REP_SENTS)
    press(page, rep, '[data-act="rep-pdf"]', "report Tải PDF", JS_PRINTED)
    if not sents or PEOPLE[0] not in (text := page.evaluate("document.getElementById('print-root').textContent")):
        rep["missing"].append(f"report pdf: want '{PEOPLE[0]}' on the print page and sentences on screen")
        return
    rep["missing"] += [f"report pdf: the print page lacks '{s}'" for s in sents if s not in text]
    if "[F" in text or HS_CODE.search(text):
        rep["missing"].append(f"report pdf: the print page holds [F or a student code: {text[:200]!r}")
    if "Báo cáo ngày 20/10/2026" not in text or "duyệt ngày" not in text:
        rep["missing"].append("report pdf: want the period and 'duyệt ngày' on the print page")


@counted()
def rep_again(page, rep: dict, phone: bool) -> None:
    """A fresh page, Tạo báo cáo for the approved day: the words and the green frame of that report."""
    page.reload()
    if not rep_open(page, rep):
        return
    page.select_option("#rep-student", label=PEOPLE[0])
    if not rep_form(page, rep, "day", REP_DAY):
        return
    press(page, rep, MAKE, "report Tạo báo cáo đã duyệt", JS_REP_LEFT_HAS, REP_AGAIN)
    expect(page, rep, JS_REP_DONE, "report again: the approved report did not open")
    if f"Báo cáo ngày 20/10/2026 của {PEOPLE[0]} đã duyệt ngày" not in page.inner_text("#panel-bao-cao"):
        rep["missing"].append("report again: the words do not name the period, the student and the day")
    see_rep(page, rep, "report again", phone)


@counted()
def rep_empty(page, rep: dict, phone: bool) -> None:
    """Kỳ Tuần "tuần này" has no approved session; a server answer with pending days adds them in brackets."""
    rep_form(page, rep, "week")
    press(page, rep, MAKE, "report Tạo báo cáo tuần này", JS_REP_LEFT_HAS, REP_NOT_READY)
    left = page.inner_text("#panel-bao-cao")
    if "Chưa làm được báo cáo tuần" not in left or REP_WAITING in left:
        rep["missing"].append("report empty: want 'Chưa làm được báo cáo tuần …' with no waiting days")
    see_rep(page, rep, "report empty", phone)
    page.route(
        "**/api/reports",
        lambda r: r.fulfill(status=409, json=REP_WAIT_BODY) if r.request.method == "POST" else r.fallback(),
    )
    press(page, rep, MAKE, "report Tạo báo cáo khi bài còn chờ", JS_REP_LEFT_HAS, REP_WAITING)
    page.unroute("**/api/reports")


@counted(commit=("report",))
def rep_resumed(page, rep: dict, data_dir: str, root: str, reqs: list, sid: int) -> None:
    """A draft made over the API shows in Bản nháp chờ duyệt; resumed elsewhere, the open draft turns green (Focus 1)"""
    tid = api(root, "POST", "/reports", {"student_id": sid, "period_kind": "month", "period_start": REP_MONTH})[
        "thread_id"
    ]
    wait_idle(root, tid)
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    rep_open(page, rep)
    item = f'.rep-item[data-tid="{tid}"]'
    if not expect(page, rep, JS_REP_ITEM, "report: the API draft is not in Bản nháp chờ duyệt", tid):
        return
    if "tháng 10/2026" not in (text := page.inner_text(item)) or "nháp" not in text or PEOPLE[0] not in text:
        rep["missing"].append(f"report resumed: the list row says {text!r}, want name, 'tháng 10/2026', 'nháp'")
    press(page, rep, item, "report mở bản nháp tháng", JS_REP_DRAFT, 1)
    before, puts = scalar(data_dir, "SELECT count(*) FROM report"), len(sent_puts(reqs, tid))
    api(root, "POST", f"/threads/{tid}/resume")
    expect(page, rep, JS_REP_DONE, "report resumed: the open draft did not turn green after a resume elsewhere")
    if scalar(data_dir, "SELECT count(*) FROM report") - before != 1 or page.locator(SENT_EDIT).count():
        rep["missing"].append("report resumed: want 1 new report row and no Sửa / Bỏ / + Thêm câu")
    page.wait_for_timeout(1500)
    if len(sent_puts(reqs, tid)) != puts:
        rep["missing"].append("report resumed: the screen PUT after the draft was approved")
    see_rep(page, rep, "report resumed", False)


def gets(reqs: list, tid: str) -> int:
    return sum(m == "GET" and f"/api/threads/{tid}?view=teacher" in u for m, u, _ in reqs)


def rep_week_draft(page, rep: dict, root: str, sid: int) -> str | None:
    """A week draft made over the API, opened from Bản nháp chờ duyệt; its thread id (None when it is not listed)."""
    tid = api(root, "POST", "/reports", {"student_id": sid, "period_kind": "week", "period_start": REP_WEEK})[
        "thread_id"
    ]
    wait_idle(root, tid)
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    rep_open(page, rep)
    if not expect(page, rep, JS_REP_ITEM, "report: the week draft is not in Bản nháp chờ duyệt", tid):
        return None
    press(page, rep, f'.rep-item[data-tid="{tid}"]', "report mở bản nháp tuần", JS_REP_DRAFT, 1)
    return tid


def rep_pause(page, rep: dict, root: str, reqs: list, tid: str, approve: bool) -> None:
    """A draft on a hidden tab stops polling; back on the tab it polls again and sees an approval made meanwhile."""
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    page.wait_for_timeout(1600)  # the poll already in flight finishes, then stops
    seen = gets(reqs, tid)
    page.wait_for_timeout(3000)
    if n := gets(reqs, tid) - seen:
        rep["missing"].append(f"report pause: {n} polls of the open draft while its tab is hidden, want 0")
    puts = len(sent_puts(reqs, tid))
    if approve:
        api(root, "POST", f"/threads/{tid}/resume")  # approved elsewhere while the tab is hidden
    seen = gets(reqs, tid)
    press(page, rep, "#tab-bao-cao", "tab bao-cao")
    if approve:
        expect(page, rep, JS_REP_DONE, "report pause: the hidden draft did not turn green once the tab came back")
        if page.locator(SENT_EDIT).count() or len(sent_puts(reqs, tid)) != puts:
            rep["missing"].append("report pause: an approved draft still has Sửa / Bỏ / + Thêm câu, or sent a PUT")
    else:
        page.wait_for_timeout(2500)
        if gets(reqs, tid) - seen < 2:
            rep["missing"].append("report pause: the draft did not poll again after its tab came back")


@counted()
def rep_prefill(page, rep: dict, root: str, sid: int, name: str, phone: bool) -> None:
    """A cold page: REPORTS.prefill(id) before the tab was ever opened still shows that student once the list is in."""
    page.goto(f"{root}?cold={'phone' if phone else 'desk'}#tro-ly")
    page.evaluate("id => REPORTS.prefill(id)", sid)
    expect(page, rep, JS_REP_NAME, f"report prefill: the form does not show {name} after a cold prefill", name)
    expect(page, rep, JS_REP_KIND_FOCUS, "report prefill: the Kỳ buttons took no focus")
    see_rep(page, rep, "report prefill", phone)


def refuse(body: dict, route, _request) -> None:
    route.fulfill(status=409, json=body)


@counted()
def rep_refused(page, rep: dict, reqs: list) -> None:
    """Duyệt báo cáo refused with 409: a raw server text never shows, the stale-draft words do, the draft stays."""
    tid = page.get_attribute("#rep-doc .rep-doc", "data-thread")
    again = re.compile(rf"/api/threads/{tid}/resume$")
    for said, want in ((tid, REP_BUSY), (REP_STALE, REP_STALE)):
        body = {"error": {"code": "not_ready", "message": said, "detail": {"reason": said}}}
        page.route(again, functools.partial(refuse, body))
        press(page, rep, APPROVE, "report Duyệt khi bị từ chối", JS_ROOT_HAS, "Vẫn duyệt?")
        press(page, rep, '[data-act="confirm-ok"]', "report Vẫn duyệt bị từ chối", JS_TOAST_HAS, want)
        page.unroute(again)
        if tid in page.inner_text("#toasts"):
            rep["missing"].append(f"report refused: a toast shows the thread id {tid}")
    if page.locator("#rep-doc .rep-doc.is-draft .sent").count() < 1:
        rep["missing"].append("report refused: the draft is gone after a refused Duyệt")


@counted(commit=("report",))
def rep_hidden(page, rep: dict, root: str, reqs: list, sid: int, phone: bool) -> None:
    """The last free period: a draft open at 390 px, its tab hidden, approved over the API meanwhile."""
    if not (tid := rep_week_draft(page, rep, root, sid)):
        return
    see_rep(page, rep, "report week draft", phone)
    rep_pause(page, rep, root, reqs, tid, True)
    see_rep(page, rep, "report hidden approved", phone)


@counted()
def rep_gone(page, rep: dict, root: str, sid: int, phone: bool) -> None:
    """A draft dropped elsewhere while it is open: the right side empties and the list drops it, no stale card."""
    if not (tid := rep_week_draft(page, rep, root, sid)):
        return
    page.focus("#rep-student")  # the tutor is in the form when the draft vanishes: the focus must stay there
    api(root, "POST", f"/threads/{tid}/cancel")
    expect(page, rep, JS_REP_HAS, f"report gone: the right side did not go back to '{REP_EMPTY}'", REP_EMPTY)
    expect(page, rep, JS_REP_NO_ITEM, "report gone: the dropped draft is still in the list", tid)
    expect(page, rep, JS_FOCUS_ID, "report gone: the focus left the student box when the draft vanished", "rep-student")
    if REP_GONE in page.inner_text("#panel-bao-cao"):
        rep["missing"].append(f"report gone: '{REP_GONE}' and a stale button are on the tab")
    see_rep(page, rep, "report gone", phone)


@counted()
def rep_discard(page, rep: dict, root: str, reqs: list, sid: int, phone: bool) -> None:
    """A draft of another period (API): hidden tab, no sentence left (Duyệt báo cáo off), then Bỏ bản nháp."""
    if not (tid := rep_week_draft(page, rep, root, sid)):
        return
    see_rep(page, rep, "report week draft", phone)
    rep_pause(page, rep, root, reqs, tid, False)
    n = page.locator('#rep-doc [data-act="sent-del"]').count()
    for k in range(n):
        press(page, rep, '#rep-doc [data-act="sent-del"] >> nth=0', "report Bỏ câu", JS_REP_DELS, n - k - 1)
    expect(page, rep, JS_OFF, "report discard: Duyệt báo cáo stayed on with no sentence", APPROVE)
    if REP_NEED_ONE not in page.inner_text("#rep-doc") or (sent_puts(reqs, tid) or [{}])[-1].get("sentences") != []:
        rep["missing"].append(f"report discard: want '{REP_NEED_ONE}' and a last PUT with no sentence")
    press(page, rep, '[data-act="rep-discard"]', "report Bỏ bản nháp", JS_ROOT_HAS, "Bỏ bản nháp")
    press(page, rep, '[data-act="confirm-ok"]', "report đồng ý bỏ", JS_REP_NO_ITEM, tid)
    expect(
        page, rep, JS_FOCUS_ACT, "report discard: the focus is not on Tạo báo cáo once Bỏ bản nháp is done", "rep-make"
    )
    if REP_EMPTY not in page.inner_text("#rep-doc"):
        rep["missing"].append(f"report discard: the right side should say '{REP_EMPTY}' again")
    if (status := page.evaluate(JS_STATUS, f"/api/threads/{tid}")) != 404:
        rep["missing"].append(f"report discard: GET /api/threads/{tid} is {status}, want 404")
    see_rep(page, rep, "report discarded", phone)


def failed_poll(route) -> None:
    """A report thread that polls as `failed` (the real one stays at the gate)."""
    r = route.fetch()
    j = r.json()
    if j.get("card", {}).get("kind") == "report":
        j["card"]["stage"] = "failed"
    route.fulfill(response=r, json=j)


def failed_list(route) -> None:
    """GET /api/reports with every draft failed (POST goes on to the server)."""
    if route.request.method != "GET":
        route.fallback()
        return
    r = route.fetch()
    j = r.json()
    for d in j["drafts"]:
        d["status"] = "failed"
    route.fulfill(response=r, json=j)


@counted()
def rep_retry(page, rep: dict, root: str, sid: int, phone: bool) -> None:
    """A draft served as failed: list chip, focus after Thử lại, and a resume refused as approved opens that report."""
    done = api(root, "GET", "/reports")["approved"][0]["id"]
    resume = re.compile(r"/api/threads/[^/?]+/resume$")
    tid = None
    try:
        if not (tid := rep_week_draft(page, rep, root, sid)):
            return
        page.route(REP_POLL, failed_poll)  # the open draft's next poll says failed
        page.route(REP_LIST, failed_list)
        page.route(resume, lambda r: r.fulfill(status=202, json={}))
        expect(page, rep, JS_REP_HAS, "report retry: the failed draft has no Thử lại", "Thử lại")
        want = f"report retry: the list chip does not say '{REP_FAILED_CHIP}'"
        expect(page, rep, JS_REP_ITEM_HAS, want, [tid, REP_FAILED_CHIP])
        see_rep(page, rep, "report failed draft", phone)
        press(page, rep, '[data-act="rep-retry"]', "report Thử lại", JS_FOCUS_ID, "rep-failed")
        off = "report retry: Thử lại stayed off"  # two more polls say failed, then it is on again
        expect(page, rep, JS_ON, off, '[data-act="rep-retry"]')
        expect(page, rep, JS_FOCUS_ID, "report retry: the focus left the status line on the redraw", "rep-failed")
        refused = {"error": {"code": "already_committed", "message": "x", "detail": {"report_id": done}}}
        page.unroute(resume)
        page.route(resume, lambda r: r.fulfill(status=409, json=refused))
        press(page, rep, '[data-act="rep-retry"]', "report Thử lại khi đã duyệt", JS_REP_DONE)
        see_rep(page, rep, "report retry approved", phone)
    finally:
        for pattern in (REP_POLL, REP_LIST, resume):
            page.unroute(pattern)
        if tid:
            api(root, "POST", f"/threads/{tid}/cancel")


def walk_reports(page, rep: dict, phone: bool, data_dir: str, root: str) -> None:
    """The Báo cáo tab, after An's 20/10 session is saved. The phone walks the approved period and a hidden draft."""
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    ids = {s["name"]: s["id"] for s in api(root, "GET", "/students?archived=true")}
    sid = ids[PEOPLE[0]]
    rep_prefill(page, rep, root, ids[PEOPLE[1]], PEOPLE[1], phone)
    if phone:
        rep_again(page, rep, phone)
        rep_discard(page, rep, root, reqs, sid, phone)  # before rep_hidden approves the week it drafts
        rep_hidden(page, rep, root, reqs, sid, phone)
        return
    if not rep_make(page, rep, phone) or not rep_edit(page, rep, reqs, phone):
        return
    rep_refused(page, rep, reqs)
    if not rep_approve(page, rep, data_dir, reqs, phone):
        return
    rep_pdf(page, rep, phone)
    rep_again(page, rep, phone)
    rep_empty(page, rep, phone)
    rep_resumed(page, rep, data_dir, root, reqs, sid)
    rep_gone(page, rep, root, sid, phone)
    rep_retry(page, rep, root, sid, phone)
    rep_discard(page, rep, root, reqs, sid, phone)


REP_WEEK_LABEL = "tuần 19/10–25/10/2026"
CHAT_REP_ASK = "Làm báo cáo tuần 19/10/2026 cho "
CHAT_REP_READY = f"Bản nháp báo cáo {REP_WEEK_LABEL} sẵn sàng"
CHAT_REP_WRITING = "Đang viết bản nháp báo cáo"
CHAT_REP_GROUP = "Báo cáo nháp"
CHAT_REP_ROW = f"{PEOPLE[0]} · {REP_WEEK_LABEL} · nháp"
CHAT_REP_FLAGS = "2 câu cần xem lại"
CHAT_REP_SAVED, CHAT_REP_SAVING = "Đã duyệt", "Đang lưu…"
CHAT_REP_FAILED = "Chưa làm xong bản nháp. Mở tab Báo cáo để thử lại."
CHAT_REP_GONE, CHAT_REP_TAB = "Bản nháp này không còn nữa.", "Sang tab Báo cáo"
CHAT_REP_ORDER = ["Bài chờ duyệt", CHAT_REP_GROUP]  # IA-app §2: waiting grading first
PENDING = "**/api/assistant/pending"
GRADING_ROW = {
    "kind": "grading",
    "thread_id": "g1-hs01-20261022",
    "student_id": 1,
    "date": "2026-10-22",
    "words": "chờ",
}
CHAT_REP_OPEN = '.rcard [data-act="c-open"]'
JS_RC_ANY = "w => [...document.querySelectorAll('#chat-msgs .rcard')].some(c => c.innerText.includes(w))"
JS_RC_HAS = """([t, w]) => { const c = document.querySelector(`#chat-msgs .card-host[data-thread="${t}"] .rcard`);
  return !!c && c.innerText.includes(w); }"""
JS_RC_TID = "() => document.querySelector('#chat-msgs .rcard')?.closest('.card-host').dataset.thread"
JS_RC_MORE = """tid => { const h = document.createElement('div'); h.className = 'card-host'; h.id = 'rc-extra';
  document.getElementById('chat-msgs').appendChild(h); CHAT.cards.report(h, { thread_id: tid }); }"""
JS_RC_EXTRA = "w => !!document.querySelector('#rc-extra .rcard')?.innerText.includes(w)"
JS_REMIND_REP = """([g, w]) => [...document.querySelectorAll('#remind .remind-card')]
  .some(c => c.querySelector('h3').innerText.startsWith(g) && c.innerText.includes(w))"""
JS_REMIND_ORDER = (
    "() => [...document.querySelectorAll('#remind .remind-card h3')].map(h => h.firstChild.textContent.trim())"
)
JS_RC_GONE = """([w, b]) => { const h = document.getElementById('rc-extra');
  return !!h && h.innerText.includes(w) && !!h.querySelector(`[data-act="c-tab"][data-tab="${b}"]`); }"""
JS_REMIND_NO = "g => ![...document.querySelectorAll('#remind .remind-card h3')].some(h => h.innerText.startsWith(g))"
JS_BADGE = """n => { const b = document.getElementById('badge-bao-cao');
  return n === '0' ? b.hidden : !b.hidden && b.textContent === n; }"""


def with_grading(route) -> None:
    """GET /api/assistant/pending with one grading reminder, so both groups show."""
    r = route.fetch()
    j = r.json()
    if not any(i["kind"] == "grading" for i in j["items"]):
        j["items"].append(GRADING_ROW)
    route.fulfill(response=r, json=j)


@counted()
def chat_rep_make(page, rep: dict, root: str) -> str | None:
    """'Làm báo cáo tuần 19/10/2026 cho @An' gives a report card in the chat, a reminder row and the Báo cáo badge."""
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    new_chat(page, rep, False)
    pick_mention(page, rep, CHAT_REP_ASK, PEOPLE[0].split()[0], PEOPLE[0])
    n = msgs(page)
    page.press("#chat-input", "Enter")
    expect(page, rep, JS_REPLIED, "chat report: no answer to the report ask", n)
    if not expect(page, rep, JS_RC_ANY, f"chat report: the card never said '{CHAT_REP_READY}'", CHAT_REP_READY):
        return None
    tid = page.evaluate(JS_RC_TID)
    expect(
        page,
        rep,
        JS_REMIND_REP,
        f"chat report: no '{CHAT_REP_GROUP}' reminder '{CHAT_REP_ROW}'",
        [CHAT_REP_GROUP, CHAT_REP_ROW],
    )
    page.route(PENDING, with_grading)
    page.evaluate("CHAT.refreshPending()")
    if (order := [g for g in page.evaluate(JS_REMIND_ORDER) if g in CHAT_REP_ORDER]) != CHAT_REP_ORDER:
        rep["missing"].append(f"chat report: the reminder groups come as {order}, want {CHAT_REP_ORDER}")
    page.unroute(PENDING)
    page.evaluate("CHAT.refreshPending()")
    want = str(api(root, "GET", "/assistant/pending")["counts"]["reports"])
    if want == "0":
        rep["missing"].append("chat report: pending.counts.reports is 0 with a draft waiting")
    expect(page, rep, JS_BADGE, f"chat report: the Báo cáo badge does not say {want} (pending.counts.reports)", want)
    see_chat(page, rep, "chat report card", False)
    return tid


@counted()
def chat_rep_open(page, rep: dict, data_dir: str, tid: str) -> None:
    """Mở trong Báo cáo opens that draft in its yellow frame; 'ok' back in the chat writes nothing."""
    press(page, rep, CHAT_REP_OPEN, "chat report Mở trong Báo cáo", JS_REP_DRAFT, 1)
    expect(
        page, rep, JS_FOCUS_ID, "chat report: the focus is not on the report title after Mở trong Báo cáo", "rep-title"
    )
    if not page.locator("#rep-doc .rep-doc").count():
        rep["missing"].append("chat report: Mở trong Báo cáo opened no draft")
        return
    head = page.inner_text("#rep-doc .rep-doc").lower()  # the eyebrow is upper case on screen
    if page.get_attribute("#rep-doc .rep-doc", "data-thread") != tid or f"báo cáo {REP_WEEK_LABEL}" not in head:
        rep["missing"].append(f"chat report: Mở trong Báo cáo opened {head[:80]!r}, want the draft of {REP_WEEK_LABEL}")
    if page.locator("#rep-doc .rep-doc.is-draft").count() != 1:
        rep["missing"].append("chat report: the opened draft has no yellow frame")
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    saved = db_state(data_dir)
    if SAVED_NOTHING not in say(page, rep, "ok"):
        rep["missing"].append(f"chat report: 'ok' should answer '{SAVED_NOTHING}'")
    if db_state(data_dir) != saved:
        rep["missing"].append("chat report: 'ok' changed tutor.db or the decisions of the report draft")


@counted()
def chat_rep_stages(page, rep: dict, reqs: list, tid: str) -> None:
    """writing, 2 flagged, saving, saved and failed are the card's words; saved and failed end its poll, all keep Mở."""
    poll = re.compile(rf"/api/threads/{tid}\?view=teacher$")
    now = {"stage": "saving", "n_flagged": 0}

    def serve(route) -> None:
        r = route.fetch()
        j = r.json()
        j["card"] |= now
        route.fulfill(response=r, json=j)

    def keeps_open(where: str) -> None:
        if page.locator(f"{where} {CHAT_REP_OPEN}").count() != 1:
            rep["missing"].append(f"chat report: {where} has no Mở trong Báo cáo")

    page.wait_for_timeout(1600)  # the hidden Báo cáo tab's last poll ends before a 'saved' is served
    page.route(poll, serve)
    page.evaluate(JS_RC_MORE, tid)  # a card whose first poll is `saving`: no draft was seen yet, so it is still writing
    expect(page, rep, JS_RC_EXTRA, f"chat report: a first poll at saving lacks '{CHAT_REP_WRITING}'", CHAT_REP_WRITING)
    now |= {"stage": "draft", "n_flagged": 2}
    expect(page, rep, JS_RC_EXTRA, f"chat report: stage draft lacks '{CHAT_REP_READY}'", CHAT_REP_READY)
    now["stage"] = "saving"
    expect(
        page, rep, JS_RC_EXTRA, f"chat report: stage saving after a draft lacks '{CHAT_REP_SAVING}'", CHAT_REP_SAVING
    )
    page.evaluate("document.getElementById('rc-extra').remove()")
    now |= {"stage": "writing", "n_flagged": 0}
    card = f'.card-host[data-thread="{tid}"]'
    expect(page, rep, JS_RC_HAS, f"chat report: stage writing lacks '{CHAT_REP_WRITING}'", [tid, CHAT_REP_WRITING])
    keeps_open(card)
    now |= {"stage": "draft", "n_flagged": 2}
    expect(page, rep, JS_RC_HAS, f"chat report: stage draft lacks '{CHAT_REP_FLAGS}'", [tid, CHAT_REP_FLAGS])
    expect(page, rep, JS_RC_HAS, f"chat report: stage draft with flags lacks '{CHAT_REP_READY}'", [tid, CHAT_REP_READY])
    now["stage"] = "saved"
    expect(page, rep, JS_RC_HAS, f"chat report: stage saved lacks '{CHAT_REP_SAVED}'", [tid, CHAT_REP_SAVED])
    keeps_open(card)
    seen = gets(reqs, tid)
    page.wait_for_timeout(2500)
    if n := gets(reqs, tid) - seen:
        rep["missing"].append(f"chat report: the card polled {n} times after it said '{CHAT_REP_SAVED}'")
    now["stage"] = "failed"
    page.evaluate(JS_RC_MORE, tid)  # the first card has stopped, so a second one meets 'failed'
    expect(page, rep, JS_RC_EXTRA, f"chat report: stage failed lacks '{CHAT_REP_FAILED}'", CHAT_REP_FAILED)
    keeps_open("#rc-extra")
    seen = gets(reqs, tid)
    page.wait_for_timeout(2500)
    if n := gets(reqs, tid) - seen:
        rep["missing"].append(f"chat report: the card polled {n} times after it said '{CHAT_REP_FAILED}'")
    page.unroute(poll)
    page.evaluate("document.getElementById('rc-extra').remove()")


@counted()
def chat_rep_drop(page, rep: dict, tid: str) -> None:
    """The reminder's Mở shows the draft; Bỏ bản nháp there takes the reminder row and the badge away, and a card
    still following the draft says it is gone and points to the Báo cáo tab."""
    page.evaluate(JS_RC_MORE, tid)
    expect(page, rep, JS_RC_EXTRA, f"chat report: the second card lacks '{CHAT_REP_READY}'", CHAT_REP_READY)
    press(
        page,
        rep,
        f'#remind .remind-card:has(h3:has-text("{CHAT_REP_GROUP}")) [data-act="c-open"]',
        "chat report nhắc Mở",
        JS_REP_DRAFT,
        1,
    )
    press(page, rep, '[data-act="rep-discard"]', "report Bỏ bản nháp", JS_ROOT_HAS, "Bỏ bản nháp")
    press(page, rep, '[data-act="confirm-ok"]', "report đồng ý bỏ", JS_REP_NO_ITEM, tid)
    press(page, rep, "#tab-tro-ly", "tab tro-ly")
    expect(
        page,
        rep,
        JS_REMIND_NO,
        f"chat report: the '{CHAT_REP_GROUP}' reminder stayed after Bỏ bản nháp",
        CHAT_REP_GROUP,
    )
    expect(page, rep, JS_BADGE, "chat report: the Báo cáo badge stayed after Bỏ bản nháp", "0")
    gone = [CHAT_REP_GONE, "bao-cao"]
    if expect(page, rep, JS_RC_GONE, f"chat report: the card lacks '{CHAT_REP_GONE}' and a Báo cáo tab button", gone):
        if CHAT_REP_TAB not in page.inner_text("#rc-extra"):
            rep["missing"].append(f"chat report: the button is not called '{CHAT_REP_TAB}'")
        press(page, rep, '#rc-extra [data-act="c-tab"]', "chat report Sang tab Báo cáo", JS_TAB, "bao-cao")
        press(page, rep, "#tab-tro-ly", "tab tro-ly")
    page.evaluate("document.getElementById('rc-extra').remove()")


def walk_chat_report(page, rep: dict, data_dir: str, root: str) -> None:
    """Desktop only. The week draft it makes is dropped at the end, so the phone walk still has 19/10 free."""
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
    if not (tid := chat_rep_make(page, rep, root)):
        return
    chat_rep_open(page, rep, data_dir, tid)
    chat_rep_stages(page, rep, reqs, tid)
    chat_rep_drop(page, rep, tid)


STU_NEW = {"desktop": "Đặng Thu Trang", "phone": "Vũ Quốc Bảo"}  # one student per walk; both walks share one tutor.db
STU_FIND = {"desktop": "dang", "phone": "bao"}  # what the tutor types for them: no accents, đ as d
STU_ONE, STU_ONE_MSG = "Minh", "Nhập đủ họ và tên (ít nhất 2 chữ)"
STU_NOTE, STU_NOTE2 = "Mới vào lớp", "Học <b>thêm</b>"  # the second one is markup the tab must show as text
XSS_DATE, XSS_LEVEL = "2026-10-<u>20", 'vững"<i>x</i>'  # strings of the API that the tab prints
TAINT_URL = re.compile(r"/api/(students/\d+/(progress|profile)|sessions\?student=\d+&status=committed)")
STU_EMPTY = (
    "Chưa có buổi nào đã chấm, chưa vẽ được tiến bộ",
    "Chưa có lỗi nào lặp lại",
    "Chưa có buổi nào đã chấm.",
    "Chưa có phiếu nào được giao",
    "Chưa có báo cáo nào được duyệt",
)
STU_TRENDS = ("↑ tiến bộ", "→ giữ", "↓ cần ôn")
BACK = '#panel-hoc-sinh [data-act="st-back"]'
JS_STU_LIST = "() => !!document.getElementById('st-cards')"
JS_STU_PROFILE = """n => !!document.querySelector('#panel-hoc-sinh .profile-grid')
  && document.getElementById('st-h1').innerText.includes(n)"""
JS_STU_CARD = "n => [...document.querySelectorAll('#st-cards .st-card')].some(c => c.innerText.includes(n))"
JS_STU_CARD_HAS = """([n, t]) => [...document.querySelectorAll('#st-cards .st-card')]
  .some(c => c.innerText.includes(n) && c.innerText.includes(t))"""
JS_STU_ARCH = "n => document.getElementById('st-arch').innerText.includes(n)"
JS_SF_ERR = "m => { const e = document.getElementById('sf-err'); return !!e && !e.hidden && e.innerText.includes(m); }"
JS_STU_SKILLS = """() => [...document.querySelectorAll('#panel-hoc-sinh .lv-group')].flatMap(g => {
  const lv = g.querySelector('h3').firstChild.textContent.trim().toLowerCase();
  return [...g.querySelectorAll('li')].map(li =>
    [li.firstElementChild.innerText.trim(), lv, li.lastElementChild.innerText.trim()]);
})"""
JS_STU_TIP = "() => /^\\d\\d\\/\\d\\d: /.test(document.getElementById('st-tip').innerText)"
JS_STU_DOT = "() => document.activeElement?.tagName.toLowerCase() === 'circle'"
JS_STU_TABLE = "() => !!document.querySelector('#st-chart table')"
JS_STU_SVG = "() => !!document.querySelector('#st-chart svg')"
JS_STU_SVG_NAME = "n => !!document.querySelector('#st-chart svg')?.getAttribute('aria-label').startsWith(n)"
JS_STU_FIT = """() => { const b = document.getElementById('st-chart'), s = b.querySelector('svg');
  return !s || s.getBoundingClientRect().width <= b.clientWidth + 1; }"""
JS_MJX = "() => !!document.querySelector('#modal-root mjx-container')"
JS_ACT = "() => document.activeElement?.dataset?.act || ''"
JS_FOCUS_ID = "i => document.activeElement?.id === i"
JS_FOCUS_CARD = """n => !!document.activeElement?.classList.contains('st-name')
  && document.activeElement.closest('.st-card').innerText.includes(n)"""
JS_WS_DRAFT = "() => !!(CHAT.worksheetThread && CHAT.worksheetThread())"
SKILL_THETA = "SELECT k.name, t.theta FROM skill_state t JOIN kc k ON k.id = t.kc_id WHERE t.student_id = ?"
SHEET_DATES = (
    "SELECT for_date FROM recommendation WHERE student_id = ? AND status <> 'rejected' GROUP BY for_date"
    " ORDER BY for_date DESC"
)
SHEET_REFS = (
    "SELECT p.ref FROM recommendation r JOIN problem p ON p.id = r.problem_id"
    " WHERE r.student_id = ? AND r.status <> 'rejected' AND r.for_date = ? ORDER BY r.position"
)


def level_of(theta: float) -> str:
    """The word for a skill_state theta (C-48: the thresholds are +-0.5), written out here, not imported."""
    return "chưa vững" if theta < -0.5 else "vững" if theta > 0.5 else "đang hình thành"


def ten(score: float, top: float) -> str:
    """U.score: out of 10, rounded to 0,5, a comma for the decimal."""
    return f"{math.floor(score / top * 20 + 0.5) / 2:g}".replace(".", ",") + "/10"


def fetch(data_dir: str, sql: str, *args) -> list:
    with closing(sqlite3.connect(f"{Path(data_dir, 'tutor.db').as_uri()}?mode=ro", uri=True)) as con:
        return con.execute(sql, args).fetchall()


SKILL_EVENTS = (
    "SELECT s.held_on, k.name, e.theta_after FROM skill_event e JOIN attempt a ON a.id = e.attempt_id"
    " JOIN session s ON s.id = a.session_id JOIN kc k ON k.id = e.kc_id"
    " WHERE e.student_id = ? AND s.status = 'committed' ORDER BY s.held_on, s.id, e.id"
)


def first_points(data_dir: str, sid: int) -> tuple[str, dict]:
    """(the first approved day, {skill: (its first day, theta_after of its last event that day)}): the first dots."""
    firsts: dict = {}
    for day, name, after in fetch(data_dir, SKILL_EVENTS, sid):
        if name not in firsts or firsts[name][0] == day:
            firsts[name] = (day, after)
    return min(d for d, _ in firsts.values()), firsts


def see_stu(page, rep: dict, where: str, phone: bool) -> None:
    """see(), plus: no student code on the tab or in a window over it."""
    see(page, rep, where, phone)
    if codes := HS_CODE.findall(page.inner_text("#panel-hoc-sinh") + page.inner_text("#modal-root")):
        rep["missing"].append(f"{where}: a student code is on screen {codes}")


def stu_list(page, rep: dict) -> bool:
    """The Học sinh tab on its list; a profile left open goes back with ← Danh sách."""
    press(page, rep, "#tab-hoc-sinh", "tab hoc-sinh")
    if page.locator(BACK).count():
        press(page, rep, BACK, "students ← Danh sách", JS_STU_LIST)
    return expect(page, rep, JS_STU_LIST, "students: the list did not show")


def stu_open(page, rep: dict, name: str) -> bool:
    if not stu_list(page, rep):
        return False
    press(page, rep, f'#st-cards .st-card:has-text("{name}") .st-name', f"students open {name}", JS_STU_PROFILE, name)
    return page.locator(BACK).count() == 1


@counted()
def stu_view(page, rep: dict, data_dir: str, root: str, phone: bool) -> None:
    """The list: the live students with their levels, the archived one only under Đã lưu trữ, search without accents."""
    if not stu_list(page, rep):
        return
    live = scalar(data_dir, "SELECT count(*) FROM student WHERE archived_at IS NULL")
    cards, arch = page.inner_text("#st-cards"), page.inner_text("#st-arch")
    if (
        f"{live} em đang học" not in page.inner_text("#panel-hoc-sinh .page-head")
        or page.locator(".st-card").count() != live
    ):
        rep["missing"].append(f"students list: want '{live} em đang học' and {live} cards")
    rep["missing"] += [f"students list: no card for {n}" for n in PEOPLE if n not in cards]
    if ARCHIVED in cards or ARCHIVED not in arch or "Bỏ lưu trữ" not in arch:
        rep["missing"].append(f"students list: {ARCHIVED} should be only under Đã lưu trữ, with Bỏ lưu trữ")
    info = {s["name"]: s for s in api(root, "GET", "/students?view=teacher&archived=true")}
    sid = info[PEOPLE[0]]["id"]
    card = page.locator("#st-cards .st-card", has_text=PEOPLE[0]).inner_text()
    got = Counter(level_of(t) for _, t in fetch(data_dir, SKILL_THETA, sid))
    for w in ("vững", "đang hình thành", "chưa vững"):
        if not re.search(rf"(?<!\d){got[w]} {w}", card):
            rep["missing"].append(f"students list: the card of {PEOPLE[0]} lacks '{got[w]} {w}'")
    last, pend = info[PEOPLE[0]]["last_session"], info[PEOPLE[0]]["pending_grading"]
    if (
        last
        and f"Buổi gần nhất: {last['held_on'][8:]}/{last['held_on'][5:7]} · {ten(last['score'], last['max_score'])}"
        not in card
    ):
        rep["missing"].append(f"students list: the last session of {PEOPLE[0]} is not on its card: {card!r}")
    if pend and f"{pend} bài chờ duyệt" not in card:
        rep["missing"].append(f"students list: want '{pend} bài chờ duyệt' on the card of {PEOPLE[0]}")
    for typed, want, words in (("binh", 1, PEOPLE[1]), ("zzz", 0, "Không có học sinh nào"), ("", live, "")):
        page.fill("#st-q", typed)
        if page.locator(".st-card").count() != want or words not in page.inner_text("#st-cards"):
            rep["missing"].append(f"students list: searching {typed!r} should leave {want} cards ({words!r})")
    see_stu(page, rep, "students list", phone)


@counted(commit=("student",))
def stu_add(page, rep: dict, data_dir: str, phone: bool, name: str) -> bool:
    """One word is refused in the server's words and adds no row (Focus 5); the full name adds one card."""
    if not stu_list(page, rep):
        return False
    before = scalar(data_dir, "SELECT count(*) FROM student")
    press(page, rep, '[data-act="st-add"]', "students + Thêm học sinh", JS_MODAL)
    page.fill("#sf-name", STU_ONE)
    press(page, rep, '[data-act="st-save"]', "students Thêm một chữ", JS_SF_ERR, STU_ONE_MSG)
    if scalar(data_dir, "SELECT count(*) FROM student") != before or not page.evaluate(JS_MODAL):
        rep["missing"].append("students add: a one-word name added a row, or the window closed")
    see_stu(page, rep, "students add refused", phone)
    page.fill("#sf-name", name)
    page.select_option("#sf-grade", "9")
    page.fill("#sf-note", STU_NOTE)
    press(page, rep, '[data-act="st-save"]', "students Thêm học sinh", JS_STU_CARD_HAS, [name, STU_NOTE])
    if scalar(data_dir, "SELECT count(*) FROM student") != before + 1 or not scalar(
        data_dir, "SELECT count(*) FROM student WHERE name = ? AND grade = 9 AND note = ?", name, STU_NOTE
    ):
        rep["missing"].append(f"students add: want 1 new row for {name}, lớp 9, with the note")
    if "Lớp 9" not in page.locator("#st-cards .st-card", has_text=name).inner_text():
        rep["missing"].append("students add: the new card lacks 'Lớp 9'")
    find = STU_FIND[rep["viewport"]]
    page.fill("#st-q", find)
    if page.locator("#st-cards .st-card").count() != 1 or name not in page.inner_text("#st-cards"):
        rep["missing"].append(f"students add: searching {find!r} should find only {name}")
    page.fill("#st-q", "")
    see_stu(page, rep, "students added", phone)
    press(page, rep, "#tab-tro-ly", "tab tro-ly")  # the @ list holds the new name once, found without accents
    page.fill("#chat-input", f"@{find}")
    expect(page, rep, JS_POP, f"students add: @{find} lists nobody in the chat")
    if (names := page.locator("#mention-pop .mention-opt b").all_inner_texts()) != [name]:
        rep["missing"].append(f"students add: chat @{find} lists {names}, want [{name!r}]")
    page.fill("#chat-input", "")
    return stu_list(page, rep)


@counted(commit=("student",))
def stu_edit(page, rep: dict, data_dir: str, root: str, phone: bool, name: str) -> None:
    """Sửa keeps a grade the box does not list; the box holds the name; markup in a note stays text on the card."""
    sid = scalar(data_dir, "SELECT id FROM student WHERE name = ?", name)
    api(root, "PATCH", f"/students/{sid}", {"grade": 3})  # the server takes 1 to 12, the box lists 6 to 12
    press(page, rep, "#tab-hoc-sinh", "tab hoc-sinh")
    expect(page, rep, JS_STU_CARD_HAS, "students edit: the card does not show Lớp 3", [name, "Lớp 3"])
    press(page, rep, f'#st-cards .st-card:has-text("{name}") [data-act="st-edit"]', "students Sửa", JS_MODAL)
    if page.input_value("#sf-name") != name or page.input_value("#sf-grade") != "3":
        rep["missing"].append(
            f"students edit: the box holds {page.input_value('#sf-name')!r}, lớp {page.input_value('#sf-grade')!r}"
        )
    page.fill("#sf-note", STU_NOTE2)
    press(page, rep, '[data-act="st-save"]', "students Lưu thay đổi", JS_STU_CARD_HAS, [name, STU_NOTE2])
    if not scalar(data_dir, "SELECT count(*) FROM student WHERE name = ? AND note = ? AND grade = 3", name, STU_NOTE2):
        rep["missing"].append("students edit: tutor.db lacks the new note, or the grade 3 changed")
    if page.locator("#st-cards .st-card", has_text=name).locator("b").count():  # no session, so a <b> is the note's
        rep["missing"].append("students edit: the note became markup on the card")
    see_stu(page, rep, "students edited", phone)


@counted()
def stu_empty(page, rep: dict, phone: bool, name: str) -> None:
    """A student with no session (Focus 4): every empty part says Chưa có, no console error; Làm báo cáo picks them."""
    errors = len(rep["console_errors"]) + len(rep["page_errors"])
    if not stu_open(page, rep, name):
        return
    text = page.inner_text("#panel-hoc-sinh")
    rep["missing"] += [f"students empty: no '{w}'" for w in STU_EMPTY if w not in text]
    if text.count("Chưa có.") != 3 or page.locator("#st-chart").count():
        rep["missing"].append("students empty: want 3 'Chưa có.' skill columns and no chart")
    see_stu(page, rep, "students empty", phone)
    press(page, rep, '#panel-hoc-sinh [data-act="st-rep"]', "students Làm báo cáo", JS_TAB, "bao-cao")
    expect(
        page,
        rep,
        JS_REP_NAME,
        f"students: Làm báo cáo does not select {name} (a student added after the Báo cáo list)",
        name,
    )
    see_rep(page, rep, "students Làm báo cáo", phone)
    if len(rep["console_errors"]) + len(rep["page_errors"]) != errors:
        rep["missing"].append("students empty: the console logged an error")


@counted(commit=("student",))
def stu_archive(page, rep: dict, data_dir: str, root: str, phone: bool, name: str) -> None:
    """Lưu trữ asks first and moves the card under Đã lưu trữ; Bỏ lưu trữ brings it back; it ends archived."""
    if not stu_list(page, rep):
        return
    card, gone = f'#st-cards .st-card:has-text("{name}")', "SELECT archived_at IS NOT NULL FROM student WHERE name = ?"
    press(page, rep, f'{card} [data-act="st-archive"]', "students Lưu trữ", JS_ROOT_HAS, f"Lưu trữ {name}?")
    press(page, rep, '[data-act="confirm-ok"]', "students đồng ý lưu trữ", JS_STU_ARCH, name)
    if page.locator(card).count() or not scalar(data_dir, gone, name):
        rep["missing"].append("students archive: the card is still in the list, or tutor.db is not archived")
    expect(page, rep, JS_FOCUS_ID, "students archive: the focus did not go to the search box", "st-q")
    see_stu(page, rep, "students archived", phone)
    press(
        page,
        rep,
        f'#st-arch .spread:has-text("{name}") [data-act="st-unarchive"]',
        "students Bỏ lưu trữ",
        JS_STU_CARD,
        name,
    )
    if scalar(data_dir, gone, name):
        rep["missing"].append("students unarchive: tutor.db still has the student archived")
    expect(page, rep, JS_FOCUS_CARD, "students unarchive: the focus is not on the name of the restored card", name)
    # the chat's @ list and the next walk want only PEOPLE live
    api(root, "POST", f"/students/{scalar(data_dir, 'SELECT id FROM student WHERE name = ?', name)}/archive")


@counted()
def stu_progress(page, rep: dict, data_dir: str, phone: bool, sid: int, name: str) -> None:
    """An's profile: every skill at the level tutor.db holds, the arrows, the chart (points, Tab, table, one skill)."""
    if not stu_open(page, rep, name):
        return
    head = page.inner_text("#panel-hoc-sinh .page-head") + " " + page.inner_text(BACK)
    rep["missing"] += [
        f"students profile: no '{w}'"
        for w in (name, "Học từ ", "Soạn phiếu với Trợ lý", "Làm báo cáo", "Sửa", "← Danh sách")
        if w not in head
    ]
    while page.locator('[data-act="st-more"]:has-text("Xem tất cả")').count():
        page.click('[data-act="st-more"]:has-text("Xem tất cả") >> nth=0')
    got = page.evaluate(JS_STU_SKILLS)
    thetas = dict(fetch(data_dir, SKILL_THETA, sid))
    if not thetas or sorted((n, lv) for n, lv, _ in got) != sorted((n, level_of(t)) for n, t in thetas.items()):
        rep["missing"].append(
            f"students profile: levels {sorted(got)[:2]}... differ from skill_state {sorted(thetas.items())[:2]}..."
        )
    rep["missing"] += [f"students profile: '{n}' has no arrow ({a!r})" for n, _, a in got if a not in STU_TRENDS]
    open_n = scalar(
        data_dir, "SELECT count(*) FROM misconception_log WHERE student_id = ? AND resolved_at IS NULL", sid
    )
    done_n = scalar(
        data_dir, "SELECT count(*) FROM misconception_log WHERE student_id = ? AND resolved_at IS NOT NULL", sid
    )
    shown = page.locator('section:has(h2:text-is("Lỗi hay lặp lại")) > ul > li').count()
    if shown != open_n or (done_n and f"Đã sửa được ({done_n})" not in page.inner_text("#panel-hoc-sinh")):
        rep["missing"].append(
            f"students profile: {shown} repeated mistakes shown, tutor.db has {open_n} open and {done_n} fixed"
        )
    see_stu(page, rep, "students profile", phone)
    first, firsts = first_points(data_dir, sid)
    dm = f"{first[8:]}/{first[5:7]}"
    if not page.locator("#st-chart circle > title").count():
        rep["missing"].append("students chart: no point with a <title>")
    page.focus("#st-chart-skill")
    page.keyboard.press("Tab")
    expect(page, rep, JS_STU_DOT, "students chart: Tab from the skill box did not reach a point")
    expect(page, rep, JS_STU_TIP, "students chart: the focused point wrote no 'dd/mm: mức'")
    day1 = [t for d, t in firsts.values() if d == first]
    want = f"{dm}: {level_of(sum(day1) / len(day1))}"
    if page.inner_text("#st-tip").strip() != want:
        rep["missing"].append(f"students chart: the first point says {page.inner_text('#st-tip')!r}, want {want!r}")
    if not page.evaluate(JS_STU_FIT):
        rep["missing"].append("students chart: the drawing is wider than its box")
    press(page, rep, '[data-act="st-table"]', "students Xem dạng bảng", JS_STU_TABLE)
    toggle = page.locator('[data-act="st-table"]')
    if first[8:] + "/" + first[5:7] + "/" + first[:4] not in page.inner_text("#st-chart"):
        rep["missing"].append("students chart: the table lacks the first date")
    if toggle.inner_text().strip() != "Xem dạng bảng" or toggle.get_attribute("aria-pressed") != "true":
        rep["missing"].append(f"students chart: the toggle says {toggle.inner_text()!r}, want 'Xem dạng bảng' pressed")
    see_stu(page, rep, "students table", phone)
    press(page, rep, '[data-act="st-table"]', "students Xem dạng bảng tắt", JS_STU_SVG)
    if toggle.inner_text().strip() != "Xem dạng bảng" or toggle.get_attribute("aria-pressed") != "false":
        rep["missing"].append("students chart: the toggle did not stay 'Xem dạng bảng', not pressed")
    names = page.eval_on_selector_all("#st-chart-skill option", "os => os.map(o => o.textContent)")
    if len(names) < 2 or names[1] not in thetas or names[1] not in firsts:
        rep["missing"].append(f"students chart: the skill box lists {names[:3]}, want 'Mức chung' then skill names")
        return
    page.select_option("#st-chart-skill", index=1)
    expect(page, rep, JS_STU_SVG_NAME, f"students chart: picking {names[1]} did not redraw it", names[1])
    page.focus("#st-chart-skill")
    page.keyboard.press("Tab")
    expect(page, rep, JS_STU_TIP, "students chart: a skill's point wrote no 'dd/mm: mức'")
    day, theta = firsts[names[1]]
    want = f"{day[8:]}/{day[5:7]}: {level_of(theta)}"
    if page.inner_text("#st-tip").strip() != want:
        rep["missing"].append(f"students chart: {names[1]} says {page.inner_text('#st-tip')!r}, want {want!r}")
    see_stu(page, rep, "students chart skill", phone)


def taint(route) -> None:
    """Fetch the real answer, then put markup into the dates and a level: strings the tab prints."""
    body, url = route.fetch().json(), route.request.url
    if url.endswith("/progress"):
        body["dates"][0], body["all"][0]["level"] = XSS_DATE, XSS_LEVEL
    elif url.endswith("/profile"):
        body["student"]["since"] = XSS_DATE
    else:
        body[0]["held_on"] = XSS_DATE
    route.fulfill(json=body)


@counted()
def stu_xss(page, rep: dict, phone: bool, name: str) -> None:
    """Dates and a level with markup show as text, never as elements: header, chart point, tip, table, sessions."""
    page.route(TAINT_URL, taint)
    try:
        if not stu_open(page, rep, name):
            return
        page_head = page.inner_text("#panel-hoc-sinh .page-head")
        if "Học từ <u>20/10/2026" not in page_head or page.locator("#panel-hoc-sinh .page-head u").count():
            rep["missing"].append(f"students xss: the header shows {page_head!r}, want the date as text")
        sessions = page.inner_text("#panel-hoc-sinh table")
        if "<u>20/10/2026" not in sessions or page.locator("#panel-hoc-sinh table u").count():
            rep["missing"].append(f"students xss: the sessions table shows {sessions!r}, want the date as text")
        titles = page.locator("#st-chart circle > title")
        title = titles.first.text_content() if titles.count() else ""
        if page.locator("#st-chart i, #st-chart u").count() or XSS_LEVEL not in title:
            rep["missing"].append("students xss: the chart point's title is not the level as text")
        page.focus("#st-chart-skill")
        page.keyboard.press("Tab")
        expect(page, rep, JS_STU_DOT, "students xss: Tab from the skill box did not reach a point")
        if (tip := page.inner_text("#st-tip").strip()) != f"<u/10: {XSS_LEVEL}":
            rep["missing"].append(f"students xss: the tip says {tip!r}, want the date and level as text")
        press(page, rep, '[data-act="st-table"]', "students xss Xem dạng bảng", JS_STU_TABLE)
        table = page.inner_text("#st-chart")
        if XSS_LEVEL not in table or "<u>20/10/2026" not in table or page.locator("#st-chart i, #st-chart u").count():
            rep["missing"].append(f"students xss: the chart table shows {table!r}, want text")
    finally:
        page.unroute(TAINT_URL, taint)
    stu_open(page, rep, name)  # a clean load for the next steps


@counted()
def stu_session(page, rep: dict, data_dir: str, phone: bool, sid: int) -> None:
    """Xem bài of 20/10: formulas typeset, steps, mistakes in words (not codes); Esc closes and returns the focus."""
    row = '#panel-hoc-sinh tr:has-text("20/10/2026")'
    press(page, rep, f'{row} [data-act="st-session"]', "students Xem bài", JS_MJX)
    text = page.inner_text("#modal-root")
    n = scalar(data_dir, "SELECT count(*) FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
                         " JOIN session s ON s.id = a.session_id WHERE s.thread_id = ?", G_S01)  # fmt: skip
    if page.locator("#modal-root .mistake").count() != n or page.inner_text(f"{row} td:nth-child(4)").strip() != str(n):
        rep["missing"].append(f"students session: want {n} mistakes in the window and in the table")
    rep["missing"] += [f"students session: no '{w}'" for w in (NEW_KIND, ADDED, NAMED, "Bước 1") if w not in text]
    if NEW_CODE in text or page.locator("#modal-root .wstep.hit").count() < 1:
        rep["missing"].append("students session: the error code shows, or no step is marked")
    see_stu(page, rep, "students session", phone)
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "students session: Esc did not close the window")
    if (on := page.evaluate(JS_ACT)) != "st-session":
        rep["missing"].append(f"students session: the focus is on {on!r} after Esc, want the Xem bài button")


@counted()
def stu_report(page, rep: dict, phone: bool, name: str) -> None:
    """Làm báo cáo selects An; Xem on the 20/10 report opens it in the Báo cáo tab, green frame."""
    press(page, rep, '#panel-hoc-sinh [data-act="st-rep"]', "students Làm báo cáo", JS_TAB, "bao-cao")
    expect(page, rep, JS_REP_NAME, f"students: Làm báo cáo does not select {name}", name)
    press(page, rep, "#tab-hoc-sinh", "tab hoc-sinh")
    row = '#panel-hoc-sinh .st-report:has-text("ngày 20/10/2026")'
    if not expect(
        page,
        rep,
        "() => !!document.querySelector('#panel-hoc-sinh .st-report')",
        "students: Báo cáo đã duyệt lists nothing",
    ):
        return
    if not re.search(r"duyệt \d\d/\d\d/\d{4}", page.inner_text(row)):
        rep["missing"].append(f"students: the 20/10 report row lacks 'duyệt dd/mm/yyyy': {page.inner_text(row)!r}")
    press(page, rep, f'{row} [data-act="st-rep-open"]', "students Xem báo cáo", JS_TAB, "bao-cao")
    expect(page, rep, JS_REP_DONE, "students: Xem did not open the approved report in the Báo cáo tab")
    expect(page, rep, JS_FOCUS_ID, "students: the focus is not on the report title after Xem", "rep-title")
    see_rep(page, rep, "students Xem báo cáo", phone)


@counted()
def stu_sheet(page, rep: dict, data_dir: str, phone: bool, sid: int, name: str) -> None:
    """Bình's sheet from walk_worksheet: Xem phiếu lists every problem with its formula."""
    if not stu_open(page, rep, name):
        return
    sheets = fetch(data_dir, SHEET_DATES, sid)
    refs = [r for (r,) in fetch(data_dir, SHEET_REFS, sid, sheets[0][0])] if sheets else []
    if not sheets or page.locator("#panel-hoc-sinh .st-sheet").count() != len(sheets):
        rep["missing"].append(f"students sheet: want {len(sheets)} sheets listed under Phiếu đã giao")
        return
    press(page, rep, '#panel-hoc-sinh .st-sheet [data-act="st-ws-view"] >> nth=0', "students Xem phiếu", JS_MJX)
    text = page.inner_text("#modal-root")
    if page.locator("#modal-root li").count() != len(refs) or any(r not in text for r in refs):
        rep["missing"].append(f"students sheet: want {len(refs)} problems {refs} in the window")
    if f"Phiếu buổi {sheets[0][0][8:]}/{sheets[0][0][5:7]}/{sheets[0][0][:4]}" not in text:
        rep["missing"].append("students sheet: the window title lacks the sheet's date")
    see_stu(page, rep, "students sheet", phone)
    page.keyboard.press("Escape")
    expect(page, rep, JS_NO_MODAL, "students sheet: Esc did not close the window")


@counted()
def stu_job(page, rep: dict, root: str, phone: bool, sid: int, name: str) -> None:
    """The waiting-grading reminder on the profile opens that G1 card in the Trợ lý tab."""
    tid = api(root, "GET", f"/students/{sid}/profile")["pending"][0]["thread_id"]
    if not stu_open(page, rep, name):
        return
    press(page, rep, '#panel-hoc-sinh [data-act="st-job"]', "students Duyệt trong Trợ lý", JS_TAB, "tro-ly")
    expect(page, rep, JS_HOST_SEL, f"students: Duyệt trong Trợ lý did not open the card of {tid}", [tid, ".mistake"])


@counted()
def stu_assist(page, rep: dict, root: str, phone: bool, sid: int, name: str) -> None:
    """Soạn phiếu với Trợ lý: the Trợ lý tab sends the ask (name on screen, no code); the draft it makes is dropped."""
    if not stu_open(page, rep, name):
        return
    n = msgs(page)
    press(page, rep, '#panel-hoc-sinh [data-act="st-ws"]', "students Soạn phiếu với Trợ lý", JS_TAB, "tro-ly")
    expect(page, rep, JS_REPLIED, "students: no answer to Soạn phiếu với Trợ lý", n)
    mine = page.locator("#chat-msgs .msg-me").last
    if mine.locator(".mention").inner_text().strip() != name or HS_CODE.search(mine.inner_text()):
        rep["missing"].append(
            f"students: the sent message shows {mine.inner_text()!r}, want the mention {name!r} and no code"
        )
    if not expect(page, rep, JS_WS_DRAFT, "students: Soạn phiếu with the assistant made no draft"):
        return
    api(root, "POST", f"/threads/{page.evaluate(JS_WS_TID)}/cancel")


def walk_students(page, rep: dict, phone: bool, data_dir: str, root: str, shots: bool) -> None:
    """The Học sinh tab after the reports are made: list, add / edit / archive, an empty profile, An's and Bình's."""
    ids = {s["name"]: s["id"] for s in api(root, "GET", "/students?archived=true")}
    an, binh, new = ids[PEOPLE[0]], ids[PEOPLE[1]], STU_NEW[rep["viewport"]]
    stu_view(page, rep, data_dir, root, phone)
    if stu_add(page, rep, data_dir, phone, new):
        stu_edit(page, rep, data_dir, root, phone, new)
        stu_empty(page, rep, phone, new)
        stu_archive(page, rep, data_dir, root, phone, new)
    stu_progress(page, rep, data_dir, phone, an, PEOPLE[0])
    if shots:
        shoot(page, rep, f"students-profile-{'phone' if phone else 'desktop'}")
    stu_xss(page, rep, phone, PEOPLE[0])
    stu_session(page, rep, data_dir, phone, an)
    stu_report(page, rep, phone, PEOPLE[0])
    stu_sheet(page, rep, data_dir, phone, binh, PEOPLE[1])
    stu_job(page, rep, root, phone, an, PEOPLE[0])
    stu_assist(page, rep, root, phone, an, PEOPLE[0])


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


def walk(browser, base: str, vp_name: str, vp: dict, shots: bool, data_dir: str | None, home: str | None) -> dict:
    rep = {"viewport": vp_name, "console_errors": [], "page_errors": [], "dead": [], "missing": [], "forbidden": [],
           "overflow": [], "shots": []}  # fmt: skip
    phone = vp is PHONE
    page = browser.new_context(viewport=vp, color_scheme="light").new_page()
    reqs: list = []
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)))
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
    walk_chat(page, rep, phone, data_dir, base)
    if data_dir:
        walk_grading(page, rep, phone, data_dir)
        walk_worksheet(page, rep, phone, data_dir)
        if not phone:
            cancel_grading(page, rep, data_dir, base)
            cancel_draft(page, rep, data_dir, base)
        walk_reports(page, rep, phone, data_dir, base)
        if not phone:
            walk_chat_report(page, rep, data_dir, base)
        walk_students(page, rep, phone, data_dir, base, shots)
    walk_bank(page, rep, phone, data_dir, files)
    walk_gear(page, rep, phone, bool(data_dir), home)
    walk_nokey(page, rep, phone)
    walk_theme(page, rep, base)
    page.wait_for_timeout(500)  # late errors
    rep["missing"] += [f"{x}: the request body holds a student name (C-40)" for x in named_bodies(reqs)]
    with step(rep, "walk end"):  # catches rows changed since the last step
        pass
    page.context.close()
    return rep


def expected_rows(backup: Path) -> dict:
    """Row counts tutor.db must have after restoring `backup`: its own, bar the sessions restore drops (R7)."""
    with closing(sqlite3.connect(f"{backup.as_uri()}?mode=ro", uri=True)) as con:
        got = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
        got["session"] = con.execute(
            "SELECT count(*) FROM session WHERE status = 'committed'"
            " OR EXISTS (SELECT 1 FROM attempt WHERE session_id = session.id)"
        ).fetchone()[0]
    return got


def walk_restore(browser, base: str, data_dir: str) -> dict:
    """--data, after both walks (they still need the seeded threads): Khôi phục is refused while work is unfinished,
    Bỏ các việc này rồi khôi phục drops it, and tutor.db ends with the rows of the chosen backup."""
    rep = {k: [] for k in ("console_errors", "page_errors", "dead", "missing", "forbidden", "overflow", "shots")}
    rep["viewport"] = "restore"
    page = browser.new_context(viewport=DESK, color_scheme="light").new_page()
    page.on(
        "console",
        lambda m: m.type == "error" and not m.text.startswith(NET_NOISE) and rep["console_errors"].append(m.text[:300]),
    )
    page.on("pageerror", lambda e: rep["page_errors"].append(str(e)[:300]))
    page.goto(base)
    with step(rep, "restore", commit=TABLES):
        expect(page, rep, JS_NO_RUNNING, "restore: a thread is still running before the walk starts")
        before = backup_names(page)
        press(page, rep, "#gear-btn", "gear")
        press(page, rep, '[data-sys="backup"]', "gear item backup", JS_ROOT_HAS, "Sao lưu ngay")
        press(page, rep, '[data-act="backup-now"]', "backup Sao lưu ngay", JS_TOAST_HAS, "Đã sao lưu dữ liệu.")
        expect(page, rep, JS_N_ROWS, "backup: Sao lưu ngay did not add a row", len(before) + 1)
        new = sorted(set(backup_names(page)) - set(before))
        if len(new) != 1:
            rep["missing"].append(f"restore: Sao lưu ngay added {new}, expected one file")
            return rep
        api(base, "POST", "/students", {"name": "Phạm Robot", "grade": 7})  # a change the backup does not hold
        open_ = [t for t in api(base, "GET", "/threads") if t["status"] in OPEN_STATES]
        want = (
            f"Còn {len(open_)} việc chưa xong ("
            + ", ".join(f"{sum(t['graph'] == g for t in open_)} {word}" for g, word in UNFINISHED)
            + ")."
        )
        if not open_:
            rep["missing"].append("restore: --data left nothing unfinished, so the refusal is not tested")
        press(
            page,
            rep,
            f'[data-act="backup-restore"][data-name="{new[0]}"]',
            "backup Khôi phục",
            JS_ROOT_HAS,
            "Khôi phục bản sao lưu?",
        )
        press(page, rep, '[data-act="confirm-ok"]', "backup Khôi phục (hỏi lại)", JS_ROOT_HAS, "Còn ")
        text = page.inner_text("#modal-root")
        if want not in text:
            rep["missing"].append(f"restore: the refusal says {text!r}, expected {want!r}")
        see(page, rep, "restore refusal", False)
        if not page.evaluate(JS_ON, '[data-act="backup-drop"]') or "Bỏ các việc này rồi khôi phục" not in text:
            rep["missing"].append("restore: Bỏ các việc này rồi khôi phục is not an enabled button")
        page.evaluate("window.__robotLoaded = 1")
        press(
            page,
            rep,
            '[data-act="backup-drop"]',
            "backup Bỏ các việc này rồi khôi phục",
            JS_TOAST_HAS,
            f"Đã khôi phục bản {backup_when(new[0])}",
        )
        expect(page, rep, JS_RELOADED, "restore: the page did not reload after Khôi phục")
        if left := [t["thread_id"] for t in api(base, "GET", "/threads") if t["status"] in OPEN_STATES]:
            rep["missing"].append(f"restore: unfinished threads left after Khôi phục: {left}")
        got, want_rows = counts(data_dir), expected_rows(Path(data_dir, "backup", new[0]))
        if diff := moved(want_rows, got):
            rep["missing"].append(f"restore: tutor.db differs from backup {new[0]} (backup, now): {diff}")
    page.wait_for_timeout(500)  # late errors
    page.context.close()
    return rep


def fold(text: str) -> str:
    """Lowercase, no diacritics; đ has no decomposition, so it is mapped by hand."""
    plain = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in plain if not unicodedata.combining(c)).replace("đ", "d")


# names that must never reach a model or a POST body. The two students the Học sinh walk adds are not here on
# purpose: their own POST /students body holds the name, and they are never asked about.
NAMES = tuple(fold(n) for n in (*PEOPLE, ARCHIVED))


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


def named_bodies(reqs: list) -> list:
    """POST and PUT requests whose body holds a student's full name (C-40)."""
    return [
        f"{m} {u.split('/api', 1)[-1]}"
        for m, u, b in reqs
        if m in ("POST", "PUT") and b and any(n in fold(b) for n in NAMES)
    ]


def check(url: str, args: argparse.Namespace) -> int:
    base = url
    data_dir = getattr(url, "data_dir", None) if args.data else None
    if data_dir:
        api(url, "POST", "/catalog/kc", {"code": "ROBOT-LE-01", "name": LEAF, "description": "robot", "lop": 8})
        api(url, "POST", f"/students/{api(url, 'POST', '/students', {'name': ARCHIVED, 'grade': 7})['id']}/archive")
        LEDGER.update(dir=data_dir, last=counts(data_dir))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        home = getattr(url, "data_dir", None)  # set only when the robot started the app: only then may it save settings
        views = [
            walk(browser, base, n, vp, args.shots, data_dir, home) for n, vp in (("desktop", DESK), ("phone", PHONE))
        ]
        if data_dir:
            views.append(walk_restore(browser, base, data_dir))
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
