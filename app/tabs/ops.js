/* Vận hành (P2-T09, P3-T08): thread + số checkpoint, xem state, chạy lại / huỷ / dọn thread, lưu trữ + sao lưu. Cài đặt, riêng tư ở P4-T09. */
(() => {
  'use strict';
  const ST = ['running', 'awaiting_review', 'failed', 'done', 'committed'];
  const ST_VI = { running: 'Đang chạy', awaiting_review: 'Chờ duyệt', failed: 'Hỏng', done: 'Xong (không ghi)', committed: 'Đã ghi' };
  const POLL_MS = 2000;
  // Kept across renders in this page session; token drops fetches from an older render.
  const S = { status: 'all', token: 0 };

  App.registerTab('ops', { title: 'Vận hành', render });

  function render(root, ctx) {
    const token = ++S.token, { ui } = ctx, h = ui.h, F = ui.fmt, p = ctx.params;
    if (p.status === 'all' || ST.includes(p.status)) S.status = p.status;
    // watch = threads this page resumed: toast + shell refresh once they leave "running".
    const life = { dead: false, timer: null, sig: null, drawer: null, watch: new Set() };
    const alive = () => !life.dead && token === S.token;
    let threads = [];
    const syncQueue = () => { if (window.TutorApi && TutorApi.refreshQueue) TutorApi.refreshQueue().catch(() => {}); };
    const syncCounts = () => { if (window.TutorApi && TutorApi.refreshCounts) TutorApi.refreshCounts().catch(() => {}); };
    const thr = (id) => '/threads/' + encodeURIComponent(id);
    // Button stays disabled while the request runs; API errors become a toast (message is Vietnamese), not a console error.
    const run = (b, req, ok) => {
      if (b) b.disabled = true;
      return req.then(ok, (e) => { ctx.toast(e.message || String(e), { kind: 'error' }); })
        .then(() => { if (b && b.isConnected) b.disabled = false; });
    };

    // The shell's status map has no "done" (graph ended without a commit node).
    const stChip = (s) => (s === 'done'
      ? h('span', { class: 'status s-ok', 'data-status': 'done', title: 'status = done: graph đã kết thúc, không có node ghi tutor.db' }, 'xong')
      : ui.status(s));
    const sec = (id, title, right, ...kids) => h('section', { class: 'section', 'data-ops-section': id },
      h('div', { class: 'section-head' }, h('div', null, h('h2', null, title)), right || null), kids);
    const failBox = (msg, e, retry) => h('div', { class: 'callout callout-crit', role: 'alert' },
      h('strong', null, msg), h('p', { class: 'mono small' }, (e && e.message) || String(e)), h('div', null, ui.button('Thử lại', retry)));

    const thrBox = h('div', { class: 'stack' }, h('p', { class: 'muted' }, 'Đang tải thread…'));
    const cleanBox = h('span');
    const storeBox = h('div', { class: 'stack' }, h('p', { class: 'muted' }, 'Đang tải lưu trữ…'));
    root.append(
      ui.pageHead({
        lead: 'Phần máy đang chạy: mọi thread dừng ở đâu, bao nhiêu checkpoint, state trong checkpoints.db; chạy lại, huỷ, dọn thread; lưu trữ và sao lưu.',
        annot: ['file:checkpoints.db', 'file:tutor.db', 'checkpoint']
      }),
      h('div', { class: 'stack' },
        sec('threads', 'Thread', cleanBox, thrBox),
        sec('storage', 'Lưu trữ', h('span', { class: 'chip' }, '1 máy · 1 người dùng · không đăng nhập'), storeBox)));

    /* ---------- threads ---------- */
    function load() {
      return api.get('/threads').then((rows) => {
        if (!alive()) return;
        threads = rows;
        const sig = JSON.stringify(rows.map((t) => [t.thread_id, t.status, t.node, t.updated_at, t.checkpoints, t.running, t.locked]));
        if (sig !== life.sig) { life.sig = sig; paintThreads(); refreshDrawer(); }
        life.watch.forEach((id) => {
          const t = rows.find((x) => x.thread_id === id);
          if (t && t.status === 'running') return;
          life.watch.delete(id);
          if (t) ctx.toast((t.subject || id) + ': ' + ST_VI[t.status] + (t.error ? ' — ' + t.error : ''), { kind: t.status === 'failed' ? 'error' : 'ok', title: 'Chạy lại xong' });
          syncQueue(); syncCounts();  // a rerun inside commit ② writes tutor.db
        });
        schedule();
      }, (e) => {
        if (!alive()) return;
        life.sig = null;
        thrBox.replaceChildren(failBox('Không tải được danh sách thread.', e, load));
      });
    }
    // Poll only while a thread runs and the page is visible.
    function schedule() {
      clearTimeout(life.timer);
      if (alive() && !document.hidden && threads.some((t) => t.status === 'running')) life.timer = setTimeout(load, POLL_MS);
    }
    const onVis = () => (document.hidden ? clearTimeout(life.timer) : schedule());
    document.addEventListener('visibilitychange', onVis);

    function paintThreads() {
      const ended = threads.filter((t) => (t.status === 'committed' || t.status === 'done') && !t.running).length;
      cleanBox.replaceChildren(ui.button('Dọn thread đã commit', (e, b) => cleanup(b, ended),
        { title: 'Xoá khỏi checkpoints.db mọi thread đã ghi / đã xong', disabledReason: ended ? null : 'không có thread đã commit' }));
      if (!threads.length) {
        thrBox.replaceChildren(ui.empty('Chưa có thread nào. Mỗi lần nộp bài ở Buổi học là một thread G1 trong checkpoints.db.',
          ui.button('Mở Buổi học', () => ctx.nav('session'))));
        return;
      }
      const match = (s) => (t) => s === 'all' || t.status === s;
      const rows = threads.filter(match(S.status)).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
      const sel = h('select', { 'aria-label': 'Lọc trạng thái', onchange: (e) => { S.status = e.target.value; paintThreads(); } },
        ['all'].concat(ST).map((s) => h('option', { value: s, selected: S.status === s },
          (s === 'all' ? 'Tất cả' : ST_VI[s]) + ' (' + threads.filter(match(s)).length + ')')));
      const running = threads.some((t) => t.status === 'running');
      const table = ui.table({
        columns: [
          { label: 'thread_id', render: (t) => h('span', { class: 'mono small nowrap' }, t.thread_id) },
          { label: 'Graph', render: (t) => ui.chip(t.graph, t.graph) },
          { label: 'Đối tượng', render: (t) => t.subject || '—' },
          { label: 'Node cuối', render: (t) => h('span', { class: 'mono small' }, t.node || '—') },
          { label: 'Trạng thái', render: (t) => h('span', { class: 'row ops-st' }, stChip(t.status), t.locked ? lockChip(t) : null) },
          { label: 'Checkpoint', align: 'right', render: (t) => F.int(t.checkpoints) },
          { label: 'Cập nhật', render: (t) => h('span', { class: 'nowrap small' }, F.dt(t.updated_at)) },
          { label: 'Lỗi', render: (t) => (t.error ? h('span', { class: 'ops-err1 small', title: t.error }, t.error) : '') },
          { label: '', render: (t) => h('div', { class: 'row ops-acts' },
            ui.button('Xem state', () => openThread(t.thread_id), { size: 'sm', title: 'Xem state ' + t.thread_id }), acts(t, 'sm')) }
        ],
        rows,
        empty: 'Không có thread nào khớp bộ lọc.',
        rowClass: (t) => (t.locked ? 'is-dim' : null),
        onRow: (t) => openThread(t.thread_id)
      });
      table.classList.add('ops-thr-tbl');
      thrBox.replaceChildren(
        h('div', { class: 'row' }, sel, h('span', { class: 'small muted' },
          rows.length + '/' + threads.length + ' thread' + (running ? ' · tự cập nhật mỗi 2 giây khi còn thread đang chạy' : ''))),
        table);
    }

    /* ---------- thread actions ---------- */
    function lockChip(t) { const c = ui.status('locked'); c.title = t.lock_reason || ''; return c; }
    // Same buttons in the table row and the drawer; G1–G5 alike, the server decides what each graph touches.
    function acts(t, size) {
      const busy = t.running || t.status === 'running', out = [];
      if (t.status === 'awaiting_review') {
        out.push(ui.button('Mở trong Hộp duyệt', () => openQueue(t), { size, kind: size ? null : 'primary', disabledReason: t.locked ? t.lock_reason : null }));
      }
      if (t.status === 'failed' || busy) {
        out.push(ui.button('Chạy lại từ checkpoint cuối', (e, b) => resumeThread(t, b), { size, kind: 'primary', disabledReason: busy ? 'thread đang chạy' : null }));
      }
      if (t.status === 'failed' || t.status === 'awaiting_review' || busy) {
        out.push(ui.button('Huỷ thread', (e, b) => cancelThread(t, b), { size, kind: 'danger', disabledReason: busy ? 'thread đang chạy — chờ dừng rồi mới huỷ được' : null }));
      }
      return out;
    }
    function openQueue(t) {
      // The shell knows a thread only after TutorApi.refreshQueue loaded it; until then G1 opens straight in Buổi học.
      if (ctx.queue && ctx.queue.open && ctx.lookup && ctx.lookup.thread(t.thread_id)) return ctx.queue.open(t.thread_id);
      if (t.graph === 'G1') return ctx.nav('session', { thread: t.thread_id });
      ctx.toast('Chưa có màn hình duyệt cho ' + t.graph + '.', { kind: 'info' });
    }
    function resumeThread(t, b) {
      return run(b, api.send('POST', thr(t.thread_id) + '/resume'), () => {
        life.watch.add(t.thread_id);
        ctx.toast('Chỉ node lỗi (' + (t.node || '—') + ') và các node sau chạy lại; các node đã xong giữ nguyên trong checkpoints.db.',
          { kind: 'info', title: 'Chạy lại ' + (t.subject || t.thread_id) + ' từ checkpoint cuối' });
        syncQueue();
        return load();
      });
    }
    function cancelThread(t, b) {
      const body = h('div', { class: 'stack' },
        h('p', null, 'Huỷ thread ', h('span', { class: 'mono' }, t.thread_id), t.subject ? ' (' + t.subject + ')' : '', '? Không hoàn tác được.'),
        h('ul', { class: 'ops-list' },
          h('li', null, 'Đề xuất đang chờ duyệt trong checkpoints.db bị xoá cùng thread.'),
          h('li', null, t.graph === 'G1'
            ? 'tutor.db không nhận dữ liệu duyệt nào; riêng dòng session chưa có bài sẽ bị xoá để nộp lại được cùng file và mở khoá buổi sau (C-15).'
            : 'tutor.db không đổi vì thread chưa commit.')));
      return ctx.confirm(body, { title: 'Huỷ thread', ok: 'Huỷ thread', cancel: 'Giữ lại', danger: true }).then((yes) => {
        if (!yes) return null;
        return run(b, api.send('POST', thr(t.thread_id) + '/cancel'), (r) => {
          ctx.toast(r.session_deleted
            ? 'Đã xoá buổi #' + t.session_id + ' khỏi tutor.db: nộp lại được cùng file, buổi sau của học sinh này được mở khoá.'
            : 'tutor.db không đổi.', { kind: 'ok', title: 'Đã huỷ ' + t.thread_id });
          if (life.drawer && life.drawer.id === t.thread_id && life.drawer.api) life.drawer.api.close();
          syncQueue();
          if (r.session_deleted) syncCounts();
          return load();
        });
      });
    }
    function cleanup(b, n) {
      const msg = 'Xoá ' + n + ' thread đã kết thúc (đã ghi tutor.db hoặc xong không ghi) khỏi checkpoints.db? tutor.db không đổi; chỉ mất state để xem lại ở đây. Không hoàn tác được.';
      return ctx.confirm(msg, { title: 'Dọn thread đã commit', ok: 'Dọn ' + n + ' thread' }).then((yes) => {
        if (!yes) return null;
        return run(b, api.send('POST', '/threads/cleanup'), (r) => {
          ctx.toast('Đã dọn ' + r.removed.length + ' thread khỏi checkpoints.db — tutor.db không đổi.', { kind: 'ok' });
          syncQueue();
          return load();
        });
      });
    }

    /* ---------- state drawer ---------- */
    function openThread(id) {
      const d = { id, el: null, t: null, api: null };
      d.api = ctx.drawer({ title: 'Thread ' + id, body: (el) => { d.el = el; el.append(h('p', { class: 'muted' }, 'Đang tải state…')); } });
      life.drawer = d;
      fetchState(d);
    }
    function fetchState(d) {
      const live = () => alive() && life.drawer === d && d.el && d.el.isConnected;
      api.get('/threads/' + encodeURIComponent(d.id) + '?include=state').then((t) => {
        if (!live()) return;
        d.t = t;
        d.el.replaceChildren(threadView(t));
      }, (e) => { if (live()) d.el.replaceChildren(failBox('Không tải được state của thread.', e, () => fetchState(d))); });
    }
    // A poll saw the open thread move on: reload its state.
    function refreshDrawer() {
      const d = life.drawer;
      if (!d || !d.el || !d.el.isConnected) { life.drawer = null; return; }
      const t = threads.find((x) => x.thread_id === d.id);
      if (t && d.t && (t.updated_at !== d.t.updated_at || t.checkpoints !== d.t.checkpoints)) fetchState(d);
    }
    function threadView(t) {
      const st = t.state || {}, keys = Object.keys(st);
      return h('div', { class: 'stack' },
        ui.kv([
          ['thread_id', h('span', { class: 'mono' }, t.thread_id)],
          ['Graph', ui.chip(t.graph, t.graph)],
          ['Đối tượng', t.subject || '—'],
          ['Trạng thái', h('span', { class: 'row ops-st' }, stChip(t.status), t.locked ? lockChip(t) : null)],
          ['Node cuối', h('span', { class: 'mono' }, t.node || '—')],
          ['Số checkpoint', F.int(t.checkpoints)],
          t.session_id != null ? ['Buổi', '#' + t.session_id] : null,
          ['Bắt đầu', F.dt(t.created_at)],
          ['Cập nhật', F.dt(t.updated_at)]
        ]),
        t.error ? h('div', { class: 'callout callout-crit', role: 'alert' },
          h('strong', null, 'Lỗi ở ' + (t.node || '—')), h('pre', { class: 'code' }, t.error),
          h('p', { class: 'small' }, 'Các node đã xong vẫn giữ trong checkpoints.db — chạy lại chỉ chạy node lỗi và các node sau.')) : null,
        t.locked ? h('div', { class: 'callout callout-warn' }, h('p', null, t.lock_reason)) : null,
        h('div', { class: 'row' },
          acts(t),
          t.graph === 'G1' ? ui.button('Mở trong Buổi học', () => ctx.nav('session', { thread: t.thread_id })) : null,
          ui.button('Xem lời gọi LLM', () => ctx.nav('logs', { thread: t.thread_id }), { kind: 'ghost' })),
        h('div', { class: 'spread' }, h('h3', null, 'State (' + keys.length + ' khoá)'), ui.store('checkpoint')),
        h('p', { class: 'small muted' }, 'Mọi khoá cấp trên của state trong checkpoints.db, đúng như graph lưu. Giá trị dài được thu gọn, bấm tên khoá để mở.'),
        keys.length ? keys.map((k) => stateKey(k, st[k])) : ui.empty('State trống.'));
    }
    function stateKey(k, v) {
      const text = typeof v === 'string' ? v : JSON.stringify(v, null, 2) || String(v);
      const n = text.split('\n').length;
      const kind = Array.isArray(v) ? 'danh sách · ' + v.length + ' mục'
        : v && typeof v === 'object' ? Object.keys(v).length + ' khoá'
          : typeof v === 'string' ? 'chuỗi · ' + v.length + ' ký tự' : v === null ? 'null' : typeof v;
      const head = [h('span', { class: 'mono ops-key' }, k), ' ', h('span', { class: 'small muted' }, kind)];
      const pre = h('pre', { class: 'code ops-val' }, text);
      if (n <= 12 && text.length <= 600) return h('div', { class: 'ops-kv' }, h('div', null, head), pre);
      return h('details', { class: 'ops-kv' }, h('summary', null, head, h('span', { class: 'small muted' }, ' · ' + n + ' dòng')), pre);
    }

    /* ---------- storage ---------- */
    function loadStorage() {
      return api.get('/backup').then((b) => {
        if (alive()) storeBox.replaceChildren(...storageView(b));
      }, (e) => { if (alive()) storeBox.replaceChildren(failBox('Không tải được thông tin lưu trữ.', e, loadStorage)); });
    }
    function storageView(b) {
      const names = Object.keys(b.rows || {}), backups = b.backups || [];
      return [
        ui.kv([
          ['Thư mục dữ liệu', h('span', { class: 'mono ops-path' }, b.data_dir)],
          ['tutor.db', h('span', null, h('b', { class: 'num' }, F.int(b.total)), ' dòng trong ' + names.length + ' bảng')],
          ['Bản sao lưu', backups.length ? backups.length + ' tệp trong data/backup/' : 'Chưa sao lưu lần nào']
        ]),
        h('div', { class: 'spread' }, h('h3', null, 'Số dòng theo bảng'), ui.store('db')),
        ui.table({
          columns: [
            { label: 'Bảng', render: (n) => h('span', { class: 'mono' }, n) },
            { label: 'Số dòng', align: 'right', render: (n) => F.int(b.rows[n]) }
          ],
          rows: names, empty: 'tutor.db chưa có bảng nào.'
        }),
        h('div', { class: 'spread' }, h('h3', null, 'Sao lưu'), ui.button('Sao lưu ngay', (e, btn) => backupNow(btn), { kind: 'primary' })),
        h('p', { class: 'small muted' }, 'App tự sao lưu trước mỗi lần ghi kết quả duyệt (commit ②); nút này sao lưu thủ công (sqlite3 .backup, chép an toàn khi app đang mở). Giữ 30 bản mới nhất và bản mới nhất của mỗi tháng.'),
        backups.length ? ui.table({
          columns: [
            { label: 'Tệp', render: (x) => h('span', { class: 'mono' }, x.name) },
            { label: 'Dung lượng', align: 'right', render: (x) => F.int(Math.ceil(x.bytes / 1024)) + ' KB' }
          ],
          rows: backups
        }) : ui.empty('Chưa sao lưu lần nào.')
      ];
    }
    function backupNow(b) {
      return run(b, api.send('POST', '/backup'), (r) => {
        ctx.toast(r.path + ' · ' + F.int(r.rows) + ' dòng — tutor.db không đổi.', { kind: 'ok', title: 'Đã sao lưu vào data/backup/' });
        syncCounts();
        return loadStorage();
      });
    }

    function jump(id) {
      const el = root.querySelector('[data-ops-section="' + id + '"]');
      if (!el) return;
      el.scrollIntoView({ block: 'start' });
      el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
    }
    Promise.all([load(), loadStorage()]).then(() => {
      if (!alive()) return;
      if (p.section) jump(p.section);
      if (p.thread && threads.some((t) => t.thread_id === p.thread)) openThread(p.thread);
    });
    return () => { life.dead = true; clearTimeout(life.timer); document.removeEventListener('visibilitychange', onVis); };
  }
})();
