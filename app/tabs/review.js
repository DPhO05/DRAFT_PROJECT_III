/* Hộp duyệt (P3-T07, IA §3.2): một hàng chờ cho mọi graph đang dừng = `tutor review`; chỉ liệt kê và mở, không ghi gì.
   Dữ liệu: hàng chờ của shell (TutorApi.refreshQueue → GET /api/threads, khoá do server tính, t.summary = số mục). */
(function () {
  'use strict';
  var GLABEL = { G1: 'Lỗi buổi học', G2: 'Tag KC + rubric', G4: 'Gợi ý', G5: 'Báo cáo' };
  var arr = function (x) { return Array.isArray(x) ? x : []; };
  // Kept across renders in this page session.
  var S = { students: null };

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, Q = ctx.queue, p = ctx.params || {};
    var f = { graph: /^G[1-5]$/.test(p.graph || '') ? p.graph : '', student: p.student ? +p.student || null : null };
    var threads = function () { return arr((ctx.data.checkpoints || {}).threads); };
    var listBox = h('div', { class: 'stack' }), sig = null, dead = false;

    function nameOf(id) { var s = arr(S.students).find(function (x) { return x.id === id; }); return s ? s.name : ''; }
    function subjectCell(t) {
      var name = t.student_id != null ? nameOf(t.student_id) : '';
      return h('div', { class: 'rv-subj' }, h('b', null, t.subject || t.thread_id), name ? h('div', { class: 'small muted' }, name) : null);
    }
    function itemsCell(t) {
      var s = t.summary;
      if (!s) return h('span', { class: 'muted', title: 'Chưa tải được state của thread' }, '—');
      return h('div', null, h('b', { class: 'num' }, s.label || s.items + ' ' + s.unit),
        t.node === 'gate_confirm_match' ? h('div', { class: 'small muted' }, 'lỗi: chưa chạy 02·03·04') : null,
        t.node === 'gate_confirm_commit' ? h('div', { class: 'small muted' }, 'đã duyệt xong, xem trước tiến bộ rồi lưu') : null);
    }
    function disagreeCell(t) {
      var s = t.summary;
      if (!s || s.disagree == null || !s.items) return h('span', { class: 'muted' }, '—');
      return ui.chip(s.disagree + '/' + s.items, s.disagree ? 'warn' : 'ok');
    }
    function cliFor(t) { return t.node === 'gate_review' || t.node === 'gate_confirm_commit' ? 'tutor review ' + t.thread_id : null; }
    function openCell(t) {
      if (t.locked) {
        return h('div', { class: 'stack rv-tight rv-act' },
          ui.button('Mở', null, { size: 'sm', disabledReason: t.lock_reason }),
          ui.button('Mở buổi chặn', function () { Q.open(t.blocking_thread_id); }, { size: 'sm', title: 'Mở ' + t.blocking_thread_id }));
      }
      return h('div', { class: 'rv-act' }, ui.button('Mở', function () { Q.open(t.thread_id); }, { kind: 'primary', size: 'sm', cli: cliFor(t) }));
    }
    function badCard(t) {
      var failed = t.status === 'failed';
      return h('div', { class: 'card ' + (failed ? 'rv-bad' : 'rv-run') },
        h('div', { class: 'spread' }, h('div', { class: 'row' }, ui.chip(t.graph, t.graph), subjectCell(t), ui.status(t.status)),
          h('span', { class: 'small muted' }, (t.node ? (failed ? 'dừng ở ' : 'tại ') + ui.nodeName(t.node) + ' · ' : '') + fmt.dt(t.updated_at))),
        failed ? h('pre', { class: 'code rv-err' }, t.error || 'Lỗi không rõ') : null,
        h('p', { class: 'small' }, failed
          ? 'Phần đã chạy xong vẫn nằm trong checkpoints.db. Chạy lại chỉ chạy node lỗi trở đi, rồi dừng ở DỪNG để thầy/cô duyệt.'
          : 'Đang chạy tại ' + ui.nodeName(t.node) + ' — chưa có gì để duyệt. Khi tới DỪNG, mục này vào danh sách chờ.'),
        h('div', { class: 'row' }, failed
          ? ui.button('Chạy lại từ checkpoint', function (e, b) { b.disabled = true; b.textContent = 'Đang chạy lại…'; return ctx.threads.resume(t.thread_id); }, { kind: 'primary' })
          : ui.button('Xem tiến trình', function () { ctx.nav(t.graph === 'G1' ? 'session' : 'ops', { thread: t.thread_id }); })));
    }

    function drawList() {
      var all = Q.list();
      var rows = Q.list({ graph: f.graph || undefined, student_id: f.student == null ? undefined : f.student });
      var first = rows.find(function (t) { return !t.locked; });
      var locked = rows.filter(function (t) { return t.locked; }).length;
      var head = h('div', { class: 'section-head' },
        h('div', null, h('h2', null, 'Danh sách chờ'), ui.store('checkpoint'),
          h('span', { class: 'small muted' }, rows.length + ' mục' + (locked ? ' · ' + locked + ' khoá' : '') + (rows.length !== all.length ? ' (lọc từ ' + all.length + ')' : ''))),
        h('div', { class: 'rv-next' },
          ui.button('Duyệt tiếp mục ưu tiên', function () { Q.open(first.thread_id); },
            { kind: 'primary', cli: 'tutor review', disabledReason: first ? null : (all.length ? 'Không có mục mở được cho bộ lọc này' : 'Hộp duyệt trống') }),
          first ? h('span', { class: 'small muted' }, '→ ' + (first.subject || first.thread_id) + ' · ' + Q.stageLabel(first)) : null));
      var body;
      if (!all.length) body = ui.empty('Hộp duyệt trống — không graph nào đang dừng.');
      else if (!rows.length) body = ui.empty('Không có mục nào cho bộ lọc này.', ui.button('Bỏ lọc', function () { ctx.nav('review', {}); }, { size: 'sm' }));
      else {
        var cols = [
          { label: 'thread_id', render: function (t) { return h('code', { class: 'small rv-tid' }, t.thread_id); } },
          { label: 'Graph', render: function (t) { return ui.chip(t.graph, t.graph); } },
          { label: 'Đối tượng', render: subjectCell },
          { label: 'Lý do dừng', render: function (t) { return h('span', { title: 'node = ' + t.node }, Q.stageLabel(t)); } },
          { label: 'Số mục', render: itemsCell },
          { label: 'Bất đồng 04', render: disagreeCell },
          { label: 'Chờ từ', render: function (t) { return h('div', { class: 'nowrap' }, fmt.ago(t.updated_at), h('div', { class: 'small muted' }, fmt.dt(t.updated_at))); } },
          { label: 'Trạng thái', render: function (t) { return ui.status(t.locked ? 'locked' : 'waiting'); } },
          { label: '', render: openCell }
        ];
        body = ui.table({ rows: rows, columns: cols, rowClass: function (t) { return t.locked ? 'is-dim rv-locked' : null; } });
        // Labels per cell let the phone layout show each row as a card (review.css).
        body.querySelectorAll('tbody tr').forEach(function (tr) { Array.prototype.forEach.call(tr.children, function (td, i) { td.setAttribute('data-label', cols[i].label); }); });
        body = h('div', { class: 'rv-table' }, body);
      }
      listBox.replaceChildren(head, body);
    }

    function draw() {
      var s = JSON.stringify(threads()) + '|' + JSON.stringify(S.students);
      if (dead || s === sig) return;  // shell refresh with the same queue: keep the DOM (and focus)
      sig = s;
      var all = Q.list(), counts = {};
      all.forEach(function (t) { counts[t.graph] = (counts[t.graph] || 0) + 1; });
      var failed = threads().filter(function (t) { return t.status === 'failed'; });
      var running = threads().filter(function (t) { return t.status === 'running'; });

      var seg = ui.segmented([{ id: '', label: 'Tất cả (' + all.length + ')' }].concat(['G1', 'G2', 'G4', 'G5'].map(function (g) {
        return { id: g, label: h('span', { class: 'rv-seg' }, h('span', { class: 'rv-dot', style: '--c: var(--' + g.toLowerCase() + ')' }), g + ' ' + GLABEL[g] + ' (' + (counts[g] || 0) + ')') };
      })), f.graph, function (id) { f.graph = id; drawList(); });
      var sel = h('select', { 'aria-label': 'Lọc theo học sinh', onchange: function () { f.student = sel.value ? +sel.value : null; drawList(); } },
        h('option', { value: '' }, 'Tất cả HS'),
        arr(S.students).map(function (s) { return h('option', { value: String(s.id), selected: f.student === s.id }, s.code + ' · ' + s.name); }));

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
            h('div', null, h('b', null, 'Duyệt'), ' = cho graph chạy tiếp tới node commit'))),
        h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, 'Bộ lọc'))),
          h('div', { class: 'row rv-filters' }, seg, h('label', { class: 'field rv-sel' }, h('span', null, 'Học sinh'), sel))),
        h('section', { class: 'section' }, listBox),
        h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, 'Thread lỗi / đang chạy'), h('span', { class: 'small muted' }, 'không duyệt được — chưa tới DỪNG'))),
          failed.length ? failed.map(badCard) : h('div', { class: 'callout callout-ok' }, h('p', null, 'Không có thread lỗi.')),
          running.map(badCard)),
        h('p', { class: 'rv-note' }, 'Không có nút “Duyệt tất cả” — cố ý: giáo viên quyết từng đề xuất (NFR4).',
          ' ', h('span', { class: 'muted' }, 'Xem thêm: '),
          ui.button('Vận hành', function () { ctx.nav('ops', {}); }, { kind: 'ghost', size: 'sm' })));
      drawList();
    }

    Q.on(draw);
    draw();
    // Student names for the filter (the queue itself is already in the shell); cached list shows first.
    api.get('/students').then(function (s) { S.students = s; draw(); }, function () { S.students = S.students || []; draw(); });
    return function () { dead = true; };
  }

  App.registerTab('review', { title: 'Hộp duyệt', render: render });
})();
