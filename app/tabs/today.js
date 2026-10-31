/* Hôm nay (P3-T09, IA §3.1 mục 1, 2, 5): việc chờ duyệt, cảnh báo, hệ thống. Nhịp dùng, HS cần chú ý, hoạt động: P4+.
   Hàng chờ = của shell (TutorApi.refreshQueue); hệ thống đọc /api/sessions, /api/backup, meta.cost. */
(function () {
  'use strict';
  var GLABEL = { G1: 'Lỗi buổi học', G2: 'Tag KC + rubric', G4: 'Gợi ý', G5: 'Báo cáo' };
  var WEEKDAY = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  var arr = function (x) { return Array.isArray(x) ? x : []; };

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, Q = ctx.queue, meta = ctx.data.meta || {};
    var today = meta.today || new Date().toISOString().slice(0, 10);
    var threads = function () { return arr((ctx.data.checkpoints || {}).threads); };
    var sys = { last: undefined, backup: undefined }, sig = null, dead = false;

    function head(title, extra) { return h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), extra || null)); }
    function who(t) { return h('b', null, t.subject || t.thread_id); }

    /* 1. Việc cần làm */
    function todo(queue) {
      var counts = {};
      queue.forEach(function (t) { counts[t.graph] = (counts[t.graph] || 0) + 1; });
      var chips = h('div', { class: 'row td-gchips' }, ['G1', 'G2', 'G4', 'G5'].map(function (g) {
        return ui.button(h('span', { class: 'td-gchip', style: '--c: var(--' + g.toLowerCase() + ')' }, h('b', null, g), ' ' + GLABEL[g] + ' ', h('span', { class: 'td-n num' }, String(counts[g] || 0))),
          function () { ctx.nav('review', { graph: g }); }, { kind: 'secondary', size: 'sm', title: 'Mở Hộp duyệt, lọc ' + g });
      }));
      var open = queue.filter(function (t) { return !t.locked; });
      var next = open[0];  // = "Duyệt tiếp mục ưu tiên" in Hộp duyệt (queue order)
      var top = open.slice().sort(function (a, b) { return String(a.updated_at).localeCompare(String(b.updated_at)); }).slice(0, 5);
      var list = top.length ? h('ol', { class: 'td-list' }, top.map(function (t) {
        return h('li', { class: 'td-item st-pending' },
          h('div', { class: 'td-item-main' },
            h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t)),
            h('div', { class: 'small td-meta' }, h('span', null, Q.stageLabel(t)),
              h('span', { class: 'muted' }, ' · chờ từ ' + fmt.ago(t.updated_at) + ' (' + fmt.dt(t.updated_at) + ')'))),
          ui.button('Mở', function () { Q.open(t.thread_id); }, { kind: 'primary', size: 'sm', cli: t.node === 'gate_review' ? 'tutor review ' + t.thread_id : null }));
      })) : ui.empty(queue.length ? 'Mọi mục chờ đang khoá — xem Cảnh báo.' : 'Không có gì chờ duyệt. Mọi đề xuất đã vào tutor.db.');
      var lockedN = queue.length - open.length;
      return h('section', { class: 'section td-todo' },
        head('Việc cần làm', h('span', { class: 'num td-big' }, String(queue.length))),
        h('p', { class: 'small td-sub' }, ui.store('checkpoint'), ' nằm trong checkpoints.db, chưa vào tutor.db'),
        chips,
        h('h3', { class: 'td-h3' }, '5 mục chờ lâu nhất', h('span', { class: 'small muted' }, ' (bỏ qua mục đang khoá)')),
        list,
        h('div', { class: 'row' },
          ui.button('Duyệt tiếp', function () { Q.open(next.thread_id); }, { kind: 'primary', cli: 'tutor review', disabledReason: next ? null : (queue.length ? 'Mọi mục đang khoá' : 'Hộp duyệt trống') }),
          next ? h('span', { class: 'small muted' }, '→ ' + (next.subject || next.thread_id) + ' · ' + Q.stageLabel(next)) : null),
        h('div', { class: 'row' },
          ui.button('Mở Hộp duyệt (' + queue.length + ')', function () { ctx.nav('review', {}); }, { kind: 'ghost', size: 'sm' }),
          open.length > top.length ? h('span', { class: 'small muted' }, '+' + (open.length - top.length) + ' mục khác') : null,
          lockedN ? h('span', { class: 'small muted' }, '· ' + lockedN + ' mục khoá') : null));
    }

    /* 2. Cảnh báo */
    function warnings(queue) {
      var failed = threads().filter(function (t) { return t.status === 'failed'; });
      var running = threads().filter(function (t) { return t.status === 'running'; });
      var locked = queue.filter(function (t) { return t.locked; });
      var items = [];
      if (!failed.length) items.push(h('div', { class: 'callout callout-ok' }, h('p', null, 'Không có thread lỗi.')));
      failed.forEach(function (t) {
        items.push(h('div', { class: 'callout callout-crit' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('failed')),
          h('p', { class: 'small' }, t.node ? ['Dừng ở ', h('b', null, ui.nodeName(t.node)), ' · '] : 'Hỏng lúc ', fmt.dt(t.updated_at)),
          h('code', { class: 'small td-err' }, t.error || 'Lỗi không rõ'),
          ui.button('Chạy lại từ checkpoint', function (e, b) { b.disabled = true; b.textContent = 'Đang chạy lại…'; return ctx.threads.resume(t.thread_id); }, { kind: 'primary', size: 'sm' }),
          h('p', { class: 'small muted' }, 'Chỉ chạy lại node lỗi trở đi; phần đã xong giữ trong checkpoints.db.')));
      });
      locked.forEach(function (t) {
        items.push(h('div', { class: 'callout callout-warn' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('locked')),
          h('p', { class: 'small' }, t.lock_reason),
          ui.button('Mở buổi chặn', function () { Q.open(t.blocking_thread_id); }, { kind: 'secondary', size: 'sm', title: 'Mở ' + t.blocking_thread_id })));
      });
      running.forEach(function (t) {
        items.push(h('div', { class: 'callout callout-info' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('running')),
          h('p', { class: 'small' }, 'Đang chạy tại ', h('b', null, ui.nodeName(t.node)), ' — chưa tới DỪNG, chưa có gì để duyệt.'),
          ui.button('Xem tiến trình', function () { ctx.nav(t.graph === 'G1' ? 'session' : 'ops', { thread: t.thread_id }); }, { kind: 'ghost', size: 'sm' })));
      });
      return h('section', { class: 'section td-warn' },
        head('Cảnh báo', h('span', { class: 'small muted' }, failed.length + ' hỏng · ' + locked.length + ' khoá · ' + running.length + ' đang chạy')), items);
    }

    /* 5. Hệ thống */
    function system() {
      var health = meta.health || {}, mc = meta.cost, bk = sys.backup, last = sys.last;
      var open = threads().filter(function (t) { return t.status !== 'committed' && t.status !== 'done'; });
      var by = function (st) { return open.filter(function (t) { return t.status === st; }).length; };
      var loading = h('span', { class: 'muted' }, 'Đang tải…');
      return h('section', { class: 'section' },
        head('Hệ thống'),
        ui.kv([
          ['Ghi tutor.db gần nhất', last === undefined ? loading : last ? h('span', null, fmt.dt(last.committed_at) + ' ', ui.chip('G1', 'G1'), ' ' + last.student_code + ' · buổi ' + fmt.date(last.held_on)) : 'Chưa ghi buổi nào'],
          ['Sao lưu gần nhất', bk === undefined ? loading : bk ? h('span', null, h('code', { class: 'small' }, bk.name), ' · ' + fmt.num(bk.bytes / 1048576, 1) + ' MB') : 'Chưa sao lưu lần nào'],
          ['Chi phí tháng ' + (+today.slice(5, 7)), mc ? h('div', { class: 'stack td-cost' },
            h('span', null, h('b', { class: 'num' }, fmt.usd(mc.total_usd)), ' / ' + (mc.budget_usd != null ? fmt.usd(mc.budget_usd) : 'chưa đặt') + ' · ' + fmt.int(mc.calls) + ' lời gọi',
              mc.assumption ? h('span', { class: 'small muted' }, ' (đơn giá giả định)') : null),
            mc.budget_usd ? ui.bar(mc.total_usd, mc.budget_usd, { kind: mc.total_usd > mc.budget_usd * 0.8 ? 'warn' : 'accent' }) : null) : 'Chưa đọc được nhật ký chi phí'],
          ['checkpoints.db', open.length + ' thread đang mở: ' + by('awaiting_review') + ' chờ duyệt · ' + by('failed') + ' hỏng · ' + by('running') + ' đang chạy'],
          ['tutor.db', (health.db === 'ok' ? 'sẵn sàng' : 'lỗi, xem Vận hành') + ' · phiên bản ' + (health.version || '?')]
        ]),
        h('div', { class: 'row' },
          ui.button('Mở Vận hành', function () { ctx.nav('ops', {}); }, { kind: 'secondary', size: 'sm' }),
          ui.button('Mở Nhật ký & chi phí', function () { ctx.nav('logs', {}); }, { kind: 'secondary', size: 'sm' })));
    }

    function draw() {
      var s = JSON.stringify([threads(), sys]);
      if (dead || s === sig) return;  // shell refresh with the same data: keep the DOM
      sig = s;
      var queue = Q.list();
      var wd = WEEKDAY[new Date(today + 'T00:00:00Z').getUTCDay()];
      root.replaceChildren(
        ui.pageHead({ lead: wd + ', ' + fmt.date(today) + ' — việc cần thầy/cô quyết và cảnh báo. Mọi đề xuất còn nằm trong checkpoints.db cho tới khi thầy/cô duyệt.' }),
        h('div', { class: 'td-top' }, todo(queue), warnings(queue)),
        system());
    }

    Q.on(draw);
    draw();
    var committed = api.get('/sessions?status=committed').then(function (rows) {
      return arr(rows).filter(function (r) { return r.committed_at; }).sort(function (a, b) { return String(b.committed_at).localeCompare(String(a.committed_at)); })[0] || null;
    }, function () { return null; });
    var backup = api.get('/backup').then(function (b) { return arr(b.backups)[0] || null; }, function () { return null; });
    Promise.all([committed, backup]).then(function (r) { sys.last = r[0]; sys.backup = r[1]; draw(); });
    return function () { dead = true; };
  }

  App.registerTab('today', { title: 'Hôm nay', render: render });
})();
