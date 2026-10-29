/* tabs/review.js — Hộp duyệt (IA §3.2): one queue for every graph paused at DỪNG = `tutor review`; lists and routes, never commits. */
(function () {
  'use strict';
  var GLABEL = { G1: 'Lỗi buổi học', G2: 'Tag KC + rubric', G3: 'Độ khó', G4: 'Gợi ý', G5: 'Báo cáo' };
  var KIND_VI = { mistake: 'lỗi', kc_tag: 'tag KC', rubric: 'rubric', difficulty: 'xếp hạng KC', recommendation: 'bài', report: 'report' };
  var arr = function (x) { return Array.isArray(x) ? x : []; };

  // Time the thread reached its interrupt (falls back to its latest checkpoint).
  function stopAt(t) {
    var cps = arr(t.checkpoints);
    var hit = t.interrupted_at ? cps.filter(function (c) { return c.node === t.interrupted_at; }).pop() : null;
    if (hit) return hit.at;
    return cps.reduce(function (m, c) { return c.at > m ? c.at : m; }, t.started_at || '');
  }

  function openFlags(t) {
    var out = [];
    arr(t.state && t.state.attempts).forEach(function (a) {
      arr(a.flags_json).forEach(function (f) { if (!f.resolved && f.type !== 'alt_method') out.push({ seq: a.seq, type: f.type }); });
    });
    return out;
  }

  function verdicts(t) {
    var ps = arr(t.state && t.state.proposals), w = 0, d = 0;
    ps.forEach(function (p) { var v = p.verifier && p.verifier.verdict; if (v === 'wrong_code') w++; else if (v === 'disagree') d++; });
    return { wrong: w, disagree: d, n: w + d, total: ps.length };
  }

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, L = ctx.lookup, M = ctx.data;
    var meta = M.meta || {};
    var students = arr((M.db || {}).student).filter(function (s) { return !s.archived_at; });
    var p = ctx.params || {};
    var pStudent = p.student ? (/^HS-/i.test(p.student) ? L.studentByCode(p.student.toUpperCase()) : L.student(p.student)) : null;
    var f = { graph: /^G[1-5]$/.test(p.graph || '') ? p.graph : '', student: pStudent ? pStudent.id : null };

    var stageLabel = function (t) { return (meta.stage_labels || {})[t.interrupted_at || t.current_node] || ui.nodeName(t.current_node); };

    function subjectCell(t) {
      var s = t.student_id != null ? L.student(t.student_id) : null;
      if (!s) return h('div', { class: 'rv-subj' }, h('b', null, t.subject || t.thread_id));
      var rest = String(t.subject || '').replace(/^HS-\d+\s*·\s*/, '');
      return h('div', { class: 'rv-subj' }, h('b', null, L.studentCode(s)), ' ', h('span', { class: 'muted' }, s.name), h('div', { class: 'small' }, rest));
    }

    // Same wording as session step 3.
    var FLAG_LABEL = { low_match: 'khớp bài chưa chắc', mismatch: 'bản chép ≠ text layer', no_rubric: 'chưa có rubric', alt_method: 'cách giải khác' };
    function reasonCell(t) {
      var bits = [h('span', null, stageLabel(t))];
      if (t.interrupted_at === 'g1.confirm_match') {
        var fl = openFlags(t);
        bits.push(h('div', { class: 'row rv-chips' }, fl.map(function (x) { var c = ui.chip('bài ' + x.seq + ' · ' + (FLAG_LABEL[x.type] || x.type), 'warn'); c.title = x.type; return c; })));
      }
      if (t.graph === 'G5') {
        var rp = arr(t.state && t.state.proposals)[0];
        if (rp && rp.tone && rp.tone.low_results) bits.push(h('div', { title: 'Tỉ lệ đạt ' + fmt.pct(rp.tone.pass_rate) + ' < ' + fmt.pct(rp.tone.threshold) + ' → không khen quá tay' }, ui.chip('kết quả thấp ' + fmt.pct(rp.tone.pass_rate), 'warn')));
      }
      return h('div', { class: 'stack rv-tight' }, bits);
    }

    function itemsCell(t) {
      var st = t.state || {};
      if (t.interrupted_at === 'g1.confirm_match') {
        var n = openFlags(t).length;
        return h('div', null, h('b', { class: 'num' }, n + ' cờ'), h('div', { class: 'small muted' }, 'lỗi: chưa chạy 02·03·04'));
      }
      var by = {}, order = [];
      arr(st.proposals).forEach(function (x) { if (!by[x.kind]) { by[x.kind] = 0; order.push(x.kind); } by[x.kind]++; });
      var main = order.map(function (k) { return by[k] + ' ' + (KIND_VI[k] || k); }).join(' + ') || '0';
      var sub = null;
      if (t.graph === 'G1') sub = arr(st.attempts).length + ' bài làm';
      if (t.graph === 'G2') sub = arr(st.problems).length + ' bài';
      if (t.graph === 'G3') sub = arr(st.proposals).reduce(function (s, x) { return s + arr(x.ranking).length; }, 0) + ' bài';
      if (t.graph === 'G4') sub = 'cho buổi ' + fmt.date(st.for_date);
      if (t.graph === 'G5') { var rp = arr(st.proposals)[0]; sub = rp ? arr(rp.audit_json).length + ' câu · tháng ' + fmt.month(st.month) : null; }
      return h('div', null, h('b', { class: 'num' }, main), sub ? h('div', { class: 'small muted' }, sub) : null);
    }

    function disagreeCell(t) {
      if (t.graph !== 'G1') return h('span', { class: 'muted' }, '—');
      var v = verdicts(t);
      if (!v.total) return h('span', { class: 'muted' }, '—');
      var parts = [];
      if (v.wrong) parts.push(v.wrong + ' sai mã');
      if (v.disagree) parts.push(v.disagree + ' phản đối');
      return h('div', null, ui.chip(v.n + '/' + v.total, v.n ? 'warn' : 'ok'), parts.length ? h('div', { class: 'small muted' }, parts.join(' · ')) : null);
    }

    function openCell(t) {
      if (t.locked) {
        return h('div', { class: 'stack rv-tight rv-act' },
          ui.button('Mở', null, { size: 'sm', disabledReason: t.lock_reason }),
          ui.button('Mở buổi chặn', function () { ctx.queue.open(t.blocker); }, { size: 'sm', cli: 'tutor review ' + t.blocker }));
      }
      return h('div', { class: 'rv-act' }, ui.button('Mở', function () { ctx.queue.open(t.thread_id); }, { kind: 'primary', size: 'sm', cli: 'tutor review ' + t.thread_id }));
    }

    function stripFor(t) {
      var cps = arr(t.checkpoints);
      var o = { compact: true, done: cps.filter(function (c) { return c.lane == null; }).map(function (c) { return c.node; }) };
      if (t.status !== 'failed') o.current = t.interrupted_at || t.current_node;
      var atts = t.graph === 'G1' ? arr(t.state && t.state.attempts) : [];
      if (atts.length) {
        o.lanes = atts.map(function (a) {
          var done = cps.filter(function (c) { return c.lane === a.seq; }).map(function (c) { return c.node; });
          var pr = a.problem_id != null ? L.problem(a.problem_id) : null;
          return { seq: a.seq, label: 'Bài ' + a.seq + (pr ? ' · ' + pr.ref : ''), done: done,
            failed: t.status === 'failed' && done.indexOf(t.current_node) < 0 ? t.current_node : undefined };
        });
      } else if (t.status === 'failed') o.failed = t.current_node;
      return ui.graphStrip(t.graph, o);
    }

    function badThreadCard(t) {
      var who = subjectCell(t);
      if (t.status === 'failed') {
        var run = ((M.ui || {}).demo_runs || {})[t.demo_run];
        var node = arr(((meta.graphs || {})[t.graph] || {}).nodes).find(function (n) { return n.id === t.current_node; });
        return h('div', { class: 'card rv-bad' },
          h('div', { class: 'spread' }, h('div', { class: 'row' }, ui.chip(t.graph, t.graph), who, ui.status('failed')),
            h('span', { class: 'small muted' }, 'dừng ở ' + ui.nodeName(t.current_node) + ' · ' + fmt.dt(stopAt(t)))),
          stripFor(t),
          h('pre', { class: 'code rv-err' }, t.error || 'Lỗi không rõ'),
          h('p', { class: 'small' }, 'Các làn đã xong vẫn nằm trong checkpoints.db. Chạy lại chỉ chạy node lỗi trở đi, rồi dừng ở DỪNG để thầy/cô duyệt.'),
          h('div', { class: 'row' },
            ui.button('Chạy lại từ checkpoint', function () { ctx.threads.resume(t.thread_id); }, { kind: 'primary' }),
            run ? h('span', { class: 'small muted' }, 'ước tính phần chạy lại: ') : null,
            run ? ui.costChip(run.llm_calls) : null),
          ui.annot(['checkpoint', node && node.agent ? 'agent:' + node.agent : null, 'table:session'].filter(Boolean)));
      }
      return h('div', { class: 'card rv-run' },
        h('div', { class: 'spread' }, h('div', { class: 'row' }, ui.chip(t.graph, t.graph), who, ui.status('running')),
          h('span', { class: 'small muted' }, 'bắt đầu ' + fmt.dt(t.started_at))),
        stripFor(t),
        h('p', { class: 'small' }, 'Đang chạy tại ' + ui.nodeName(t.current_node) + ' — chưa có gì để duyệt. Khi tới DỪNG, mục này vào danh sách chờ.'),
        h('div', { class: 'row' }, ui.button('Xem đang chạy', function () { ctx.nav('session', { thread: t.thread_id }); }, { kind: 'secondary' })));
    }

    var listBox = h('div', { class: 'stack' });
    var stripBox = h('div');

    function drawList() {
      var rows = ctx.queue.list({ graph: f.graph || undefined, student_id: f.student == null ? undefined : f.student });
      var all = ctx.queue.list();
      var first = rows.find(function (t) { return !t.locked; });
      var locked = rows.filter(function (t) { return t.locked; }).length;
      var head = h('div', { class: 'section-head' },
        h('div', null, h('h2', null, 'Danh sách chờ'), ui.store('checkpoint'),
          h('span', { class: 'small muted' }, rows.length + ' mục' + (locked ? ' · ' + locked + ' khoá' : '') + (rows.length !== all.length ? ' (lọc từ ' + all.length + ')' : ''))),
        h('div', { class: 'rv-next' },
          ui.button('Duyệt tiếp mục ưu tiên', function () { if (first) ctx.queue.open(first.thread_id); },
            { kind: 'primary', cli: 'tutor review', disabledReason: first ? null : (all.length ? 'Không có mục mở được cho bộ lọc này' : 'Hộp duyệt trống') }),
          first ? h('span', { class: 'small muted' }, '→ ' + first.subject + ' · ' + stageLabel(first)) : null));
      var body;
      if (!all.length) body = ui.empty('Hộp duyệt trống — không graph nào đang dừng.');
      else if (!rows.length) body = ui.empty('Không có mục nào cho bộ lọc này.', ui.button('Bỏ lọc', function () { ctx.nav('review', {}); }, { size: 'sm' }));
      else {
        var cols;
        body = ui.table({
          rows: rows,
          rowClass: function (t) { return t.locked ? 'is-dim rv-locked' : null; },
          onRow: function (t) { ctx.queue.open(t.thread_id); },
          columns: cols = [
            { key: 'thread_id', label: 'thread_id', render: function (t) { return h('code', { class: 'small nowrap' }, t.thread_id); } },
            { key: 'graph', label: 'Graph', render: function (t) { return ui.chip(t.graph, t.graph); } },
            { key: 'subject', label: 'Đối tượng', render: subjectCell },
            { key: 'stage', label: 'Lý do dừng', render: reasonCell },
            { key: 'items', label: 'Số mục', render: itemsCell },
            { key: 'dis', label: 'Bất đồng 04', render: disagreeCell },
            { key: 'since', label: 'Chờ từ', render: function (t) { var at = stopAt(t); return h('div', { class: 'nowrap' }, fmt.ago(at), h('div', { class: 'small muted' }, fmt.dt(at))); } },
            { key: 'st', label: 'Trạng thái', render: function (t) { return ui.status(t.locked ? 'locked' : 'waiting'); } },
            { key: 'act', label: '', render: openCell }
          ]
        });
        // Labels per cell let the phone layout show each row as a card (review.css).
        body.querySelectorAll('tbody tr').forEach(function (tr) { Array.prototype.forEach.call(tr.children, function (td, i) { td.setAttribute('data-label', cols[i].label); }); });
        body = h('div', { class: 'rv-table' }, body);
      }
      listBox.replaceChildren(head, body);
      var g = f.graph || 'G1', stop = g.toLowerCase() + '.review';
      var nodes = arr(((meta.graphs || {})[g] || {}).nodes), i = nodes.findIndex(function (n) { return n.id === stop; });
      stripBox.replaceChildren(ui.graphStrip(g, { compact: true, current: stop, done: nodes.slice(0, Math.max(0, i)).map(function (n) { return n.id; }) }));
      ctx.tex(listBox);
    }

    function draw() {
      var all = ctx.queue.list();
      var counts = {};
      all.forEach(function (t) { counts[t.graph] = (counts[t.graph] || 0) + 1; });
      var threads = arr((M.checkpoints || {}).threads);
      var failed = threads.filter(function (t) { return t.status === 'failed'; });
      var running = threads.filter(function (t) { return t.status === 'running'; });

      var seg = ui.segmented([{ id: '', label: 'Tất cả (' + all.length + ')' }].concat(['G1', 'G2', 'G3', 'G4', 'G5'].map(function (g) {
        return { id: g, label: h('span', { class: 'rv-seg' }, h('span', { class: 'rv-dot', style: '--c: var(--' + g.toLowerCase() + ')' }), g + ' ' + GLABEL[g] + ' (' + (counts[g] || 0) + ')') };
      })), f.graph, function (id) { f.graph = id; drawList(); });

      var sel = h('select', { 'aria-label': 'Lọc theo học sinh', onchange: function () { f.student = sel.value ? +sel.value : null; drawList(); } },
        h('option', { value: '' }, 'Tất cả HS'),
        students.map(function (s) { return h('option', { value: String(s.id), selected: f.student === s.id }, L.studentCode(s) + ' · ' + s.name); }));

      root.replaceChildren(
        ui.pageHead({
          lead: 'Một hàng chờ cho mọi graph đang dừng ở DỪNG (giống lệnh tutor review). Bấm “Mở” để tới đúng màn hình duyệt; việc duyệt diễn ra ở đó.',
          annot: ['cli:tutor review', 'file:checkpoints.db', 'interrupt()']
        }),
        h('section', { class: 'section rv-banner st-pending' },
          h('p', { class: 'rv-banner-text' }, 'Các mục dưới đây đang nằm trong ', ui.store('checkpoint'), ', CHƯA vào ', ui.store('db'),
            '. Chỉ khi thầy/cô duyệt, commit node mới ghi — mỗi lần duyệt là 1 transaction.'),
          h('div', { class: 'rv-explain' },
            h('div', null, h('b', null, 'DỪNG'), ' = graph lưu state vào checkpoints.db rồi chờ bạn'),
            h('div', null, h('b', null, 'Duyệt'), ' = cho graph chạy tiếp tới node commit')),
          stripBox),
        h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, 'Bộ lọc'), ui.annot(['file:checkpoints.db']))),
          h('div', { class: 'row rv-filters' }, seg, h('label', { class: 'field rv-sel' }, h('span', null, 'Học sinh'), sel))),
        h('section', { class: 'section' }, listBox),
        h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, 'Thread lỗi / đang chạy'), h('span', { class: 'small muted' }, 'không duyệt được — chưa tới DỪNG'), ui.annot(['checkpoint', 'G1']))),
          failed.length ? failed.map(badThreadCard) : h('div', { class: 'callout callout-ok' }, h('p', null, 'Không có thread lỗi.')),
          running.map(badThreadCard)),
        h('p', { class: 'rv-note' }, 'Không có nút “Duyệt tất cả” — cố ý: giáo viên quyết từng đề xuất (NFR4).',
          ' ', h('span', { class: 'muted' }, 'Xem thêm: '),
          ui.button('Vận hành', function () { ctx.nav('ops', {}); }, { kind: 'ghost', size: 'sm' }))
      );
      drawList();
    }

    ctx.queue.on(draw);
    draw();
  }

  App.registerTab('review', { title: 'Hộp duyệt', render: render });
})();
