#!/usr/bin/env python3
"""Robot for app-user.html: errors, forbidden words, button sweep, 4 scripted flows, 390 px overflow, screenshots.

  cd PROJECT_III && uv run python docs/prototype/app-user/check.py [SHOT_DIR]
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = (Path(__file__).resolve().parent.parent / "app-user.html").as_uri()
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
TABS = ["tro-ly", "hoc-sinh", "bao-cao", "ngan-hang"]
FORBIDDEN = re.compile(r"θ|δ|Δθ|\[F\d\d\]|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear|thread|token|checkpoint|\bnode\b|g[1-5]-hs|HS-\d\d|JSON|\bKC\b")
STUB = "window.print = function () { window.__printed = (window.__printed || 0) + 1; };"
fails, notes = [], []


def check(cond, msg):
    (notes if cond else fails).append(("ok   " if cond else "FAIL ") + msg)


def visible_text_ok(pg, where):
    txt = pg.evaluate("document.body.innerText")
    bad = sorted(set(FORBIDDEN.findall(txt)))
    check(not bad, f"no technical words visible [{where}] {bad if bad else ''}")


def overflow(pg, where):
    sw = pg.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)")
    iw = pg.evaluate("window.innerWidth")
    check(sw <= iw, f"no horizontal overflow at {iw}px [{where}] scrollWidth={sw}")


def wait_tex(pg):
    try:
        pg.wait_for_function("window.MathJax && MathJax.typesetPromise", timeout=15000)
        pg.wait_for_timeout(400)
    except Exception:
        notes.append("note MathJax CDN not loaded within 15 s")


def open_page(ctx, tab, block_cdn=False):
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "net::" not in m.text and "Failed to load resource" not in m.text and errs.append(m.text))
    if block_cdn:
        pg.route(re.compile(r"^https?://"), lambda r: r.abort())
    pg.goto(f"{URL}#{tab}", wait_until="domcontentloaded")
    pg.wait_for_timeout(300)
    pg.errs = errs
    return pg


def sweep(ctx):
    """Every visible, enabled button on each tab's first screen changes the DOM when clicked."""
    total = 0
    for tab in TABS:
        pg = open_page(ctx, tab, block_cdn=True)
        n = pg.evaluate("Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent && !b.disabled).length")
        dead = []
        for i in range(n):
            pg.reload(wait_until="domcontentloaded")
            pg.wait_for_timeout(150)
            label = pg.evaluate("""i => { const b = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent && !b.disabled)[i];
              if (!b) return null; window.__m = 0; new MutationObserver(r => window.__m += r.length).observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
              const t = (b.getAttribute('aria-label') || b.textContent).trim().slice(0, 40); b.click(); return t; }""", i)
            if label is None:
                continue
            pg.wait_for_timeout(700)
            if not pg.evaluate("window.__m"):
                dead.append(label)
            total += 1
        check(not dead, f"[{tab}] {n} buttons each change the DOM {dead if dead else ''}")
        check(not pg.errs, f"[{tab}] sweep without page errors {pg.errs[:3]}")
        pg.close()
    return total


def flows(ctx, shots):
    pg = open_page(ctx, "tro-ly")
    wait_tex(pg)
    visible_text_ok(pg, "Trợ lý start")
    if shots:
        pg.screenshot(path=str(shots / "desktop-1-tro-ly.png"))

    # F1 grading: attach An's file → confirm match → review each mistake → save
    pg.click("button[data-act=suggest]:has-text('Chấm bài của An')")
    pg.wait_for_selector(".steps .on:has-text('Đang đọc bài')", timeout=3000)
    check(True, "F1 progress 'Đang đọc bài…' shown")
    pg.wait_for_selector("text=Bài 3 không ghi mã bài", timeout=8000)
    check(pg.locator(".gcard").last.locator("mjx-container").count() > 0, "F1 match candidates render formulas")
    pg.click("button[data-act=g-match-ok]")
    pg.wait_for_selector("button[data-act=g-save]", timeout=8000)
    save = pg.locator("button[data-act=g-save]").last
    check(save.is_disabled(), "F1 'Lưu kết quả' disabled before every mistake is decided")
    card = pg.locator(".gcard").last
    decs = card.locator("[data-act=g-dec][data-v=ok]")
    nm = decs.count()
    check(nm == 3, f"F1 three mistakes to review (got {nm})")
    card.locator("[data-act=g-dec][data-v=ok]").nth(0).click()
    card.locator("[data-act=g-dec][data-v=edit]").nth(1).click()
    card.locator(".edit-form textarea").fill("Dùng sai hằng đẳng thức khi bỏ dấu giá trị tuyệt đối.")
    card.locator("[data-act=g-edit-done]").click()
    card.locator("[data-act=g-dec][data-v=drop]").nth(2).click()
    card.locator("[data-act=g-add]").first.click()
    card.locator(".edit-form textarea").fill("Quên kết luận nghiệm.")
    card.locator("[data-act=g-add-ok]").click()
    check(card.locator("text=Xem trước tiến bộ").is_visible(), "F1 progress preview in words after all decided")
    check(card.locator(".ch-up, .ch-down, .ch-keep").count() > 0, "F1 preview uses tiến bộ / giữ / cần ôn")
    check(pg.locator("button[data-act=g-save]").last.is_enabled(), "F1 'Lưu kết quả' enabled when all decided")
    visible_text_ok(pg, "F1 review")
    if shots:
        card.locator(".gprob").last.scroll_into_view_if_needed()
        pg.screenshot(path=str(shots / "flow-1-grading-card.png"))
    pg.locator("button[data-act=g-save]").last.click()
    pg.wait_for_selector("text=Đã lưu kết quả buổi 21/10", timeout=5000)
    check(pg.locator(".gcard.is-saved .steps .done:has-text('Xong')").count() == 1, "F1 saved: card shows 'Xong' + confirmation message")

    # F2 worksheet draft: suggest → reorder / remove / add by code → date → Tạo phiếu → .tex + PDF
    pg.click("button[data-act=conv-new]")
    pg.click("button[data-act=suggest]:has-text('Gợi ý 6 bài cho An')")
    pg.wait_for_selector("#draft .draft-item", timeout=6000)
    n0 = pg.locator("#draft .draft-item").count()
    check(n0 == 6, f"F2 draft has 6 problems (got {n0})")
    check(pg.input_value("#ws-date") == "2026-10-24", f"F2 'thứ Bảy' -> Saturday 24/10 (got {pg.input_value('#ws-date')})")
    first = pg.locator("#draft .draft-item .ref").first.inner_text()
    pg.locator("#draft [data-act=ws-move][data-d='1']").first.click()
    check(pg.locator("#draft .draft-item .ref").nth(1).inner_text() == first, "F2 move down reorders")
    pg.locator("#draft [data-act=ws-del]").nth(2).click()
    check(pg.locator("#draft .draft-item").count() == 5, "F2 remove drops a problem")
    pg.fill("#chat-input", "9DS-PT2-012, 9DS-HPT-005")
    pg.click("button[data-act=send]")
    pg.wait_for_selector("text=vào phiếu nháp của", timeout=5000)
    check(pg.locator("#draft .draft-item").count() == 7, "F2 typing codes in chat adds them to the draft")
    pg.fill("#ws-code", "9DS-CAN-010")
    pg.click("button[data-act=ws-add]")
    check(pg.locator("#draft .draft-item").count() == 8, "F2 add by code in panel")
    pg.fill("#ws-date", "2026-10-24")
    if shots:
        pg.screenshot(path=str(shots / "flow-2-worksheet-draft.png"))
    pg.click("button[data-act=ws-create]")
    pg.wait_for_selector("text=Đã tạo phiếu cho", timeout=5000)
    with pg.expect_download() as dl:
        pg.locator("#draft button[data-act=ws-tex]").click()
    check(dl.value.suggested_filename.endswith("2026-10-24.tex"), f"F2 .tex download ({dl.value.suggested_filename})")
    pg.locator("#draft button[data-act=ws-pdf]").click()
    pg.wait_for_timeout(1500)
    check(pg.evaluate("window.__printed || 0") >= 1, "F2 'In PDF' opens the print dialog")

    # F3 Q&A + @ mention + 'ok' saves nothing
    pg.click("button[data-act=conv-new]")
    pg.click("button[data-act=suggest]:has-text('Tháng này An yếu gì?')")
    pg.wait_for_selector(".msg-bot >> nth=-1 >> text=Nguồn:", timeout=5000)
    check(pg.locator(".msg-bot").last.locator(".uncheck").count() == 1, "F3 unchecked number marked gently")
    pg.click("button[data-act=suggest]:has-text('Ai còn nhầm dấu')")
    pg.wait_for_timeout(900)
    check(pg.locator(".msg-bot").last.locator("tbody tr").count() >= 2, "F3 'Ai còn nhầm dấu' lists students")
    pg.click("#chat-input")
    pg.keyboard.type("Em @Bả")
    check(pg.is_visible("#mention-pop"), "F3 @ opens the student picker")
    pg.keyboard.press("Enter")
    val = pg.input_value("#chat-input")
    check("@Bảo " in val, f"F3 picker inserts the name ({val!r})")
    pg.keyboard.type("tiến bộ thế nào?")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(900)
    check(pg.locator(".msg-me .mention").last.inner_text() == "Bảo", "F3 sent message shows the name chip")
    check("Bảo" in pg.locator(".msg-bot").last.inner_text(), "F3 profile answer for Bảo")
    pg.fill("#chat-input", "ok")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(900)
    check("chưa lưu gì" in pg.locator(".msg-bot").last.inner_text(), "F3 typing 'ok' saves nothing")
    pg.fill("#chat-input", "Tìm 3 bài Viète mức vừa")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(900)
    check(pg.locator(".msg-bot").last.locator(".pcard").count() == 3, "F3 search shows 3 problem cards")
    wait_tex(pg)
    check(pg.locator(".msg-bot").last.locator("mjx-container").count() > 0, "F3 problem cards render formulas")
    visible_text_ok(pg, "F3 answers")
    if shots:
        pg.screenshot(path=str(shots / "flow-3-qa.png"))

    # F4 report: this week refused → last week draft → edit flagged sentence → approve → PDF
    pg.click("button[data-act=conv-new]")
    pg.click("button[data-act=suggest]:has-text('Làm báo cáo tuần cho Bảo')")
    pg.wait_for_selector("text=chưa có buổi nào đã duyệt", timeout=5000)
    check(True, "F4 empty period refused with a reason")
    pg.click("button[data-act=rep-start]")
    pg.wait_for_selector("button[data-act=rep-open]:has-text('Mở trong Báo cáo')", timeout=6000)
    pg.click("button[data-act=rep-open]:has-text('Mở trong Báo cáo')")
    pg.wait_for_selector("#rep-doc.is-draft")
    flagged = pg.locator("#rep-doc .sent:has(.uncheck)")
    check(flagged.count() == 1, "F4 draft marks 1 sentence to re-check")
    flagged.locator("[data-act=sent-edit]").click()
    pg.fill("#rep-doc textarea", "Em làm bài cẩn thận hơn ở các bài có lời giải dài.")
    pg.click("[data-act=sent-save]")
    check(pg.locator("#rep-doc .uncheck").count() == 0, "F4 edited sentence passes the number check")
    pg.locator("#rep-doc [data-act=sent-edit]").first.click()
    pg.fill("#rep-doc textarea", "Trong tuần em làm 9 bài, đạt 80%.")
    pg.click("[data-act=sent-save]")
    check(pg.locator("#rep-doc .uncheck").count() == 1, "F4 a made-up number gets flagged again")
    pg.locator("#rep-doc .sent:has(.uncheck) [data-act=sent-del]").click()
    visible_text_ok(pg, "F4 report draft")
    if shots:
        pg.screenshot(path=str(shots / "flow-4-report-draft.png"))
    pg.click("[data-act=rep-approve]")
    pg.wait_for_selector("#rep-doc.is-approved")
    pg.click("[data-act=rep-pdf]")
    pg.wait_for_timeout(1500)
    check(pg.evaluate("window.__printed || 0") >= 2, "F4 'Tải PDF' opens the print dialog")
    check(pg.evaluate("getComputedStyle(document.getElementById('print-root')).display") == "none", "F4 print sheet hidden on screen (@media print shows it)")
    pg.emulate_media(media="print")
    check(pg.evaluate("getComputedStyle(document.getElementById('print-root')).display") == "block" and
          pg.evaluate("getComputedStyle(document.getElementById('app')).display") == "none", "F4 print CSS shows only the report")
    pg.emulate_media(media="screen")

    # Báo cáo tab direct: month report for Bảo + already-approved period
    pg.select_option("#rep-student", "1")
    pg.click("[data-act=rep-kind][data-kind=month]")
    pg.select_option("#rep-start", "2026-09-01")
    pg.click("[data-act=rep-make]")
    pg.wait_for_selector("text=đã duyệt ngày 03/10/2026", timeout=4000)
    check(True, "Báo cáo: an approved period is not approved twice")

    # Học sinh: profile shows the newly saved session; chart + session view; add / archive
    pg.click("#tab-hoc-sinh")
    pg.click("article.st-card[data-sid='1'] h3 button")
    check(pg.locator("text=Thứ Tư 21/10/2026").count() >= 1, "Học sinh: An's saved 21/10 session listed")
    check(pg.locator("#st-chart svg path.cline").count() == 1, "Học sinh: progress chart drawn")
    pg.select_option("#st-chart-skill", index=2)
    check(pg.locator("#st-chart svg path.cline").count() == 1, "Học sinh: chart per skill")
    pg.locator("[data-act=st-session]").first.click()
    check(pg.locator(".modal .mistake, .modal .gprob").count() > 0, "Học sinh: session view shows work + mistakes")
    pg.keyboard.press("Escape")
    check(pg.locator(".modal").count() == 0, "Esc closes the modal")
    visible_text_ok(pg, "Học sinh profile")
    pg.click("[data-act=st-back]")
    pg.click("[data-act=st-add]")
    pg.fill("#sf-name", "Hoàng Minh Tú")
    pg.click("[data-act=st-save]")
    check(pg.locator("article.st-card:has-text('Hoàng Minh Tú')").count() == 1, "Học sinh: add student")
    pg.locator("article.st-card:has-text('Hoàng Minh Tú') [data-act=st-archive]").click()
    pg.click("[data-act=confirm-ok]")
    check(pg.locator("[data-act=st-unarchive]").count() == 1, "Học sinh: archive moves to 'Đã lưu trữ'")

    # Ngân hàng: import with missing labels, error file, edit a problem
    pg.click("#tab-ngan-hang")
    pg.click("[data-act=imp-open]")
    pg.locator("[data-act=imp-read]").nth(1).click()
    pg.wait_for_selector("text=Không nạp được", timeout=3000)
    pg.click("[data-act=imp-back]")
    pg.locator("[data-act=imp-read]").first.click()
    pg.wait_for_selector("[data-act=imp-save]", timeout=3000)
    check(pg.locator("[data-act=imp-save]").is_disabled(), "Ngân hàng: save disabled while labels missing")
    pg.click("[data-act=imp-only][data-v='1']")
    n_need = pg.locator("select[data-imp-skill]").count()
    check(n_need == 7, f"Ngân hàng: 7 problems need the teacher (missing skill and/or level) (got {n_need})")
    for i in range(n_need):
        sel = pg.locator("select[data-imp-skill]").nth(i)
        if not sel.input_value():
            sel.select_option(index=1 + i % 3)
    pg.locator("[data-act=imp-level][data-v=kho]").first.click()
    check(pg.locator("[data-act=imp-save]").is_enabled(), "Ngân hàng: save enabled once every problem has a skill")
    if shots:
        pg.screenshot(path=str(shots / "flow-5-bank-import.png"))
    pg.click("[data-act=imp-save]")
    pg.wait_for_selector("text=Đã thêm 31 bài", timeout=3000)
    pg.click("[data-act=imp-show]")
    check("31 bài" in pg.locator("#panel-ngan-hang .page").inner_text(), "Ngân hàng: 31 new problems browsable")
    pg.locator("article.bcard").first.click()
    pg.click("[data-act=b-edit]")
    pg.click("[data-act=e-level][data-v=kho]")
    pg.click("[data-act=e-radd]")
    pg.locator("[data-rt]").last.fill("Kết luận đúng đáp số")
    pg.click("[data-act=e-save]")
    check(pg.locator(".toast:has-text('Áp dụng cho các lần chấm từ nay')").count() == 1, "Ngân hàng: edit skill / level / rubric saved")
    pg.click("[data-act=b-level][data-v=kho]")
    check(pg.locator("article.bcard").count() > 0, "Ngân hàng: filter by level")

    # ⚙ menu panels + keyboard tabs
    for key in ["backup", "catalog", "settings", "cost"]:
        pg.click("#gear-btn")
        pg.click(f"[data-act=sys][data-sys={key}]")
        check(pg.locator(".modal").count() == 1, f"⚙ {key} panel opens")
        visible_text_ok(pg, f"⚙ {key}")
        pg.keyboard.press("Escape")
    pg.focus("#tab-ngan-hang")
    pg.keyboard.press("ArrowRight")
    check(pg.evaluate("location.hash") == "#tro-ly" and pg.evaluate("document.activeElement.id") == "tab-tro-ly", "keyboard: arrow keys move between tabs")
    check(not pg.errs, f"flows without page errors {pg.errs[:3]}")
    pg.close()


def phone(ctx, shots):
    pg = open_page(ctx, "tro-ly")
    wait_tex(pg)
    for tab in TABS:
        pg.click(f"#tab-{tab}")
        pg.wait_for_timeout(500)
        overflow(pg, tab)
        if shots:
            pg.screenshot(path=str(shots / f"phone-{TABS.index(tab) + 1}-{tab}.png"))
    pg.click("#tab-tro-ly")
    pg.click("button[data-act=suggest]:has-text('Chấm bài của An')")
    pg.wait_for_selector("button[data-act=g-match-ok]", timeout=8000)
    pg.click("button[data-act=g-match-ok]")
    pg.wait_for_selector("button[data-act=g-save]", timeout=8000)
    overflow(pg, "grading card")
    pg.click("button[data-act=suggest]:has-text('Gợi ý 6 bài')")
    pg.wait_for_selector("#draft.open .draft-item", timeout=6000)
    overflow(pg, "worksheet sheet")
    if shots:
        pg.screenshot(path=str(shots / "phone-flow-worksheet-sheet.png"))
    pg.keyboard.press("Escape")
    pg.click("#tab-hoc-sinh")
    pg.click("article.st-card[data-sid='4'] h3 button")
    pg.wait_for_timeout(300)
    overflow(pg, "student profile")
    if shots:
        pg.screenshot(path=str(shots / "phone-flow-student-profile.png"), full_page=True)
    pg.click("#tab-ngan-hang")
    pg.click("[data-act=imp-open]")
    pg.locator("[data-act=imp-read]").first.click()
    pg.wait_for_selector("[data-act=imp-save]", timeout=3000)
    overflow(pg, "bank import")
    pg.keyboard.press("Escape")
    pg.click("#tab-bao-cao")
    pg.locator(".rep-item").first.click()
    overflow(pg, "report draft")
    check(not pg.errs, f"390 px without page errors {pg.errs[:3]}")
    pg.close()


def safe(fn, *a):
    try:
        fn(*a)
    except Exception as e:  # report the crash as a failure, keep the rest of the run
        fails.append(f"FAIL {fn.__name__} crashed: {str(e).splitlines()[0]}")


def main():
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        desk = b.new_context(viewport={"width": 1280, "height": 860}, color_scheme="light", accept_downloads=True)
        desk.add_init_script(STUB)
        safe(flows, desk, SHOTS)
        for tab in TABS[1:]:
            pg = open_page(desk, tab)
            wait_tex(pg)
            visible_text_ok(pg, tab)
            if SHOTS:
                pg.screenshot(path=str(SHOTS / f"desktop-{TABS.index(tab) + 1}-{tab}.png"))
            check(not pg.errs, f"[{tab}] loads without page errors {pg.errs[:3]}")
            pg.close()
        dark = b.new_context(viewport={"width": 1280, "height": 860}, color_scheme="dark")
        pg = open_page(dark, "hoc-sinh")
        pg.click("article.st-card[data-sid='1'] h3 button")
        wait_tex(pg)
        check(pg.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(17, 22, 27)", "dark theme follows the system")
        if SHOTS:
            pg.screenshot(path=str(SHOTS / "dark-hoc-sinh-profile.png"))
        pg.close()
        mob = b.new_context(viewport={"width": 390, "height": 844}, color_scheme="light", is_mobile=True, has_touch=True)
        mob.add_init_script(STUB)
        safe(phone, mob, SHOTS)
        sw = b.new_context(viewport={"width": 1280, "height": 860})
        sw.add_init_script(STUB)
        n = sweep(sw)
        notes.append(f"note swept {n} buttons")
        b.close()
    print("\n".join(notes + fails))
    print(f"\n{len(notes) - sum(1 for x in notes if x.startswith('note'))} passed, {len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
