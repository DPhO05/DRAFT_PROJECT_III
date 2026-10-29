/* tabs/session.js — Buổi học (G1 session_graph, FR1–FR5, agents 01–05).
   Views: danh sách buổi · bước 1 nộp bài · stepper theo thread (đang chạy / lỗi / khoá / bước 3 xác nhận /
   bước 4 duyệt lỗi + Profiler / bước 5 kết quả) · chi tiết buổi đã ghi (chỉ đọc).
   Fields marked † are mock-only (contract.md). */
(function () {
  'use strict';
  if (!window.App) return;

  var C, ui, h, F;
  var UIS = {};          // per-thread view state (attempt tab, selected card, modes, opened-at) — UI only, not data
  var RUNS = {};         // thread_id → simulated run driven by this tab
  var RESUMING = {};     // thread_id → resumed through ctx.threads.resume (the shell drives that run)
  var MOUNT = null;      // what the current render shows, so run ticks can repaint it
  var LIST = { student: '', month: '', status: '' };
  var FORM = { student: '', held_on: '', file: '', dup: null };

  var STEPS = ['Nộp bài', 'Chạy G1', 'Xác nhận', 'Duyệt lỗi', 'Ghi DB & tiến bộ'];
  var CATS = [['computational', 'Tính toán'], ['conceptual', 'Khái niệm'], ['notational', 'Ký hiệu'], ['presentation', 'Trình bày'], ['other', 'Khác']];
  var VERDICT = { agree: ['04 đồng ý', 'ok'], disagree: ['04 không đồng ý', 'danger'], wrong_code: ['04: sai mã', 'warn'] };
  var GROUPS = ['04 phản đối / sai mã', 'Độ tin cậy thấp', 'Còn lại', 'Thầy/cô thêm'];
  var FLAG_LABEL = { low_match: 'khớp bài chưa chắc', mismatch: 'bản chép ≠ text layer', no_rubric: 'chưa có rubric', alt_method: 'cách giải khác' };
  var NODE_ORDER = ['g1.write_session', 'g1.01_ingest', 'g1.confirm_match', 'g1.02_grader', 'g1.03_diagnoser', 'g1.04_verifier', 'g1.review', 'g1.05_profiler', 'g1.commit'];

  /* ---------- small helpers ---------- */
  function arr(x) { return Array.isArray(x) ? x : []; }
  function db() { return C.data.db; }
  function today() { return (C.data.meta || {}).today || '2026-10-21'; }
  function pad2(n) { return String(n).padStart(2, '0'); }
  function nowISO() { var d = new Date(); return today() + 'T' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()) + 'Z'; }
  function dm(d) { var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(d || '')); return m ? m[2] + '/' + m[1] : String(d || ''); }
  function maxId(rows) { return arr(rows).reduce(function (m, r) { return Math.max(m, +r.id || 0); }, 0); }
  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }
  function mmss(sec) { sec = Math.max(0, Math.round(+sec || 0)); return pad2(Math.floor(sec / 60)) + ':' + pad2(sec % 60); }
  function lowConf() { return ((C.data.settings || {}).review || {}).low_confidence || 0.6; }
  function kParam() { return ((C.data.settings || {}).elo || {}).K || 0.3; }
  function needStreak() { return ((C.data.settings || {}).misconception || {}).resolve_streak || 2; }
  function reduced() { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } }
  function stepMs() { return reduced() ? 60 : 300; }
  function hasTex(s) { return /\$|\\\(|\\\[|\\begin\{/.test(String(s == null ? '' : s)); }
  // Math only inside .tex; plain Vietnamese text stays text (ui.latex would wrap it as math).
  function tx(s, block) {
    if (s == null || s === '') return h('span', { class: 'muted' }, '—');
    return hasTex(s) ? ui.latex(s, { block: !!block }) : h(block ? 'div' : 'span', { class: 'sx-plain' }, String(s));
  }
  // h()-style child lists for replaceChildren/append: arrays flattened, null/false dropped.
  function kidsOf(args) { return Array.prototype.slice.call(args, 1).flat(Infinity).filter(function (x) { return x != null && x !== false && x !== true; }); }
  function put(el) { el.replaceChildren.apply(el, kidsOf(arguments)); return el; }
  function add(el) { el.append.apply(el, kidsOf(arguments)); return el; }
  function plain(s, n) {
    var t = String(s || '').replace(/\\\[|\\\]|\\\(|\\\)|\$/g, '').replace(/\\(dfrac|frac)/g, '').replace(/\\[a-zA-Z]+/g, ' ').replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
    return n && t.length > n ? t.slice(0, n - 1) + '…' : t;
  }
  function student(id) { return C.lookup.student(id); }
  function scode(id) { var s = student(id); return s ? C.lookup.studentCode(s) : '—'; }
  function sname(id) { var s = student(id); return s ? s.name : ''; }
  function problem(id) { return id == null ? null : C.lookup.problem(id); }
  function refOf(id) { var p = problem(id); return p ? p.ref : '(chưa khớp)'; }
  function kc(id) { return id == null ? null : C.lookup.kc(id); }
  function kcName(id) { var k = kc(id); return k ? k.name : '—'; }
  function errName(code) { var e = C.lookup.errorCode(code); return e ? e.description : String(code || '—'); }
  function sessionOf(t) {
    if (!t) return null;
    return arr(db().session).find(function (s) { return s.id === t.session_id; }) || C.lookup.sessionByThread(t.thread_id);
  }
  function resolveStudent(v) {
    if (v == null || v === '') return null;
    return /^HS-/i.test(String(v)) ? C.lookup.studentByCode(String(v).toUpperCase()) : student(+v);
  }
  function kcsOfProblem(pid) {
    var rows = arr(db().problem_kc).filter(function (r) { return r.problem_id === pid; }).sort(function (a, b) { return a.step_idx - b.step_idx; });
    var out = []; rows.forEach(function (r) { if (out.indexOf(r.kc_id) < 0) out.push(r.kc_id); });
    return out;
  }
  function rubricOf(a) {
    if (a.rubric_id != null) { var r = arr(db().rubric).find(function (x) { return x.id === a.rubric_id; }); if (r) return r; }
    if (a.rubric_draft) return { version: 1, items_json: a.rubric_draft.items_json, max_score: a.rubric_draft.max_score, draft: true };
    return a.problem_id != null ? C.lookup.rubricFor(a.problem_id) : null;
  }
  function callsOf(tid) { return arr((C.data.files || {}).llm_log).filter(function (c) { return c.thread_id === tid; }); }
  function stageLabel(t) { var n = t.interrupted_at || t.current_node; return ((C.data.meta || {}).stage_labels || {})[n] || ui.nodeName(n); }
  function overlayOpen() { return !!document.querySelector('#modal-root .modal, #drawer-root .drawer'); }
  // Teacher reads the description / KC name; the raw code stays on hover.
  function codeChip(code) {
    var c = ui.chip(errName(code), 'neutral');
    c.classList.add('chip-wrap'); c.title = code || ''; return c;
  }
  function kcLabel(id) { var k = kc(id); return id == null ? 'không gắn' : k ? k.name : '#' + id; }
  function kcChip(id) {
    if (id == null) return ui.chip('không gắn KC — không ảnh hưởng Elo', 'neutral');
    var k = kc(id), c = ui.chip(kcLabel(id), 'info');
    c.classList.add('chip-wrap'); if (k) c.title = k.code; return c;
  }
  function agentBadge(id) { return h('span', { class: 'gn-agent', style: '--ac: var(--a' + id + ')' }, id); }
  function section(title, o) {
    o = o || {};
    var kids = Array.prototype.slice.call(arguments, 2);
    return h('section', { class: 'section ' + (o.cls || ''), id: o.id || null },
      h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), o.annot ? ui.annot(o.annot) : null, o.extra || null), o.right || null),
      kids);
  }
  function scrollFlash(el) {
    if (!el) return;
    try { el.scrollIntoView({ block: 'center', behavior: reduced() ? 'auto' : 'smooth' }); } catch (e) { el.scrollIntoView(); }
    el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
  }
  function recentMistakeIds(sid) {
    var d = db(), sess = {}, att = {};
    d.session.forEach(function (s) { if (s.student_id === sid && s.status === 'committed') sess[s.id] = s; });
    d.attempt.forEach(function (a) { if (sess[a.session_id]) att[a.id] = a; });
    return C.calc.currentMistakes(d).filter(function (m) { return att[m.attempt_id]; })
      .sort(function (a, b) { return (a.reviewed_at < b.reviewed_at ? 1 : a.reviewed_at > b.reviewed_at ? -1 : 0) || b.id - a.id; })
      .slice(0, 5).map(function (m) { return m.id; });
  }
  function lastCommittedDay(sid) {
    return arr(db().session).reduce(function (m, x) { return x.student_id === sid && x.status === 'committed' && x.held_on > m ? x.held_on : m; }, '');
  }
  // Shell locks only behind earlier awaiting threads; an earlier failed/running G1 of the same student blocks too (sơ đồ 11: duyệt theo thứ tự ngày học).
  function blockerOf(t) {
    if (!t || t.graph !== 'G1' || t.status !== 'awaiting_review') return null;
    if (t.locked) return C.lookup.thread(t.blocker) || null;
    var ho = C.queue.heldOn(t);
    return arr((C.data.checkpoints || {}).threads).filter(function (o) {
      return o !== t && o.graph === 'G1' && o.student_id === t.student_id && (o.status === 'failed' || o.status === 'running') && C.queue.heldOn(o) < ho;
    }).sort(function (a, b) { return C.queue.heldOn(a) < C.queue.heldOn(b) ? -1 : 1; })[0] || null;
  }
  function replaceStudentRows(rows, sid, fresh) {
    for (var i = rows.length - 1; i >= 0; i--) if (rows[i].student_id === sid) rows.splice(i, 1);
    fresh.forEach(function (r) { rows.push(Object.assign({}, r)); });
  }

  /* ---------- stepper + strip ---------- */
  function skip3(t) {
    return !arr(t.checkpoints).some(function (c) { return c.node === 'g1.confirm_match'; }) && (t.interrupted_at || t.current_node) !== 'g1.confirm_match';
  }
  function stepper(cur, o) {
    o = o || {};
    return h('ol', { class: 'sx-stepper', 'aria-label': 'Các bước G1' }, STEPS.map(function (label, i) {
      var n = i + 1, skip = n === 3 && o.skip3 && cur > 3;
      var cls = (n < cur || o.allDone) ? (skip ? 'is-skip' : 'is-done') : n === cur ? (o.failed ? 'is-fail' : 'is-cur') : '';
      var mark = (n < cur || o.allDone) && !skip ? '✓' : o.failed && n === cur ? '✕' : String(n);
      return h('li', { class: cls, 'aria-current': n === cur && !o.allDone ? 'step' : null },
        h('span', { class: 'sx-num', 'aria-hidden': 'true' }, mark),
        h('span', null, label, n === 3 ? h('small', null, skip ? ' (bỏ qua — không có cờ)' : ' (chỉ khi có cờ)') : null));
    }));
  }
  function laneOfError(err) { var m = /lane (\d+)/.exec(String(err || '')); return m ? +m[1] : null; }
  function strip(t, o) {
    o = o || {};
    var cps = arr(t.checkpoints), atts = arr(t.state && t.state.attempts);
    var seqs = atts.length ? atts.map(function (a) { return a.seq; }) : [];
    cps.forEach(function (c) { if (c.lane != null && seqs.indexOf(c.lane) < 0) seqs.push(c.lane); });
    seqs.sort(function (a, b) { return a - b; });
    var failLane = t.status === 'failed' ? laneOfError(t.error) : null;
    var lanes = seqs.map(function (seq) {
      var a = atts.find(function (x) { return x.seq === seq; });
      return {
        seq: seq, label: 'Bài ' + seq + (a && a.problem_id != null ? ' · ' + refOf(a.problem_id) : ''),
        done: cps.filter(function (c) { return c.lane === seq; }).map(function (c) { return c.node; }).concat(o.laneDone || []),
        failed: failLane === seq ? t.current_node : null
      };
    });
    var done = cps.filter(function (c) { return c.lane == null; }).map(function (c) { return c.node; }).concat(o.done || []);
    if (cps.some(function (c) { return c.lane != null; })) done.push('g1.confirm_match');   // lanes started = stop 1 passed (or had no flags)
    var current = o.current !== undefined ? o.current : t.status === 'failed' ? null : (t.interrupted_at || t.current_node);
    var el = ui.graphStrip('G1', { current: current, done: done, lanes: lanes.length ? lanes : undefined, compact: !!o.compact,
      failed: t.status === 'failed' && failLane == null ? t.current_node : undefined });
    cps.forEach(function (c) {
      if (!c.ms && !c.tokens_in && !c.tokens_out) return;
      var scope = c.lane != null ? el.querySelector('[data-lane="' + c.lane + '"]') : el.querySelector('.strip-flow');
      var n = scope && Array.prototype.find.call(scope.querySelectorAll('[data-node="' + c.node + '"]'), function (x) { return c.lane != null || !x.closest('.strip-lanes'); });
      var m = n && n.querySelector('.gn-meta');
      if (m) m.textContent = F.ms(c.ms) + ((c.tokens_in || c.tokens_out) ? ' · ' + F.int((c.tokens_in || 0) + (c.tokens_out || 0)) + ' tok vào+ra' : '');
    });
    return el;
  }
  function runLog(t) {
    var rows = arr(t.checkpoints).slice();
    return ui.table({
      columns: [
        { label: 'Node', render: function (c) { return ui.nodeName(c.node); } },
        { label: 'Làn', align: 'right', render: function (c) { return c.lane != null ? String(c.lane) : '—'; } },
        { label: 'Lúc', render: function (c) { return h('span', { class: 'mono small' }, String(c.at || '').slice(11, 19)); } },
        { label: 'Thời gian', align: 'right', render: function (c) { return c.ms ? F.ms(c.ms) : '—'; } },
        { label: 'Token vào / ra', align: 'right', render: function (c) { return (c.tokens_in || c.tokens_out) ? F.int(c.tokens_in) + ' / ' + F.int(c.tokens_out) : '—'; } }
      ],
      rows: rows, empty: 'Chưa có checkpoint nào.'
    });
  }

  /* ---------- transcript modal ---------- */
  function splitProblems(text) {
    var out = [], re = /\\begin\{problem\}(?:\[([^\]]*)\])?\s*([\s\S]*?)\\end\{problem\}/g, m;
    while ((m = re.exec(text))) out.push({ ref: m[1] || null, body: m[2].trim() });
    return out.length ? out : [{ ref: null, body: String(text || '').replace(/^%.*$/mg, '').trim() }];
  }
  function markDiff(a, b) {
    var i = 0, j = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i++;
    while (j < a.length - i && j < b.length - i && a[a.length - 1 - j] === b[b.length - 1 - j]) j++;
    var one = function (s) { return h('span', { class: 'sx-src-code' }, s.slice(0, i), h('mark', { class: 'sx-mark' }, s.slice(i, s.length - j) || '∅'), s.slice(s.length - j)); };
    return { a: one(a), b: one(b), da: a.slice(i, a.length - j), db: b.slice(i, b.length - j) };
  }
  function mismatchBox(f) {
    var d = markDiff(String(f.transcript || ''), String(f.text_layer || ''));
    var sign = function (s) { return s.replace(/-/g, '−'); };
    return h('div', { class: 'stack sx-mismatch' },
      h('div', { class: 'sx-diff' },
        h('div', { class: 'sx-diff-box' }, h('div', { class: 'small' }, h('b', null, 'Bản chép (01)'), ' ', ui.prov('llm', '01')), d.a, tx(f.transcript, true)),
        h('div', { class: 'sx-diff-box' }, h('div', { class: 'small' }, h('b', null, 'Text layer (PDF gốc)'), ' ', ui.prov('code', 'pdftext')), d.b, tx(f.text_layer, true))),
      h('p', { class: 'small' }, 'Khác nhau ở bước ' + f.step_idx + ': “' + sign(d.da) + '” (bản chép) ↔ “' + sign(d.db) + '” (text layer).'));
  }
  function openTranscript(text, t) {
    var flags = [];
    arr(t && t.state && t.state.attempts).forEach(function (a) { arr(a.flags_json).forEach(function (f) { if (f.type === 'mismatch') flags.push({ seq: a.seq, f: f }); }); });
    var probs = splitProblems(text), src = false, isPdf = /^%\s*01 Ingest chép từ PDF/.test(String(text));
    C.modal({
      title: 'Bản chép LaTeX' + (t ? ' · ' + t.thread_id : ''), wide: true,
      body: function (el) {
        var box = h('div', { class: 'stack sx-tr' });
        var draw = function () {
          put(box, src ? [h('pre', { class: 'code' }, String(text))] : probs.map(function (p, i) {
            var mm = flags.filter(function (x) { return x.seq === i + 1; });
            return h('div', { class: 'card' },
              h('div', { class: 'row' }, h('b', null, 'Bài ' + (i + 1)), p.ref ? h('span', { class: 'mono small' }, '[' + p.ref + ']') : ui.chip('không có id — 01 so đề với ngân hàng', 'warn')),
              tx(p.body, true),
              mm.map(function (x) { return h('div', { class: 'callout callout-warn' }, h('strong', null, 'Chỗ khác text layer (bước ' + x.f.step_idx + ')'), mismatchBox(x.f)); }));
          }));
          C.tex(box);
        };
        el.append(
          h('p', { class: 'small muted' }, isPdf ? '01 Ingest gửi PDF cho Claude chép ra LaTeX, rồi code so với text layer của PDF. Chỗ khác nhau được tô.' : 'File .tex gốc; 01 cắt theo \\begin{problem}[id] và tách bước theo dòng trống.', ' ', ui.store('checkpoint'), ' session.transcript_latex chỉ ghi ở ②.'),
          ui.button('Xem mã nguồn .tex', function (ev, b) { src = !src; b.textContent = src ? 'Xem dạng công thức' : 'Xem mã nguồn .tex'; draw(); }, { kind: 'secondary', size: 'sm' }),
          box);
        draw();
      },
      actions: [{ label: 'Đóng' }]
    });
  }
  function transcriptBtn(t, s) {
    var text = (t && t.state && t.state.transcript_latex) || (s && s.transcript_latex);
    return ui.button('Xem bản chép LaTeX', function () { openTranscript(text, t); }, { kind: 'secondary', disabledReason: text ? null : '01 Ingest chưa chép xong' });
  }

  /* ---------- run engine (simulated G1 run, data-level; the view only repaints) ---------- */
  function sortSteps(steps) {
    return steps.slice().sort(function (a, b) {
      var la = a.lane != null, lb = b.lane != null;
      if (la !== lb) return la ? 1 : -1;
      return (NODE_ORDER.indexOf(a.node) - NODE_ORDER.indexOf(b.node)) || ((a.lane || 0) - (b.lane || 0));
    });
  }
  function patchCalls(calls, t) {
    var code = scode(t.student_id);
    return arr(calls).map(function (c) { return Object.assign({}, c, { thread_id: t.thread_id, student_code: code }); });
  }
  // Final attempts/proposals after a run, with the teacher's stop-1 choices re-applied.
  function mergedResult(t, run) {
    var st = t.state, conf = st.confirm || {};
    var atts = arr(st.attempts).slice();
    arr(run.attempts).forEach(function (ra) {
      var i = atts.findIndex(function (a) { return a.seq === ra.seq; }), prev = i >= 0 ? atts[i] : null, a = clone(ra);
      if (prev) {
        if (prev.match && prev.match.method === 'llm') a.match = prev.match;
        var pf = arr(prev.flags_json).filter(function (f) { return f.resolved && f.type !== 'alt_method'; });
        a.flags_json = pf.concat(arr(a.flags_json).filter(function (f) { return !pf.some(function (x) { return x.type === f.type; }); }));
      }
      var c = conf[a.seq] || {};
      if (c.match) { a.problem_id = c.match; var r = C.lookup.rubricFor(c.match); a.rubric_id = r ? r.id : null; }
      if (c.rubric) { a.rubric_draft = { items_json: clone(c.rubric.items_json), max_score: c.rubric.max_score }; a.rubric_id = null; }
      if (c.mismatch === 'transcript') keepTranscript(a);
      if (i >= 0) atts[i] = a; else atts.push(a);
    });
    var props = arr(st.proposals).slice();
    arr(run.proposals).forEach(function (p) { if (!props.some(function (x) { return x.pid === p.pid; })) props.push(clone(p)); });
    atts.forEach(function (a) {
      if ((conf[a.seq] || {}).mismatch !== 'transcript') return;
      var f = arr(a.flags_json).find(function (x) { return x.type === 'mismatch'; });
      // Teacher kept 01's copy: the "error" was 01's slip, so 03's copy_error on that step goes away.
      if (f) props = props.filter(function (p) { return !(p.attempt_seq === a.seq && p.step_idx === f.step_idx && p.code === 'computational.copy_error'); });
    });
    return { attempts: atts.sort(function (a, b) { return a.seq - b.seq; }), proposals: props };
  }
  function keepTranscript(a) {
    var f = arr(a.flags_json).find(function (x) { return x.type === 'mismatch'; });
    if (!f || !f.text_layer) return;
    arr(a.steps_json).forEach(function (s) { if (s.idx === f.step_idx) s.latex = String(s.latex).split(f.text_layer).join(f.transcript); });
    var rub = rubricOf(a), pts = function (id) { var it = rub && arr(rub.items_json).find(function (x) { return x.item_id === id; }); return it ? +it.points || 0 : 1; };
    arr(a.grade_json).forEach(function (g) {
      if (String(g.evidence_latex).indexOf(f.text_layer) >= 0) { g.passed = true; g.evidence_latex = String(g.evidence_latex).split(f.text_layer).join(f.transcript); }
    });
    if (a.grade_json) a.score = a.grade_json.filter(function (g) { return g.passed; }).reduce(function (s, g) { return s + pts(g.item_id); }, 0);
  }
  function buildTranscript(t) {
    return arr(t.state.attempts).map(function (a) {
      return '\\begin{problem}' + (a.problem_id != null ? '[' + refOf(a.problem_id) + ']' : '') + '\n' + arr(a.steps_json).map(function (s) { return s.latex; }).join('\n\n') + '\n\\end{problem}';
    }).join('\n\n');
  }
  function startRun(t) {
    if (RUNS[t.thread_id]) return RUNS[t.thread_id];
    var run = ((C.data.ui || {}).demo_runs || {})[t.demo_run];
    if (!run || t.status !== 'running') return null;
    var have = {}; arr(t.checkpoints).forEach(function (c) { have[c.node + '|' + (c.lane == null ? '' : c.lane)] = 1; });
    var R = { t: t, run: run, steps: sortSteps(arr(run.node_timings).filter(function (n) { return !have[n.node + '|' + (n.lane == null ? '' : n.lane)]; })), i: 0, timer: null };
    RUNS[t.thread_id] = R;
    var tick = function () {
      if (t.status !== 'running' || RUNS[t.thread_id] !== R) { if (RUNS[t.thread_id] === R) delete RUNS[t.thread_id]; return; }
      if (R.i >= R.steps.length) { finishRun(R); return; }
      runStep(R, R.steps[R.i++]);
      paint(t);
      R.timer = setTimeout(tick, stepMs());
    };
    R.timer = setTimeout(tick, stepMs());
    return R;
  }
  function runStep(R, s) {
    var t = R.t;
    t.checkpoints = arr(t.checkpoints);
    t.checkpoints.push({ node: s.node, lane: s.lane, at: nowISO(), ms: s.ms, tokens_in: s.tokens_in, tokens_out: s.tokens_out });
    t.current_node = s.node;
    if (s.node === 'g1.01_ingest' && !arr(t.state.attempts).length) {
      t.state.attempts = clone(arr(R.run.attempts));
      t.state.transcript_latex = buildTranscript(t);
    }
  }
  function finishRun(R) {
    var t = R.t, st = t.state, s = sessionOf(t);
    delete RUNS[t.thread_id];
    var res = mergedResult(t, R.run);
    st.attempts = res.attempts; st.proposals = res.proposals;
    if (!st.transcript_latex) st.transcript_latex = buildTranscript(t);
    var f = C.data.files; f.llm_log = arr(f.llm_log); Array.prototype.push.apply(f.llm_log, patchCalls(R.run.llm_calls, t));
    t.checkpoints.push({ node: 'g1.review', at: nowISO(), ms: 0, tokens_in: 0, tokens_out: 0 });
    t.status = 'awaiting_review'; t.current_node = 'g1.review'; t.interrupted_at = 'g1.review';
    if (s) s.status = 'awaiting_review';
    C.refresh();
    C.toast('Sẵn sàng duyệt: ' + st.attempts.length + ' bài, ' + st.proposals.length + ' lỗi đề xuất', { kind: 'ok', title: t.subject + ' · DỪNG' });
    var here = MOUNT && MOUNT.tid === t.thread_id && document.querySelector('#view').dataset.tab === 'session';
    if (here && !overlayOpen()) C.nav('session', { thread: t.thread_id, step: 4 });
    else if (here && MOUNT.onDone) MOUNT.onDone();
  }
  function paint(t) {
    if (!MOUNT || MOUNT.tid !== t.thread_id || !MOUNT.paint) return;
    try { MOUNT.paint(); } catch (e) { console.error('[session paint]', e); }
  }
  function simulateFail(t) {
    var R = RUNS[t.thread_id];
    if (!R || t.status !== 'running') { C.toast('Chỉ giả lập được khi graph đang chạy.', { kind: 'info' }); return; }
    clearTimeout(R.timer); delete RUNS[t.thread_id];
    if (!arr(t.state.attempts).length) {
      var ing = arr(R.run.node_timings).find(function (n) { return n.node === 'g1.01_ingest'; });
      if (ing) runStep(R, ing); else { t.state.attempts = clone(arr(R.run.attempts)); t.state.transcript_latex = buildTranscript(t); }
    }
    var n = arr(t.state.attempts).length, lane = Math.min(3, n) || 1;
    var a = arr(t.state.attempts).find(function (x) { return x.seq === lane; });
    // The failing lane must have reached 03: finish its 02 (and anything before the lanes) first.
    R.steps.slice(R.i).forEach(function (x) {
      if (arr(t.checkpoints).some(function (c) { return c.node === x.node && c.lane === x.lane; })) return;
      if ((x.lane == null && NODE_ORDER.indexOf(x.node) < NODE_ORDER.indexOf('g1.02_grader')) || (x.lane === lane && x.node === 'g1.02_grader')) runStep(R, x);
    });
    t.checkpoints = arr(t.checkpoints).filter(function (c) { return !(c.lane === lane && (c.node === 'g1.03_diagnoser' || c.node === 'g1.04_verifier')); });
    var res = mergedResult(t, R.run);
    var left = arr(R.run.node_timings).filter(function (x) { return !t.checkpoints.some(function (c) { return c.node === x.node && c.lane === x.lane; }); });
    // Resume replays only what is left, from a derived demo run († mock-only key).
    var key = t.thread_id + ' · resume';
    C.data.ui.demo_runs[key] = { attempts: res.attempts, proposals: res.proposals, node_timings: left, llm_calls: patchCalls(R.run.llm_calls, t) };
    t.demo_run = key;
    C.threads.fail(t.thread_id, 'g1.03_diagnoser', 'APITimeoutError: hết thời gian chờ sau 3 lần thử (lane ' + lane + (a && a.problem_id != null ? ' · ' + refOf(a.problem_id) : '') + ')');
  }
  function resume(t) {
    RESUMING[t.thread_id] = true;
    C.threads.resume(t.thread_id);
  }

  /* ---------- proposals → cards ---------- */
  function cards(t) {
    var st = t.state, dec = st.decisions || (st.decisions = {}), lo = lowConf();
    var list = arr(st.proposals).map(function (p) {
      var v = p.verifier || {};
      return { pid: p.pid, p: p, d: dec[p.pid] || null, added: false, seq: p.attempt_seq,
        grp: v.verdict && v.verdict !== 'agree' ? 0 : (p.confidence != null && p.confidence < lo ? 1 : 2) };
    });
    list.sort(function (a, b) { return (a.grp - b.grp) || (a.p.attempt_seq - b.p.attempt_seq) || (a.p.step_idx - b.p.step_idx) || (a.pid < b.pid ? -1 : 1); });
    Object.keys(dec).forEach(function (k) { var d = dec[k]; if (d && d.action === 'add') list.push({ pid: k, p: null, d: d, added: true, seq: d.attempt_seq, grp: 3 }); });
    return list;
  }
  function eff(c) {
    if (c.added) return c.d;
    if (c.d && c.d.action === 'edit') {
      var o = Object.assign({}, c.p);
      ['code', 'kc_id', 'step_idx', 'description', 'evidence_latex'].forEach(function (k) { if (c.d[k] !== undefined) o[k] = c.d[k]; });
      return o;
    }
    return c.p;
  }
  function llmJson(p) { return { step_idx: p.step_idx, code: p.code, kc_id: p.kc_id, description: p.description, evidence_latex: p.evidence_latex, confidence: p.confidence }; }

  /* ---------- Profiler (05): code Elo on a virtual commit, LLM knowledge_state ---------- */
  function simulate(t) {
    var d = db(), st = t.state, s = sessionOf(t), now = nowISO(), conf = st.confirm || {};
    var aId = maxId(d.attempt), mId = maxId(d.mistake), rId = maxId(d.rubric);
    var rubs = [], atts = [], mists = [], bySeq = {};
    arr(st.attempts).slice().sort(function (a, b) { return a.seq - b.seq; }).forEach(function (a) {
      var rid = a.rubric_id, appr = (conf[a.seq] || {}).rubric;
      if (rid == null && (appr || a.rubric_draft)) {
        var ver = arr(d.rubric).filter(function (r) { return r.problem_id === a.problem_id; }).reduce(function (m, r) { return Math.max(m, r.version); }, 0) + 1;
        rid = ++rId;
        rubs.push({ id: rid, problem_id: a.problem_id, version: ver, items_json: clone((appr || a.rubric_draft).items_json),
          max_score: (appr || a.rubric_draft).max_score, approved_at: (appr && appr.approved_at) || now });
      }
      var steps = clone(arr(a.steps_json));
      var row = { id: ++aId, session_id: s.id, seq: a.seq, problem_id: a.problem_id, rubric_id: rid,
        solution_latex: steps.map(function (x) { return x.latex; }).join('\n\n'), steps_json: steps, flags_json: clone(arr(a.flags_json)),
        grade_json: clone(arr(a.grade_json)), score: a.score, max_score: a.max_score, supersedes_id: null, created_at: now };
      atts.push(row); bySeq[a.seq] = row;
    });
    cards(t).forEach(function (c) {
      if (!c.d || !bySeq[c.seq]) return;
      var base = { id: ++mId, attempt_id: bySeq[c.seq].id, teacher_note: c.d.teacher_note || null, supersedes_id: null, reviewed_at: now, created_at: now };
      if (c.added) {
        mists.push(Object.assign(base, { step_idx: c.d.step_idx, code: c.d.code, kc_id: c.d.kc_id, description: c.d.description, evidence_latex: c.d.evidence_latex,
          confidence: null, verifier_verdict: null, verifier_reason: null, status: 'added', llm_json: null }));
        return;
      }
      var e = eff(c), v = c.p.verifier || {};
      mists.push(Object.assign(base, { step_idx: e.step_idx, code: e.code, kc_id: e.kc_id, description: e.description, evidence_latex: e.evidence_latex,
        confidence: c.p.confidence, verifier_verdict: v.verdict || null, verifier_reason: v.reason || null,
        status: { accept: 'confirmed', edit: 'edited', reject: 'rejected' }[c.d.action], llm_json: llmJson(c.p) }));
    });
    var vs = Object.assign({}, s, { status: 'committed', committed_at: now });
    var vdb = Object.assign({}, d, { session: d.session.map(function (x) { return x === s ? vs : x; }), attempt: d.attempt.concat(atts), mistake: d.mistake.concat(mists), rubric: d.rubric.concat(rubs) });
    var rep = C.calc.replay(vdb, s.student_id);
    var ids = {}; atts.forEach(function (a) { ids[a.id] = a.seq; });
    return { now: now, atts: atts, mists: mists, rubs: rubs, rep: rep, dv: C.calc.deltaVsPrevious(vdb, s.id),
      events: rep.skill_event.filter(function (e) { return ids[e.attempt_id] != null; }), seqOf: ids, s: s };
  }
  function misDiff(rows, sid) {
    var key = function (m) { return m.code + '|' + m.kc_id; };
    var old = {}; arr(db().misconception_log).forEach(function (m) { if (m.student_id === sid) old[key(m)] = m; });
    var out = [];
    rows.forEach(function (m) {
      var o = old[key(m)];
      if (!o) out.push({ kind: 'mới', m: m });
      else if (m.count > o.count) out.push({ kind: o.resolved_at ? 'tái xuất hiện' : 'lỗi lặp', m: m, o: o });
      else if (o.resolved_at == null && m.resolved_at) out.push({ kind: 'đã hết', m: m, o: o });
    });
    return out;
  }
  function stuckNote() { return [ui.chip('Chưa chốt', 'warn'), ' Buổi failed (lỗi, hoặc thread đã huỷ) vẫn giữ dòng session do ① ghi trong tutor.db, nên luật chặn file trùng không cho nộp lại file này. Nếu không chạy lại được: xoá buổi, hay cho nộp lại file?']; }
  function vnNum(x) { return (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(2); }
  function knowledgeText(sim) {
    var s = sim.s, p = 0, n = 0;
    sim.atts.forEach(function (a) { arr(a.grade_json).forEach(function (g) { n++; if (g.passed) p++; }); });
    var kcs = arr(sim.dv && sim.dv.kcs).slice().sort(function (a, b) { return b.d - a.d; });
    var txt = 'Buổi ' + F.date(s.held_on) + ': ' + sim.atts.length + ' bài, đạt ' + p + '/' + n + ' mục rubric.';
    if (kcs.length && kcs[0].d > 0) txt += ' θ tăng rõ nhất ở “' + kcName(kcs[0].kc_id) + '” (' + vnNum(kcs[0].d) + ').';
    var lo = kcs[kcs.length - 1];
    if (lo && lo.d < 0) txt += ' θ giảm ở “' + kcName(lo.kc_id) + '” (' + vnNum(lo.d) + '): cần ôn lại.';
    // lỗi lặp = cặp (mã lỗi, KC) count ≥ 2, chưa hết; same sentences as knowledge_state in mock/gen_mock.py
    var log = arr(sim.rep.misconception_log);
    var rec = log.filter(function (m) { return m.count >= 2 && !m.resolved_at; }).sort(function (a, b) { return b.count - a.count; })[0];
    if (rec) txt += ' Lỗi lặp “' + errName(rec.code).toLowerCase() + '” ở “' + kcName(rec.kc_id) + '” (' + rec.count + ' lần), chưa hết.';
    var res = log.find(function (m) { return m.resolved_at === s.held_on; });
    if (res) txt += ' Đã hết lỗi “' + errName(res.code).toLowerCase() + '” ở “' + kcName(res.kc_id) + '” sau ' + needStreak() + ' lần làm đúng liên tiếp.';
    if (!(lo && lo.d < 0) && !rec) txt += ' Không có kỹ năng nào giảm; có thể tăng độ khó buổi sau.';
    return txt;
  }
  function eloWhy(e, ref) {
    var K = kParam();
    return h('div', { class: 'stack', style: 'gap:6px' },
      ui.kv([['θ trước', F.signed(e.theta_before)], ['δ (' + ref + ')', F.signed(e.delta)], ['X', e.outcome + (e.outcome ? ' — không có lỗi gắn KC này' : ' — có lỗi đã duyệt gắn KC này')],
        ['P', '1 / (1 + e^−(θ − δ)) = 1 / (1 + e^−(' + F.signed(e.theta_before) + ' − ' + F.signed(e.delta) + ')) = ' + F.num(e.p_expected)],
        ['θ sau', 'θ + K·(X − P) = ' + F.signed(e.theta_before) + ' + ' + K + '·(' + e.outcome + ' − ' + F.num(e.p_expected) + ') = ' + F.signed(e.theta_after)]]),
      h('p', { class: 'small muted' }, 'elo.py · K = ' + K + ' cố định (spec §8) · δ không cập nhật · lưu 4 chữ số.'), ui.prov('code'));
  }
  function deltaRows(kcs) {
    var mx = Math.max(0.3, Math.max.apply(null, arr(kcs).map(function (k) { return Math.abs(k.d); }).concat([0])));
    if (!arr(kcs).length) return ui.empty('Buổi này không chạm KC nào (bài chưa gắn KC).');
    return h('div', { class: 'sx-dtheta' }, arr(kcs).map(function (k) {
      var x = kc(k.kc_id);
      return [h('div', { class: 'small' }, h('span', { class: 'mono' }, x ? x.code : '#' + k.kc_id), ' ', h('span', { class: 'muted' }, x ? x.name : '')),
        ui.bar(k.d, mx, { signed: true }),
        h('div', { class: 'num small nowrap' }, F.signed(k.theta_before, 3) + ' → ' + F.signed(k.theta_after, 3) + ' ', h('b', null, '(' + F.signed(k.d) + ')'), ' ',
          ui.why(function () { return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'Δθ = θ sau buổi − θ trước lần đầu gặp KC trong buổi = ' + F.signed(k.theta_after, 3) + ' − ' + F.signed(k.theta_before, 3) + ' = ' + F.signed(k.d) + '.'), h('p', { class: 'small muted' }, 'deltaVsPrevious(): code tính từ skill_event, không phải LLM.'), ui.prov('code')); }))];
    }));
  }
  function codeChips(dv) {
    if (!dv) return null;
    var row = h('div', { class: 'row sx-codechips' });
    var add = function (pre, c, kind) { var ch = ui.chip(pre + ' · ' + errName(c), kind); ch.title = c; row.append(ch); };
    arr(dv.repeat).forEach(function (c) { add('có ở cả 2 buổi', c, 'warn'); });
    arr(dv.new).forEach(function (c) { add('mới', c, 'info'); });
    arr(dv.gone).forEach(function (c) { add('đã hết', c, 'ok'); });
    if (!row.childNodes.length) row.append(h('span', { class: 'muted small' }, 'Không có mã lỗi nào (cả buổi này và buổi trước).'));
    return row;
  }

  /* ---------- mistake form (E / N / sửa lỗi đã lưu) ---------- */
  function mistakeForm(o) {
    var codes = arr(db().error_code);
    var selCode = h('select', { 'aria-label': 'Mã lỗi' });
    CATS.forEach(function (c) {
      var g = h('optgroup', { label: c[1] + ' · ' + c[0] });
      codes.filter(function (e) { return e.category === c[0] && (e.active || e.code === o.init.code); }).forEach(function (e) {
        g.append(h('option', { value: e.code }, e.code + (e.active ? '' : ' (đã tắt)') + ' — ' + e.description));
      });
      if (g.children.length) selCode.append(g);
    });
    selCode.value = o.init.code || 'other.unclear';
    var kcs = kcsOfProblem(o.problem_id);
    var selKc = h('select', { 'aria-label': 'KC' }, h('option', { value: '' }, 'không gắn KC (không ảnh hưởng Elo)'),
      kcs.map(function (id) { var k = kc(id); return h('option', { value: String(id) }, (k ? k.code + ' · ' + k.name : '#' + id)); }));
    selKc.value = o.init.kc_id == null ? '' : String(o.init.kc_id);
    var selStep = h('select', { 'aria-label': 'Bước' }, arr(o.steps).map(function (s) { return h('option', { value: String(s.idx) }, 'Bước ' + s.idx + ': ' + plain(s.latex, 48)); }));
    selStep.value = String(o.init.step_idx || (o.steps[0] || {}).idx || 1);
    var desc = h('textarea', { rows: 3, 'aria-label': 'Mô tả', placeholder: 'Mô tả lỗi (có thể dùng $…$)' }); desc.value = o.init.description || '';
    var note = h('textarea', { rows: 2, 'aria-label': 'Ghi chú GV', placeholder: 'Ghi chú của thầy/cô (teacher_note)' }); note.value = o.init.teacher_note || '';
    var hint = h('span', { class: 'small muted' });
    var body = h('div', { class: 'stack' },
      o.lead ? h('p', { class: 'small muted' }, o.lead) : null,
      h('label', { class: 'field' }, h('span', null, 'Mã lỗi (chỉ mã đang bật, theo 5 nhóm)'), selCode),
      o.suggested ? h('div', { class: 'row' }, ui.button('Dùng mã 04 gợi ý: ' + o.suggested, function () { selCode.value = o.suggested; hint.textContent = 'Đã chọn mã 04 gợi ý ✓'; }, { kind: 'ghost', size: 'sm' }), hint) : null,
      h('label', { class: 'field' }, h('span', null, 'KC (chỉ KC của bài ' + refOf(o.problem_id) + ' trong problem_kc)'), selKc),
      o.noStep ? null : h('label', { class: 'field' }, h('span', null, 'Bước trong bài HS'), selStep),
      h('label', { class: 'field' }, h('span', null, 'Mô tả'), desc),
      h('label', { class: 'field' }, h('span', null, 'Ghi chú GV'), note));
    C.modal({
      title: o.title, wide: true, body: body,
      actions: [{ label: 'Huỷ' }, { label: o.saveLabel || 'Lưu', kind: 'primary', onClick: function (close) {
        if (!desc.value.trim()) { C.toast('Cần mô tả lỗi.', { kind: 'warn' }); desc.focus(); return; }
        var step = o.noStep ? o.init.step_idx : +selStep.value;
        var st = arr(o.steps).find(function (s) { return s.idx === step; });
        o.onSave({ code: selCode.value, kc_id: selKc.value === '' ? null : +selKc.value, step_idx: step, description: desc.value.trim(),
          teacher_note: note.value.trim() || null, evidence_latex: step === o.init.step_idx && o.init.evidence_latex ? o.init.evidence_latex : (st ? st.latex : o.init.evidence_latex) });
        close();
      } }]
    });
  }

  /* ---------- views ---------- */
  function notFound(root, msg) {
    add(root, ui.pageHead({ title: 'Buổi học' }), h('div', { class: 'callout callout-warn' }, h('strong', null, msg),
      h('div', null, ui.button('Về danh sách buổi', function () { C.nav('session'); }, { kind: 'secondary' }))));
  }
  function titleOf(day, sid) {   // keep "HS-05" from breaking at the hyphen
    return h('span', null, 'Buổi ' + F.date(day) + ' · ', h('span', { class: 'nowrap' }, scode(sid)), ' · ' + sname(sid));
  }
  function threadHead(t, s, eyebrow, actions, lead) {
    return ui.pageHead({
      eyebrow: eyebrow, title: titleOf(s ? s.held_on : C.queue.heldOn(t), t.student_id),
      lead: lead || null, annot: ['G1', 'cli:tutor review ' + t.thread_id],
      actions: arr(actions).concat([ui.button('Về danh sách buổi', function () { C.nav('session'); }, { kind: 'ghost' })])
    });
  }
  function srcLine(t, s) {
    var src = (t && t.state && t.state.source) || { path: s.source_path, kind: s.source_kind, sha256: s.source_sha256 };
    return h('div', { class: 'row sx-src' },
      h('span', { class: 'chip st-file mono' }, src.path), ui.chip(src.kind || '—', src.kind === 'pdf' ? 'warn' : 'neutral'),
      h('span', { class: 'mono small muted' }, 'sha256 ' + String(src.sha256 || '').slice(0, 8)),
      t ? h('span', { class: 'mono small muted' }, 'thread ' + t.thread_id) : null);
  }

  function route(root, p, cl) {
    if (p.session) {
      var s = arr(db().session).find(function (x) { return String(x.id) === String(p.session); });
      if (!s) return notFound(root, 'Không tìm thấy buổi #' + p.session + '.');
      if (s.status !== 'committed') { var t0 = C.lookup.thread(s.thread_id); if (t0) return viewThread(root, t0, p, cl); }
      return viewDetail(root, s, p);
    }
    if (p.thread) {
      var t = C.lookup.thread(p.thread);
      if (!t) {
        var s2 = C.lookup.sessionByThread(p.thread);
        if (s2) return viewDetail(root, s2, p);
        return notFound(root, 'Không tìm thấy thread ' + p.thread + ' (có thể đã huỷ hoặc đã dọn).');
      }
      return viewThread(root, t, p, cl);
    }
    if (String(p.step) === '1') return viewSubmit(root, p);
    return viewList(root, p);
  }
  function viewThread(root, t, p, cl) {
    if (t.graph !== 'G1') {
      add(root, ui.pageHead({ title: 'Buổi học' }), h('div', { class: 'callout callout-info' }, h('p', null, 'Thread ' + t.thread_id + ' thuộc ' + t.graph + ', không phải buổi học.'),
        h('div', null, ui.button('Mở đúng màn hình', function () { C.queue.open(t.thread_id); }, { kind: 'primary' }))));
      return;
    }
    var s = sessionOf(t);
    if (t.status !== 'running') delete RESUMING[t.thread_id];
    if (t.status === 'committed') return String(p.step) === '5' ? viewResult(root, t, s) : viewDetail(root, s, p);
    if (t.status === 'failed') return viewFailed(root, t, s);
    if (t.status === 'running') return viewRunning(root, t, s);
    C.queue.list();
    var blk = blockerOf(t);
    if (blk) return viewLocked(root, t, s, blk);
    if ((t.interrupted_at || t.current_node) === 'g1.confirm_match') return viewConfirm(root, t, s);
    return viewReview(root, t, s, p, cl);
  }

  /* ----- list ----- */
  function viewList(root, p) {
    if (p.student) { var ps = resolveStudent(p.student); if (ps) LIST.student = String(ps.id); }
    var d = db();
    var cur = {}; C.calc.currentMistakes(d).forEach(function (m) { cur[m.attempt_id] = (cur[m.attempt_id] || 0) + 1; });
    var attBy = {}; d.attempt.forEach(function (a) { (attBy[a.session_id] = attBy[a.session_id] || []).push(a); });
    C.queue.list();
    var rows = d.session.filter(function (s) {
      return (!LIST.student || String(s.student_id) === LIST.student) && (!LIST.month || String(s.held_on).slice(0, 7) === LIST.month) && (!LIST.status || s.status === LIST.status);
    }).sort(function (a, b) { return a.held_on < b.held_on ? 1 : a.held_on > b.held_on ? -1 : b.id - a.id; });
    var counts = {}; d.session.forEach(function (s) { counts[s.status] = (counts[s.status] || 0) + 1; });
    var sel = function (label, key, opts) {
      var el = h('select', { 'aria-label': label, onchange: function () { LIST[key] = el.value; C.rerender(); } }, opts.map(function (o) { return h('option', { value: o[0] }, o[1]); }));
      el.value = LIST[key]; return h('label', { class: 'field' }, h('span', null, label), el);
    };
    var filters = h('div', { class: 'row sx-filters' },
      sel('Học sinh', 'student', [['', 'Tất cả HS']].concat(arr(d.student).map(function (s) { return [String(s.id), C.lookup.studentCode(s) + ' · ' + s.name]; }))),
      sel('Tháng', 'month', [['', 'Tất cả tháng']].concat(arr(C.data.meta.months).map(function (m) { return [m, 'Tháng ' + F.month(m)]; }))),
      sel('Trạng thái', 'status', [['', 'Mọi trạng thái'], ['running', 'đang chạy'], ['awaiting_review', 'chờ duyệt'], ['failed', 'hỏng'], ['committed', 'đã ghi']]));
    var open = function (s) {
      if (s.status === 'committed') C.nav('session', { session: s.id });
      else if (C.lookup.thread(s.thread_id)) C.nav('session', { thread: s.thread_id });
      else C.nav('session', { session: s.id });
    };
    var tbl = ui.table({
      rows: rows, empty: 'Không có buổi nào khớp bộ lọc.',
      onRow: open,
      rowClass: function (s) { return s.status === 'committed' ? null : 'sx-row-open'; },
      columns: [
        { label: 'Ngày học', render: function (s) { return h('span', { class: 'num nowrap' }, F.date(s.held_on)); } },
        { label: 'Học sinh', render: function (s) { return h('span', { class: 'nowrap' }, h('b', { class: 'mono' }, scode(s.student_id)), ' ', h('span', { class: 'muted small' }, sname(s.student_id))); } },
        { label: 'Nguồn', render: function (s) { return h('span', { class: 'row nowrap', style: 'gap:6px' }, ui.chip(s.source_kind, s.source_kind === 'pdf' ? 'warn' : 'neutral'), h('span', { class: 'mono small' }, String(s.source_path).replace('data/inbox/', ''))); } },
        { label: 'Số bài', align: 'right', render: function (s) {
          if (s.status === 'committed') return String(arr(attBy[s.id]).length);
          var t = C.lookup.thread(s.thread_id), n = t ? arr(t.state && t.state.attempts).length : 0; return n ? h('span', { class: 'muted' }, String(n)) : '—';
        } },
        { label: 'Điểm', align: 'right', render: function (s) {
          if (s.status !== 'committed') return h('span', { class: 'muted small' }, 'chưa ghi');
          var as = arr(attBy[s.id]), sc = as.reduce(function (x, a) { return x + (+a.score || 0); }, 0), mx = as.reduce(function (x, a) { return x + (+a.max_score || 0); }, 0);
          return h('span', { class: 'num nowrap' }, sc + '/' + mx);
        } },
        { label: 'Lỗi đã duyệt', align: 'right', render: function (s) {
          if (s.status !== 'committed') return '—';
          return String(arr(attBy[s.id]).reduce(function (x, a) { return x + (cur[a.id] || 0); }, 0));
        } },
        { label: 'Trạng thái', render: function (s) {
          var t = C.lookup.thread(s.thread_id);
          return h('span', { class: 'row nowrap', style: 'gap:4px' }, ui.status(s.status), blockerOf(t) ? ui.status('locked') : null,
            t && t.status === 'awaiting_review' ? h('span', { class: 'small muted' }, stageLabel(t)) : null);
        } },
        { label: 'thread_id', render: function (s) { return h('span', { class: 'mono small muted nowrap' }, s.thread_id || '—'); } },
        { label: '', render: function (s) { return ui.button('Mở', function () { open(s); }, { size: 'sm', kind: s.status === 'committed' ? 'secondary' : 'primary' }); } }
      ]
    });
    tbl.classList.add('sx-sess-tbl');
    add(root, 
      ui.pageHead({
        lead: 'Sau mỗi buổi: nộp bài → G1 chạy 01 → 02 · 03 · 04 → thầy/cô duyệt từng lỗi → 1 transaction ghi tutor.db. Bảng dưới là bảng session.',
        annot: ['G1', 'table:session', 'cli:tutor ingest <hs> <file>'],
        actions: [ui.button('Nộp bài mới', function () { C.nav('session', { step: 1 }); }, { kind: 'primary', cli: 'tutor ingest <hs> <file>' }),
          ui.button('Mở Hộp duyệt', function () { C.nav('review'); }, { kind: 'secondary', cli: 'tutor review' })]
      }),
      section('Danh sách buổi', { annot: ['table:session', 'table:attempt', 'table:mistake'], right: h('span', { class: 'small muted' }, rows.length + '/' + d.session.length + ' buổi') },
        h('div', { class: 'row' }, ['running', 'awaiting_review', 'failed', 'committed'].map(function (k) { return h('span', { class: 'row', style: 'gap:4px' }, ui.status(k), h('b', { class: 'num small' }, String(counts[k] || 0))); })),
        filters,
        h('p', { class: 'small muted' }, 'Dòng session được ghi ngay khi bắt đầu chạy (① status running) — attempt, mistake chỉ ghi khi thầy/cô duyệt xong (②). ', ui.store('db'), ' “Lỗi đã duyệt” = mistake_current (không tính lỗi đã bỏ hoặc đã bị thay).'),
        tbl));
  }

  /* ----- step 1 ----- */
  function viewSubmit(root, p) {
    var inbox = arr((C.data.files || {}).inbox);
    if (p.student) { var ps = resolveStudent(p.student); if (ps && FORM.from !== p.student) { FORM.student = String(ps.id); FORM.from = p.student; } }
    if (!FORM.held_on) FORM.held_on = today();
    var sid = +FORM.student || null, file = inbox.find(function (f) { return f.path === FORM.file; }) || null;
    var code = sid ? scode(sid) : null;
    var stuSel = h('select', { 'aria-label': 'Học sinh', onchange: function () { FORM.student = stuSel.value; FORM.dup = null; C.rerender(); } },
      h('option', { value: '' }, 'Chọn học sinh…'),
      arr(db().student).filter(function (s) { return !s.archived_at; }).map(function (s) { return h('option', { value: String(s.id) }, C.lookup.studentCode(s) + ' · ' + s.name + ' · lớp ' + s.grade); }));
    stuSel.value = FORM.student;
    var date = h('input', { type: 'date', 'aria-label': 'Ngày học', onchange: function () { FORM.held_on = date.value || today(); C.rerender(); } });
    date.value = FORM.held_on;
    var files = inbox.length ? h('div', { class: 'sx-files' }, inbox.map(function (f) {
      var picked = f.path === FORM.file, name = f.path.split('/').pop();
      return h('div', { class: 'st-file sx-file-row' + (picked ? ' is-picked' : '') },
        h('span', { class: 'mono' }, name), ui.chip(f.kind, f.kind === 'pdf' ? 'warn' : 'neutral'),
        h('span', { class: 'mono small muted' }, 'sha256 ' + f.sha256.slice(0, 8)),
        h('span', { class: 'small muted' }, 'theo tên file: ' + scode(f.student_id) + ' · ' + F.date(f.held_on)),
        picked ? ui.chip('đã chọn', 'info') : ui.button('Chọn tệp', function () {
          FORM.file = f.path; FORM.dup = null;
          if (!FORM.student) FORM.student = String(f.student_id);
          if (f.held_on) FORM.held_on = f.held_on;
          C.rerender();
        }, { size: 'sm' }));
    })) : ui.empty('Không có file trong data/inbox');
    var lastDay = sid ? lastCommittedDay(sid) : '', back = !!lastDay && FORM.held_on < lastDay;
    var reason = !sid && !file ? 'chọn học sinh và tệp trước' : !sid ? 'chọn học sinh trước' : !file ? 'chọn tệp trong data/inbox trước'
      : back ? 'ngày học ' + dm(FORM.held_on) + ' trước buổi đã ghi ' + dm(lastDay) + ' của ' + code : null;
    var dup = FORM.dup ? arr(db().session).find(function (s) { return s.id === FORM.dup; }) : null;
    add(root, 
      ui.pageHead({ eyebrow: 'Buổi học · bước 1', title: 'Nộp bài', lead: 'Chọn học sinh và file bài làm vừa học. Bấm “Bắt đầu xử lý” = chạy lệnh tutor ingest: G1 ghi dòng session rồi cho 01–04 chạy, tới DỪNG thì chờ thầy/cô.',
        annot: ['agent:01', 'table:session', 'cli:tutor ingest <hs> <file>'], actions: [ui.button('Về danh sách buổi', function () { C.nav('session'); }, { kind: 'ghost' })] }),
      stepper(1),
      h('div', { class: 'grid cols-2 sx-submit' },
        section('1 · Nộp bài', { annot: ['agent:01', 'table:session'] },
          h('div', { class: 'grid cols-2' },
            h('label', { class: 'field' }, h('span', null, 'Học sinh'), stuSel,
              code ? h('span', { class: 'chip chip-privacy' }, 'API nhận: ' + code) : h('span', { class: 'small muted' }, 'Tên chỉ lưu trên máy; API chỉ nhận mã HS.')),
            h('label', { class: 'field' }, h('span', null, 'Ngày học (session.held_on)'), date)),
          h('div', { class: 'field' }, h('span', null, 'Tệp trong data/inbox/ ', ui.store('file')), files),
          file ? h('div', { class: 'stack sx-picked' },
            h('div', { class: 'row' }, h('span', { class: 'chip st-file mono' }, file.path.split('/').pop()), ui.chip(file.kind, file.kind === 'pdf' ? 'warn' : 'neutral'), h('span', { class: 'mono small' }, 'sha256 ' + file.sha256.slice(0, 8))),
            file.kind === 'pdf' ? h('div', { class: 'callout callout-info' }, h('p', null, '01 sẽ chép LaTeX từ PDF + kiểm tra với text layer.')) : null,
            sid && file.student_id !== sid ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Tên file ghi ' + scode(file.student_id) + ' nhưng đang chọn ' + code + '. Hệ thống không tự kiểm tên file — thầy/cô xem lại.')) : null,
            !file.demo_run ? h('p', { class: 'small muted' }, 'Bản nháp: chỉ hs02-2026-10-21.tex có lần chạy mẫu riêng; file khác dùng lại lần chạy mẫu đó.') : null) : null,
          back ? h('div', { class: 'callout callout-warn' }, h('strong', null, 'Ngày học trước buổi đã ghi gần nhất'),
            h('p', null, code + ' đã có buổi ' + dm(lastDay) + ' ghi vào tutor.db. Các buổi của 1 học sinh phải duyệt theo thứ tự ngày học vì Elo cập nhật tuần tự (sơ đồ 11), nên bản nháp chặn buổi ' + dm(FORM.held_on) + '.'),
            h('p', { class: 'small muted' }, 'Nộp bù buổi cũ hơn (chèn vào giữa lịch sử rồi tính lại Elo) là điểm chưa chốt.')) : null,
          dup ? h('div', { class: 'callout callout-crit' }, h('strong', null, 'Đã chặn: trùng sha256'),
            h('p', null, 'File này đã nộp cho ' + scode(dup.student_id) + ' ngày ' + dm(dup.held_on) + ' (buổi #' + dup.id + ', ' + dup.status + '). UNIQUE(student_id, source_sha256) không cho nộp lại.'),
            dup.status === 'failed' ? h('p', null, stuckNote()) : null,
            h('div', null, ui.button('Mở buổi đã nộp', function () { C.nav('session', dup.status === 'committed' ? { session: dup.id } : { thread: dup.thread_id }); }, { kind: 'secondary', size: 'sm' }))) : null,
          ui.button('Bắt đầu xử lý', startIngest, { kind: 'primary', disabledReason: reason, privacy: code || undefined,
            cli: 'tutor ingest ' + (code || '<hs>') + ' ' + (file ? file.path : '<file>') })),
        section('Bấm “Bắt đầu xử lý” thì sao?', { annot: ['G1', 'file:checkpoints.db'] },
          h('ol', { class: 'sx-howto' },
            h('li', null, '① Ghi ngay 1 dòng session (status running, thread_id) ', ui.store('db')),
            h('li', null, '01 Ingest chép LaTeX, cắt từng bài, khớp mã bài với ngân hàng'),
            h('li', null, 'Cờ (khớp chưa chắc, PDF khác text layer, chưa có rubric) → DỪNG ở bước 3'),
            h('li', null, 'Mỗi bài một làn: 02 chấm · 03 chẩn đoán · 04 phản biện, chạy song song'),
            h('li', null, 'DỪNG chờ duyệt: đề xuất nằm trong checkpoints.db ', ui.store('checkpoint'), ', chưa vào tutor.db')),
          ui.graphStrip('G1', { compact: true }))));
  }
  function startIngest() {
    var inbox = arr((C.data.files || {}).inbox), sid = +FORM.student, f = inbox.find(function (x) { return x.path === FORM.file; });
    if (!sid || !f) { C.toast('Chọn học sinh và tệp trước.', { kind: 'warn' }); return; }
    var d = db(), code = scode(sid), lastDay = lastCommittedDay(sid);
    if (lastDay && (FORM.held_on || today()) < lastDay) { C.toast(code + ' đã có buổi ' + dm(lastDay) + ' ghi vào tutor.db — không nộp buổi cũ hơn.', { kind: 'error' }); return; }
    var dup = d.session.find(function (s) { return s.student_id === sid && s.source_sha256 === f.sha256; });
    if (dup) {
      FORM.dup = dup.id;
      C.toast('File này đã nộp cho ' + code + ' ngày ' + dm(dup.held_on) + ' (trùng sha256)', { kind: 'error' });
      C.rerender();
      return;
    }
    var held = FORM.held_on || today(), base = 'g1-' + code.toLowerCase().replace('-', '') + '-' + held.replace(/-/g, ''), tid = base, k = 2;
    while (C.lookup.thread(tid) || d.session.some(function (s) { return s.thread_id === tid; })) tid = base + '-' + (k++);
    var now = nowISO();
    var sess = { id: maxId(d.session) + 1, student_id: sid, held_on: held, source_path: f.path, source_kind: f.kind, source_sha256: f.sha256,
      transcript_latex: null, knowledge_state: null, thread_id: tid, status: 'running', created_at: now, committed_at: null, review_seconds: null };
    d.session.push(sess);
    C.queue.add({
      thread_id: tid, graph: 'G1', subject: code + ' · buổi ' + F.date(held), student_id: sid, session_id: sess.id, started_at: now,
      status: 'running', current_node: 'g1.write_session', interrupted_at: null, error: null, checkpoints: [],
      demo_run: f.demo_run || 'hs02-1021',
      state: { source: { path: f.path, kind: f.kind, sha256: f.sha256 }, transcript_latex: null, attempts: [], proposals: [], decisions: {},
        context_mistake_ids: recentMistakeIds(sid), profile: null }
    });
    FORM = { student: '', held_on: '', file: '', dup: null };
    C.toast('① Đã ghi dòng session #' + sess.id + ' (running) · thread ' + tid, { kind: 'info' });
    C.nav('session', { thread: tid });
  }

  /* ----- running ----- */
  function viewRunning(root, t, s) {
    var shellRun = !!RESUMING[t.thread_id];
    var R = shellRun ? null : startRun(t);
    var stripBox = h('div'), logBox = h('div'), btnBox = h('div', { class: 'row' }), nowLine = h('p', { class: 'small' });
    var doneBox = h('div');
    var fillBtns = function () {
      put(btnBox, transcriptBtn(t, s),
        R ? ui.button('Giả lập lỗi giữa chừng', function () { simulateFail(t); }, { kind: 'danger', noAutoclick: true }) : null,
        R ? h('span', { class: 'small muted' }, 'thử tình huống lỗi API: làn 3 · node 03 hỏng, các làn khác giữ trong checkpoint') : null);
    };
    var hadTranscript = !!t.state.transcript_latex;
    var paintAll = function () {
      put(stripBox, strip(t));
      put(logBox, runLog(t));
      put(nowLine, ui.status(t.status), ' ', t.status === 'running' ? 'đang ở ' + ui.nodeName(t.current_node) : stageLabel(t),
        ' · ', h('span', { class: 'muted' }, arr(t.checkpoints).length + ' checkpoint'));
      if (!!t.state.transcript_latex !== hadTranscript) { hadTranscript = !hadTranscript; fillBtns(); }
    };
    MOUNT.tid = t.thread_id;
    MOUNT.paint = paintAll;
    MOUNT.onDone = function () {
      put(doneBox, h('div', { class: 'callout callout-ok' }, h('strong', null, 'Đã tới DỪNG — sẵn sàng duyệt.'),
        h('div', null, ui.button('Duyệt lỗi ngay', function () { C.nav('session', { thread: t.thread_id, step: 4 }); }, { kind: 'primary' }))));
      paintAll();
    };
    fillBtns(); paintAll();
    add(root, 
      threadHead(t, s, 'Buổi học · bước 2 · G1 đang chạy', [], 'Graph chạy theo thứ tự cố định; không agent nào tự gọi agent khác. Số ms và token dưới mỗi node lấy từ lần chạy.'),
      stepper(2, { skip3: skip3(t) }),
      section('2 · Chạy G1', { annot: ['G1', 'agent:01', 'agent:02', 'agent:03', 'agent:04', 'file:checkpoints.db'] },
        srcLine(t, s),
        h('div', { class: 'callout callout-info' }, h('p', null, h('b', null, '① ghi session: '), 'dòng session được ghi ngay (status running) — phần còn lại chỉ ghi ở ②. ', ui.store('db'), ' ', ui.store('checkpoint'))),
        shellRun ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Đang chạy lại từ checkpoint: chỉ node lỗi và các node sau chạy — các bài đã xong không chạy lại.')) : null,
        !R && !shellRun ? h('p', { class: 'small muted' }, 'Không có dữ liệu chạy mẫu cho thread này.') : null,
        nowLine, stripBox, doneBox, btnBox,
        h('details', { class: 'sx-details' }, h('summary', null, 'Nhật ký checkpoint (checkpoints.db)'), logBox)));
  }

  /* ----- failed ----- */
  function viewFailed(root, t, s) {
    var lane = laneOfError(t.error), code = scode(t.student_id);
    add(root, 
      threadHead(t, s, 'Buổi học · thread lỗi', [transcriptBtn(t, s)]),
      stepper(2, { failed: true, skip3: skip3(t) }),
      section('Graph dừng vì lỗi', { annot: ['G1', 'file:checkpoints.db'] },
        srcLine(t, s),
        h('div', { class: 'callout callout-crit', role: 'alert' },
          h('strong', null, 'Lỗi ở node ' + ui.nodeName(t.current_node) + (lane ? ' · làn ' + lane : '')),
          h('p', { class: 'mono small' }, t.error || '—'),
          h('p', null, 'Các node đã xong được giữ trong checkpoint. Chạy lại thì chỉ node lỗi và các node sau chạy (NFR9) — không tốn token cho bài đã xong.'), h('p', null, stuckNote())),
        strip(t),
        h('div', { class: 'row' },
          ui.button('Chạy lại từ checkpoint', function () { resume(t); }, { kind: 'primary', privacy: code }),
          ui.button('Xem trong Vận hành', function () { C.nav('ops', { thread: t.thread_id }); }, { kind: 'secondary' })),
        h('details', { class: 'sx-details', open: true }, h('summary', null, 'Checkpoint đã lưu (' + arr(t.checkpoints).length + ')'), runLog(t))));
  }

  /* ----- locked ----- */
  function viewLocked(root, t, s, b) {
    var bDay = F.date(C.queue.heldOn(b)), bState = b.status === 'failed' ? 'đang lỗi — chạy lại rồi duyệt' : b.status === 'running' ? 'đang chạy — chờ xong rồi duyệt' : 'chờ duyệt';
    var reason = t.locked && t.lock_reason ? t.lock_reason : 'Elo cập nhật tuần tự: buổi ' + bDay + ' của ' + scode(t.student_id) + ' ' + bState + ' trước';
    add(root, 
      threadHead(t, s, 'Buổi học · đang khoá'),
      stepper(4, { skip3: skip3(t) }),
      h('div', { class: 'callout callout-warn' }, h('strong', { class: 'row', style: 'gap:6px' }, ui.status('locked'), reason),
        h('p', null, 'Elo cập nhật theo thứ tự ngày: θ sau buổi trước là θ trước của buổi này, nên buổi ' + bDay + ' (' + bState + ') phải xong trước. Đề xuất của buổi này vẫn giữ trong checkpoints.db.'),
        h('div', null, ui.button('Mở buổi chặn', function () { C.queue.open(b.thread_id); }, { kind: 'primary', cli: 'tutor review ' + b.thread_id }))),
      section('Đang chờ trong checkpoint', { annot: ['file:checkpoints.db'] },
        srcLine(t, s),
        ui.kv([['Số bài', String(arr(t.state.attempts).length)], ['Đề xuất lỗi', String(arr(t.state.proposals).length)], ['Dừng ở', stageLabel(t)]]),
        strip(t, { compact: true })));
  }

  /* ----- step 3: confirm (stop 1) ----- */
  function viewConfirm(root, t, s) {
    var st = t.state, conf = st.confirm || (st.confirm = {}), code = scode(t.student_id), tid = t.thread_id;
    var flagged = arr(st.attempts).filter(function (a) { return arr(a.flags_json).some(function (f) { return f.type !== 'alt_method'; }); });
    var all = []; flagged.forEach(function (a) { a.flags_json.forEach(function (f) { if (f.type !== 'alt_method') all.push(f); }); });
    var left = all.filter(function (f) { return !f.resolved; }).length;
    var stu = student(t.student_id) || {};
    var choose = function (a, pid) {
      var f = a.flags_json.find(function (x) { return x.type === 'low_match'; });
      conf[a.seq] = Object.assign(conf[a.seq] || {}, { match: pid });
      if (f) { f.resolved = true; f.resolution = 'GV chọn ' + refOf(pid); }
      C.toast('Bài ' + a.seq + ' khớp ' + refOf(pid) + ' — attempt.problem_id = ' + pid, { kind: 'ok' });
      C.rerender();
    };
    var lowMatch = function (a, f) {
      var picked = (conf[a.seq] || {}).match, cands = arr(a.match && a.match.candidates);
      var candEl = function (pid, score, top) {
        var pr = problem(pid); if (!pr) return null;
        var on = picked === pid;
        return h('div', { class: 'card sx-cand' + (on ? ' is-picked' : '') },
          h('div', { class: 'spread' }, h('span', { class: 'row', style: 'gap:6px' }, h('b', { class: 'mono' }, pr.ref), ui.status(C.lookup.problemStatus(pr))),
            score != null ? h('span', { class: 'sx-conf' }, 'độ khớp', ui.bar(score, 1, { kind: score >= 0.8 ? 'ok' : 'warn' }), h('b', { class: 'num' }, F.num(score)), ui.prov('llm', '01')) : ui.prov('gv')),
          tx(pr.statement_latex, true),
          h('div', { class: 'row' }, kcsOfProblem(pid).map(kcChip)),
          on ? h('div', { class: 'row' }, ui.chip('đã chọn · GV', 'ok')) : ui.button('Xác nhận bài khớp', function () { choose(a, pid); }, { kind: top && !picked ? 'primary' : 'secondary', size: 'sm' }));
      };
      var extra = picked && !cands.some(function (c) { return c.problem_id === picked; }) ? candEl(picked, null, false) : null;
      return h('div', { class: 'stack' },
        h('p', null, f.detail || 'Bài không có id; 01 so đề với ngân hàng.'),
        h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + code + ' · 2 bước đầu'),
          h('ol', { class: 'sx-steps' }, arr(a.steps_json).slice(0, 2).map(function (x) { return h('li', { class: 'sx-step' }, h('span', { class: 'sx-step-n' }, String(x.idx)), h('div', null, tx(x.latex, true))); }))),
        h('div', { class: 'grid cols-3' }, cands.map(function (c, i) { return candEl(c.problem_id, c.score, i === 0); }), extra),
        h('div', { class: 'row' }, ui.button('Chọn bài khác', function () { pickOther(a, stu.grade, function (pid) { choose(a, pid); }); }, { kind: 'secondary' }),
          h('span', { class: 'small muted' }, 'tìm trong ngân hàng theo mã bài hoặc nội dung đề')));
    };
    var mismatch = function (a, f) {
      var c = (conf[a.seq] || {}).mismatch;
      var pick = function (v) {
        conf[a.seq] = Object.assign(conf[a.seq] || {}, { mismatch: v });
        f.resolved = true; f.resolution = v === 'text_layer' ? 'dùng text layer — giữ lỗi HS' : 'giữ bản chép của 01';
        C.toast(v === 'text_layer' ? 'Dùng text layer: giữ đúng chỗ HS viết sai.' : 'Giữ bản chép của 01.', { kind: 'ok' });
        C.rerender();
      };
      return h('div', { class: 'stack' },
        h('p', null, f.detail),
        mismatchBox(f),
        h('p', { class: 'small muted' }, 'Model hay tự sửa lỗi HS khi chép (Seong 2026) — text layer là chữ HS thật sự gõ trong PDF.'),
        h('div', { class: 'row' },
          ui.button('Dùng text layer (giữ lỗi HS)', function () { pick('text_layer'); }, { kind: c === 'text_layer' ? 'primary' : 'secondary', size: 'sm' }),
          ui.button('Giữ bản chép', function () { pick('transcript'); }, { kind: c === 'transcript' ? 'primary' : 'secondary', size: 'sm' }),
          c ? ui.chip('đã chọn: ' + f.resolution, 'ok') : null));
    };
    var noRubric = function (a, f) {
      var c = conf[a.seq] || (conf[a.seq] = {});
      if (!c.draft) c.draft = clone(a.rubric_draft || { items_json: [], max_score: 0 });
      var approved = !!c.rubric;
      return h('div', { class: 'stack' },
        h('p', null, f.detail || (refOf(a.problem_id) + ' chưa có rubric.')),
        h('div', { class: 'row' }, h('b', null, 'Rubric 02 vừa sinh'), ui.prov('llm', '02'), approved ? ui.chip('rubric v1 · GV duyệt', 'ok') : ui.chip('bản nháp', 'warn')),
        approved ? rubricList(c.rubric) : ui.rubricEditor(c.draft, { onChange: function (r) { c.draft = r; } }),
        h('div', { class: 'row' }, approved
          ? ui.button('Sửa lại rubric', function () { c.draft = clone(c.rubric); delete c.rubric; f.resolved = false; delete f.resolution; C.rerender(); }, { kind: 'secondary', size: 'sm' })
          : ui.button('Duyệt rubric', function () {
            if (!arr(c.draft.items_json).length) { C.toast('Rubric cần ít nhất 1 mục.', { kind: 'warn' }); return; }
            c.rubric = { items_json: clone(c.draft.items_json), max_score: c.draft.max_score, approved_at: nowISO() };
            f.resolved = true; f.resolution = 'rubric v1';
            C.toast('Đã duyệt rubric v1 cho ' + refOf(a.problem_id) + ' — ghi cùng commit ②', { kind: 'ok' });
            C.rerender();
          }, { kind: 'primary', size: 'sm' })),
        h('p', { class: 'small muted' }, 'rubric duyệt ở đây được ghi cùng commit ② (attempt.rubric_id NOT NULL) — sơ đồ 11 chưa liệt kê rubric trong commit ②: điểm cần chốt'));
    };
    var go = function () {
      var n = all.filter(function (f) { return !f.resolved; }).length;
      if (n) { C.toast('Còn ' + n + ' cờ chưa xử lý.', { kind: 'warn' }); return; }
      t.status = 'running'; t.current_node = 'g1.02_grader'; t.interrupted_at = null;
      if (s) s.status = 'running';
      C.refresh();
      C.toast('Chạy tiếp từ DỪNG 1: 02 · 03 · 04 cho ' + arr(st.attempts).length + ' bài.', { kind: 'info' });
      C.nav('session', { thread: tid });
    };
    add(root, 
      threadHead(t, s, 'Buổi học · bước 3 · ' + stageLabel(t), [transcriptBtn(t, s)], '01 Ingest gắn cờ ' + all.length + ' chỗ chưa chắc. Graph dừng ở đây (DỪNG 1): chưa chấm, chưa chẩn đoán. Xử lý hết cờ rồi bấm “Chạy tiếp”.'),
      stepper(3),
      section('3 · Xác nhận', { annot: ['agent:01', 'agent:02', 'table:rubric', 'cli:tutor review ' + tid], right: ui.store('checkpoint') },
        srcLine(t, s),
        strip(t),
        flagged.map(function (a) {
          var fs = a.flags_json.filter(function (f) { return f.type !== 'alt_method'; }), ok = fs.every(function (f) { return f.resolved; });
          return h('article', { class: 'card sx-flagcard ' + (ok ? 'sx-done' : 'st-pending') },
            h('div', { class: 'spread' }, h('h3', null, 'Bài ' + a.seq + ' · ', h('span', { class: 'mono' }, a.problem_id != null ? refOf(a.problem_id) : 'chưa có id')),
              h('span', { class: 'row', style: 'gap:4px' }, fs.map(function (f) { return ui.chip(FLAG_LABEL[f.type] || f.type, f.resolved ? 'ok' : 'warn'); }))),
            fs.map(function (f) {
              return h('div', { class: 'sx-flag' }, h('div', { class: 'eyebrow' }, 'Cờ ' + f.type + (f.resolved ? ' · đã xử lý' : '')),
                f.type === 'low_match' ? lowMatch(a, f) : f.type === 'mismatch' ? mismatch(a, f) : f.type === 'no_rubric' ? noRubric(a, f) : h('p', null, f.detail));
            }));
        }),
        h('div', { class: 'row sx-actbar' },
          h('span', { class: 'small' }, 'Đã xử lý ', h('b', { class: 'num' }, (all.length - left) + '/' + all.length), ' cờ'),
          ui.button('Chạy tiếp', go, { kind: 'primary', privacy: code, cli: 'tutor review ' + tid, disabledReason: left ? 'còn ' + left + ' cờ chưa xử lý' : null }))));
  }
  // Read-only rubric: shell's readOnly editor would typeset plain-text items as math.
  function rubricList(r) {
    return h('div', { class: 'stack', style: 'gap:6px' },
      h('ol', { class: 'sx-grade' }, arr(r.items_json).map(function (it) {
        return h('li', { class: 'sx-gi' }, h('span', { class: 'mono small muted' }, it.item_id), h('div', null, tx(it.text)), h('span', { class: 'num small nowrap' }, (it.points == null ? 0 : it.points) + ' đ'));
      })),
      h('div', { class: 'row small' }, 'Tổng: ', h('b', { class: 'num' }, String(r.max_score)), ' điểm = max_score', ui.prov('code')));
  }
  function pickOther(a, grade, onPick) {
    var pool = arr(db().problem).filter(function (p) { return !grade || p.lop === grade; });
    var top = arr(a.match && a.match.candidates)[0], pre = top ? refOf(top.problem_id).replace(/\d+$/, '') : '';
    var q = h('input', { type: 'search', placeholder: 'Mã bài (vd 8DS-PS-) hoặc chữ trong đề', 'aria-label': 'Tìm bài' });
    q.value = pre;
    var list = h('div', { class: 'stack sx-pick' }), m = null;
    var fill = function () {
      var s = q.value.trim().toLowerCase();
      var rows = pool.filter(function (p) { return !s || p.ref.toLowerCase().indexOf(s) >= 0 || String(p.statement_latex).toLowerCase().indexOf(s) >= 0; });
      put(list, h('p', { class: 'small muted' }, rows.length + ' bài khớp' + (rows.length > 8 ? ' · hiện 8 bài đầu' : '')),
        rows.length ? rows.slice(0, 8).map(function (p) {
          return h('div', { class: 'card' }, h('div', { class: 'spread' }, h('span', { class: 'row', style: 'gap:6px' }, h('b', { class: 'mono' }, p.ref), ui.status(C.lookup.problemStatus(p))),
            ui.button('Chọn', function () { onPick(p.id); if (m) m.close(); }, { kind: 'primary', size: 'sm' })), tx(p.statement_latex, true));
        }) : ui.empty('Không có bài nào khớp.'));
      C.tex(list);
    };
    q.addEventListener('input', fill);
    m = C.modal({ title: 'Chọn bài khác · ngân hàng lớp ' + (grade || '—'), wide: true,
      body: h('div', { class: 'stack' }, h('label', { class: 'field' }, h('span', null, 'Tìm theo ref hoặc đề (statement_latex)'), q), list), actions: [{ label: 'Đóng' }] });
    fill();
  }

  /* ----- step 4: review mistakes ----- */
  function viewReview(root, t, s, p, cl) {
    var st = t.state, tid = t.thread_id, code = scode(t.student_id);
    st.decisions = st.decisions || {};
    var S = UIS[tid] || (UIS[tid] = { seq: null, sel: null, add: false, sol: false, opened: Date.now() });
    var body = h('div', { class: 'stack' });
    var timerEl = null;
    var atts = arr(st.attempts).slice().sort(function (a, b) { return a.seq - b.seq; });
    var attBySeq = function (seq) { return atts.find(function (a) { return a.seq === seq; }); };

    var invalidate = function () { if (st.profile) { st.profile = null; S.note = 'Quyết định đã đổi — cần chạy lại Profiler.'; } };
    var nextOpen = function (list, from) {
      var i = list.findIndex(function (c) { return c.pid === from; });
      for (var k = 1; k <= list.length; k++) { var c = list[(i + k) % list.length]; if (c && !c.d && !c.added) return c.pid; }
      return from;
    };
    var decide = function (c, action, vals) {
      st.decisions[c.pid] = Object.assign({ action: c.added ? 'add' : action, at: nowISO() }, c.added ? c.d : {}, vals || {});
      if (c.added) st.decisions[c.pid].action = 'add';
      invalidate();
      var list = cards(t);
      S.sel = action === 'edit' ? c.pid : nextOpen(list, c.pid);
      draw();
    };
    var accept = function (c) {
      if (c.added) { C.toast('Lỗi GV thêm đã được tính là quyết định (added).', { kind: 'info' }); return; }
      decide(c, 'accept'); C.toast(c.pid + ' → confirmed (chờ ghi)', { kind: 'ok' });
    };
    var reject = function (c) {
      if (c.added) { delete st.decisions[c.pid]; invalidate(); S.sel = null; draw(); C.toast('Đã xoá lỗi vừa thêm ' + c.pid + '.', { kind: 'info' }); return; }
      decide(c, 'reject'); C.toast(c.pid + ' → rejected · vẫn lưu để đo độ chính xác', { kind: 'info' });
    };
    var edit = function (c) {
      var e = eff(c), a = attBySeq(c.seq);
      if (!a) return;
      S.sel = c.pid;
      mistakeForm({
        title: (c.added ? 'Sửa lỗi GV thêm ' : 'Sửa đề xuất ') + c.pid + ' · Bài ' + c.seq + ' · ' + refOf(a.problem_id),
        lead: c.added ? null : 'Bản gốc của 03 vẫn giữ trong mistake.llm_json; thẻ chuyển sang “edited”.',
        problem_id: a.problem_id, steps: a.steps_json, init: e, suggested: c.p && c.p.verifier && c.p.verifier.suggested_code,
        saveLabel: 'Lưu sửa', onSave: function (v) { decide(c, 'edit', v); C.toast(c.pid + ' → edited (chờ ghi)', { kind: 'ok' }); }
      });
    };
    var addAt = function (a, idx) {
      var stp = arr(a.steps_json).find(function (x) { return x.idx === idx; });
      mistakeForm({
        title: 'Thêm lỗi bị sót · Bài ' + a.seq + ' · bước ' + idx, noStep: true,
        lead: 'Lỗi do thầy/cô thêm: status = added, llm_json = NULL, không có ý kiến 03/04.',
        problem_id: a.problem_id, steps: a.steps_json, init: { step_idx: idx, code: 'other.unclear', kc_id: null, description: '', evidence_latex: stp ? stp.latex : '' },
        saveLabel: 'Thêm lỗi', onSave: function (v) {
          var n = 1; while (st.decisions['n' + n]) n++;
          st.decisions['n' + n] = Object.assign({ action: 'add', attempt_seq: a.seq, at: nowISO() }, v);
          S.sel = 'n' + n; S.add = false; invalidate(); draw();
          C.toast('Đã thêm lỗi n' + n + ' (added) ở bài ' + a.seq + ' bước ' + idx, { kind: 'ok' });
        }
      });
    };
    var showEvidence = function (c) {
      S.sel = c.pid; S.seq = c.seq; draw();
      var el = body.querySelector('.sx-col-work [data-step="' + eff(c).step_idx + '"]');
      scrollFlash(el);
    };
    var rawDrawer = function (c) {
      S.sel = c.pid;
      C.drawer({
        title: 'Đề xuất gốc ' + c.pid + ' · Bài ' + c.seq,
        body: h('div', { class: 'stack' },
          h('p', { class: 'small muted' }, 'Hai lời gọi riêng, không chung context: 04 chỉ thấy bài làm + lời giải mẫu + từng lỗi, không thấy lý luận của 03.'),
          h('h3', null, '03 Diagnoser · mistake.llm_json ', ui.prov('llm', '03')), h('pre', { class: 'code' }, JSON.stringify(llmJson(c.p), null, 2)),
          h('h3', null, '04 Verifier · Verdict ', ui.prov('llm', '04')), h('pre', { class: 'code' }, JSON.stringify(c.p.verifier || null, null, 2)),
          c.d ? [h('h3', null, 'Quyết định của thầy/cô ', ui.prov('gv')), h('pre', { class: 'code' }, JSON.stringify(c.d, null, 2))] : null,
          ui.button('Xem lời gọi LLM', function () { C.nav('logs', { thread: tid, agent: '03' }); }, { kind: 'secondary', size: 'sm' }))
      });
    };
    var toggleAdd = function () { S.add = !S.add; draw(); if (S.add) C.toast('Chọn bước có lỗi bị sót ở cột “Bài làm HS”.', { kind: 'info' }); };
    var runProfiler = function () {
      var list = cards(t), open = list.filter(function (c) { return !c.added && !c.d; }).length;
      if (open) { C.toast('Còn ' + open + ' đề xuất chưa quyết.', { kind: 'warn' }); return; }
      var sim = simulate(t);
      st.profile = { at: nowISO(), knowledge_state: knowledgeText(sim), n_events: sim.events.length };
      S.note = null;
      C.toast('05 Profiler: code tính Elo cho ' + sim.events.length + ' cặp (bài, KC) · LLM viết knowledge_state', { kind: 'ok' });
      draw();
      scrollFlash(body.querySelector('#sx-profile'));
    };
    var commit = function () {
      if (!st.profile) { C.toast('Chạy Profiler trước.', { kind: 'warn' }); return; }
      var d = db(), sim = simulate(t), sObj = sim.s;
      Array.prototype.push.apply(d.rubric, sim.rubs);
      Array.prototype.push.apply(d.attempt, sim.atts);
      Array.prototype.push.apply(d.mistake, sim.mists);
      var eId = maxId(d.skill_event);
      sim.events.forEach(function (e) { d.skill_event.push(Object.assign({ id: ++eId }, e)); });
      replaceStudentRows(d.skill_state, sObj.student_id, sim.rep.skill_state);
      replaceStudentRows(d.misconception_log, sObj.student_id, sim.rep.misconception_log);
      sObj.transcript_latex = sObj.transcript_latex || st.transcript_latex;
      sObj.knowledge_state = st.profile.knowledge_state;
      sObj.review_seconds = Math.round((Date.now() - S.opened) / 1000); // † mock-only column
      sObj.status = 'committed'; sObj.committed_at = sim.now;
      t.checkpoints = arr(t.checkpoints);
      t.checkpoints.push({ node: 'g1.05_profiler', at: sim.now, ms: 0, tokens_in: 0, tokens_out: 0 }, { node: 'g1.commit', at: sim.now, ms: 0, tokens_in: 0, tokens_out: 0 });
      var rows = (sim.rubs.length ? [['rubric', sim.rubs.length]] : []).concat([['attempt', sim.atts.length], ['mistake', sim.mists.length], ['skill_event', sim.events.length],
        ['skill_state', 'cập nhật'], ['misconception_log', 'cập nhật'], ['session', '→ committed']]);
      C.receipt('Ghi buổi ' + code + ' · ' + dm(sObj.held_on), rows, { graph: 'G1', backup: true });
      C.queue.resolve(tid);
      delete UIS[tid];
      C.nav('session', { thread: tid, step: 5 });
    };

    function cardEl(c) {
      var e = eff(c), d = c.d, act = d ? d.action : null, a = attBySeq(c.seq), lo = lowConf();
      var cls = 'sx-card ' + (!d ? 'is-open' : act === 'reject' ? 'is-rej' : 'is-ok') + (S.sel === c.pid ? ' is-sel' : '');
      var pill = !d ? h('span', { class: 'status s-pending' }, 'chờ quyết')
        : act === 'reject' ? ui.status('rejected')
        : h('span', { class: 'status s-ok', title: 'status = ' + ({ accept: 'confirmed', edit: 'edited', add: 'added' }[act]) }, ({ accept: 'confirmed', edit: 'edited', add: 'added' }[act]) + ' · chờ ghi');
      var says = null;
      if (!c.added) {
        var v = c.p.verifier || {}, vd = VERDICT[v.verdict] || [v.verdict || '—', 'neutral'];
        says = h('div', { class: 'sx-says' },
          h('div', { class: 'sx-say' }, h('div', { class: 'sx-say-h' }, agentBadge('03'), 'Diagnoser (03) nói', ui.prov('llm')),
            h('div', { class: 'row', style: 'gap:4px' }, codeChip(c.p.code), kcChip(c.p.kc_id), h('span', { class: 'small' }, 'bước ' + c.p.step_idx + ' · tin cậy ' + F.num(c.p.confidence))),
            act === 'edit' ? h('div', { class: 'small' }, tx(c.p.description)) : null),
          h('div', { class: 'sx-rule' }, 'không chung context'),
          h('div', { class: 'sx-say' }, h('div', { class: 'sx-say-h' }, agentBadge('04'), 'Verifier (04) nói', ui.prov('llm')),
            h('div', { class: 'row', style: 'gap:4px' }, ui.chip(vd[0], vd[1]), v.suggested_code ? h('span', { class: 'small' }, 'gợi ý mã ', codeChip(v.suggested_code)) : null),
            h('div', { class: 'small' }, tx(v.reason || '—'))));
      }
      var diff = null;
      if (act === 'edit') {
        var chg = [];
        if (d.code !== c.p.code) chg.push(['loại lỗi', errName(c.p.code), errName(d.code)]);
        if (d.kc_id !== c.p.kc_id) chg.push(['KC', kcLabel(c.p.kc_id), kcLabel(d.kc_id)]);
        if (d.step_idx !== c.p.step_idx) chg.push(['bước', c.p.step_idx, d.step_idx]);
        if (d.description !== c.p.description) chg.push(['mô tả', plain(c.p.description, 40), plain(d.description, 40)]);
        diff = h('div', { class: 'sx-diffline small' }, h('b', null, 'Khác đề xuất LLM: '), chg.length ? chg.map(function (x, i) {
          return h('span', null, i ? ' · ' : '', x[0] + ': ', h('s', null, String(x[1])), ' → ', h('b', null, String(x[2])));
        }) : 'không đổi trường nào (chỉ thêm ghi chú)', ' ', ui.prov('gv'));
      }
      return h('article', { class: cls, 'data-pid': c.pid },
        h('div', { class: 'sx-card-h' }, h('span', { class: 'small' }, h('b', { class: 'mono' }, c.pid), ' · Bài ' + c.seq + ' · ', h('span', { class: 'mono' }, refOf(a && a.problem_id)), ' · bước ' + e.step_idx), pill),
        h('div', { class: 'row', style: 'gap:6px' }, codeChip(e.code), kcChip(e.kc_id),
          !c.added && c.p.confidence != null ? h('span', { class: 'sx-conf' }, 'tin cậy', ui.bar(c.p.confidence, 1, { kind: c.p.confidence < lo ? 'warn' : 'accent' }), h('b', { class: 'num' }, F.num(c.p.confidence))) : ui.chip('GV thêm', 'neutral')),
        h('div', { class: 'sx-strike' }, tx(e.description)),
        h('div', { class: 'sx-evid sx-strike' }, h('span', { class: 'small muted' }, 'Bằng chứng: '), tx(e.evidence_latex, true)),
        c.added ? h('p', { class: 'small muted' }, 'Lỗi do thầy/cô thêm — không có ý kiến 03/04 (llm_json = NULL).') : says,
        diff,
        d && d.teacher_note ? h('p', { class: 'small' }, h('b', null, 'Ghi chú GV: '), d.teacher_note) : null,
        act === 'reject' ? h('p', { class: 'small' }, 'Đã bỏ — vẫn lưu để đo độ chính xác (status rejected, mistake_current không tính).') : null,
        c.added ? null : h('p', { class: 'sx-foot-note' }, 'Hệ thống không tự quyết — thầy/cô quyết.'),
        h('div', { class: 'sx-acts' },
          c.added ? null : ui.button('Chấp nhận (A)', function () { accept(c); }, { kind: act === 'accept' ? 'primary' : 'secondary', size: 'sm' }),
          ui.button('Sửa (E)', function () { edit(c); }, { kind: act === 'edit' ? 'primary' : 'secondary', size: 'sm' }),
          ui.button(c.added ? 'Xoá lỗi vừa thêm (R)' : 'Bỏ (R)', function () { reject(c); }, { kind: act === 'reject' ? 'primary' : 'secondary', size: 'sm' }),
          ui.button('Xem bằng chứng', function () { showEvidence(c); }, { kind: 'ghost', size: 'sm' }),
          c.added ? null : ui.button('Xem đề xuất gốc', function () { rawDrawer(c); }, { kind: 'ghost', size: 'sm' }),
          c.added ? null : ui.button('Xem lời gọi LLM', function () { C.nav('logs', { thread: tid, agent: '03' }); }, { kind: 'ghost', size: 'sm' })));
    }
    function workCol(a, list) {
      var pr = problem(a.problem_id) || {};
      var hits = {};
      list.forEach(function (c) { if (c.seq === a.seq) { var e = eff(c); (hits[e.step_idx] = hits[e.step_idx] || []).push(c); } });
      var selC = list.find(function (c) { return c.pid === S.sel; }), selStep = selC && selC.seq === a.seq ? eff(selC).step_idx : null;
      var steps = h('ol', { class: 'sx-steps' }, arr(a.steps_json).map(function (x) {
        var hs = hits[x.idx] || [], live = hs.some(function (c) { return !(c.d && c.d.action === 'reject'); });
        return h('li', { class: 'sx-step' + (live ? ' is-hit' : '') + (selStep === x.idx ? ' is-sel' : ''), 'data-step': x.idx },
          h('span', { class: 'sx-step-n' }, String(x.idx)), h('div', { class: 'sx-step-body' }, tx(x.latex, true)),
          hs.length || S.add ? h('div', { class: 'sx-step-tags' },
            hs.map(function (c) { var ch = ui.chip(c.pid + ' · ' + errName(eff(c).code), !c.d ? 'warn' : c.d.action === 'reject' ? 'neutral' : 'ok'); ch.classList.add('chip-wrap'); ch.title = eff(c).code; return ch; }),
            S.add ? ui.button('Thêm lỗi ở bước này', function () { addAt(a, x.idx); }, { kind: 'primary', size: 'sm' }) : null) : null);
      }));
      return h('div', { class: 'sx-col sx-col-work' },
        h('div', { class: 'spread' }, h('h3', null, 'Bài làm HS ', ui.annot(['agent:01', 'table:attempt'])),
          ui.button(S.add ? 'Thôi thêm lỗi' : 'Thêm lỗi bị sót (N)', toggleAdd, { kind: S.add ? 'primary' : 'ghost', size: 'sm' })),
        h('div', { class: 'sx-prob' }, h('div', { class: 'spread small muted' }, h('span', null, 'Đề bài · ', h('span', { class: 'mono' }, pr.ref || '—')),
          pr.ref ? ui.button('Xem trong Ngân hàng bài', function () { C.nav('bank', { problem: pr.ref }); }, { kind: 'ghost', size: 'sm' }) : null), tx(pr.statement_latex, true)),
        S.add ? h('div', { class: 'callout callout-info' }, h('p', { class: 'small' }, 'Bấm “Thêm lỗi ở bước này” cạnh bước có lỗi bị sót.')) : null,
        h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + code), steps),
        h('div', null, ui.button(S.sol ? 'Ẩn lời giải mẫu' : 'Lời giải mẫu', function () { S.sol = !S.sol; draw(); }, { kind: 'secondary', size: 'sm' })),
        S.sol ? h('div', { class: 'card sx-sol' }, h('div', { class: 'small muted' }, 'Lời giải mẫu (problem.solution_latex) ', ui.prov('gv', 'bank')),
          h('ol', { class: 'sx-steps' }, arr(pr.solution_steps).map(function (x) { return h('li', { class: 'sx-step' }, h('span', { class: 'sx-step-n' }, String(x.idx)), h('div', null, tx(x.latex, true))); }))) : null);
    }
    function gradeCol(a) {
      var rub = rubricOf(a), items = rub ? arr(rub.items_json) : [], g = arr(a.grade_json);
      var pts = function (id) { var it = items.find(function (x) { return x.item_id === id; }); return it ? +it.points || 0 : 1; };
      var passed = g.filter(function (x) { return x.passed; });
      var sum = passed.reduce(function (s0, x) { return s0 + pts(x.item_id); }, 0);
      var okSum = a.score != null && Math.abs(sum - a.score) < 1e-9, okEv = passed.every(function (x) { return String(x.evidence_latex || '').trim(); });
      var ids = items.map(function (x) { return x.item_id; }); g.forEach(function (x) { if (ids.indexOf(x.item_id) < 0) ids.push(x.item_id); });
      var flags = arr(a.flags_json);
      return h('div', { class: 'sx-col sx-col-grade' },
        h('div', { class: 'spread' }, h('h3', null, agentBadge('02'), ' 02 Grader ', ui.annot(['agent:02', 'table:attempt'])),
          rub ? ui.chip('rubric v' + rub.version + (rub.draft ? ' · duyệt ở bước 3' : ''), rub.draft ? 'warn' : 'neutral') : ui.chip('chưa có rubric', 'danger')),
        h('div', { class: 'row' }, h('span', { class: 'sx-score num' }, (a.score == null ? '—' : a.score) + '/' + (a.max_score == null ? '—' : a.max_score)), ui.prov('llm', '02'),
          ui.why(function () {
            return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'Điểm = tổng điểm các mục đạt = ' + (passed.map(function (x) { return x.item_id + ' (' + pts(x.item_id) + ')'; }).join(' + ') || '0') + ' = ' + sum + '.'),
              h('p', null, 'max_score = ' + (rub ? rub.max_score : a.max_score) + ' (rubric v' + (rub ? rub.version : '—') + ').'), h('p', { class: 'small muted' }, '02 chấm từng mục; code kiểm tra tổng và bằng chứng.'));
          })),
        h('div', { class: 'row', style: 'gap:6px' }, ui.chip('tổng = tổng các mục ' + (okSum ? '✓' : '✗') + ' · mục đạt có bằng chứng ' + (okEv ? '✓' : '✗'), okSum && okEv ? 'ok' : 'danger'), ui.prov('code')),
        flags.filter(function (f) { return f.type !== 'alt_method' && f.resolved; }).length ? h('div', { class: 'row', style: 'gap:4px' }, flags.filter(function (f) { return f.type !== 'alt_method' && f.resolved; }).map(function (f) { return ui.chip((FLAG_LABEL[f.type] || f.type) + ': ' + (f.resolution || 'đã xử lý'), 'ok'); })) : null,
        flags.filter(function (f) { return f.type === 'alt_method'; }).map(function (f) {
          return h('div', { class: 'callout ' + (f.resolved ? 'callout-ok' : 'callout-warn') },
            h('strong', null, 'Cờ alt_method · cách giải khác lời giải mẫu'), h('p', { class: 'small' }, f.detail + (f.step_idx ? ' (bước ' + f.step_idx + ')' : '')),
            f.resolved ? h('p', { class: 'small' }, '✓ Thầy/cô đã chấp nhận cách giải khác — ghi vào attempt.flags_json.')
              : h('div', null, ui.button('Chấp nhận cách giải khác', function () { f.resolved = true; f.resolution = 'GV chấp nhận'; invalidate(); draw(); C.toast('Đã chấp nhận cách giải khác ở bài ' + a.seq + '.', { kind: 'ok' }); }, { kind: 'secondary', size: 'sm' })));
        }),
        g.length ? h('ol', { class: 'sx-grade' }, ids.map(function (id) {
          var it = items.find(function (x) { return x.item_id === id; }) || { item_id: id, text: '', points: 1 }, gr = g.find(function (x) { return x.item_id === id; });
          return h('li', { class: 'sx-gi' },
            h('span', { class: 'sx-tick ' + (gr && gr.passed ? 'ok' : 'no'), 'aria-label': gr && gr.passed ? 'đạt' : 'chưa đạt' }, gr && gr.passed ? '✓' : '✗'),
            h('div', null, h('span', { class: 'mono small muted' }, id + ' '), tx(it.text || '(mục không có trong rubric)')),
            h('span', { class: 'num small nowrap' }, (gr && gr.passed ? pts(id) : 0) + '/' + pts(id) + ' đ'),
            gr ? h('div', { class: 'sx-ev' }, h('span', { class: 'muted' }, 'bằng chứng: '), tx(gr.evidence_latex)) : null);
        })) : ui.empty('02 chưa chấm bài này.'));
    }
    function draw() {
      var list = cards(t);
      if (!list.some(function (c) { return c.pid === S.sel; })) S.sel = (list.find(function (c) { return !c.d && !c.added; }) || list[0] || {}).pid || null;
      var selC = list.find(function (c) { return c.pid === S.sel; });
      if (S.seq == null || !attBySeq(S.seq)) S.seq = selC ? selC.seq : (atts[0] || {}).seq;
      var a = attBySeq(S.seq);
      var total = list.filter(function (c) { return !c.added; }).length, done = list.filter(function (c) { return !c.added && c.d; }).length;
      var open = total - done, addedN = list.length - total;
      var tabs = ui.segmented(atts.map(function (x) {
        var n = list.filter(function (c) { return c.seq === x.seq; }).length;
        return { id: String(x.seq), label: 'Bài ' + x.seq + ' · ' + refOf(x.problem_id) + ' · ' + (x.score == null ? '—' : x.score) + '/' + (x.max_score == null ? '—' : x.max_score) + ' · ' + n + ' đề xuất' };
      }), String(S.seq), function (id) { S.seq = +id; draw(); });
      var groups = [0, 1, 2, 3].map(function (gi) {
        var cs = list.filter(function (c) { return c.grp === gi; });
        if (!cs.length) return null;
        return h('div', { class: 'stack sx-group' }, h('div', { class: 'sx-group-h' }, GROUPS[gi] + (gi === 1 ? ' (< ' + lowConf() + ')' : ''), h('span', { class: 'num' }, '· ' + cs.length)), cs.map(cardEl));
      });
      var ctxIds = arr(st.context_mistake_ids);
      var ctxRows = ctxIds.map(function (id) { return arr(db().mistake).find(function (m) { return m.id === id; }); }).filter(Boolean);
      var heldOf = function (m) {
        var at = arr(db().attempt).find(function (x) { return x.id === m.attempt_id; }), se = at && arr(db().session).find(function (x) { return x.id === at.session_id; });
        return se ? dm(se.held_on) : '';
      };
      var sim = st.profile ? simulate(t) : null;
      var calls = callsOf(tid);
      put(body, 
        h('div', { class: 'row sx-info' }, srcLine(t, s), calls.length ? ui.costChip(calls) : null, h('span', { class: 'small muted' }, 'chờ từ ' + F.ago(t.started_at)), ui.store('checkpoint')),
        strip(t, { compact: true, current: st.profile ? 'g1.05_profiler' : 'g1.review', done: st.profile ? ['g1.review'] : [] }),
        atts.length ? tabs : null,
        !atts.length ? ui.empty('Thread chưa có bài nào.') : h('div', { class: 'sx-cols' },
          a ? workCol(a, list) : null,
          a ? gradeCol(a) : null,
          h('div', { class: 'sx-col sx-col-cards' },
            h('div', { class: 'spread' }, h('h3', null, 'Đề xuất lỗi ', ui.annot(['agent:03', 'agent:04', 'table:mistake'])), h('span', { class: 'small muted' }, total + ' đề xuất' + (addedN ? ' · ' + addedN + ' GV thêm' : ''))),
            h('p', { class: 'small muted' }, 'Xếp: 04 phản đối / sai mã → độ tin cậy < ' + lowConf() + ' → còn lại.' + (atts.length > 1 ? ' Cả ' + atts.length + ' bài, không riêng bài đang mở.' : '')),
            total === 0 && !addedN ? h('div', { class: 'callout callout-info' }, h('p', null, '02/03 không tìm thấy lỗi — vẫn cần thầy/cô xác nhận.')) : null,
            groups)),
        h('div', { class: 'grid cols-3 sx-foot' },
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Đã quyết'), h('span', { class: 'kpi-value num' }, done + '/' + total), ui.bar(done, total || 1, { kind: open ? 'warn' : 'ok' })),
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Thời gian duyệt'), timerEl = h('span', { class: 'kpi-value num' }, mmss((Date.now() - S.opened) / 1000)),
            h('span', { class: 'kpi-sub' }, 'tính từ lúc mở · ghi vào session.review_seconds †')),
          h('div', { class: 'card sx-ctx' }, h('div', { class: 'small' }, h('b', null, 'Ngữ cảnh 03 đã dùng: '), ctxRows.length + ' lỗi đã duyệt gần nhất của ' + code, ' ', ui.annot(['table:mistake'])),
            ctxRows.length ? h('div', { class: 'row', style: 'gap:4px' }, ctxRows.map(function (m) { var c0 = ui.chip(errName(m.code) + ' · ' + (m.kc_id == null ? 'không KC' : kcLabel(m.kc_id)) + ' · ' + heldOf(m), 'neutral'); c0.classList.add('chip-wrap'); c0.title = m.code + ((kc(m.kc_id) || {}).code ? ' · ' + kc(m.kc_id).code : '') + ' — ' + plain(m.description, 80); return c0; }))
              : h('span', { class: 'small muted' }, 'Chưa có lỗi đã duyệt (HS mới).'))),
        S.note ? h('div', { class: 'callout callout-warn' }, h('p', null, S.note)) : null,
        h('div', { class: 'row sx-actbar', id: 'sx-actbar' },
          ui.button('Chạy Profiler', runProfiler, { kind: st.profile ? 'secondary' : 'primary', privacy: code, disabledReason: open ? 'còn ' + open + ' đề xuất chưa quyết (A/E/R)' : null }),
          ui.button('Tạm dừng, duyệt sau', function () { C.toast('Đã lưu, còn trong Hộp duyệt — ' + done + '/' + total + ' quyết định giữ trong checkpoint.', { kind: 'ok' }); C.nav('today'); }, { kind: 'secondary', cli: 'tutor review ' + tid }),
          ui.button('Danh mục mã lỗi', function () { C.nav('catalog', { tab: 'codes' }); }, { kind: 'ghost' }),
          h('span', { class: 'small muted sx-kbd' }, 'Phím: ', h('kbd', null, 'A'), ' chấp nhận · ', h('kbd', null, 'E'), ' sửa · ', h('kbd', null, 'R'), ' bỏ · ', h('kbd', null, 'N'), ' thêm lỗi · ', h('kbd', null, 'J'), '/', h('kbd', null, 'K'), ' thẻ sau/trước')),
        sim ? profilePanel(t, sim, commit) : null);
      C.tex(body);
    }
    function profilePanel(t, sim, onCommit) {
      var md = misDiff(sim.rep.misconception_log, sim.s.student_id);
      var words = String(st.profile.knowledge_state).split(/\s+/).filter(Boolean).length;
      var kindChip = { 'mới': 'info', 'lỗi lặp': 'warn', 'tái xuất hiện': 'warn', 'đã hết': 'ok' };
      var wr = [['attempt', sim.atts.length], ['mistake', sim.mists.length], ['skill_event', sim.events.length]];
      return h('section', { class: 'section st-pending sx-profile', id: 'sx-profile' },
        h('div', { class: 'section-head' }, h('div', null, h('h2', null, '05 Profiler · xem trước'), ui.annot(['agent:05', 'table:skill_event', 'table:skill_state', 'table:misconception_log'])), ui.store('checkpoint')),
        h('p', { class: 'small muted' }, 'Code tính Elo, streak, lỗi lặp (elo.py, K = ' + kParam() + '); LLM chỉ viết knowledge_state. Chưa ghi gì — bấm “Ghi vào tutor.db” để commit.'),
        h('h3', null, 'Elo theo (bài, KC) ', ui.prov('code')),
        ui.table({ rows: sim.events, empty: 'Không có cặp (bài, KC) nào — bài chưa gắn KC.', columns: [
          { label: 'Bài', render: function (e) { var a = sim.atts.find(function (x) { return x.id === e.attempt_id; }); return h('span', { class: 'nowrap' }, 'Bài ' + sim.seqOf[e.attempt_id] + ' · ', h('span', { class: 'mono' }, refOf(a && a.problem_id))); } },
          { label: 'KC', render: function (e) { var k = kc(e.kc_id); return h('span', null, h('span', { class: 'mono' }, k ? k.code : '#' + e.kc_id), ' ', h('span', { class: 'muted small' }, k ? k.name : '')); } },
          { label: 'X', align: 'center', render: function (e) { return ui.chip(String(e.outcome), e.outcome ? 'ok' : 'danger'); } },
          { label: 'P', align: 'right', render: function (e) { return h('span', { class: 'num' }, F.num(e.p_expected)); } },
          { label: 'θ trước → θ sau', align: 'right', render: function (e) { return h('span', { class: 'num nowrap' }, F.signed(e.theta_before) + ' → ', h('b', null, F.signed(e.theta_after))); } },
          { label: 'δ', align: 'right', render: function (e) { return h('span', { class: 'num' }, F.signed(e.delta)); } },
          { label: '', render: function (e) { var a = sim.atts.find(function (x) { return x.id === e.attempt_id; }); return ui.why(function () { return eloWhy(e, refOf(a && a.problem_id)); }); } }
        ] }),
        h('div', { class: 'grid cols-2' },
          h('div', { class: 'stack' }, h('h3', null, 'Δθ so với buổi đã ghi trước ', ui.prov('code')), deltaRows(sim.dv && sim.dv.kcs),
            h('div', { class: 'small muted' }, 'Mã lỗi so với buổi trước:'), codeChips(sim.dv)),
          h('div', { class: 'stack' }, h('h3', null, 'Thay đổi misconception_log ', ui.prov('code')),
            h('p', { class: 'small muted' }, 'lỗi lặp = cùng lỗi + cùng KC, ≥ 2 lần, chưa hết.'),
            md.length ? h('ul', { class: 'sx-list' }, md.map(function (x) {
              return h('li', { title: x.m.code + (kc(x.m.kc_id) ? ' · ' + kc(x.m.kc_id).code : '') }, ui.chip(x.kind, kindChip[x.kind] || 'neutral'), ' ', errName(x.m.code) + ' ở “' + kcName(x.m.kc_id) + '” ',
                h('span', { class: 'small muted' }, x.kind === 'đã hết' ? '· hết ' + F.date(x.m.resolved_at) + ' (' + needStreak() + ' lần đúng liên tiếp)' : '· ' + (x.o ? x.o.count + ' → ' : '') + x.m.count + ' lần'));
            })) : h('p', { class: 'small muted' }, 'Không đổi.'))),
        h('div', { class: 'card' }, h('div', { class: 'row' }, h('b', null, 'knowledge_state'), ui.prov('llm', '05'), h('span', { class: 'small muted' }, 'viết từ số liệu, không tự chấm · ' + words + '/150 từ')),
          h('p', { class: 'sx-ks' }, st.profile.knowledge_state)),
        h('div', { class: 'card st-pending' }, h('b', null, 'Sẽ ghi vào tutor.db (1 transaction)'),
          h('ul', { class: 'sx-list' },
            sim.rubs.length ? h('li', null, h('span', { class: 'mono' }, 'rubric'), ' ×' + sim.rubs.length + ' (v1 duyệt ở bước 3)') : null,
            wr.map(function (r) { return h('li', null, h('span', { class: 'mono' }, r[0]), ' ×' + r[1]); }),
            h('li', null, h('span', { class: 'mono' }, 'skill_state'), ' — tính lại ' + sim.rep.skill_state.length + ' dòng của ' + scode(sim.s.student_id)),
            h('li', null, h('span', { class: 'mono' }, 'misconception_log'), ' — tính lại ' + sim.rep.misconception_log.length + ' dòng'),
            h('li', null, h('span', { class: 'mono' }, 'session'), ' → committed (+ knowledge_state, transcript_latex)')),
          h('p', { class: 'small muted' }, 'Trước khi ghi: sao lưu data/backup/tutor-' + today() + '.db (tài liệu thiết kế §8.7).')),
        ui.button('Ghi vào tutor.db', onCommit, { kind: 'primary', cli: 'tutor review ' + tid }));
    }

    add(root, 
      threadHead(t, s, 'Buổi học · bước 4 · ' + stageLabel(t), [transcriptBtn(t, s)], 'Duyệt từng lỗi 03 đề xuất. 04 kiểm tra độc lập (không thấy lý luận của 03); mục bất đồng và mục độ tin cậy thấp lên đầu. Không có “duyệt tất cả”.'),
      stepper(4, { skip3: skip3(t) }),
      String(p.step) === '5' && !st.profile ? h('div', { class: 'callout callout-info' }, h('p', null, 'Bước 5 cần quyết xong mọi đề xuất, chạy Profiler, rồi “Ghi vào tutor.db” ở cuối trang.')) : null,
      body);
    draw();
    var iv = setInterval(function () { if (timerEl && timerEl.isConnected) timerEl.textContent = mmss((Date.now() - S.opened) / 1000); }, 1000);
    cl.push(function () { clearInterval(iv); });
    var onKey = function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
      var tg = e.target;
      if (tg && tg.closest && tg.closest('input, textarea, select, [contenteditable]')) return;
      if (overlayOpen() || document.querySelector('#view').dataset.tab !== 'session') return;
      var k = String(e.key || '').toLowerCase();
      if ('aernjk'.indexOf(k) < 0 || k.length !== 1) return;
      var list = cards(t), i = list.findIndex(function (c) { return c.pid === S.sel; }), c = list[i];
      e.preventDefault();
      if (k === 'j' || k === 'k') {
        if (!list.length) return;
        var n = list[(i + (k === 'j' ? 1 : -1) + list.length) % list.length];
        S.sel = n.pid; S.seq = n.seq; draw();
        scrollFlash(body.querySelector('[data-pid="' + n.pid + '"]'));
        return;
      }
      if (k === 'n') { toggleAdd(); return; }
      if (!c) return;
      if (k === 'a') accept(c); else if (k === 'e') edit(c); else if (k === 'r') reject(c);
    };
    document.addEventListener('keydown', onKey);
    cl.push(function () { document.removeEventListener('keydown', onKey); });
    if (String(p.step) === '5') setTimeout(function () { scrollFlash(body.querySelector('#sx-profile') || body.querySelector('#sx-actbar')); }, 300);
  }

  /* ----- step 5: result ----- */
  function viewResult(root, t, s) {
    var d = db(), atts = d.attempt.filter(function (a) { return a.session_id === s.id; }), ids = {};
    atts.forEach(function (a) { ids[a.id] = 1; });
    var mists = d.mistake.filter(function (m) { return ids[m.attempt_id]; }), evs = d.skill_event.filter(function (e) { return ids[e.attempt_id]; });
    var dv = C.calc.deltaVsPrevious(d, s.id), code = scode(s.student_id);
    var resolved = arr(dv && dv.resolved);
    var nextT = C.queue.list({ graph: 'G1', student_id: s.student_id }).find(function (x) { return !blockerOf(x); });
    var bk = arr((C.data.files || {}).backups)[0];
    add(root, 
      threadHead(t, s, 'Buổi học · bước 5 · đã ghi tutor.db', [ui.button('Xem chi tiết buổi', function () { C.nav('session', { session: s.id }); }, { kind: 'secondary' })]),
      stepper(5, { allDone: true, skip3: skip3(t) }),
      h('div', { class: 'callout callout-ok st-db' },
        h('strong', null, 'Đã ghi 1 transaction vào tutor.db' + (s.committed_at ? ' lúc ' + String(s.committed_at).slice(11, 16) : '')),
        h('p', { class: 'mono small' }, '1 transaction · +' + atts.length + ' attempt · +' + mists.length + ' mistake · +' + evs.length + ' skill_event · skill_state · misconception_log · session → committed'),
        bk ? h('p', { class: 'small' }, 'Sao lưu trước khi ghi: ', h('span', { class: 'mono' }, bk.path)) : null,
        h('p', { class: 'small' }, 'Thread ' + t.thread_id + ' đã commit — đề xuất không còn chờ trong checkpoints.db.')),
      h('div', { class: 'grid cols-2' },
        section('Δθ theo KC (so với buổi trước)', { annot: ['agent:05', 'table:skill_event'] }, deltaRows(dv && dv.kcs)),
        section('Mã lỗi so với buổi trước: có ở cả 2 buổi / mới / đã hết', { annot: ['table:mistake', 'table:misconception_log'] }, codeChips(dv),
          h('h3', null, 'Cặp lỗi đã hết (resolved)'),
          resolved.length ? h('ul', { class: 'sx-list' }, resolved.map(function (r) { return h('li', { title: r.code }, errName(r.code) + ' ở “' + kcName(r.kc_id) + '” ', h('span', { class: 'small muted' }, '· ' + needStreak() + ' lần đúng liên tiếp')); }))
            : h('p', { class: 'small muted' }, 'Buổi này chưa có cặp lỗi nào hết.'))),
      section('knowledge_state', { annot: ['agent:05', 'table:session'], extra: ui.prov('llm', '05') },
        h('p', { class: 'sx-ks' }, s.knowledge_state || '—'), h('p', { class: 'small muted' }, '05 viết từ số liệu do code tính, không tự chấm.')),
      section('Bước tiếp theo', {},
        h('div', { class: 'row' },
          ui.button('Gợi ý bài buổi sau cho HS này', function () { C.nav('recommend', { student: s.student_id }); }, { kind: 'primary', cli: 'tutor recommend ' + code }),
          ui.button('Xem hồ sơ', function () { C.nav('students', { student: s.student_id }); }, { kind: 'secondary' }),
          nextT ? ui.button('Duyệt buổi ' + dm(C.queue.heldOn(nextT)) + ' của ' + code, function () { C.queue.open(nextT.thread_id); }, { kind: 'secondary', cli: 'tutor review ' + nextT.thread_id }) : null,
          ui.button('Nộp bài mới', function () { C.nav('session', { step: 1 }); }, { kind: 'ghost' }))));
  }

  /* ----- read-only detail ----- */
  function viewDetail(root, s, p) {
    var d = db(), t = C.lookup.thread(s.thread_id), code = scode(s.student_id);
    var atts = d.attempt.filter(function (a) { return a.session_id === s.id; }).sort(function (a, b) { return a.seq - b.seq; });
    var calls = callsOf(s.thread_id), cost = calls.reduce(function (x, c) { return x + (+c.cost_usd || 0); }, 0);
    var tok = calls.reduce(function (x, c) { return x + (c.tokens_in || 0) + (c.tokens_out || 0) + (c.cache_read_tokens || 0); }, 0);
    var cache = calls.reduce(function (x, c) { return x + (c.cache_read_tokens || 0); }, 0);
    var supBy = {}; d.mistake.forEach(function (m) { if (m.supersedes_id != null) supBy[m.supersedes_id] = m.id; });
    var dv = s.status === 'committed' ? C.calc.deltaVsPrevious(d, s.id) : null;
    var editSaved = function (m, a) {
      mistakeForm({
        title: 'Sửa lỗi đã lưu #' + m.id, saveLabel: 'Ghi bản sửa',
        lead: 'mistake: không sửa dòng cũ — thêm dòng mới với supersedes_id = ' + m.id + ', rồi dựng lại skill_state, misconception_log từ lịch sử. skill_event: bản nháp ghi lại tại chỗ các dòng đã lưu của ' + code + ' cho khớp replay — chưa chốt (schema nói append-only nhưng UNIQUE(attempt_id, kc_id), không có supersedes_id).',
        problem_id: a.problem_id, steps: a.steps_json, init: m,
        onSave: function (v) {
          var id = maxId(d.mistake) + 1, now = nowISO();
          d.mistake.push(Object.assign({}, m, v, { id: id, status: m.llm_json ? 'edited' : 'added', llm_json: m.llm_json, supersedes_id: m.id, reviewed_at: now, created_at: now }));
          var rep = C.calc.replay(d, s.student_id), byKey = {};
          rep.skill_event.forEach(function (e) { byKey[e.attempt_id + '|' + e.kc_id] = e; });
          // shortcut: skill_event θ values follow the replay in place so stored rows equal replay(); real rule for events after a supersede is open (schema rule 3–4).
          var nEv = 0;
          d.skill_event.forEach(function (e) {
            var r = e.student_id === s.student_id && byKey[e.attempt_id + '|' + e.kc_id];
            if (!r || (e.outcome === r.outcome && e.p_expected === r.p_expected && e.theta_before === r.theta_before && e.theta_after === r.theta_after)) return;
            nEv++; e.outcome = r.outcome; e.p_expected = r.p_expected; e.theta_before = r.theta_before; e.theta_after = r.theta_after;
          });
          replaceStudentRows(d.skill_state, s.student_id, rep.skill_state);
          replaceStudentRows(d.misconception_log, s.student_id, rep.misconception_log);
          C.receipt('Sửa lỗi đã lưu #' + m.id + ' → #' + id, [['mistake', 1], ['skill_event', nEv ? 'ghi lại ' + nEv + ' dòng (chưa chốt)' : 'không đổi'], ['skill_state', 'cập nhật'], ['misconception_log', 'cập nhật']], { graph: 'G1' });
          C.toast('replay skill_state, misconception_log của ' + code + ' (từ ' + rep.skill_event.length + ' skill_event)' + (nEv ? ' · ghi lại ' + nEv + ' skill_event tại chỗ (chưa chốt)' : ''), { kind: nEv ? 'warn' : 'info' });
          C.rerender();
        }
      });
    };
    var mistakeEl = function (m, a) {
      var newer = supBy[m.id], cls = 'sx-mrow ' + (newer ? 'is-old' : m.status === 'rejected' ? 'is-rej' : 'st-db');
      var lj = m.llm_json, diff = null;
      if (lj && (m.status === 'edited' || m.supersedes_id != null)) {
        var ch = [];
        if (lj.code !== m.code) ch.push(['loại lỗi', errName(lj.code), errName(m.code)]);
        if (lj.kc_id !== m.kc_id) ch.push(['KC', kcLabel(lj.kc_id), kcLabel(m.kc_id)]);
        if (lj.step_idx !== m.step_idx) ch.push(['bước', lj.step_idx, m.step_idx]);
        if (lj.description !== m.description) ch.push(['mô tả', plain(lj.description, 50), plain(m.description, 50)]);
        diff = h('div', { class: 'sx-diffline small' }, h('b', null, 'Đề xuất gốc LLM → bản cuối: '), ch.length ? ch.map(function (x, i) { return h('span', null, i ? ' · ' : '', x[0] + ': ', h('s', null, String(x[1])), ' → ', h('b', null, String(x[2]))); }) : 'giống đề xuất gốc', ' ', ui.prov('gv'));
      }
      var vd = VERDICT[m.verifier_verdict];
      return h('div', { class: cls, 'data-mistake': m.id },
        h('div', { class: 'spread' }, h('span', { class: 'row', style: 'gap:6px' }, h('b', { class: 'mono' }, '#' + m.id), ui.status(m.status), h('span', { class: 'small' }, 'bước ' + m.step_idx), codeChip(m.code), kcChip(m.kc_id),
          m.confidence != null ? h('span', { class: 'small muted' }, 'tin cậy ' + F.num(m.confidence)) : null, vd ? ui.chip(vd[0], vd[1]) : null),
          newer ? ui.chip('thay bằng #' + newer, 'neutral') : null),
        h('div', { class: newer || m.status === 'rejected' ? 'sx-strike-all' : '' }, tx(m.description)),
        h('div', { class: 'sx-evid' }, h('span', { class: 'small muted' }, 'Bằng chứng: '), tx(m.evidence_latex, true)),
        m.verifier_reason ? h('p', { class: 'small' }, h('span', { class: 'muted' }, '04: '), m.verifier_reason) : null,
        diff,
        m.supersedes_id != null ? h('p', { class: 'small' }, 'Sửa của #' + m.supersedes_id + ' (supersedes_id).') : null,
        m.teacher_note ? h('p', { class: 'small' }, h('b', null, 'Ghi chú GV: '), m.teacher_note) : null,
        m.status === 'rejected' && !newer ? h('p', { class: 'small muted' }, 'Đã bỏ — vẫn lưu để đo độ chính xác.') : null,
        !newer && s.status === 'committed' ? h('div', null, ui.button('Sửa lỗi đã lưu', function () { editSaved(m, a); }, { kind: 'secondary', size: 'sm' })) : null);
    };
    var attEl = function (a) {
      var rub = rubricOf(a), ms = d.mistake.filter(function (m) { return m.attempt_id === a.id; }).sort(function (x, y) { return (x.step_idx - y.step_idx) || (x.id - y.id); });
      var g = arr(a.grade_json), items = rub ? arr(rub.items_json) : [];
      return h('article', { class: 'card sx-att' },
        h('div', { class: 'spread' }, h('h3', null, 'Bài ' + a.seq + ' · ', h('span', { class: 'mono' }, refOf(a.problem_id))),
          h('span', { class: 'row', style: 'gap:6px' }, h('b', { class: 'num' }, a.score + '/' + a.max_score), ui.prov('llm', '02'), rub ? ui.chip('rubric v' + rub.version, 'neutral') : null)),
        h('details', { class: 'sx-details' }, h('summary', null, 'Chấm theo rubric (' + g.filter(function (x) { return x.passed; }).length + '/' + g.length + ' mục đạt)'),
          h('ol', { class: 'sx-grade' }, g.map(function (x) {
            var it = items.find(function (i) { return i.item_id === x.item_id; }) || {};
            return h('li', { class: 'sx-gi' }, h('span', { class: 'sx-tick ' + (x.passed ? 'ok' : 'no') }, x.passed ? '✓' : '✗'),
              h('div', null, h('span', { class: 'mono small muted' }, x.item_id + ' '), tx(it.text || '')), h('span', { class: 'num small' }, (it.points || 1) + ' đ'),
              h('div', { class: 'sx-ev' }, h('span', { class: 'muted' }, 'bằng chứng: '), tx(x.evidence_latex)));
          }))),
        h('details', { class: 'sx-details' }, h('summary', null, 'Bài làm HS (' + arr(a.steps_json).length + ' bước)'),
          h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + code),
            h('ol', { class: 'sx-steps' }, arr(a.steps_json).map(function (x) { return h('li', { class: 'sx-step', 'data-step': x.idx }, h('span', { class: 'sx-step-n' }, String(x.idx)), h('div', null, tx(x.latex, true))); })))),
        ms.length ? h('div', { class: 'stack', style: 'gap:8px' }, ms.map(function (m) { return mistakeEl(m, a); })) : h('p', { class: 'small muted' }, 'Không có lỗi nào được ghi cho bài này.'));
    };
    add(root, 
      ui.pageHead({
        eyebrow: 'Buổi học · ' + (s.status === 'committed' ? 'đã ghi tutor.db (chỉ đọc)' : s.status), title: titleOf(s.held_on, s.student_id),
        annot: ['table:session', 'table:attempt', 'table:mistake', 'file:llm.jsonl'],
        actions: [transcriptBtn(t, s),
          ui.button('Xem hồ sơ', function () { C.nav('students', { student: s.student_id }); }, { kind: 'secondary' }),
          ui.button('Xem lời gọi LLM', function () { C.nav('logs', { thread: s.thread_id }); }, { kind: 'secondary' }),
          ui.button('Về danh sách buổi', function () { C.nav('session'); }, { kind: 'ghost' })]
      }),
      s.status !== 'committed' ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Buổi này chưa ghi vào tutor.db (' + s.status + (s.cancel_note ? ' · ' + s.cancel_note : '') + '). Chỉ có dòng session do ① ghi.'), s.status === 'failed' ? h('p', null, stuckNote()) : null) : null,
      section('Thông tin buổi', { annot: ['table:session'] },
        ui.kv([
          ['Ngày học', F.date(s.held_on)],
          ['Nguồn', h('span', { class: 'row', style: 'gap:6px' }, h('span', { class: 'chip st-file mono' }, s.source_path), ui.chip(s.source_kind, s.source_kind === 'pdf' ? 'warn' : 'neutral'))],
          ['sha256', h('span', { class: 'mono small sx-wrap' }, s.source_sha256)],
          ['thread_id', h('span', { class: 'mono' }, s.thread_id || '—')],
          ['Trạng thái', h('span', { class: 'row', style: 'gap:6px' }, ui.status(s.status), s.committed_at ? h('span', { class: 'small muted' }, 'ghi lúc ' + F.dt(s.committed_at)) : null)],
          ['Thời gian duyệt', s.review_seconds != null ? h('span', { class: 'num' }, mmss(s.review_seconds) + ' (mm:ss)') : '—'],
          ['Chi phí buổi', h('span', { class: 'row', style: 'gap:6px' }, h('b', { class: 'num' }, F.usd(cost)), h('span', { class: 'small muted' }, calls.length + ' lời gọi · ' + F.int(tok) + ' token (vào+ra ' + F.int(tok - cache) + ' · cache ' + F.int(cache) + ')'),
            ui.why(function () {
              var by = {}; calls.forEach(function (c) { by[c.agent] = (by[c.agent] || 0) + (+c.cost_usd || 0); });
              return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'Σ cost_usd của ' + calls.length + ' dòng trong data/logs/llm.jsonl có thread_id = ' + s.thread_id + '.'),
                ui.kv(Object.keys(by).sort().map(function (k) { return ['agent ' + k, F.usd(by[k])]; })), h('p', { class: 'small muted' }, 'Đơn giá giả định cho bản nháp (settings.price_assumption).'));
            }))]
        ])),
      s.status === 'committed' ? h('div', { class: 'grid cols-2' },
        section('knowledge_state', { extra: ui.prov('llm', '05') }, h('p', { class: 'sx-ks' }, s.knowledge_state || '—')),
        section('So với buổi trước', { annot: ['table:skill_event'] }, deltaRows(dv && dv.kcs), codeChips(dv))) : null,
      section('Bài làm và lỗi đã duyệt', { annot: ['table:attempt', 'table:mistake'], right: h('span', { class: 'small muted' }, atts.length + ' bài') },
        h('p', { class: 'small muted' }, 'Trạng thái lỗi: confirmed / edited / rejected / added. Sửa sau khi ghi = dòng mới với supersedes_id; dòng cũ gạch “thay bằng #id”.'),
        atts.length ? atts.map(attEl) : ui.empty('Chưa có bài nào được ghi cho buổi này.')));
    if (p && p.mistake) setTimeout(function () { var el = root.querySelector('[data-mistake="' + p.mistake + '"]'); if (el) { var dt = el.closest('details'); if (dt) dt.open = true; scrollFlash(el); } }, 200);
  }

  App.registerTab('session', {
    title: 'Buổi học',
    render: function (root, ctx) {
      C = ctx; ui = ctx.ui; h = ui.h; F = ui.fmt;
      var cl = [];
      MOUNT = { tid: null, paint: null, onDone: null };
      var mine = MOUNT;
      route(root, ctx.params || {}, cl);
      return function () { cl.forEach(function (fn) { try { fn(); } catch (e) { console.error('[session cleanup]', e); } }); if (MOUNT === mine) MOUNT = null; };
    }
  });
})();
