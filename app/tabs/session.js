/* Buổi học (G1): danh sách buổi, bước 1 nộp bài, bước 2 tiến độ G1 (P1-T11), bước 3 xác nhận cờ (P2-T06),
   bước 4 duyệt lỗi (P3-T05), bước 5 xem trước tiến bộ (P4-T07) + ghi DB + xem buổi đã ghi (P3-T06).
   Routing (params): none → danh sách; step=1 (+ student) → nộp bài; thread=<id> → thread đó ở bước nó đang dừng
   (đã commit → bước 5); session=<id> → buổi đã ghi (chỉ đọc), chưa ghi → về thread của nó. */
(function () {
  'use strict';
  if (!window.App) return;

  var C, ui, h, F;
  var LIST = { student: '' };
  var FORM = { student: '', held_on: '', file: '' };
  var STEPS = [['Nộp bài'], ['Chạy G1'], ['Xác nhận'], ['Duyệt lỗi'], ['Ghi DB']];
  var NODE = { ingest: '01 Ingest', prepare: '02 soạn rubric nháp', mark_waiting: 'đánh dấu chờ xác nhận', gate_confirm_match: 'DỪNG xác nhận khớp bài',
    apply_match: 'áp dụng xác nhận', lane: '02 · 03 · 04 theo bài', queue: 'xếp hàng đề xuất', mark_waiting_review: 'đánh dấu chờ duyệt', gate_review: 'duyệt lỗi',
    profile: '05 tính tiến bộ', mark_waiting_confirm: 'đánh dấu chờ lưu', gate_confirm_commit: 'DỪNG lưu kết quả', commit: '② ghi tutor.db' };
  var FLAG = { low_match: 'khớp bài chưa chắc', no_rubric: 'chưa có rubric', mismatch: 'bản chép ≠ text layer' };
  var GFLAG = { alt_method: 'cách giải khác', schema: 'lỗi schema', missing_item: 'thiếu mục chấm', score_mismatch: 'điểm lệch',
    no_evidence: 'thiếu bằng chứng', bad_code: 'bỏ lỗi: mã tắt', bad_kc: 'bỏ lỗi: KC ngoài bài', bad_step: 'bỏ lỗi: sai bước' };
  var VERDICT = { agree: ['04 đồng ý', 'ok'], disagree: ['04 không đồng ý', 'danger'], wrong_code: ['04: sai mã', 'warn'] };
  // Strip slot per node. runner.py: failed/awaiting → `node` = the node next to run; running → the last finished one (RUN_NEXT).
  var POS = { ingest: 1, prepare: 2, mark_waiting: 3, gate_confirm_match: 3, apply_match: 3, lane: 4, queue: 5, mark_waiting_review: 6, gate_review: 6,
    profile: 7, mark_waiting_confirm: 8, gate_confirm_commit: 8, commit: 9 };
  var RUN_NEXT = { ingest: 2, prepare: 4, mark_waiting: 3, gate_confirm_match: 2, apply_match: 2, lane: 4, queue: 6, mark_waiting_review: 6, gate_review: 7,
    profile: 8, mark_waiting_confirm: 8, gate_confirm_commit: 9, commit: 9 };
  var CAT = { computational: 'Tính toán', conceptual: 'Khái niệm', notational: 'Ký hiệu', presentation: 'Trình bày', other: 'Khác' };  // = catalog.js
  // shortcut: = config review.low_confidence default; the API does not expose settings yet — read it when it does.
  var LOW = 0.6;
  var GROUPS = ['04 phản đối / sai mã', 'tin cậy < ' + LOW, 'còn lại', 'GV thêm'];
  var ST = { accept: 'confirmed', edit: 'edited', reject: 'rejected', add: 'added' };
  var REF = { codes: [], code: {}, kc: {} };  // error codes + KCs, reloaded by every view that shows them

  function arr(x) { return Array.isArray(x) ? x : []; }
  function put(el) { el.replaceChildren.apply(el, Array.prototype.slice.call(arguments, 1).flat(Infinity).filter(function (x) { return x != null && x !== false; })); return el; }
  function today() { return (C.data.meta || {}).today || new Date().toISOString().slice(0, 10); }
  function code(id) { return 'HS-' + String(id).padStart(2, '0'); }  // = config.student_code
  function errText(e) { return (e && e.message) || String(e); }
  function kb(n) { return n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB'; }
  function loading() { return h('p', { class: 'small muted' }, 'Đang tải…'); }
  function section(title, body) {
    return h('section', { class: 'section' }, h('div', { class: 'section-head' }, h('div', null, h('h2', null, title))), body);
  }
  function failBox(e, what) {
    return h('div', { class: 'callout callout-crit', role: 'alert' }, h('strong', null, 'Không tải được ' + what),
      h('p', { class: 'mono small' }, errText(e)), h('div', null, ui.button('Thử lại', function () { C.rerender(); }, { size: 'sm' })));
  }
  function backBtn() { return ui.button('Về danh sách buổi', function () { C.nav('session'); }, { kind: 'ghost' }); }
  function hasTex(s) { return /\$|\\\(|\\\[|\\begin\{/.test(s); }
  // Plain Vietnamese stays text: ui.latex would typeset a string without $…$ as math.
  function tx(s, block) {
    if (s == null || s === '') return h('span', { class: 'muted' }, '—');
    return hasTex(String(s)) ? ui.latex(String(s), { block: !!block }) : h(block ? 'div' : 'span', { class: 'sx-plain' }, String(s));
  }
  function pts(x) { return x == null ? '—' : String(+x); }
  function rubricOk(items) {  // = session._rubric_ok
    return arr(items).length > 0 && items.every(function (i) { return String(i.text || '').trim() && +i.points > 0; });
  }
  function agentBadge(id) { return h('span', { class: 'gn-agent', style: '--ac: var(--a' + id + ')' }, id); }
  function mmss(s) { s = Math.max(0, Math.floor(+s || 0)); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); }
  function refreshQueue() { if (window.TutorApi && TutorApi.refreshQueue) TutorApi.refreshQueue().catch(function () { /* badges only */ }); }
  function refreshCounts() { if (window.TutorApi && TutorApi.refreshCounts) TutorApi.refreshCounts().catch(function () { /* gauge only */ }); }
  function loadRef() {
    return Promise.all([api.get('/catalog/error-codes'), api.get('/catalog/kc')]).then(function (r) {
      REF = { codes: r[0], code: {}, kc: {} };
      r[0].forEach(function (e) { REF.code[e.code] = e; });
      r[1].forEach(function (k) { REF.kc[k.id] = k; });
    });
  }
  function codeChip(c) {
    var e = REF.code[c];
    return h('span', { class: 'chip mono chip-wrap', title: e ? e.description + (e.active ? '' : ' (mã đã tắt)') : 'mã lỗi' }, c || '—');
  }
  function kcName(id) { return id == null ? 'không gắn KC' : (REF.kc[id] || {}).code || 'KC #' + id; }
  function kcChip(id) {
    if (id == null) return ui.chip('không gắn KC — không ảnh hưởng Elo');
    var c = ui.chip(kcName(id), 'info'); c.title = (REF.kc[id] || {}).name || ''; return c;
  }
  // LLM proposal (or llm_json) vs the teacher's final mistake: changed fields only.
  function diffLine(o, f, label) {
    var ch = [['mã', o.code, f.code], ['KC', kcName(o.kc_id), kcName(f.kc_id)], ['bước', o.step_idx, f.step_idx], ['mô tả', o.description, f.description]]
      .filter(function (x) { return String(x[1]) !== String(x[2]); });
    return h('div', { class: 'sx-diffline small' }, h('b', null, label),
      ch.length ? ch.map(function (x, i) { return h('span', null, i ? ' · ' : '', x[0] + ': ', h('s', null, String(x[1])), ' → ', h('b', null, String(x[2]))); })
        : 'không đổi trường nào (chỉ thêm ghi chú)', ' ', ui.prov('gv'));
  }
  function gradeList(items, graded) {
    var g = {}, ids = arr(items).map(function (i) { return i.item_id; }), it = {};
    arr(items).forEach(function (i) { it[i.item_id] = i; });
    arr(graded).forEach(function (x) { g[x.item_id] = x; if (ids.indexOf(x.item_id) < 0) ids.push(x.item_id); });
    if (!arr(graded).length) return ui.empty('02 chưa chấm bài này.');
    return h('ol', { class: 'sx-grade' }, ids.map(function (id) {
      var r = it[id] || {}, x = g[id] || {}, p = +r.points || 0;
      return h('li', { class: 'sx-gi' },
        h('span', { class: 'sx-tick ' + (x.passed ? 'ok' : 'no'), 'aria-label': x.passed ? 'đạt' : 'chưa đạt' }, x.passed ? '✓' : '✗'),
        h('div', null, h('span', { class: 'mono small muted' }, id + ' '), r.text ? tx(r.text) : h('span', { class: 'muted' }, '(mục không có trong rubric)')),
        h('span', { class: 'num small nowrap' }, pts(x.passed ? p : 0) + '/' + pts(p) + ' đ'),
        x.evidence_latex ? h('div', { class: 'sx-ev' }, h('span', { class: 'muted' }, 'bằng chứng: '), tx(x.evidence_latex)) : null);
    }));
  }
  function stepList(steps, who) {
    return h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + who),
      h('ol', { class: 'sx-steps' }, arr(steps).map(function (s) {
        return h('li', { class: 'sx-step', 'data-step': s.idx }, h('span', { class: 'sx-step-n' }, String(s.idx)), h('div', { class: 'sx-step-body' }, tx(s.latex, true)));
      })));
  }
  function clip(s, n) { s = String(s || '').replace(/\s+/g, ' '); return s.length > n ? s.slice(0, n - 1) + '…' : s; }

  // Sửa / thêm lỗi: only active codes grouped by category, KC = the problem's KCs or none (server re-checks both).
  function mistakeForm(o) {
    var on = {};
    var selCode = h('select', { 'aria-label': 'Mã lỗi' }, h('option', { value: '' }, 'Chọn mã lỗi…'));
    Object.keys(CAT).forEach(function (cat) {
      var cs = REF.codes.filter(function (e) { return e.category === cat && e.active; });
      cs.forEach(function (e) { on[e.code] = 1; });
      if (cs.length) selCode.append(h('optgroup', { label: CAT[cat] + ' · ' + cat }, cs.map(function (e) { return h('option', { value: e.code }, e.code + ' — ' + e.description); })));
    });
    selCode.value = on[o.init.code] ? o.init.code : '';
    var kcs = arr(o.kcs);
    var selKc = h('select', { 'aria-label': 'KC' }, h('option', { value: '' }, 'không gắn KC (không ảnh hưởng Elo)'),
      kcs.map(function (k) { return h('option', { value: String(k.id) }, k.code + ' · ' + k.name); }));
    selKc.value = kcs.some(function (k) { return k.id === o.init.kc_id; }) ? String(o.init.kc_id) : '';
    var selStep = h('select', { 'aria-label': 'Bước' }, arr(o.steps).map(function (s) { return h('option', { value: String(s.idx) }, 'Bước ' + s.idx + ': ' + clip(s.latex, 60)); }));
    selStep.value = String(o.init.step_idx);
    var desc = h('textarea', { rows: 3, 'aria-label': 'Mô tả', placeholder: 'Mô tả lỗi (có thể dùng $…$)', autofocus: !!o.noStep });
    desc.value = o.init.description || '';
    var note = h('textarea', { rows: 2, 'aria-label': 'Ghi chú GV', placeholder: 'Ghi chú của thầy/cô (không bắt buộc)' });
    note.value = o.init.teacher_note || '';
    var hint = h('span', { class: 'small muted', role: 'status' });
    var sug = o.suggested && on[o.suggested];
    C.modal({
      title: o.title,
      body: h('div', { class: 'stack' },
        o.lead ? h('p', { class: 'small muted' }, o.lead) : null,
        h('label', { class: 'field' }, h('span', null, 'Mã lỗi (chỉ mã đang bật, theo 5 nhóm)'), selCode),
        sug ? h('div', { class: 'row' }, ui.button('Dùng mã 04 gợi ý: ' + o.suggested, function () {
          selCode.value = o.suggested; hint.textContent = 'Đã chọn mã 04 gợi ý ✓';
        }, { kind: 'ghost', size: 'sm' }), hint) : null,
        h('label', { class: 'field' }, h('span', null, 'KC (chỉ KC của bài này, hoặc không gắn)'), selKc),
        o.noStep ? null : h('label', { class: 'field' }, h('span', null, 'Bước trong bài làm HS'), selStep),
        h('label', { class: 'field' }, h('span', null, 'Mô tả'), desc),
        h('label', { class: 'field' }, h('span', null, 'Ghi chú GV'), note)),
      actions: [{ label: 'Huỷ' }, { label: o.saveLabel, kind: 'primary', onClick: function (close) {
        if (!selCode.value) { C.toast('Chọn một mã lỗi đang bật.', { kind: 'warn' }); selCode.focus(); return; }
        if (!desc.value.trim()) { C.toast('Cần mô tả lỗi.', { kind: 'warn' }); desc.focus(); return; }
        var r = o.onSave({ code: selCode.value, kc_id: selKc.value === '' ? null : +selKc.value, step_idx: o.noStep ? o.init.step_idx : +selStep.value,
          description: desc.value.trim(), teacher_note: note.value.trim() });
        if (r !== false) close();
      } }]
    });
  }

  /* ---------- stepper + G1 strip ---------- */
  function stepper(cur, o) {
    o = o || {};
    return h('ol', { class: 'sx-stepper', 'aria-label': 'Các bước G1' }, STEPS.map(function (s, i) {
      var n = i + 1, skip = n === 3 && o.skip3 && cur > 3;
      var cls = n < cur ? (skip ? 'is-skip' : 'is-done') : n === cur ? (o.failed ? 'is-fail' : 'is-cur') : s[1] ? 'is-later' : '';
      return h('li', { class: cls, 'aria-current': n === cur ? 'step' : null },
        h('span', { class: 'sx-num', 'aria-hidden': 'true' }, n < cur && !skip ? '✓' : o.failed && n === cur ? '✕' : String(n)),
        h('span', null, s[0], n === 3 ? h('small', null, skip ? ' · bỏ qua, không có cờ' : ' · chỉ khi có cờ') : s[1] ? h('small', null, ' · làm ở ' + s[1]) : null));
    }));
  }
  function g1States(t, state) {
    var s = t.status, cur = s === 'running' ? RUN_NEXT[t.node] || 1 : s === 'committed' ? 10 : POS[t.node] || 1;
    var ing = state && state.ingest, st = ['done'];  // slot 0 = ① session row, written before the graph starts
    for (var k = 1; k <= 9; k++) st[k] = k < cur ? 'done' : k === cur ? (s === 'failed' ? 'failed' : 'current') : '';
    if (cur === 2 && POS[t.node] === 3) st[3] = 'done';  // resumed past the gate: prepare re-checks the answers
    if (st[3] === 'done' && ing && !arr(ing.flags).length) st[3] = 'skip';
    return st;
  }
  function g1Strip(t, compact, state) {
    var st = t ? g1States(t, state) : [], n = state && state.ingest ? arr(state.ingest.attempts).length : 0;
    var node = function (label, kind, agent, state, sub) {
      return h('div', { class: 'gn gn-' + kind + (state ? ' is-' + state : ''), title: label },
        h('span', { class: 'gn-top' }, agent ? agentBadge(agent) : null, agent ? label.slice(3) : label),
        sub ? h('span', { class: 'gn-sub' }, sub) : null, kind === 'stop' ? h('span', { class: 'gn-wait' }) : null);
    };
    var arrow = function () { return h('span', { class: 'strip-arrow', 'aria-hidden': 'true' }, '→'); };
    var slots = [['① ghi session', 'code', null, 'tutor.db'], ['01 Ingest', 'llm', '01', 'cắt bài · khớp mã'], ['02 rubric nháp', 'llm', '02', 'bài chưa có rubric'],
      ['DỪNG xác nhận khớp', 'stop', null, st[3] === 'skip' ? 'bỏ qua: không có cờ' : 'chỉ khi có cờ'],
      ['02 · 03 · 04 theo bài', 'llm', null, n ? n + ' bài, chạy song song' : 'mỗi bài một làn'], ['xếp hàng đề xuất', 'code', null, '04 phản đối lên đầu'],
      ['DỪNG duyệt lỗi', 'stop', null, 'bước 4'], ['05 Profiler', 'code', '05', 'tính tiến bộ · chưa ghi'], ['DỪNG lưu kết quả', 'stop', null, 'bước 5'],
      ['② ghi tutor.db', 'commit', null, 'sao lưu → 1 transaction']];
    return h('div', { class: 'strip sx-strip' + (compact ? ' strip-compact' : '') },
      h('div', { class: 'strip-head' }, ui.chip('G1', 'G1'), h('span', { class: 'mono' }, 'session_graph'), h('span', null, 'Buổi học')),
      h('div', { class: 'strip-flow' },
        slots.map(function (x, i) { return [i ? arrow() : null, node(x[0], x[1], x[2], st[i], x[3])]; })));
  }

  /* ---------- danh sách buổi ---------- */
  function viewList(root, life) {
    var body = h('div', { class: 'stack' }, loading());
    root.append(
      ui.pageHead({
        lead: 'Sau mỗi buổi: chép file .tex bài làm vào data/inbox/, nộp ở bước 1 → G1 ghi dòng session, cắt bài, chấm, chẩn đoán rồi dừng chờ thầy/cô duyệt lỗi; duyệt xong mới ghi tutor.db.',
        actions: [ui.button('Nộp bài mới', function () { C.nav('session', { step: 1 }); }, { kind: 'primary' })]
      }),
      section('Danh sách buổi', body));
    function load() {
      Promise.all([api.get('/students'), api.get('/sessions' + (LIST.student ? '?student=' + LIST.student : ''))])
        .then(function (r) { if (life.alive) paint(r[0], r[1]); }, function (e) { if (life.alive) put(body, failBox(e, 'danh sách buổi')); });
    }
    function paint(students, rows) {
      var sel = h('select', { 'aria-label': 'Học sinh', onchange: function () { LIST.student = sel.value; put(body, loading()); load(); } },
        h('option', { value: '' }, 'Tất cả học sinh'),
        students.map(function (s) { return h('option', { value: String(s.id) }, s.code + ' · ' + s.name); }));
      sel.value = LIST.student;
      var open = function (s) { C.nav('session', s.status === 'committed' ? { session: s.id } : { thread: s.thread_id }); };
      put(body,
        h('div', { class: 'spread sx-listbar' }, h('label', { class: 'field sx-filter' }, h('span', null, 'Học sinh'), sel), h('span', { class: 'small muted' }, rows.length + ' buổi')),
        ui.table({
          rows: rows, onRow: open,
          empty: LIST.student ? 'Học sinh này chưa có buổi nào.' : students.length ? 'Chưa có buổi nào. Bấm “Nộp bài mới” để nộp bài đầu tiên.'
            : 'Chưa có học sinh và buổi nào. Thêm học sinh ở tab Học sinh, chép file .tex vào data/inbox/, rồi bấm “Nộp bài mới”.',
          columns: [
            { label: 'HS', render: function (s) { return h('b', { class: 'mono nowrap' }, s.student_code); } },
            { label: 'Ngày học', render: function (s) { return h('span', { class: 'num nowrap' }, F.date(s.held_on)); } },
            { label: 'File', render: function (s) {
              return h('span', { class: 'row sx-cell' }, h('span', { class: 'mono small sx-wrap' }, String(s.source_path).replace(/^data\/inbox\//, '')),
                s.source_kind === 'pdf' ? ui.chip('PDF', 'warn') : null);
            } },
            { label: 'Trạng thái', render: function (s) { return ui.status(s.status); } },
            { label: 'thread_id', render: function (s) { return h('span', { class: 'mono small muted sx-wrap' }, s.thread_id || '—'); } },
            { label: '', render: function (s) { return ui.button('Mở', function () { open(s); }, { size: 'sm' }); } }
          ]
        }));
    }
    load();
  }

  /* ---------- bước 1: nộp bài ---------- */
  function viewSubmit(root, life) {
    if (!FORM.held_on) FORM.held_on = today();
    var body = h('div', { class: 'stack' }, loading()), students = [], inbox = [], dup = null;
    root.append(
      ui.pageHead({
        eyebrow: 'Buổi học · bước 1', title: 'Nộp bài',
        lead: 'Chọn học sinh, ngày học và file bài làm trong data/inbox/. “Bắt đầu xử lý” ghi dòng session rồi cho G1 chạy nền; trang chuyển sang bước 2 để theo dõi.'
      }),
      stepper(1),
      h('div', { class: 'grid cols-2 sx-submit' }, section('1 · Nộp bài', body),
        section('Bấm “Bắt đầu xử lý” thì sao?', h('div', { class: 'stack' },
          h('ol', { class: 'sx-howto' },
            h('li', null, '① Ghi ngay 1 dòng session (status running, thread_id) vào tutor.db. File trùng sha256 hoặc ngày học sớm hơn buổi đã ghi thì bị chặn.'),
            h('li', null, '01 Ingest cắt từng bài theo \\begin{problem}[mã], tách bước theo dòng, khớp mã bài với ngân hàng.'),
            h('li', null, 'Bài không ghi mã → 01 hỏi LLM tìm bài giống nhất. Khớp chưa chắc hoặc bài chưa có rubric → cờ, G1 DỪNG chờ xác nhận (bước 3).'),
            h('li', null, 'Hết cờ → mỗi bài một làn 02 Chấm · 03 Chẩn đoán · 04 Phản biện, rồi G1 DỪNG chờ duyệt lỗi (bước 4).')),
          g1Strip(null, true)))));
    function load() {
      put(body, loading());
      Promise.all([api.get('/students'), api.get('/sessions/inbox')]).then(function (r) {
        if (!life.alive) return;
        students = r[0]; inbox = r[1];
        var want = C.params.student, ps = want && students.find(function (s) { return String(s.id) === want || s.code === want; });
        if (ps) FORM.student = String(ps.id);
        if (!students.some(function (s) { return String(s.id) === FORM.student; })) FORM.student = '';
        if (!inbox.some(function (f) { return f.path === FORM.file && f.kind === 'tex'; })) FORM.file = '';
        draw();
      }, function (e) { if (life.alive) put(body, failBox(e, 'học sinh / data/inbox/')); });
    }
    function pick(path) { FORM.file = path; dup = null; draw(); }
    function fileRow(f) {
      var pdf = f.kind === 'pdf', on = f.path === FORM.file, by = arr(f.submitted_by).map(code);
      return h('div', { class: 'st-file sx-file-row' + (on ? ' is-picked' : '') + (pdf ? ' is-off' : '') },
        h('span', { class: 'mono sx-wrap' }, f.path), pdf ? ui.chip('PDF', 'warn') : ui.chip('tex'),
        h('span', { class: 'small muted nowrap' }, kb(f.bytes)),
        h('span', { class: 'mono small muted nowrap', title: 'sha256 ' + f.sha256 }, 'sha256 ' + f.sha256.slice(0, 8)),
        by.length ? ui.chip('đã nộp cho ' + by.join(', '), 'info') : null,
        pdf ? ui.button('Chọn', null, { size: 'sm', disabledReason: 'Nhánh PDF chưa làm (P1-T09)' })
          : on ? ui.chip('đã chọn', 'ok') : ui.button('Chọn', function () { pick(f.path); }, { size: 'sm' }));
    }
    function draw() {
      var hs = FORM.student ? code(FORM.student) : null, file = inbox.find(function (f) { return f.path === FORM.file; });
      var stuSel = h('select', { 'aria-label': 'Học sinh', onchange: function () { FORM.student = stuSel.value; dup = null; draw(); } },
        h('option', { value: '' }, 'Chọn học sinh…'),
        students.map(function (s) { return h('option', { value: String(s.id) }, s.code + ' · ' + s.name + (s.grade ? ' · lớp ' + s.grade : '')); }));
      stuSel.value = FORM.student;
      var date = h('input', { type: 'date', 'aria-label': 'Ngày học', value: FORM.held_on, onchange: function () { FORM.held_on = date.value; dup = null; } });
      var again = file && hs && arr(file.submitted_by).indexOf(+FORM.student) >= 0;
      put(body,
        students.length ? null : h('div', { class: 'callout callout-warn' }, h('strong', null, 'Chưa có học sinh nào'),
          h('p', null, 'Thêm học sinh ở ', h('a', { href: '#students', 'data-tab-link': 'students' }, 'tab Học sinh'), ' trước, rồi quay lại đây.')),
        h('div', { class: 'grid cols-2' },
          h('label', { class: 'field' }, h('span', null, 'Học sinh'), stuSel,
            h('span', { class: 'small muted' }, hs ? 'API chỉ nhận mã ' + hs + ', tên không rời máy.' : 'Tên chỉ lưu trên máy; API chỉ nhận mã HS.')),
          h('label', { class: 'field' }, h('span', null, 'Ngày học'), date)),
        h('div', { class: 'field' }, h('span', null, 'File trong data/inbox/ ', ui.store('file')),
          inbox.length ? h('div', { class: 'sx-files' }, inbox.map(fileRow))
            : h('div', { class: 'callout callout-info' }, h('strong', null, 'Chưa có file nào trong data/inbox/'),
              h('p', null, 'Chép file .tex bài làm của học sinh vào thư mục data/inbox/ trong thư mục dữ liệu của app, rồi bấm Tải lại.'),
              h('div', null, ui.button('Tải lại', load, { size: 'sm' })))),
        dup ? h('div', { class: 'callout callout-crit', role: 'alert' }, h('strong', null, 'Đã chặn: trùng sha256'),
          h('p', null, 'File này đã nộp cho ' + dup.code + ' ở buổi #' + dup.session_id + '. Mỗi học sinh chỉ nộp một file một lần.'),
          h('div', null, ui.button('Mở buổi đã nộp', function () { C.nav('session', { thread: dup.thread_id }); }, { size: 'sm' })))
          : again ? h('div', { class: 'callout callout-warn' }, h('p', null, 'File này đã nộp cho ' + hs + ' — nộp lại sẽ bị chặn (trùng sha256).')) : null,
        h('div', { class: 'row sx-actions' }, ui.button('Bắt đầu xử lý', submit, { kind: 'primary', privacy: hs || undefined }), backBtn()));
    }
    function submit(ev, b) {
      if (!FORM.student) { C.toast('Chọn học sinh trước.', { kind: 'warn' }); return; }
      if (!FORM.file) { C.toast('Chọn một file .tex trong data/inbox/ trước.', { kind: 'warn' }); return; }
      if (!FORM.held_on) { C.toast('Chọn ngày học trước.', { kind: 'warn' }); return; }
      b.disabled = true; b.textContent = 'Đang gửi…';
      var sid = FORM.student;
      api.send('POST', '/sessions', { student_id: +sid, held_on: FORM.held_on, path: FORM.file }).then(function (r) {
        C.toast('① Đã ghi buổi #' + r.session_id + ' (đang chạy) · thread ' + r.thread_id, { kind: 'ok' });
        TutorApi.refreshCounts().catch(function () { /* gauge only; next refresh fixes it */ });
        FORM.file = '';
        if (life.alive) C.nav('session', { thread: r.thread_id });
      }, function (e) {
        if (e.code === 'duplicate_submission') {
          var d = e.detail || {};
          C.toast('File này đã nộp cho ' + code(sid) + ' (trùng sha256), buổi #' + d.session_id + '.', { kind: 'error', title: 'Đã chặn nộp trùng' });
          dup = { code: code(sid), session_id: d.session_id, thread_id: d.thread_id };
        } else C.toast(errText(e), { kind: 'error', title: e.status ? 'Không nộp được (' + e.status + ')' : 'Không gọi được máy chủ' });
        if (life.alive) draw();
      });
    }
    load();
  }

  /* ---------- bước 2: tiến độ G1 ---------- */
  function openTranscript(text, t) {
    C.modal({
      title: 'Bản chép LaTeX · ' + t.thread_id, wide: true,
      body: function (el) {
        el.append(
          h('p', { class: 'small muted' }, 'File .tex gốc học sinh nộp, hiển thị nguyên văn (không chạy công thức). 01 cắt bài theo \\begin{problem}[mã], tách bước theo dòng.'),
          h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · bài làm học sinh'),
            h('pre', { class: 'code' }, String(text))));
      },
      actions: [{ label: 'Đóng' }]
    });
  }
  function statusText(t) {
    if (t.status === 'awaiting_review') return t.node === 'gate_review' ? 'DỪNG ở duyệt lỗi (bước 4)' : t.node === 'gate_confirm_commit' ? 'DỪNG ở lưu kết quả (bước 5)' : 'DỪNG ở xác nhận khớp bài (bước 3)';
    if (t.status === 'running' && RUN_NEXT[t.node] === 9) return '② đang sao lưu và ghi tutor.db';
    return {
      running: t.node ? 'xong ' + (NODE[t.node] || t.node) + ', đang chạy bước kế' : 'đang chạy 01 Ingest',
      failed: 'G1 dừng vì lỗi ở ' + (NODE[t.node] || t.node || '01 Ingest'),
      committed: 'đã ghi tutor.db (bước 5)'
    }[t.status] || t.status;
  }
  function results(state) {
    var ing = state.ingest;
    if (!ing) return h('p', { class: 'small muted' }, '01 Ingest chưa có kết quả.');
    var flags = arr(ing.flags);
    return h('div', { class: 'stack' },
      h('h3', null, '01 cắt được ' + arr(ing.attempts).length + ' bài'),
      ui.table({
        rows: arr(ing.attempts), empty: 'Không cắt được bài nào.',
        columns: [
          { label: 'Bài', align: 'right', render: function (a) { return String(a.seq); } },
          { label: 'Mã bài', render: function (a) { return a.ref ? h('span', { class: 'mono nowrap' }, a.ref) : ui.chip('chưa khớp', 'warn'); } },
          { label: 'Số bước', align: 'right', render: function (a) { return String(arr(a.steps).length); } },
          { label: 'Ứng viên (điểm)', render: function (a) {
            return arr(a.candidates).length ? h('span', { class: 'row sx-cell' }, a.candidates.map(function (c) { return ui.chip(c.ref + ' · ' + F.num(c.score)); }))
              : h('span', { class: 'muted' }, '—');
          } }
        ]
      }),
      h('h3', null, 'Cờ'),
      flags.length ? h('ul', { class: 'sx-flags' }, flags.map(function (f) {
        return h('li', null, ui.chip(FLAG[f.type] || f.type, 'warn'), h('span', { class: 'mono small muted' }, f.type),
          h('span', null, f.detail), f.resolved ? ui.chip('đã xử lý', 'ok') : null);
      }))
        : h('p', { class: 'small muted' }, 'Không có cờ: mọi bài khớp mã trong ngân hàng và đã có rubric.'));
  }
  // Student's own text of one problem: transcript[pos:pos_end] without the \begin{problem}[ref] … \end{problem} wrapper.
  function workBox(state, a, who) {
    var src = String(state.transcript || '').slice(a.pos, a.pos_end).replace(/\\begin\{problem\}(\[[^\]]*\])?|\\end\{problem\}/g, '');
    var lines = src.split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    if (!lines.length) lines = arr(a.steps).map(function (s) { return s.latex; });
    return h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + who + ' · bài ' + a.seq),
      h('ol', { class: 'sx-steps' }, lines.map(function (l, i) {
        return h('li', { class: 'sx-step' }, h('span', { class: 'sx-step-n' }, String(i + 1)), h('div', { class: 'sx-step-body' }, tx(l, true)));
      })));
  }
  function rubricList(items) {
    return h('div', { class: 'stack sx-rublist' },
      h('ol', { class: 'sx-grade' }, arr(items).map(function (it) {
        return h('li', { class: 'sx-gi' }, h('span', { class: 'mono small muted' }, it.item_id), h('div', null, tx(it.text)), h('span', { class: 'num small nowrap' }, pts(it.points) + ' đ'));
      })),
      h('div', { class: 'row small' }, 'Tổng: ', h('b', { class: 'num' }, pts(arr(items).reduce(function (s, i) { return s + (+i.points || 0); }, 0))), ' điểm = max_score', ui.prov('code')));
  }

  function viewThread(root, life, tid) {
    var top = h('div', { class: 'stack' }), body = h('div', { class: 'stack' }, loading()), t = null, state = {}, shown = '', bank = null;
    var RV = null, committing = false, lockEl = null;  // RV: step-4 refs + UI state, kept across repaints
    root.append(top, body);
    put(top, ui.pageHead({ eyebrow: 'Buổi học', title: 'Thread ' + tid }), stepper(2));
    var path = '/threads/' + encodeURIComponent(tid);
    function fail(e) {
      if (!life.alive) return;
      put(body, e && e.status === 404
        ? h('div', { class: 'callout callout-warn' }, h('strong', null, 'Không tìm thấy thread ' + tid), h('p', null, 'Có thể đã bị huỷ hoặc dọn khỏi checkpoints.db.'), h('div', null, backBtn()))
        : failBox(e, 'thread'));
    }
    function full() {
      api.get(path + '?include=state').then(function (r) { if (!life.alive) return; state = r.state || {}; next(r, true); }, fail);
    }
    function poll() {
      api.get(path).then(function (r) { if (!life.alive) return; if (r.status === 'running') next(r); else full(); }, fail);
    }
    function next(r, force) {
      t = r;
      if (committing && t.status !== 'running') landed();
      if (force || shown !== t.status + '|' + t.node) paint();
      if (t.status === 'running') life.timer = setTimeout(poll, 1000);
    }
    // Gate: continue with the saved decisions. Failed: rerun from the last checkpoint.
    function resume() {
      return api.send('POST', path + '/resume').then(function (r) { refreshQueue(); if (life.alive) full(); return r; });
    }
    // Commit ② finished (or failed) after "Lưu kết quả" in this view.
    function landed() {
      committing = false;
      refreshQueue();
      if (t.status === 'awaiting_review' && t.node === 'gate_confirm_commit') {  // another session of this student was saved first: nothing written
        C.toast('Hồ sơ của học sinh vừa đổi (buổi khác đã lưu). Đã tính lại bản xem trước, chưa lưu gì.', { kind: 'warn', title: 'Chưa lưu', ms: 6500 });
        return;
      }
      if (t.status !== 'committed') return;
      refreshCounts();
      var rc = t.receipt || {};
      if (rc.backup) C.toast('Đã sao lưu data/backup/' + rc.backup, { kind: 'info' });
      if (rc.by_status) C.toast(receiptLine(rc), { kind: 'ok', title: 'Đã ghi ' + (t.subject || t.thread_id) + ' → tutor.db', ms: 6500 });
    }
    function paint() {
      shown = t.status + '|' + t.node;
      life.flush = null;
      if (life.off) { life.off(); life.off = null; }
      if (t.status === 'awaiting_review' && t.node === 'gate_confirm_match') paintConfirm();
      else if (t.status === 'awaiting_review' && t.node === 'gate_review') paintReview();
      else if (t.status === 'awaiting_review' && t.node === 'gate_confirm_commit') paintPreview();
      else if (t.status === 'committed') paintDone();
      else paintProgress();
      C.tex(body);
    }
    // C-28: an earlier session of this student is not committed yet → resume answers 409 date_order_locked.
    function lockBox() {
      return t.locked ? h('div', { class: 'callout callout-warn', role: 'status' }, h('strong', null, 'Buổi này đang bị khoá'),
        h('p', null, t.lock_reason || 'Buổi sớm hơn của học sinh này chưa ghi tutor.db.'),
        t.blocking_thread_id ? h('div', null, ui.button('Mở buổi chặn', function () { C.nav('session', { thread: t.blocking_thread_id }); }, { size: 'sm' })) : null) : null;
    }
    function lockFrom(e) {
      t.locked = true; t.lock_reason = e.message;
      t.blocking_thread_id = (e.detail || {}).blocking_thread_id || t.blocking_thread_id;
      if (lockEl) put(lockEl, lockBox());
    }
    function srcLine() {
      return h('div', { class: 'row sx-src' },
        state.source_path ? h('span', { class: 'chip st-file mono sx-wrap' }, state.source_path) : null,
        state.source_kind ? ui.chip(state.source_kind) : null,
        t.session_id != null ? h('span', { class: 'small muted' }, 'buổi #' + t.session_id) : null,
        h('span', { class: 'mono small muted sx-wrap' }, 'thread ' + t.thread_id));
    }
    function tools() {
      return h('div', { class: 'row' }, ui.button('Xem bản chép LaTeX', function () { openTranscript(state.transcript, t); },
        { kind: 'secondary', disabledReason: state.transcript ? null : t.status === 'running' ? '01 Ingest chưa chép xong' : 'thread không có bản chép' }), backBtn());
    }

    function paintProgress() {
      put(top, ui.pageHead({
        eyebrow: 'Buổi học · bước 2 · G1', title: t.subject || t.thread_id,
        lead: 'Graph chạy nền trong app; trang tự cập nhật mỗi giây khi G1 còn chạy.'
      }), stepper(2, { failed: t.status === 'failed' }));
      put(body,
        section('2 · Chạy G1', h('div', { class: 'stack' },
          srcLine(),
          h('div', { class: 'row sx-now', role: 'status' }, ui.status(t.status), h('span', null, statusText(t)),
            h('span', { class: 'small muted' }, 'node cuối: ', h('span', { class: 'mono' }, t.node || '—'), ' · cập nhật ' + F.dt(t.updated_at))),
          g1Strip(t, false, state),
          t.status === 'failed' ? h('div', { class: 'callout callout-crit', role: 'alert' },
            h('strong', null, 'Lỗi ở ' + (NODE[t.node] || t.node || '01 Ingest')),
            h('pre', { class: 'code sx-err' }, t.error || '—'),
            h('p', { class: 'small' }, 'Các node đã xong vẫn giữ trong checkpoints.db; chạy lại chỉ chạy node lỗi và các node sau. Buổi này mang status failed tới khi chạy lại.'),
            h('div', null, ui.button('Chạy lại từ checkpoint', retry, { kind: 'primary', privacy: code(t.student_id) }))) : null,
          t.status === 'running' ? null : results(state),
          tools())),
        section('Bước sau', h('ul', { class: 'sx-later-notes' },
          h('li', null, h('b', null, '4 · Duyệt lỗi'), ': thầy/cô chấp nhận / sửa / bỏ từng lỗi 03 đề xuất, thêm lỗi bị sót.'),
          h('li', null, h('b', null, '5 · Lưu kết quả'), ': 05 Profiler tính tiến bộ để thầy/cô xem trước; bấm “Lưu kết quả” thì ② sao lưu tutor.db rồi ghi 1 transaction.'))));
    }
    function retry(ev, b) {
      b.disabled = true; b.textContent = 'Đang gửi…';
      return resume().then(function () {
        C.toast('Chạy lại ' + t.thread_id + ' từ checkpoint: chỉ node lỗi và các node sau.', { kind: 'info' });
      }, function (e) {
        C.toast(errText(e), { kind: 'error', title: 'Không chạy lại được' + (e.status ? ' (' + e.status + ')' : '') });
        if (life.alive) full();
      });
    }

    /* ---------- bước 3: xác nhận cờ (DỪNG confirm_match) ---------- */
    function paintConfirm() {
      var ing = state.ingest || {}, open = arr(ing.flags).filter(function (f) { return !f.resolved; }), atts = {}, who = code(t.student_id);
      arr(ing.attempts).forEach(function (a) { atts[a.seq] = a; });
      if (!bank && open.some(function (f) { return f.type === 'low_match'; })) {
        put(body, loading());
        api.get('/bank/problems?limit=100000').then(function (rows) {
          if (!life.alive) return;
          bank = {}; rows.forEach(function (p) { bank[p.ref] = p; });
          paintConfirm(); C.tex(body);
        }, fail);
        return;
      }
      var DEC = {}, EDIT = {}, cardEls = {}, timer = null, saveMsg = '';
      try { var saved = JSON.parse(t.decisions_json || '{}'); if (saved && typeof saved === 'object' && !Array.isArray(saved)) DEC = saved; } catch (e) { /* unreadable → start empty */ }
      var seqs = open.map(function (f) { return f.seq; }).filter(function (s, i, a) { return a.indexOf(s) === i; }).sort(function (a, b) { return a - b; });
      var bar = h('div', { class: 'row sx-actbar' });

      function ok(f) { var d = DEC[f.seq] || {}; return f.type === 'low_match' ? !!d.problem_ref : rubricOk(d.rubric_items); }
      function left() { return open.filter(function (f) { return !ok(f); }).length; }
      function dec(seq) { return DEC[seq] || (DEC[seq] = {}); }
      // PUT replaces the saved object, so always the whole DEC.
      function save() {
        clearTimeout(timer); timer = null;
        Object.keys(DEC).forEach(function (k) { if (!Object.keys(DEC[k] || {}).length) delete DEC[k]; });
        saveMsg = 'Đang lưu…'; if (life.alive) paintBar();
        return api.send('PUT', path + '/decisions', DEC).then(function (r) {
          saveMsg = 'Đã lưu ' + new Date().toTimeString().slice(0, 8); if (life.alive) paintBar(); return r;
        }, function (e) { saveMsg = 'Chưa lưu được: ' + errText(e); if (life.alive) paintBar(); throw e; });
      }
      function changed() {
        clearTimeout(timer);
        timer = setTimeout(function () { save().catch(function () { /* saveMsg already shows it */ }); }, 500);
        paintBar();
      }
      life.flush = function () { if (timer) save().catch(function () { /* page is gone */ }); };
      function repaint(seq) {
        var n = card(seq);
        cardEls[seq].replaceWith(n); cardEls[seq] = n; C.tex(n);
        paintBar();
      }
      function go(ev, b) {
        b.disabled = true; b.textContent = 'Đang gửi…';
        return save().then(function (r) {
          if (r.pending) { C.toast('Còn ' + r.pending + ' cờ chưa xử lý.', { kind: 'warn' }); paintBar(); return; }
          return resume().then(function () { C.toast('Chạy tiếp từ DỪNG xác nhận: 02 · 03 · 04 cho từng bài.', { kind: 'info' }); });
        }).catch(function (e) {
          if (e.code === 'date_order_locked') lockFrom(e);
          C.toast(e.code === 'undecided_items' ? 'Còn ' + (e.detail || {}).n + ' cờ chưa xử lý.' : errText(e),
            { kind: 'warn', title: 'Chưa chạy tiếp được' + (e.status ? ' (' + e.status + ')' : '') });
          if (life.alive) paintBar();
        });
      }
      function pause(ev, b) {
        b.disabled = true;
        return save().then(function () {
          C.toast('Đã lưu ' + (open.length - left()) + '/' + open.length + ' cờ. Buổi vẫn chờ xác nhận; mở lại từ danh sách buổi.', { kind: 'ok' });
          if (life.alive) C.nav('session');
        }, function (e) { C.toast(errText(e), { kind: 'error', title: 'Chưa lưu được' }); if (life.alive) paintBar(); });
      }
      function paintBar() {
        var n = left();
        put(bar,
          h('span', { class: 'small' }, 'Đã xử lý ', h('b', { class: 'num' }, (open.length - n) + '/' + open.length), ' cờ'),
          ui.button('Chạy tiếp', go, { kind: 'primary', privacy: who, disabledReason: t.locked ? t.lock_reason || 'buổi đang bị khoá' : n ? 'còn ' + n + ' cờ chưa xử lý' : null }),
          ui.button('Tạm dừng, duyệt sau', pause, { kind: 'secondary' }),
          saveMsg ? h('span', { class: 'small muted', role: 'status' }, saveMsg) : null);
      }

      function lowMatch(f, a) {
        var d = DEC[f.seq] || {}, picked = d.problem_ref, refs = arr(a.candidates).slice(0, 3).map(function (c) { return c.ref; });
        var score = {};
        arr(a.candidates).forEach(function (c) { score[c.ref] = c.score; });
        if (picked && refs.indexOf(picked) < 0) refs.push(picked);
        var choose = function (ref) { dec(f.seq).problem_ref = ref; changed(); repaint(f.seq); };
        var note = h('input', { type: 'text', value: d.note || '', placeholder: 'vd: đề trong vở khác số liệu', 'aria-label': 'Lý do bài ' + f.seq });
        note.addEventListener('input', function () {
          var v = note.value.trim();
          if (v) dec(f.seq).note = v; else if (DEC[f.seq]) delete DEC[f.seq].note;
          changed();
        });
        return [
          h('p', null, f.detail),
          h('fieldset', { class: 'sx-cands' }, h('legend', { class: 'small muted' }, 'Bài này khớp bài nào trong ngân hàng?'),
            refs.length ? refs.map(function (ref) {
              var p = bank[ref], on = picked === ref, s = score[ref];
              return h('label', { class: 'card sx-cand' + (on ? ' is-picked' : '') },
                h('span', { class: 'row sx-cell' },
                  h('input', { type: 'radio', name: 'lm-' + f.seq, value: ref, checked: on, onchange: function () { choose(ref); } }),
                  h('b', { class: 'mono' }, ref),
                  s != null ? h('span', { class: 'sx-conf' }, 'độ khớp', ui.bar(s, 1, { kind: s >= 0.8 ? 'ok' : 'warn' }), h('b', { class: 'num' }, F.num(s)), ui.prov('llm', '01')) : ui.prov('gv', 'GV tìm'),
                  p && !p.has_rubric ? ui.chip('chưa có rubric: 02 soạn nháp, G1 dừng lại để duyệt', 'warn') : null,
                  on ? ui.chip('đã chọn', 'ok') : null),
                p ? tx(p.statement_latex, true) : h('span', { class: 'small muted' }, 'Không thấy bài này trong ngân hàng.'));
            }) : h('p', { class: 'small muted' }, '01 không tìm được ứng viên nào. Bấm “Chọn bài khác”.')),
          h('div', { class: 'row' }, ui.button('Chọn bài khác', function () { pickOther(f, a, choose); }, { kind: 'secondary', size: 'sm' }),
            h('span', { class: 'small muted' }, 'tìm trong ngân hàng theo mã bài hoặc chữ trong đề')),
          h('label', { class: 'field' }, h('span', null, 'Lý do (không bắt buộc)'), note)
        ];
      }
      function noRubric(f) {
        var d = DEC[f.seq] || {}, draft = (state.rubric_drafts || {})[f.seq];
        if (d.rubric_items) {
          return [
            h('p', null, f.detail),
            h('div', { class: 'row' }, h('b', null, 'Rubric đã duyệt'), ui.prov('gv'), ui.chip('ghi cùng commit ② ở bước 5', 'ok')),
            rubricList(d.rubric_items),
            h('div', null, ui.button('Sửa lại rubric', function () {
              EDIT[f.seq] = d.rubric_items; delete DEC[f.seq].rubric_items; changed(); repaint(f.seq);
            }, { kind: 'secondary', size: 'sm' }))
          ];
        }
        if (!EDIT[f.seq]) EDIT[f.seq] = draft ? arr(draft.items) : [{ item_id: 'r1', text: '', points: 1 }];
        return [
          h('p', null, f.detail),
          draft ? h('div', { class: 'row' }, h('b', null, 'Rubric 02 vừa soạn'), ui.prov('llm', '02'), ui.chip('bản nháp, chưa duyệt', 'warn'))
            : h('div', { class: 'callout callout-warn' }, h('strong', null, '02 không soạn được rubric'), h('p', null, 'Thầy/cô tự viết các mục: nội dung và điểm > 0.')),
          draft && draft.alt_methods ? h('p', { class: 'small' }, h('b', null, 'Cách giải khác 02 ghi nhận: '), tx(draft.alt_methods)) : null,
          ui.rubricEditor({ items_json: EDIT[f.seq] }, { onChange: function (r) { EDIT[f.seq] = r.items_json; } }),
          h('div', { class: 'row' }, ui.button('Duyệt rubric này', function () { approve(f); }, { kind: 'primary', size: 'sm' }),
            h('span', { class: 'small muted' }, 'max_score = tổng điểm các mục; rubric ghi vào tutor.db cùng commit ②.'))
        ];
      }
      function approve(f) {
        var items = arr(EDIT[f.seq]).map(function (x, i) { return { item_id: 'r' + (i + 1), text: String(x.text || '').trim(), points: +x.points || 0 }; });
        if (!rubricOk(items)) { C.toast('Rubric cần ít nhất 1 mục; mỗi mục có nội dung và điểm > 0.', { kind: 'warn' }); return; }
        dec(f.seq).rubric_items = items; changed(); repaint(f.seq);
        C.toast('Đã duyệt rubric bài ' + f.seq + ': ' + items.length + ' mục, ' + pts(items.reduce(function (s, i) { return s + i.points; }, 0)) + ' điểm.', { kind: 'ok' });
      }
      function card(seq) {
        var a = atts[seq] || { seq: seq }, fs = open.filter(function (f) { return f.seq === seq; }), done = fs.every(ok);
        return h('article', { class: 'card sx-flagcard ' + (done ? 'sx-done' : 'st-pending') },
          h('div', { class: 'spread' }, h('h3', null, 'Bài ' + seq + ' · ', h('span', { class: 'mono' }, (DEC[seq] || {}).problem_ref || a.ref || 'chưa có mã')),
            h('span', { class: 'row sx-cell' }, fs.map(function (f) { return ui.chip(FLAG[f.type] || f.type, ok(f) ? 'ok' : 'warn'); }))),
          workBox(state, a, who),
          fs.map(function (f) {
            return h('div', { class: 'sx-flag' }, h('div', { class: 'eyebrow' }, 'Cờ ' + f.type + (ok(f) ? ' · đã xử lý' : '')),
              f.type === 'low_match' ? lowMatch(f, a) : f.type === 'no_rubric' ? noRubric(f) : h('p', null, f.detail + ' (bản này chưa xử lý loại cờ này)'));
          }));
      }

      put(top, ui.pageHead({
        eyebrow: 'Buổi học · bước 3 · DỪNG xác nhận khớp bài', title: t.subject || t.thread_id,
        lead: 'G1 gắn ' + open.length + ' cờ chưa chắc và dừng ở đây: chưa chấm, chưa chẩn đoán. Xử lý hết cờ rồi bấm “Chạy tiếp”. Câu trả lời tự lưu, đóng trang rồi quay lại vẫn còn.'
      }), stepper(3));
      put(body,
        section('3 · Xác nhận', h('div', { class: 'stack' },
          lockEl = h('div', { class: 'sx-lock' }, lockBox()), srcLine(), g1Strip(t, true, state),
          seqs.map(function (seq) { return (cardEls[seq] = card(seq)); }),
          bar)),
        tools());
      paintBar();
    }
    function pickOther(f, a, choose) {
      var q = h('input', { type: 'search', placeholder: 'Mã bài (vd 8DS-PTNT-) hoặc chữ trong đề', 'aria-label': 'Tìm bài' });
      var list = h('div', { class: 'stack sx-pick' }), m = null, timer = null, n = 0, first = arr(a.candidates)[0];
      q.value = first ? first.ref.replace(/\d+$/, '') : '';
      var fill = function () {
        var mine = ++n;
        api.get('/bank/problems?limit=20&q=' + encodeURIComponent(q.value.trim())).then(function (rows) {
          if (mine !== n || !list.isConnected) return;
          rows.forEach(function (p) { bank[p.ref] = p; });
          put(list, h('p', { class: 'small muted' }, rows.length ? 'Hiện ' + rows.length + ' bài đầu khớp.' : ''),
            rows.length ? rows.map(function (p) {
              return h('div', { class: 'card' },
                h('div', { class: 'spread' }, h('span', { class: 'row sx-cell' }, h('b', { class: 'mono' }, p.ref), p.has_rubric ? null : ui.chip('chưa có rubric', 'warn')),
                  ui.button('Chọn', function () { m.close(); choose(p.ref); }, { kind: 'primary', size: 'sm' })),
                tx(p.statement_latex, true));
            }) : ui.empty('Không có bài nào khớp.'));
          C.tex(list);
        }, function (e) { if (mine === n) put(list, h('p', { class: 'small sx-err' }, 'Không tìm được: ' + errText(e))); });
      };
      q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(fill, 250); });
      m = C.modal({
        title: 'Chọn bài khác · bài ' + f.seq, wide: true,
        body: h('div', { class: 'stack' }, h('label', { class: 'field' }, h('span', null, 'Tìm theo mã bài hoặc đề'), q), list), actions: [{ label: 'Đóng' }]
      });
      put(list, loading());
      fill();
    }

    /* ---------- bước 4: duyệt lỗi (DỪNG review) ---------- */
    function paintReview() {
      var lanes = arr(state.lanes).slice().sort(function (a, b) { return a.seq - b.seq; });
      if (!RV || !RV.prob) {
        put(body, loading());
        RV = { sel: null, seq: null, add: false };
        var ids = lanes.map(function (l) { return l.problem_id; }).filter(function (x, i, a) { return a.indexOf(x) === i; });
        Promise.all([loadRef()].concat(ids.map(function (id) { return api.get('/bank/problems/' + id); }))).then(function (r) {
          if (!life.alive) return;
          RV.prob = {};
          r.slice(1).forEach(function (p) { RV.prob[p.id] = p; });
          paintReview(); C.tex(body);
        }, function (e) { RV = null; fail(e); });
        return;
      }
      var ing = state.ingest || {}, props = arr(state.proposals), who = code(t.student_id), atts = {}, laneOf = {}, pmap = {};
      arr(ing.attempts).forEach(function (a) { atts[a.seq] = a; });
      lanes.forEach(function (l) { laneOf[l.seq] = l; });
      props.forEach(function (p) { pmap[p.pid] = p; });
      if (!RV.dec) {  // reopen: decisions + review time saved by the last PUT (step-3 answers have no `cards`)
        var saved = null;
        try { saved = JSON.parse(t.decisions_json || 'null'); } catch (e) { /* unreadable → start empty */ }
        var cs = saved && saved.cards && typeof saved.cards === 'object' && !Array.isArray(saved.cards) ? saved.cards : {}, keep = {};
        Object.keys(cs).forEach(function (k) { if (cs[k] && (pmap[k] || cs[k].action === 'add')) keep[k] = cs[k]; });
        RV.dec = { cards: keep, review_seconds: 0 };
        RV.base = saved && typeof saved.review_seconds === 'number' ? Math.max(0, Math.round(saved.review_seconds)) : 0;
        RV.opened = Date.now();
      }
      var D = RV.dec.cards, cardEls = {}, stepEls = {}, chain = Promise.resolve(), saveMsg = '', srvPending = null;
      var workEl, footEl, bar, timerEl;

      function secs() { return RV.base + Math.floor((Date.now() - RV.opened) / 1000); }
      function grp(p) { var v = (p.verifier || {}).verdict; return v !== 'agree' ? 0 : p.confidence < LOW ? 1 : 2; }
      function list() {
        var out = props.map(function (p) { return { key: p.pid, p: p, seq: p.attempt_seq, grp: grp(p) }; });
        Object.keys(D).filter(function (k) { return !pmap[k]; }).sort(function (a, b) { return (+a.slice(1) || 0) - (+b.slice(1) || 0); })
          .forEach(function (k) { out.push({ key: k, p: null, seq: D[k].attempt_seq, grp: 3, added: true }); });
        // cards render grouped; J/K and #n follow the same order
        return [0, 1, 2, 3].reduce(function (acc, g) { return acc.concat(out.filter(function (c) { return c.grp === g; })); }, []);
      }
      function find(key) { return list().find(function (c) { return c.key === key; }) || null; }
      function decided(c) { var d = D[c.key]; return !!d && (c.added || d.action === 'accept' || d.action === 'edit' || d.action === 'reject'); }
      function left() { return props.filter(function (p) { return !decided({ key: p.pid }); }).length; }
      function stepOf(seq, idx) { return arr((atts[seq] || {}).steps).find(function (s) { return s.idx === idx; }); }
      function eff(c) {
        var d = D[c.key] || {};
        if (c.added) return { step_idx: d.step_idx, code: d.code, kc_id: d.kc_id == null ? null : d.kc_id, description: d.description, evidence_latex: d.evidence_latex || (stepOf(c.seq, d.step_idx) || {}).latex };
        var f = { step_idx: c.p.step_idx, code: c.p.code, kc_id: c.p.kc_id, description: c.p.description, evidence_latex: c.p.evidence_latex };
        if (d.action === 'edit') Object.keys(f).forEach(function (k) { if (k in d) f[k] = d[k]; });
        return f;
      }

      // PUT replaces the saved object: always the whole decision set + cumulative review time (C-09). Chained so saves land in order.
      function save() {
        saveMsg = 'Đang lưu…'; paintBar();
        var p = chain.then(function () { RV.dec.review_seconds = secs(); return api.send('PUT', path + '/decisions', RV.dec); });
        chain = p.catch(function () { /* next save still runs */ });
        return p.then(function (r) {
          srvPending = r.pending; saveMsg = 'Đã lưu ' + new Date().toTimeString().slice(0, 8); paintBar(); return r;
        }, function (e) {
          saveMsg = 'Chưa lưu được: ' + errText(e); paintBar();
          if (e.code === 'not_ready' && life.alive) full();  // thread already left the review gate: decisions are frozen, show where it is
          throw e;
        });
      }
      function autosave() { save().catch(function () { /* saveMsg already shows it */ }); }
      life.flush = autosave;  // leaving the page keeps the review time

      function decide(c, d) {
        if (d) D[c.key] = d; else delete D[c.key];
        autosave();
        var old = cardEls[c.key];
        if (old) { var n = cardEl(c, list().findIndex(function (x) { return x.key === c.key; })); old.replaceWith(n); cardEls[c.key] = n; C.tex(n); }
        tint(); paintFoot();
      }
      function advance(c) {
        var L = list(), i = L.findIndex(function (x) { return x.key === c.key; });
        for (var k = 1; k < L.length; k++) { var n = L[(i + k) % L.length]; if (!decided(n)) { select(n.key, true); return; } }
      }
      function select(key, scroll) {
        var c = find(key);
        if (!c) return;
        RV.sel = key;
        if (c.seq !== RV.seq) { RV.seq = c.seq; draw(); }
        else { Object.keys(cardEls).forEach(function (k) { cardEls[k].classList.toggle('is-sel', k === key); }); tint(); }
        if (scroll && cardEls[key]) cardEls[key].scrollIntoView({ block: 'nearest' });
      }
      function accept(c) {
        if (c.added) { C.toast('Lỗi thầy/cô thêm đã tính là quyết định (added).', { kind: 'info' }); return; }
        decide(c, { action: 'accept' }); advance(c);
      }
      function reject(c) {
        if (c.added) {
          delete D[c.key]; autosave(); RV.sel = null; draw();
          C.toast('Đã xoá lỗi vừa thêm ' + c.key + '.', { kind: 'info' }); return;
        }
        var old = D[c.key];
        decide(c, old && old.action === 'reject' ? old : { action: 'reject' }); advance(c);
      }
      function edit(c) {
        select(c.key);
        var a = atts[c.seq] || {}, l = laneOf[c.seq] || {}, e = eff(c), d = D[c.key] || {};
        mistakeForm({
          title: (c.added ? 'Sửa lỗi thầy/cô thêm ' : 'Sửa đề xuất ') + c.key + ' · Bài ' + c.seq,
          lead: c.added ? null : 'Bản gốc của 03 vẫn giữ trong mistake.llm_json; thẻ chuyển sang “edited”.',
          kcs: (RV.prob[l.problem_id] || {}).kcs, steps: a.steps, suggested: c.p && (c.p.verifier || {}).suggested_code, saveLabel: 'Lưu sửa',
          init: { code: e.code, kc_id: e.kc_id, step_idx: e.step_idx, description: e.description, teacher_note: d.teacher_note },
          onSave: function (v) {
            var x;
            if (c.added) x = { action: 'add', attempt_seq: c.seq, step_idx: v.step_idx, code: v.code, kc_id: v.kc_id, description: v.description };
            else {
              x = { action: 'edit' };  // only fields that differ from 03's proposal
              ['code', 'kc_id', 'step_idx', 'description'].forEach(function (k) { if (v[k] !== c.p[k]) x[k] = v[k]; });
              if (x.step_idx != null) x.evidence_latex = (stepOf(c.seq, x.step_idx) || {}).latex || '';
              if (Object.keys(x).length === 1 && !v.teacher_note) { C.toast('Chưa đổi gì. Đề xuất đúng thì bấm Chấp nhận (A).', { kind: 'warn' }); return false; }
            }
            if (v.teacher_note) x.teacher_note = v.teacher_note;
            decide(c, x);
            C.toast(c.key + ' → ' + ST[x.action] + ' (chờ ghi)', { kind: 'ok' });
          }
        });
      }
      function addAt(seq, idx) {
        var a = atts[seq] || {}, l = laneOf[seq] || {};
        mistakeForm({
          title: 'Thêm lỗi bị sót · Bài ' + seq + ' · bước ' + idx, noStep: true, saveLabel: 'Thêm lỗi',
          lead: 'Lỗi do thầy/cô thêm: status added, không có ý kiến 03/04. Bằng chứng = dòng bước ' + idx + ' của bài làm.',
          kcs: (RV.prob[l.problem_id] || {}).kcs, steps: a.steps, init: { step_idx: idx, code: '', kc_id: null, description: '' },
          onSave: function (v) {
            var n = 1;
            while (D['n' + n] || pmap['n' + n]) n++;
            var x = { action: 'add', attempt_seq: seq, step_idx: idx, code: v.code, kc_id: v.kc_id, description: v.description };
            if (v.teacher_note) x.teacher_note = v.teacher_note;
            D['n' + n] = x; RV.add = false; RV.sel = 'n' + n;
            autosave(); draw();
            C.toast('Đã thêm lỗi n' + n + ' (added) ở bài ' + seq + ' bước ' + idx + '.', { kind: 'ok' });
          }
        });
      }
      function toggleAdd() {
        RV.add = !RV.add;
        var n = workCol(); workEl.replaceWith(n); workEl = n; tint(); C.tex(n);
        if (RV.add) { C.toast('Bấm “Thêm lỗi ở bước này” cạnh bước có lỗi bị sót (cột Bài làm HS).', { kind: 'info' }); workEl.scrollIntoView({ block: 'nearest' }); }
      }
      function showEvidence(c) {
        select(c.key);
        var el = stepEls[eff(c).step_idx];
        if (!el) { C.toast('Không thấy bước ' + eff(c).step_idx + ' trong bài làm.', { kind: 'warn' }); return; }
        el.scrollIntoView({ block: 'center' });
        el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
      }
      function onKey(e) {
        if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented || !life.alive) return;
        var k = String(e.key || '').toLowerCase();
        if (k.length !== 1 || 'aernjk'.indexOf(k) < 0) return;
        var tg = e.target;
        if (tg && tg.closest && tg.closest('input, textarea, select, [contenteditable]')) return;
        if (document.querySelector('#modal-root .modal, #drawer-root .drawer')) return;
        e.preventDefault();
        var L = list(), i = L.findIndex(function (c) { return c.key === RV.sel; }), c = L[i];
        if (k === 'j' || k === 'k') { if (L.length) select(L[i < 0 ? 0 : (i + (k === 'j' ? 1 : -1) + L.length) % L.length].key, true); return; }
        if (k === 'n') { toggleAdd(); return; }
        if (!c) return;
        if (k === 'a') accept(c); else if (k === 'e') edit(c); else reject(c);
      }
      document.addEventListener('keydown', onKey);
      var iv = setInterval(function () { if (timerEl) timerEl.textContent = mmss(secs()); }, 1000);
      life.off = function () { document.removeEventListener('keydown', onKey); clearInterval(iv); };

      function workCol() {
        var a = atts[RV.seq] || {}, pr = RV.prob[(laneOf[RV.seq] || {}).problem_id] || {};
        stepEls = {};
        var steps = h('ol', { class: 'sx-steps' }, arr(a.steps).map(function (s) {
          return (stepEls[s.idx] = h('li', { class: 'sx-step', 'data-step': s.idx }, h('span', { class: 'sx-step-n' }, String(s.idx)),
            h('div', { class: 'sx-step-body' }, tx(s.latex, true)), h('div', { class: 'sx-step-tags' })));
        }));
        return h('div', { class: 'sx-col sx-col-work' },
          h('div', { class: 'spread' }, h('h3', null, 'Bài làm HS ', agentBadge('01')),
            ui.button(RV.add ? 'Thôi thêm lỗi' : 'Thêm lỗi bị sót (N)', toggleAdd, { kind: RV.add ? 'primary' : 'ghost', size: 'sm' })),
          h('div', { class: 'sx-prob' }, h('div', { class: 'small muted' }, 'Đề bài · ', h('span', { class: 'mono' }, pr.ref || a.ref || '—')), tx(pr.statement_latex, true)),
          RV.add ? h('div', { class: 'callout callout-info' }, h('p', { class: 'small' }, 'Bấm “Thêm lỗi ở bước này” cạnh bước có lỗi bị sót.')) : null,
          h('div', { class: 'untrusted sx-untrusted' }, h('div', { class: 'sx-untrusted-h' }, 'UNTRUSTED INPUT · ' + who + ' · bài ' + (a.seq || '—')), steps),
          pr.solution_latex ? h('details', { class: 'sx-details' }, h('summary', null, 'Lời giải mẫu'), tx(pr.solution_latex, true)) : null);
      }
      // Steps with a live card are tinted; chips name the cards on each step.
      function tint() {
        var hits = {}, sc = find(RV.sel), selStep = sc && sc.seq === RV.seq ? eff(sc).step_idx : null;
        list().forEach(function (c) { if (c.seq === RV.seq) { var i = eff(c).step_idx; (hits[i] = hits[i] || []).push(c); } });
        Object.keys(stepEls).forEach(function (idx) {
          var li = stepEls[idx], hs = hits[idx] || [];
          li.classList.toggle('is-hit', hs.some(function (c) { return (D[c.key] || {}).action !== 'reject'; }));
          li.classList.toggle('is-sel', +idx === selStep);
          put(li.querySelector('.sx-step-tags'), hs.map(function (c) {
            var ch = ui.chip(c.key + ' · ' + eff(c).code, !decided(c) ? 'warn' : D[c.key].action === 'reject' ? 'neutral' : 'ok');
            ch.classList.add('chip-wrap'); return ch;
          }), RV.add ? ui.button('Thêm lỗi ở bước này', function () { addAt(RV.seq, +idx); }, { kind: 'primary', size: 'sm' }) : null);
        });
      }
      function gradeCol() {
        var l = laneOf[RV.seq] || {}, g = l.grade || {}, items = arr((l.rubric || {}).items), p = {};
        items.forEach(function (i) { p[i.item_id] = +i.points || 0; });
        var passed = arr(g.items).filter(function (x) { return x.passed; });
        var sum = passed.reduce(function (s, x) { return s + (p[x.item_id] || 0); }, 0);
        var okSum = g.score != null && Math.abs(sum - g.score) < 1e-9, okEv = passed.every(function (x) { return String(x.evidence_latex || '').trim(); });
        var fl = arr(g.flags).concat(arr((l.diagnosis || {}).flags));
        return h('div', { class: 'sx-col sx-col-grade' },
          h('div', { class: 'spread' }, h('h3', null, agentBadge('02'), ' 02 Grader'),
            l.rubric && l.rubric.version != null ? ui.chip('rubric v' + l.rubric.version) : ui.chip('rubric duyệt ở bước 3', 'ok')),
          h('div', { class: 'row' }, h('span', { class: 'sx-score num' }, pts(g.score) + '/' + pts(g.max_score)), ui.prov('llm', '02')),
          h('div', { class: 'row sx-cell' }, ui.chip('tổng = tổng các mục ' + (okSum ? '✓' : '✗') + ' · mục đạt có bằng chứng ' + (okEv ? '✓' : '✗'), okSum && okEv ? 'ok' : 'danger'), ui.prov('code')),
          fl.length ? h('div', { class: 'row sx-cell' }, fl.map(function (f) { var c = ui.chip(GFLAG[f.type] || f.type, 'warn'); c.title = f.detail || f.type; return c; })) : null,
          gradeList(items, g.items));
      }
      function rejNote(c) {
        var inp = h('input', { type: 'text', value: (D[c.key] || {}).teacher_note || '', placeholder: 'vd: HS chỉ viết tắt, không phải lỗi', 'aria-label': 'Lý do bỏ ' + c.key });
        inp.addEventListener('change', function () {
          var d = D[c.key], v = inp.value.trim();
          if (!d || d.action !== 'reject') return;
          if (v) d.teacher_note = v; else delete d.teacher_note;
          autosave();
        });
        return h('label', { class: 'field' }, h('span', null, 'Đã bỏ — vẫn lưu để đo độ chính xác. Lý do (không bắt buộc)'), inp);
      }
      function cardEl(c, i) {
        var e = eff(c), d = D[c.key], act = d && d.action, done = decided(c), p = c.p, says = null;
        var pill = !done ? h('span', { class: 'status s-pending' }, 'chờ quyết') : act === 'reject' ? ui.status('rejected')
          : h('span', { class: 'status s-db', title: 'status = ' + ST[act] }, ST[act] + ' · chờ ghi');
        if (p) {
          var v = p.verifier || {}, vd = VERDICT[v.verdict] || ['04 chưa có ý kiến', 'warn'];
          says = h('div', { class: 'sx-says' },
            h('div', { class: 'sx-say' }, h('div', { class: 'sx-say-h' }, agentBadge('03'), 'Diagnoser (03) nói', ui.prov('llm')),
              h('div', { class: 'row sx-cell' }, codeChip(p.code), kcChip(p.kc_id), h('span', { class: 'small' }, 'bước ' + p.step_idx)),
              h('div', { class: 'small' }, tx(p.description))),
            h('div', { class: 'sx-rule' }, 'không chung context'),
            h('div', { class: 'sx-say' }, h('div', { class: 'sx-say-h' }, agentBadge('04'), 'Verifier (04) nói', ui.prov('llm')),
              h('div', { class: 'row sx-cell' }, ui.chip(vd[0], vd[1]), v.suggested_code ? h('span', { class: 'small' }, 'gợi ý mã ', codeChip(v.suggested_code)) : null),
              h('div', { class: 'small' }, tx(v.reason))));
        }
        return h('article', {
          class: 'sx-card ' + (!done ? 'is-open' : act === 'reject' ? 'is-rej' : 'is-ok') + (RV.sel === c.key ? ' is-sel' : ''), 'data-pid': c.key,
          onclick: function (ev) { if (!ev.target.closest('button, input, textarea, select, a, summary, label')) select(c.key); }
        },
          h('div', { class: 'sx-card-h' }, h('span', { class: 'small' }, h('b', { class: 'num' }, '#' + (i + 1)), ' · ', h('b', { class: 'mono' }, c.key),
            ' · Bài ' + c.seq + ' · ', h('span', { class: 'mono' }, (atts[c.seq] || {}).ref || '—'), ' · bước ' + e.step_idx), pill),
          h('div', { class: 'row sx-cell' }, codeChip(e.code), kcChip(e.kc_id),
            !p ? ui.chip('GV thêm') : p.confidence != null ? h('span', { class: 'sx-conf' }, 'tin cậy', ui.bar(p.confidence, 1, { kind: p.confidence < LOW ? 'warn' : 'accent' }), h('b', { class: 'num' }, F.num(p.confidence))) : null),
          h('div', { class: 'sx-strike' }, tx(e.description)),
          h('div', { class: 'sx-evid sx-strike' }, h('span', { class: 'small muted' }, 'Bằng chứng: '), tx(e.evidence_latex, true)),
          p ? says : h('p', { class: 'small muted' }, 'Lỗi do thầy/cô thêm — không có ý kiến 03/04 (llm_json = NULL).'),
          act === 'edit' ? diffLine(p, e, 'Khác đề xuất LLM: ') : null,
          act === 'reject' ? rejNote(c) : d && d.teacher_note ? h('p', { class: 'small' }, h('b', null, 'Ghi chú GV: '), d.teacher_note) : null,
          p ? h('p', { class: 'sx-foot-note' }, 'Hệ thống không tự quyết — thầy/cô quyết.') : null,
          h('div', { class: 'sx-acts' },
            p ? ui.button('Chấp nhận (A)', function () { accept(c); }, { kind: act === 'accept' ? 'primary' : 'secondary', size: 'sm' }) : null,
            ui.button('Sửa (E)', function () { edit(c); }, { kind: act === 'edit' ? 'primary' : 'secondary', size: 'sm' }),
            ui.button(p ? 'Bỏ (R)' : 'Xoá lỗi vừa thêm (R)', function () { reject(c); }, { kind: act === 'reject' ? 'primary' : 'secondary', size: 'sm' }),
            ui.button('Xem bằng chứng', function () { showEvidence(c); }, { kind: 'ghost', size: 'sm' })));
      }
      function cardsCol(L) {
        var added = L.length - props.length;
        return h('div', { class: 'sx-col sx-col-cards' },
          h('div', { class: 'spread' }, h('h3', null, 'Đề xuất lỗi ', ui.prov('llm', '03'), ui.prov('llm', '04')),
            h('span', { class: 'small muted' }, props.length + ' đề xuất' + (added ? ' · ' + added + ' GV thêm' : ''))),
          h('p', { class: 'small muted' }, 'Xếp sẵn: 04 phản đối / sai mã → tin cậy < ' + LOW + ' → còn lại. Cả ' + lanes.length + ' bài, không riêng bài đang mở.'),
          props.length ? null : h('div', { class: 'callout callout-info' }, h('p', null, '02/03 không tìm thấy lỗi — vẫn cần thầy/cô xác nhận.')),
          [0, 1, 2, 3].map(function (gi) {
            var cs = L.filter(function (c) { return c.grp === gi; });
            return cs.length ? h('div', { class: 'stack sx-group' }, h('div', { class: 'sx-group-h' }, GROUPS[gi], h('span', { class: 'num' }, '· ' + cs.length)),
              cs.map(function (c) { return (cardEls[c.key] = cardEl(c, L.indexOf(c))); })) : null;
          }));
      }
      function ctxBox() {
        var seen = {}, rows = [];
        lanes.forEach(function (l) {
          arr((l.diagnosis || {}).context).forEach(function (m) { var k = JSON.stringify(m); if (!seen[k]) { seen[k] = 1; rows.push(m); } });
        });
        return h('div', { class: 'card sx-ctx' },
          h('div', { class: 'small' }, h('b', null, 'Ngữ cảnh 03 đã dùng: '), rows.length ? rows.length + ' lỗi đã duyệt gần nhất của ' + who : 'không có'),
          rows.length ? h('div', { class: 'row sx-cell' }, rows.map(function (m) {
            var c = ui.chip(m.code + ' · ' + kcName(m.kc_id) + ' · ' + F.date(m.held_on).slice(0, 5)); c.classList.add('chip-wrap'); c.title = m.description || ''; return c;
          })) : h('p', { class: 'small muted' }, who + ' chưa có lỗi nào đã ghi tutor.db, nên 03 chẩn đoán không có ngữ cảnh lỗi cũ.'));
      }
      function paintFoot() {
        var m = props.length, n = m - left(), added = list().length - m;
        var el = h('div', { class: 'grid cols-3 sx-foot' },
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Đã quyết'), h('span', { class: 'kpi-value num' }, n + '/' + m), ui.bar(n, m || 1, { kind: n < m ? 'warn' : 'ok' }),
            added ? h('span', { class: 'kpi-sub' }, '+ ' + added + ' lỗi thầy/cô thêm') : null),
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Thời gian duyệt'), timerEl = h('span', { class: 'kpi-value num' }, mmss(secs())),
            h('span', { class: 'kpi-sub' }, 'cộng dồn qua các lần mở · ghi vào session.review_seconds')),
          ctxBox());
        if (footEl) footEl.replaceWith(el);
        footEl = el;
        paintBar();
      }
      function paintBar() {
        if (!bar || !life.alive) return;
        var n = left(), why = t.locked ? t.lock_reason || 'buổi đang bị khoá' : n ? 'còn ' + n + ' đề xuất chưa quyết' : srvPending ? 'máy chủ báo còn ' + srvPending + ' mục chưa hợp lệ' : null;
        put(bar,
          ui.button('Xem trước tiến bộ', previewGo, { kind: 'primary', disabledReason: why }),
          ui.button('Tạm dừng, duyệt sau', pause, { kind: 'secondary' }),
          h('span', { class: 'small muted sx-kbd' }, 'Phím: ', h('kbd', null, 'A'), ' chấp nhận · ', h('kbd', null, 'E'), ' sửa · ', h('kbd', null, 'R'), ' bỏ · ',
            h('kbd', null, 'N'), ' thêm lỗi · ', h('kbd', null, 'J'), '/', h('kbd', null, 'K'), ' thẻ sau/trước'),
          saveMsg ? h('span', { class: 'small muted', role: 'status' }, saveMsg + (srvPending != null ? ' · máy chủ: còn ' + srvPending + ' chưa quyết' : '')) : null);
      }
      // 05 runs on resume and the thread stops at gate_confirm_commit; nothing is written yet.
      function previewGo(ev, b) {
        b.disabled = true; b.textContent = 'Đang tính…';
        return save().then(function (r) {
          if (r.pending) { C.toast('Còn ' + r.pending + ' mục chưa quyết hoặc chưa hợp lệ.', { kind: 'warn' }); return; }
          return resume().then(function () { C.toast('Đang tính tiến bộ…', { kind: 'info' }); });
        }).catch(function (e) {
          if (e.code === 'date_order_locked') lockFrom(e);
          C.toast(e.code === 'undecided_items' ? 'Còn ' + (e.detail || {}).n + ' mục chưa quyết.' : errText(e),
            { kind: 'warn', title: 'Chưa xem trước được' + (e.status ? ' (' + e.status + ')' : '') });
          paintBar();
        });
      }
      function pause(ev, b) {
        b.disabled = true;
        return save().then(function () {
          life.flush = null;
          C.toast('Đã lưu ' + (props.length - left()) + '/' + props.length + ' quyết định. Buổi vẫn chờ duyệt trong Hộp duyệt.', { kind: 'ok' });
          if (life.alive) C.nav('today');
        }, function (e) { C.toast(errText(e), { kind: 'error', title: 'Chưa lưu được' }); b.disabled = false; });
      }
      function draw() {
        var L = list();
        if (!L.some(function (c) { return c.key === RV.sel; })) RV.sel = (L.find(function (c) { return !decided(c); }) || L[0] || {}).key || null;
        var sc = find(RV.sel);
        if (RV.seq == null || !laneOf[RV.seq]) RV.seq = sc ? sc.seq : (lanes[0] || {}).seq;
        cardEls = {}; footEl = null;
        bar = h('div', { class: 'row sx-actbar' });
        workEl = lanes.length ? workCol() : null;
        put(body,
          section('4 · Duyệt lỗi', h('div', { class: 'stack' },
            lockEl = h('div', { class: 'sx-lock' }, lockBox()),
            srcLine(), g1Strip(t, true, state),
            lanes.length > 1 ? ui.segmented(lanes.map(function (l) {
              var g = l.grade || {}, n = L.filter(function (c) { return c.seq === l.seq; }).length;
              return { id: String(l.seq), label: 'Bài ' + l.seq + ' · ' + ((atts[l.seq] || {}).ref || '—') + ' · ' + pts(g.score) + '/' + pts(g.max_score) + ' · ' + n + ' lỗi' };
            }), String(RV.seq), function (id) { RV.seq = +id; draw(); }) : null,
            lanes.length ? h('div', { class: 'sx-cols' }, workEl, gradeCol(), cardsCol(L)) : ui.empty('Thread chưa có bài nào được chấm.'),
            (paintFoot(), footEl), bar)),
          tools());
        tint(); paintBar();
        C.tex(body);
      }

      put(top, ui.pageHead({
        eyebrow: 'Buổi học · bước 4 · DỪNG duyệt lỗi', title: t.subject || t.thread_id,
        lead: 'Duyệt từng lỗi 03 đề xuất; 04 kiểm tra độc lập (không thấy lý luận của 03), mục bất đồng và độ tin cậy thấp lên đầu. Không có “duyệt tất cả”. Mỗi quyết định tự lưu; đóng trang rồi mở lại vẫn còn.'
      }), stepper(4, { skip3: !arr(ing.flags).length }));
      draw();
    }

    /* ---------- bước 5: xem trước tiến bộ (DỪNG confirm_commit) ---------- */
    function paintPreview() {
      var pv = state.preview || {}, kcs = arr(pv.kcs), mc = pv.miscon || {}, w = pv.writes || {}, bar = h('div', { class: 'row sx-actbar' });
      var cards = {}, n = { accept: 0, edit: 0, reject: 0, add: 0 };
      try { cards = (JSON.parse(t.decisions_json || '{}') || {}).cards || {}; } catch (e) { /* unreadable → no summary */ }
      Object.keys(cards).forEach(function (k) { var a = (cards[k] || {}).action; if (a in n) n[a]++; });
      var LISTS = [['new', 'Lỗi lặp mới ghi nhận'], ['again', 'Lỗi cũ gặp lại'], ['resolved', 'Lỗi đã hết']];
      var TREND = { 'tiến bộ': 'ok', 'cần ôn': 'warn' };
      function paintBar() {
        put(bar,
          ui.button('Lưu kết quả', saveGo, { kind: 'primary', disabledReason: t.locked ? t.lock_reason || 'buổi đang bị khoá' : null }),
          h('span', { class: 'small muted' }, 'Chưa ghi gì vào tutor.db cho tới khi bấm “Lưu kết quả”.'));
      }
      function saveGo(ev, b) {
        b.disabled = true; b.textContent = 'Đang lưu…';
        committing = true;
        return resume().then(function () { C.toast('② Sao lưu tutor.db rồi ghi 1 transaction…', { kind: 'info' }); }, function (e) {
          committing = false;
          if (e.code === 'date_order_locked') lockFrom(e);
          C.toast(errText(e), { kind: 'warn', title: 'Chưa lưu được' + (e.status ? ' (' + e.status + ')' : '') });
          if (e.code === 'not_ready' || e.code === 'already_committed') { if (life.alive) full(); } else paintBar();
        });
      }
      put(top, ui.pageHead({
        eyebrow: 'Buổi học · bước 5 · DỪNG lưu kết quả', title: t.subject || t.thread_id,
        lead: '05 đã tính tiến bộ của học sinh sau buổi này từ các quyết định duyệt lỗi. Đây mới là bản xem trước: chưa ghi gì vào tutor.db.'
      }), stepper(5, { skip3: !arr((state.ingest || {}).flags).length }));
      put(body,
        section('5 · Xem trước tiến bộ', h('div', { class: 'stack' },
          lockEl = h('div', { class: 'sx-lock' }, lockBox()), srcLine(), g1Strip(t, true, state),
          h('h3', null, 'Kỹ năng thay đổi'),
          ui.table({
            rows: kcs, empty: 'Không có kỹ năng nào được cập nhật',
            columns: [
              { label: 'Kỹ năng', render: function (k) { return tx(k.kc); } },
              { label: 'Trước', render: function (k) { return k.before == null ? '—' : String(k.before); } },
              { label: 'Sau', render: function (k) { return k.after == null ? '—' : String(k.after); } },
              { label: 'Thay đổi', render: function (k) { return ui.chip(String(k.trend), TREND[k.trend] || 'neutral'); } }
            ]
          }),
          h('div', { class: 'grid cols-3' }, LISTS.map(function (l) {
            var xs = arr(mc[l[0]]);
            return h('div', { class: 'card stack' }, h('h3', null, l[1], ' ', h('span', { class: 'num small muted' }, '· ' + xs.length)),
              xs.length ? h('ul', { class: 'sx-flags' }, xs.map(function (x) { return h('li', null, tx(x)); })) : h('p', { class: 'small muted' }, 'không có'));
          })),
          h('p', null, 'Sẽ ghi (1 transaction): ' + (w.attempt || 0) + ' bài làm, ' + (w.mistake || 0) + ' lỗi, ' + (w.rubric || 0) + ' rubric mới, ' +
            (w.skill_event || 0) + ' lượt cập nhật kỹ năng; cập nhật hồ sơ ' + (w.skill_state || 0) + ' kỹ năng, ' + (w.misconception_log || 0) + ' lỗi lặp.'),
          h('p', { class: 'small muted' }, 'Quyết định duyệt lỗi đã chốt: ' + n.accept + ' chấp nhận, ' + n.edit + ' sửa, ' + n.reject + ' bỏ, ' + n.add + ' thêm. ' +
            'Không sửa lại được ở đây; muốn đổi thì huỷ thread ở ', h('a', { href: '#ops', 'data-tab-link': 'ops' }, 'tab Vận hành'), ' rồi nộp bài lại.'),
          bar)),
        tools());
      paintBar();
    }

    /* ---------- bước 5: đã ghi tutor.db ---------- */
    function paintDone() {
      var rc = t.receipt || state.receipt || {}, sid = t.session_id, detail = h('div', { class: 'stack' }, loading());
      put(top, ui.pageHead({ eyebrow: 'Buổi học · bước 5 · đã ghi tutor.db', title: t.subject || t.thread_id }),
        stepper(6, { skip3: !arr((state.ingest || {}).flags).length }));
      put(body,
        section('5 · Ghi DB', h('div', { class: 'stack' },
          rc.by_status ? h('div', { class: 'callout callout-ok st-db', role: 'status' },
            h('strong', null, 'Đã ghi 1 transaction vào tutor.db' + (rc.committed_at ? ' lúc ' + F.dt(rc.committed_at) : '')),
            h('p', { class: 'mono small sx-wrap' }, receiptLine(rc)),
            rc.backup ? h('p', { class: 'small' }, 'Sao lưu trước khi ghi: ', h('span', { class: 'mono sx-wrap' }, 'data/backup/' + rc.backup)) : null,
            h('p', { class: 'small muted' }, 'Thread ' + t.thread_id + ' đã commit: đề xuất không còn chờ trong checkpoints.db.'))
            : h('div', { class: 'callout callout-warn' }, h('p', null, 'Thread đã commit nhưng không đọc được biên nhận.')),
          g1Strip(t, true, state),
          h('div', { class: 'row' },
            sid != null ? ui.button('Xem buổi đã ghi', function () { C.nav('session', { session: sid }); }, { kind: 'primary' }) : null,
            ui.button('Nộp bài mới', function () { C.nav('session', { step: 1 }); }, { kind: 'secondary' }),
            ui.button('Về danh sách', function () { C.nav('session'); }, { kind: 'ghost' })))),
        detail);
      if (sid == null) { put(detail); return; }
      Promise.all([api.get('/sessions/' + sid), loadRef()]).then(function (r) {
        if (!life.alive) return;
        put(detail, detailBody(r[0])); C.tex(detail);
      }, function (e) { if (life.alive) put(detail, failBox(e, 'buổi #' + sid)); });
    }
    full();
  }

  /* ---------- buổi đã ghi (chỉ đọc) ---------- */
  function receiptLine(rc) {
    var b = rc.by_status || {};
    return '1 transaction · +' + rc.attempt + ' attempt · +' + rc.mistake + ' mistake (' + (b.confirmed || 0) + ' confirmed, ' + (b.edited || 0) + ' edited, ' +
      (b.rejected || 0) + ' rejected, ' + (b.added || 0) + ' added) · +' + rc.rubric + ' rubric' +
      (rc.skill_event == null ? '' : ' · +' + rc.skill_event + ' lượt cập nhật kỹ năng') + ' · session → committed';
  }
  function mistakeRow(m) {
    var lj = m.llm_json, rej = m.status === 'rejected', vd = VERDICT[m.verifier_verdict];
    return h('div', { class: 'sx-mrow ' + (rej ? 'is-rej' : 'st-db'), 'data-mistake': m.id },
      h('div', { class: 'row sx-cell' }, h('b', { class: 'mono' }, '#' + m.id), ui.status(m.status), h('span', { class: 'small' }, 'bước ' + m.step_idx),
        codeChip(m.code), kcChip(m.kc_id), m.confidence != null ? h('span', { class: 'small muted' }, 'tin cậy ' + F.num(m.confidence)) : null,
        vd ? ui.chip(vd[0], vd[1]) : null),
      h('div', { class: rej ? 'sx-strike-all' : null }, tx(m.description)),
      h('div', { class: 'sx-evid' }, h('span', { class: 'small muted' }, 'Bằng chứng: '), tx(m.evidence_latex, true)),
      m.verifier_reason ? h('p', { class: 'small' }, h('span', { class: 'muted' }, '04: '), tx(m.verifier_reason)) : null,
      m.status === 'edited' && lj ? diffLine(lj, m, 'Đề xuất gốc LLM → bản cuối: ') : null,
      m.status === 'added' ? h('p', { class: 'small muted' }, 'Thầy/cô thêm — không có đề xuất gốc LLM (llm_json = NULL).') : null,
      m.teacher_note ? h('p', { class: 'small' }, h('b', null, 'Ghi chú GV: '), m.teacher_note) : null,
      rej ? h('p', { class: 'small muted' }, 'Đã bỏ — vẫn lưu để đo độ chính xác (mistake_current không tính).') : null,
      lj ? h('details', { class: 'sx-details' }, h('summary', null, 'Đề xuất gốc LLM (llm_json)'), h('pre', { class: 'code' }, JSON.stringify(lj, null, 2))) : null);
  }
  function detailBody(s) {
    var atts = arr(s.attempts), ms = [];
    atts.forEach(function (a) { ms = ms.concat(arr(a.mistakes)); });
    var n = {};
    ms.forEach(function (m) { n[m.status] = (n[m.status] || 0) + 1; });
    return [
      section('Thông tin buổi', ui.kv([
        ['Ngày học', F.date(s.held_on)],
        ['Học sinh', h('b', { class: 'mono' }, s.student_code)],
        ['File', h('span', { class: 'row sx-cell' }, h('span', { class: 'chip st-file mono sx-wrap' }, s.source_path || '—'), s.source_kind ? ui.chip(s.source_kind) : null)],
        ['sha256', h('span', { class: 'mono small', title: s.source_sha256 || '' }, s.source_sha256 ? s.source_sha256.slice(0, 12) + '…' : '—')],
        ['thread_id', h('span', { class: 'mono small sx-wrap' }, s.thread_id || '—')],
        ['Trạng thái', h('span', { class: 'row sx-cell' }, ui.status(s.status), s.committed_at ? h('span', { class: 'small muted' }, 'ghi lúc ' + F.dt(s.committed_at)) : null)],
        ['Thời gian duyệt', s.review_seconds != null ? h('span', { class: 'num' }, mmss(s.review_seconds) + ' (mm:ss)') : '—'],
        ['Lỗi đã ghi', ms.length ? h('span', { class: 'row sx-cell' }, ['confirmed', 'edited', 'added', 'rejected'].map(function (k) {
          return n[k] ? [ui.status(k), h('span', { class: 'num small' }, '×' + n[k])] : null;
        })) : 'không có']
      ])),
      section('Bài đã ghi · ' + atts.length + ' bài', h('div', { class: 'stack' }, atts.length ? atts.map(function (a) {
        var g = arr(a.grade), ok = g.filter(function (x) { return x.passed; }).length, mm = arr(a.mistakes);
        return h('article', { class: 'card sx-att st-db' },
          h('div', { class: 'spread' }, h('h3', null, 'Bài ' + a.seq + ' · ', h('span', { class: 'mono' }, a.ref || '—')),
            h('span', { class: 'row sx-cell' }, h('b', { class: 'num' }, pts(a.score) + '/' + pts(a.max_score)), ui.prov('llm', '02'),
              a.rubric && a.rubric.version != null ? ui.chip('rubric v' + a.rubric.version) : null)),
          h('details', { class: 'sx-details' }, h('summary', null, 'Chấm theo rubric (' + ok + '/' + g.length + ' mục đạt)'), gradeList((a.rubric || {}).items, g)),
          h('details', { class: 'sx-details' }, h('summary', null, 'Bài làm HS (' + arr(a.steps).length + ' bước)'), stepList(a.steps, s.student_code + ' · bài ' + a.seq)),
          mm.length ? h('div', { class: 'stack sx-mlist' }, mm.map(mistakeRow)) : h('p', { class: 'small muted' }, 'Không có lỗi nào được ghi cho bài này.'));
      }) : ui.empty('Buổi này không có bài nào.')))
    ];
  }
  function viewSession(root, life, sid) {
    var top = h('div', { class: 'stack' }, ui.pageHead({ eyebrow: 'Buổi học', title: 'Buổi #' + sid })), body = h('div', { class: 'stack' }, loading());
    root.append(top, body);
    Promise.all([api.get('/sessions/' + encodeURIComponent(sid)), loadRef()]).then(function (r) {
      if (!life.alive) return;
      var s = r[0];
      if (s.status !== 'committed' && s.thread_id) { C.nav('session', { thread: s.thread_id }); return; }
      put(top, ui.pageHead({
        eyebrow: 'Buổi học · ' + (s.status === 'committed' ? 'đã ghi tutor.db (chỉ đọc)' : s.status), title: s.student_code + ' · buổi ' + F.date(s.held_on),
        actions: [ui.button('Xem bản chép LaTeX', function () { openTranscript(s.transcript_latex, { thread_id: s.thread_id || 'buổi #' + s.id }); },
          { kind: 'secondary', disabledReason: s.transcript_latex ? null : 'buổi không có bản chép' }), backBtn()]
      }));
      put(body, detailBody(s));
      C.tex(root);
    }, function (e) {
      if (!life.alive) return;
      put(body, e.status === 404 ? h('div', { class: 'callout callout-warn' }, h('strong', null, 'Không tìm thấy buổi #' + sid), h('div', null, backBtn())) : failBox(e, 'buổi #' + sid));
    });
  }

  App.registerTab('session', {
    title: 'Buổi học',
    render: function (root, ctx) {
      C = ctx; ui = ctx.ui; h = ui.h; F = ui.fmt;
      var life = { alive: true, timer: null, flush: null, off: null }, p = ctx.params;
      if (p.thread) viewThread(root, life, p.thread);
      else if (p.session) viewSession(root, life, p.session);
      else if (p.step === '1') viewSubmit(root, life);
      else viewList(root, life);
      // Same #view element is reused by the next render: stop polling, keys, timers and late fetch callbacks; send a pending save now.
      return function () { life.alive = false; clearTimeout(life.timer); if (life.off) life.off(); if (life.flush) life.flush(); };
    }
  });
})();
