# Shell report (as built)

The app shell, `build.py` and `check.py` are written and pass the robot check. I ran it with zero tab files and no `mock.js`: 11 tabs, 0 page errors, 0 console errors, 0 dead buttons, no horizontal scroll at 390px, MathJax loaded. A throwaway demo tab exercised the whole API and passed clean (18 clicks, no dead buttons), and I looked at desktop/phone and light/dark screenshots. The demo tab and temp files are deleted.

**Design:** graph-paper background with white work-sheet panels, fountain-pen blue accent, red handwriting (Patrick Hand) for explain-mode notes. Fonts: Be Vietnam Pro, Barlow Semi Condensed, JetBrains Mono (all have Vietnamese). Status colours are separate from the accent.

## Files
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/src/shell.html` — tokens, components, header, sidebar for all 11 tabs, review/ops badges, two-store gauge, cost meter, privacy chip, explain toggle, theme toggle (Theo máy/Sáng/Tối), footer legend, core JS. Injection points: `/*__TABS_CSS__*/`, `/*__MOCK__*/`, `/*__TABS_JS__*/`, plus `<!--__BODY__-->` marking where the head ends.
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/build.py` → `dist/app-draft.html` (full document) and `dist/artifact.html` (starts with `<title>Trợ lý gia sư Toán</title>`). Missing `mock.js` becomes `window.MOCK = {};`. Each tab JS file gets its own `<script>` tag, so one broken tab can't stop the others. Build fails if an injected file contains `</script` or `</style`.
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/check.py`

## Run
```
cd /private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto
python3 build.py
uv run --quiet --with playwright python check.py [--tabs today session] [--shots]
```
- The robot reloads the page before each tab, so every tab starts from fresh mock data.
- It clicks only buttons in the topmost modal, then the drawer, then `#view`, and closes the overlay when done.
- A button is "dead" if nothing in the page changed and no toast appeared within 300 ms.
- Per-tab report fields: `clicks`, `dead`, `navigated`, `click_failures`, `overflow_390` (with the elements that overflow), `tex_errors`, `console_errors`, `page_errors`.

## Shell API as implemented
- **`App`**: `registerTab(id, {title, render(root, ctx)})`, `start()`, `tour.{start,next,prev,stop,steps}`, `nav(id, params)`, `refresh()`, `tabs`, `registered()`, `texReady()`, `texDone()`, `started`.
  - `render` may return a cleanup function, or a promise of one.
  - If `render` throws, the error goes to `console.error` and the tab shows an error box with "Thử lại".
- **`ctx`**: `data`, `params` (all values are strings), `nav`, `rerender()` (keeps scroll position), `refresh()`, `toast(msg, {kind, title?, ms?})`, `receipt(title, rows, {graph, backup})`, `modal({title, body, actions:[{label, kind, onClick(close), noAutoclick, disabledReason}], wide, onClose}) → {close, el}`, `confirm(msg, {title, ok, cancel, danger}) → Promise<bool>`, `drawer({title, body}) → {close, el}`, `tex(el)`, `calc`, `explain`, `setExplain(bool)`, `tab`.
- **`ctx.lookup`**: everything in contract §10, plus `studentCode(s)`.
- **`ctx.queue`**:
  - `list({graph, student_id})` sets `locked`, `lock_reason`, `blocker` on each thread.
  - `count()`, `open(id)`, `resolve(id)`, `add(t)`, `heldOn(t)`.
  - `on(fn) → unsubscribe`: `fn` runs on every `refresh()` and is removed automatically on the next render.
- **`ctx.threads`**: `resume(id)`, `fail(id, node, error)`, `cancel(id, {confirm: true}) → Promise<bool>`. If the open tab registered no queue listener, the shell re-renders it after these.
- **`ctx.ui`**:
  - Everything in contract §10. `fmt` adds `int` (prints "41 200") and `ms`.
  - Extras: `pageHead({title?, lead, actions, annot, eyebrow})` (adds the P5–P7 chip itself), `costChip(calls)`, `privacy(code)`, `nodeName(nodeId)`, `svg(str)`.
  - `button(label, fn, opts)` returns a bare `<button>`. With `cli`, `privacy` or `disabledReason` it returns a `span.btn-wrap` instead, whose `.button` is the button. `size: 'sm'` makes a small button.
  - `latex(src, {block})` wraps pure math in `\(…\)` / `\[…\]`; text that already contains `$`, `\(`, `\[` or `\begin{` is passed through. Blank lines become paragraphs in block mode.

## DOM conventions
- Contract §11, plus:
  - **Math is typeset only inside `.tex` elements.** `ctx.tex` and the automatic typeset after each render, modal, drawer and popover all look only at `.tex`. This keeps text like "$0.62 / $30" from turning into math.
  - The robot also skips `[data-modal-close]`, any button inside a `[data-no-autoclick]` element, and the already-selected segment button.
- CSS classes for tab builders:
  - Layout: `.section`, `.section-head`, `.grid` (`.cols-2/3/4`), `.row`, `.stack`, `.spread`, `.card`.
  - Content: `.kpi` / `.kpi-label` / `.kpi-value`, `.callout-info|warn|crit|ok`, `pre.code`, `.untrusted`, `.field`.
  - Utilities: `.flash-hl`, `.muted`, `.small`, `.mono`, `.num`.
  - Table rows: `tr.is-dim`, `tr.is-sel`.
  - State and source marks: `.st-*`, `.pv-*`, `.chip-*`, `.status`.

## Where I differ from `contract.md`
1. **Files:** one `src/shell.html` replaces index.html, styles.css and shell.js. Mock data goes in `src/mock.js`; tabs in `src/tabs/*.js` and `*.css`, injected in filename order.
2. **MathJax:** loaded async from cdnjs 3.2.2 (not jsdelivr), with the menu turned off.
3. **Links:** the URL hash is just the tab id (`#session`), as the artifact page rules require. Params are kept in memory, so back/forward opens the tab with no params. Old-style `#/tab?k=v` links are still read.
4. **Downloads:** `ui.download` opens a modal with the file text and a copy button, because the artifact page can't download files.
5. **Thread cancel:** `threads.cancel` asks for confirmation itself, so the ops tab should not add its own.
6. **Opening a locked thread:** `queue.open` shows a warning toast and returns `false` without navigating.
7. **Resolve:** `queue.resolve` also marks the G1 session as committed and shows a toast for any session it unlocks.
8. **Receipts:** a `'cập nhật'` row shows as the bare table name; other text values are appended, e.g. "session → committed".
9. **Navigation:** `nav` closes modals, the drawer, the popover and the phone menu. While a modal or drawer is open the rest of the page is inert.
10. **Tour:** the 8 steps only navigate and show captions; nothing is committed. The students step passes `student: '3'` (an id, not "HS-03"), so the students tab must accept ids.
11. **`check.py` exit code:** it exits 1 on page errors and also on app console errors, except network-load failures.

`src/mock.js` doesn't exist yet. Some other agent has created `proto/mock/tutor_calc.js`, but `build.py` only reads `src/mock.js`, so the mock agent must write there. I haven't tested the shell against the real mock data. MathJax and the fonts need network access, both in the robot and in the browser.

# Mock data report (as built)

I wrote the generator and ran it. `src/mock.js` is 1.48 MB and every self-check passes. Two runs give byte-identical output. A node check also runs the JS `TutorCalc` against the generated data and gets the same rows. That covers Elo replay for all 6 students, all 15 approved lists plus the HS-02 23/10 list, the audits of every report sentence, and the data restored at load.

**Files**
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/mock/gen_mock.py`: the generator. Python stdlib only, seed 2026. It ends with assert self-checks and the node check (skipped if node is missing).
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/mock/tutor_calc.js`: `window.TutorCalc` plus a small step that rebuilds derived fields at load. The generator appends it to `mock.js`.
- `/private/tmp/claude-501/-Users-dphong2005-Desktop-PROJECT-III/0a49ed08-8508-4162-b08f-f22b59420d76/scratchpad/proto/src/mock.js`: the output.

**Top-level keys of `window.MOCK`:** `['meta', 'settings', 'db', 'checkpoints', 'files', 'ui']`
**`window.TutorCalc`:** `elo, xFor, replay, deltaVsPrevious, passRate, audit, selectRecommendations, largestRemainder, currentMistakes`

**Counts**

| collection | rows |
|---|---|
| kc / kc_prereq / error_code | 74 / 74 / 18 (13 with an example) |
| problem / problem_kc / rubric / problem_pair | 180 / 416 / 178 / 798 |
| student / session / attempt | 6 / 41 (35 committed + 6 open) / 123 |
| mistake | 158: 104 confirmed · 22 edited · 25 rejected · 7 added |
| skill_event / skill_state / misconception_log | 293 / 137 / 89 |
| recommendation / report | 98 (15 lists) / 4 |
| checkpoints.threads | 82: 11 open (9 awaiting, 1 locked; 1 failed; 1 running) + 71 committed |
| files: llm_log / inbox / out / backups / bank | 2,920 / 4 / 19 / 5 / 10 |
| ui: activity / demo_runs | 12 / 6 |

Estimated LLM cost: about $14.7 in September and $14.7 in October against the $30 budget, plus $29 for the August bank setup.

**Contract §8.5:** `selectRecommendations(db, settings, 2, '2026-10-23')` returns exactly r1–r6 in contract order. The three excluded examples are present: 9DS-PT2-002 done 24/09, 9DS-PT2-019 has no rubric, 9DS-HSB2-007 has no approved δ.

**Contract deviations (and why)**
1. **Output path:** I wrote `src/mock.js` as the task said; contract §1 says `proto/mock.js`. `build.py` reads `src/`, so the build works.
2. **Fields rebuilt at load:** to stay under the 1.5 MB target, some fields are stored compactly in the JSON. Code at the end of `mock.js` restores them before any tab runs, so tabs see the contract shapes; only someone reading the raw JSON sees the compact forms. Affected:
   - `problem.solution_steps` and the G2 thread's problem steps
   - attempt solution text and step positions
   - transcripts of committed sessions
   - `problem_pair`, `skill_event` and `llm_log` (stored as columns)
   - `llm_json` for accepted mistakes
3. **`deltaVsPrevious`** returns one object with `kcs` plus `repeat`, `new`, `gone`, `resolved`. The contract's "[...] + {...}" was ambiguous.
4. **`selectRecommendations` rules the contract left open:**
   - Each pick is a different KC, so the "≥ 3 KCs" rule always holds and the swap step never runs.
   - A review pick is the easiest eligible problem for that KC. The contract doesn't say how to choose within a KC; this choice is needed to reproduce §8.5.
   - It also returns `counts` and `kc_mix`. Its `kc_selection` has no reason text; the G4 thread does.
5. **HS-02 is hand-planned:**
   - Its September problems and errors are fixed in the code.
   - In October it skips the six showcase problems: they get recommended but not done.
   - 7 δ noise values are hand-picked (all within ±0.15).
   - HS-02's October sessions have 3 attempts each.
   - These are the conditions under which the real select rule outputs §8.5.
6. **§8.3 order:** the contract lists "p4, p6, p5" but also says "rest by seq then step", which gives p4, p5, p6. I checked the groups and the seq/step order.
7. **Reports follow the contract, not the task text:** 2026-09 is approved for HS-01/03/05/06, and HS-02/HS-04 2026-09 are pending in the review queue. There are no 2026-10 reports. The pending G4 list is for 2026-10-23, not 10-24.
8. **Smaller choices:**
   - Teacher-added mistakes have `confidence` null.
   - G3 rankings are sorted easy to hard.
   - Committed history threads keep minimal state; the full data is in `db`.
   - Open sessions have `transcript_latex` null in `db`; the transcript is in the thread state.
   - `demo_runs` carry only new items; the shell already replaces attempts by seq and adds proposals by pid.

**Not done / risks**
- I did not open the prototype in a browser. The node check and `build.py` both run, but no tab code has read the data yet.
- Report sentences avoid digits outside facts (no student codes, no "tháng 9") because the audit counts every digit as a number. Three KC names that contain digits use digit-free display names in reports.
- Only problems 001–020 and complete blocks are read. Each run asserts that refs 001–020 are complete in every file, so it fails loudly if other agents' appends ever break that.

# Build/check overrides
- PROTO_DIST=<dir> (output dir for build.py, input for check.py), PROTO_TABS=id1,id2 (build only these tab files), PROTO_SHOTS=<dir> (screenshots).
