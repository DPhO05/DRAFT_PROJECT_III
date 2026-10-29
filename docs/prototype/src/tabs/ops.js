/* Vận hành (NFR1, NFR5, NFR7, NFR9): thread G1–G5, checkpoint, chạy lại, lưu trữ, sao lưu, cài đặt, riêng tư. */
(function () {
  'use strict';
  var GIDS = ['G1', 'G2', 'G3', 'G4', 'G5'];
  var ST_VI = { running: 'đang chạy', awaiting_review: 'chờ duyệt', committed: 'đã ghi', failed: 'hỏng' };
  var GROUP_VI = { A: 'A · Danh mục & ngân hàng bài', B: 'B · Học sinh, buổi học, lỗi', C: 'C · Tiến bộ (05 tính, dựng lại được)', D: 'D · Gợi ý & báo cáo', view: 'View (chỉ đọc)' };
  // Kept across navigations: filters, unsaved settings draft, payload picker, open drawer.
  var S = { graph: '', status: 'open', draft: null, pAgent: '03', pCode: 'HS-03', dr: null };

  function pad2(n) { return String(n).padStart(2, '0'); }
  function dm(d) { var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(d || '')); return m ? m[2] + '/' + m[1] : ''; }

  App.registerTab('ops', { title: 'Vận hành', render: render });

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, L = ctx.lookup, M = ctx.data, db = M.db;
    var p = ctx.params, timers = [];
    if (GIDS.indexOf(p.graph) >= 0) S.graph = p.graph;
    if (p.status && (p.status === 'open' || p.status === 'all' || ST_VI[p.status])) S.status = p.status;
    S.dr = null;

    function threads() { return (M.checkpoints && M.checkpoints.threads) || []; }
    function nowISO() { var n = new Date(); return M.meta.today + 'T' + pad2(n.getHours()) + ':' + pad2(n.getMinutes()) + ':' + pad2(n.getSeconds()) + 'Z'; }
    function scode(id) { return L.studentCode(L.student(id)); }
    function sec(id, title, tags, right) {
      var kids = Array.prototype.slice.call(arguments, 4);
      return h('section', { class: 'section', 'data-ops-section': id },
        h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), tags ? ui.annot(tags) : null), right || null), kids);
    }
    function note(label, meaning) { return h('span', { class: 'annot-group' }, h('span', { class: 'annot', title: meaning, 'aria-label': label + ': ' + meaning }, label)); }
    function shortLabel(t) {
      var st = t.state || {};
      if (t.graph === 'G1') return scode(t.student_id) + ' ' + dm(ctx.queue.heldOn(t));
      if (t.graph === 'G4') return scode(t.student_id) + ' ' + dm(st.for_date);
      if (t.graph === 'G5') return scode(t.student_id) + ' ' + fmt.month(st.month);
      if (t.graph === 'G2') { var f = (M.files.bank || []).find(function (b) { return b.path === st.bank_file; }); return f ? f.kc_group : t.thread_id; }
      return st.kc_group || t.thread_id;
    }
    function lanesOf(t) {
      var cps = t.checkpoints || [], seqs = [];
      cps.forEach(function (c) { if (c.lane != null && seqs.indexOf(c.lane) < 0) seqs.push(c.lane); });
      seqs.sort(function (a, b) { return a - b; });
      var atts = (t.state || {}).attempts || [];
      var lanes = seqs.map(function (s) {
        var a = atts.find(function (x) { return x.seq === s; }), pr = a && L.problem(a.problem_id);
        return { seq: s, label: 'Bài ' + s + (pr ? ' · ' + pr.ref : ''), done: cps.filter(function (c) { return c.lane === s; }).map(function (c) { return c.node; }) };
      });
      if (t.status === 'failed') { var fl = lanes.filter(function (l) { return l.done.indexOf(t.current_node) < 0; }).pop(); if (fl) fl.failed = t.current_node; }
      return lanes;
    }
    function nodeText(t) {
      var lane = t.status === 'failed' ? (lanesOf(t).find(function (l) { return l.failed; }) || {}).seq : null;
      if (t.interrupted_at) return 'DỪNG · ' + ((M.meta.stage_labels || {})[t.interrupted_at] || ui.nodeName(t.interrupted_at));
      return ui.nodeName(t.current_node) + (lane ? ' · làn ' + lane : '');
    }
    function resume(t) { ctx.threads.resume(t.thread_id); }
    function openQueue(t) { ctx.queue.open(t.thread_id); }

    /* ---------- thread drawer ---------- */
    function openThread(id) {
      var api = ctx.drawer({ title: 'Thread ' + id, body: function (el) { S.dr = { id: id, el: el, api: null }; drawThread(true); } });
      if (S.dr) S.dr.api = api;
    }
    function snapshot(t) {
      var st = t.state || {};
      var trim = function (v, d) {
        if (typeof v === 'string') return v.length > 90 ? v.slice(0, 87) + '…' : v;
        if (Array.isArray(v)) { var a = v.slice(0, 4).map(function (x) { return trim(x, d + 1); }); if (v.length > 4) a.push('… +' + (v.length - 4) + ' mục'); return a; }
        if (v && typeof v === 'object') { if (d > 3) return '{…}'; var o = {}; Object.keys(v).forEach(function (k) { o[k] = trim(v[k], d + 1); }); return o; }
        return v;
      };
      if (t.graph !== 'G1') return trim(st, 0);
      var atts = st.attempts || [], props = st.proposals || [];
      var ref = function (a) { var pr = L.problem(a.problem_id); return pr ? pr.ref : null; };
      return trim({
        source: st.source,
        attempts: atts.map(function (a) { return { seq: a.seq, problem: ref(a), score: a.score, max_score: a.max_score }; }),
        flags: [].concat.apply([], atts.map(function (a) { return (a.flags_json || []).map(function (f) { return { seq: a.seq, type: f.type, resolved: f.resolved }; }); })),
        grades: atts.map(function (a) { return { seq: a.seq, items: (a.grade_json || []).map(function (g) { return g.item_id + (g.passed ? '✓' : '✗'); }).join(' ') }; }),
        mistakes: props.map(function (x) { return { pid: x.pid, seq: x.attempt_seq, step: x.step_idx, code: x.code, confidence: x.confidence }; }),
        verdicts: props.map(function (x) { return { pid: x.pid, verdict: x.verifier ? x.verifier.verdict : null }; }),
        decisions: st.decisions || {},
        profile: st.profile == null ? null : st.profile
      }, 0);
    }
    function drawThread(first) {
      var d = S.dr;
      if (!d || !d.el || (!first && !d.el.isConnected)) { S.dr = null; return; }
      var t = L.thread(d.id);
      if (!t) { if (d.api) d.api.close(); S.dr = null; return; }
      var cps = t.checkpoints || [], lanes = lanesOf(t), g = M.meta.graphs[t.graph] || { nodes: [] };
      var strip = ui.graphStrip(t.graph, {
        done: t.status === 'committed' ? g.nodes.map(function (n) { return n.id; }) : cps.filter(function (c) { return c.lane == null; }).map(function (c) { return c.node; }),
        current: t.status === 'committed' || t.status === 'failed' ? null : (t.interrupted_at || t.current_node),
        failed: t.status === 'failed' && !lanes.length ? t.current_node : null,
        lanes: lanes.length ? lanes : null
      });
      var s = t.graph === 'G1' ? L.sessionByThread(t.thread_id) : null;
      d.el.replaceChildren(h('div', { class: 'stack' },
        ui.kv([
          ['thread_id', h('span', { class: 'mono' }, t.thread_id)],
          ['Graph', h('span', null, ui.chip(t.graph, t.graph), ' ', g.name || '', ' · ', g.title_vi || '')],
          ['Đối tượng', t.subject],
          ['Bắt đầu', fmt.dt(t.started_at)],
          ['Node hiện tại', nodeText(t)],
          ['Trạng thái', h('span', null, ui.status(t.status), t.locked ? [' ', ui.status('locked')] : null)],
          ['Số checkpoint', String(cps.length)]
        ]),
        t.error ? h('div', { class: 'callout callout-crit' }, h('p', null, h('b', null, 'Lỗi: '), h('span', { class: 'mono' }, t.error)),
          h('p', { class: 'small' }, 'Các node đã xong được giữ trong checkpoint — chạy lại chỉ chạy node lỗi và các node sau.')) : null,
        t.locked ? h('div', { class: 'callout callout-warn' }, h('p', null, t.lock_reason)) : null,
        s && t.status !== 'committed' ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Huỷ thread chỉ xoá đề xuất trong checkpoints.db. Buổi #' + s.id + ' do bước ① ghi vẫn còn trong tutor.db (chuyển sang failed), nên luật chặn file trùng sẽ không cho nộp lại file này. ',
          ui.chip('Chưa chốt', 'warn'), ' khi huỷ thì xoá buổi #' + s.id + ', hay cho nộp lại file của buổi failed?')) : null,
        h('div', { class: 'row' },
          t.status === 'awaiting_review' ? ui.button('Mở trong Hộp duyệt', function () { openQueue(t); }, { kind: 'primary', cli: 'tutor review ' + t.thread_id, disabledReason: t.locked ? t.lock_reason : null }) : null,
          t.status === 'failed' ? ui.button('Chạy lại từ checkpoint cuối', function () { resume(t); }, { kind: 'primary' }) : null,
          t.graph === 'G1' && t.status !== 'awaiting_review' ? ui.button('Mở trong Buổi học', function () { ctx.nav('session', t.status === 'committed' && s ? { session: s.id } : { thread: t.thread_id }); }) : null,
          ui.button('Xem lời gọi LLM', function () { ctx.nav('logs', { thread: t.thread_id }); }, { kind: 'ghost' }),
          t.status !== 'committed' ? ui.button('Huỷ thread', function () { ctx.threads.cancel(t.thread_id); }, { kind: 'danger', noAutoclick: true }) : null),
        h('h3', null, 'Đường đi trong graph'), strip,
        h('h3', null, 'Checkpoint (', cps.length, ')'),
        ui.table({
          columns: [
            { label: '#', align: 'right', render: function (c) { return cps.indexOf(c) + 1; } },
            { label: 'Node', render: function (c) { return ui.nodeName(c.node); } },
            { label: 'Làn', align: 'right', render: function (c) { return c.lane == null ? '—' : c.lane; } },
            { label: 'Lúc', render: function (c) { return h('span', { class: 'nowrap' }, fmt.dt(c.at)); } },
            { label: 'Thời gian', align: 'right', render: function (c) { return c.ms ? fmt.ms(c.ms) : '—'; } },
            { label: 'Token', align: 'right', render: function (c) { var n = (c.tokens_in || 0) + (c.tokens_out || 0); return n ? fmt.int(n) : '—'; } }
          ], rows: cps, empty: 'Chưa có checkpoint nào.'
        }),
        h('div', { class: 'spread' }, h('h3', null, 'State trong checkpoints.db'), ui.store('checkpoint')),
        h('p', { class: 'small muted' }, t.graph === 'G1' ? 'SessionState (tài liệu thiết kế §3.4): attempts, flags, grades, mistakes, verdicts, decisions, profile — chuỗi dài đã rút gọn.' : 'State của graph — chuỗi dài và danh sách dài đã rút gọn.'),
        h('pre', { class: 'code' }, JSON.stringify(snapshot(t), null, 2)),
        ui.annot(['file:checkpoints.db', 'checkpoint', 'interrupt'])));
    }

    /* ---------- sections ---------- */
    function failedBox() {
      var bad = threads().filter(function (t) { return t.status === 'failed'; }), run = threads().filter(function (t) { return t.status === 'running'; });
      return sec('failed', 'Thread lỗi', ['file:checkpoints.db'], null,
        bad.length ? bad.map(function (t) {
          return h('div', { class: 'callout callout-crit' },
            h('p', null, h('b', null, t.subject), ' · ', h('span', { class: 'mono small' }, t.thread_id), ' — dừng ở ', h('b', null, nodeText(t))),
            h('p', { class: 'mono small' }, t.error),
            h('div', { class: 'row' }, ui.button('Chạy lại từ checkpoint cuối', function () { resume(t); }, { kind: 'primary' }), ui.button('Xem state', function () { openThread(t.thread_id); })));
        }) : h('p', { class: 'muted' }, 'Không có thread lỗi.'),
        run.map(function (t) { return h('p', { class: 'small' }, ui.status('running'), ' ', t.subject, ' — đang ở ', h('b', null, nodeText(t)), ' (', h('span', { class: 'mono' }, t.thread_id), ')'); }),
        h('p', { class: 'small muted' }, 'NFR9: mỗi node xong là một checkpoint trong checkpoints.db; lỗi API giữa chừng không làm mất các bài đã chấm.'));
    }

    function lanesSec() {
      var all = threads();
      var strips = GIDS.map(function (gid) {
        var ths = all.filter(function (t) { return t.graph === gid; }), open = ths.filter(function (t) { return t.status !== 'committed'; });
        var f = open.find(function (t) { return t.status === 'failed'; }), r = open.find(function (t) { return t.status === 'running'; });
        var strip = ui.graphStrip(gid, { compact: true, failed: f ? f.current_node : null, current: r ? r.current_node : null });
        open.forEach(function (t) {
          var node = t.interrupted_at || t.current_node, el = strip.querySelector('[data-node="' + node + '"]');
          if (!el) return;
          var box = el.querySelector('.ops-dots') || el.appendChild(h('span', { class: 'ops-dots' }));
          var b = ui.button(shortLabel(t), function () { openThread(t.thread_id); }, { title: t.thread_id + ' · ' + (t.locked ? 'khoá' : ST_VI[t.status]) });
          b.className = 'ops-dot is-' + (t.locked ? 'locked' : t.status);
          b.dataset.thread = t.thread_id;
          // paint() rebuilds the whole tab on any thread change; keep an unchanged dot so a click landing mid-repaint still hits it.
          var old = content.querySelector('button.ops-dot[data-thread="' + t.thread_id + '"]');
          box.append(old && old.className === b.className && old.title === b.title && old.textContent === b.textContent ? old : b);
        });
        var nc = ths.length - open.length, g = M.meta.graphs[gid], last = g && g.nodes[g.nodes.length - 1];
        var cel = last && strip.querySelector('[data-node="' + last.id + '"]');
        if (cel && nc) cel.appendChild(h('span', { class: 'ops-dots' }, h('span', { class: 'ops-dot is-committed', title: nc + ' thread đã commit (còn trong checkpoints.db tới khi dọn)' }, nc + ' đã ghi')));
        return strip;
      });
      var key = function (cls, text) { return h('span', { class: 'row', style: 'gap:4px' }, h('span', { class: 'ops-dot ' + cls }, 'HS'), text); };
      return sec('lanes', '5 làn graph', GIDS.concat(['file:checkpoints.db']), null,
        h('p', { class: 'small muted' }, 'Mỗi nhãn là một thread đang nằm ở node đó. Bấm nhãn để xem checkpoint và state. Làn dài thì kéo ngang để xem hết.'),
        h('div', { class: 'stack', style: 'gap:8px' }, strips),
        h('div', { class: 'row small muted' }, key('is-running', 'đang chạy'), key('is-awaiting_review', 'chờ thầy/cô duyệt'), key('is-locked', 'khoá (chờ buổi trước)'), key('is-failed', 'hỏng'), key('is-committed', 'đã ghi')));
    }

    function threadSec() {
      var all = threads(), cnt = function (f) { return all.filter(f).length; };
      var rows = all.filter(function (t) {
        return (!S.graph || t.graph === S.graph) && (S.status === 'all' || (S.status === 'open' ? t.status !== 'committed' : t.status === S.status));
      }).sort(function (a, b) { return String(b.started_at).localeCompare(String(a.started_at)); });
      var gSel = h('select', { 'aria-label': 'Lọc graph', onchange: function (e) { S.graph = e.target.value; paint(); } },
        [h('option', { value: '' }, 'Tất cả graph (' + all.length + ')')].concat(GIDS.map(function (g) { return h('option', { value: g, selected: S.graph === g }, g + ' · ' + M.meta.graphs[g].title_vi + ' (' + cnt(function (t) { return t.graph === g; }) + ')'); })));
      var sOpts = [['open', 'Chưa ghi', function (t) { return t.status !== 'committed'; }], ['running', 'Đang chạy'], ['awaiting_review', 'Chờ duyệt'], ['failed', 'Hỏng'], ['committed', 'Đã ghi'], ['all', 'Tất cả', function () { return true; }]];
      var sSel = h('select', { 'aria-label': 'Lọc trạng thái', onchange: function (e) { S.status = e.target.value; paint(); } }, sOpts.map(function (o) {
        return h('option', { value: o[0], selected: S.status === o[0] }, o[1] + ' (' + cnt(o[2] || function (t) { return t.status === o[0]; }) + ')');
      }));
      var nCommitted = cnt(function (t) { return t.status === 'committed'; });
      var clean = ui.button('Dọn thread đã commit', function () {
        var n = threads().filter(function (t) { return t.status === 'committed'; }).length;
        if (!n) return;
        ctx.confirm('Xoá ' + n + ' thread đã commit khỏi checkpoints.db? Dữ liệu của chúng đã nằm trong tutor.db — không mất gì.', { title: 'Dọn thread đã commit', ok: 'Dọn ' + n + ' thread' }).then(function (yes) {
          if (!yes) return;
          var list = M.checkpoints.threads;
          for (var i = list.length - 1; i >= 0; i--) if (list[i].status === 'committed') list.splice(i, 1);
          ctx.toast('Đã dọn ' + n + ' thread đã commit khỏi checkpoints.db — tutor.db không đổi.', { kind: 'ok' });
          ctx.refresh();
        });
      }, { disabledReason: nCommitted ? null : 'không còn thread đã commit' });
      var table = ui.table({
        columns: [
          { label: 'thread_id', render: function (t) { return h('span', { class: 'mono small nowrap' }, t.thread_id); } },
          { label: 'Graph', render: function (t) { return ui.chip(t.graph, t.graph); } },
          { label: 'Đối tượng', render: function (t) { return t.subject; } },
          { label: 'Bắt đầu', render: function (t) { return h('span', { class: 'nowrap' }, fmt.dt(t.started_at)); } },
          { label: 'Node hiện tại', render: function (t) { return nodeText(t); } },
          { label: 'Trạng thái', render: function (t) { return h('span', { class: 'row', style: 'gap:4px' }, ui.status(t.status), t.locked ? ui.status('locked') : null); } },
          { label: 'Checkpoint', align: 'right', render: function (t) { return (t.checkpoints || []).length; } },
          { label: '', render: function (t) {
            return h('div', { class: 'row ops-acts' },
              ui.button('Xem state', function () { openThread(t.thread_id); }, { size: 'sm' }),
              t.status === 'awaiting_review' ? ui.button('Mở trong Hộp duyệt', function () { openQueue(t); }, { size: 'sm', disabledReason: t.locked ? 'khoá — duyệt buổi trước' : null }) : null,
              t.status === 'failed' ? ui.button('Chạy lại từ checkpoint cuối', function () { resume(t); }, { size: 'sm', kind: 'primary' }) : null,
              t.status !== 'committed' ? ui.button('Huỷ thread', function () { ctx.threads.cancel(t.thread_id); }, { size: 'sm', kind: 'danger', noAutoclick: true }) : null);
          } }
        ],
        rows: rows, empty: 'Không có thread nào khớp bộ lọc.',
        rowClass: function (t) { return t.locked ? 'is-dim' : null; },
        onRow: function (t) { openThread(t.thread_id); }
      });
      table.classList.add('ops-thr-tbl');
      return sec('threads', 'Thread', ['file:checkpoints.db', 'thread', 'cli:tutor review'], clean,
        h('div', { class: 'row' }, gSel, sSel, h('span', { class: 'small muted' }, rows.length + ' thread · ' + nCommitted + ' đã commit vẫn còn trong checkpoints.db (tài liệu thiết kế §8.7: xoá thread cũ sau khi commit)')),
        table);
    }

    function rulesSec() {
      var locked = ctx.queue.list().filter(function (t) { return t.locked; });
      var stuck = db.session.filter(function (s) { return s.status === 'failed'; });
      var dup = (M.files.inbox || []).filter(function (f) { return db.session.some(function (s) { return s.student_id === f.student_id && s.source_sha256 === f.sha256; }); });
      var g2wait = (M.files.bank || []).filter(function (b) { return b.status === 'cho_duyet_tag'; });
      var card = function (title, text, live, tags) { return h('div', { class: 'card' }, h('h3', null, title, ' ', ui.annot(tags)), h('p', null, text), h('div', { class: 'small' }, live)); };
      return sec('rules', 'Quy tắc vận hành', null, null, h('div', { class: 'grid ops-rules' },
        card('Duyệt theo thứ tự ngày cho từng HS', 'Elo cập nhật tuần tự: buổi sau của một học sinh chỉ mở khi buổi trước đã ghi vào tutor.db.',
          locked.length ? locked.map(function (t) { return h('p', null, ui.status('locked'), ' ', t.subject, ' — ', t.lock_reason); }) : h('p', { class: 'muted' }, 'Hiện không có buổi nào bị khoá.'), ['G1', 'table:skill_event']),
        card('Chặn file trùng', 'UNIQUE(student_id, source_sha256): cùng học sinh nộp lại đúng file đã nộp → báo trùng, không chạy G1.',
          [h('p', null, dup.length + '/' + (M.files.inbox || []).length + ' file trong data/inbox/ trùng sha256 với buổi đã có: ', h('span', { class: 'mono' }, dup.map(function (f) { return f.path.split('/').pop(); }).join(', ') || '—')),
          h('p', null, ui.chip('Chưa chốt', 'warn'), ' Buổi failed (lỗi, hoặc thread đã huỷ) vẫn giữ dòng session do ① ghi → nếu không chạy lại được thì file đó cũng không nộp lại được. Buổi failed hiện có: ',
            h('span', { class: 'mono' }, stuck.map(function (s) { return '#' + s.id + ' ' + L.studentCode(L.student(s.student_id)); }).join(', ') || '—'))], ['table:session', 'file:data/inbox/']),
        card('G3 chạy sau G2', 'Xếp độ khó (G3) chỉ chạy cho bài đã có tag KC được duyệt (G2) — so cặp trong cùng KC.',
          g2wait.length ? g2wait.map(function (b) { return h('p', null, h('span', { class: 'mono' }, b.file), ': chờ duyệt tag → chưa xếp độ khó được'); }) : h('p', { class: 'muted' }, 'Mọi file ngân hàng đã qua G2.'), ['G2', 'G3']),
        card('Chỉ commit node ghi tutor.db', 'Mọi đề xuất trước đó nằm trong checkpoints.db; mỗi lần duyệt = 1 transaction (NFR5).',
          GIDS.map(function (gid) { var g = M.meta.graphs[gid]; return h('p', null, ui.chip(gid, gid), ' ', h('span', { class: 'mono' }, gid.toLowerCase() + '.commit'), ' → ', (g.commit_tables || []).join(', ')); }), ['commit node', 'file:tutor.db'])));
    }

    function storageSec() {
      var tables = M.meta.tables || [], th = threads(), F = M.files;
      var supA = new Set(db.attempt.filter(function (a) { return a.supersedes_id != null; }).map(function (a) { return a.supersedes_id; }));
      var count = function (name) {
        if (name === 'attempt_current') return db.attempt.filter(function (a) { return !supA.has(a.id); }).length;
        if (name === 'mistake_current') return ctx.calc.currentMistakes(db).length;
        return (db[name] || []).length;
      };
      var real = tables.filter(function (t) { return t.group !== 'view'; }), views = tables.filter(function (t) { return t.group === 'view'; });
      var total = real.reduce(function (s, t) { return s + count(t.name); }, 0);
      var file = function (path, title, value, sub, tags) { return h('div', { class: 'card st-file' }, h('span', { class: 'mono ops-path' }, path), h('b', null, value), h('span', { class: 'small muted' }, title), sub ? h('span', { class: 'small' }, sub) : null, ui.annot(tags)); };
      var byStatus = Object.keys(ST_VI).map(function (s) { var n = th.filter(function (t) { return t.status === s; }).length; return n ? n + ' ' + ST_VI[s] : null; }).filter(Boolean).join(' · ');
      var md = (F.out || []).length, bank = (F.bank || []).length;
      return sec('storage', 'Lưu trữ', ['file:tutor.db', 'file:checkpoints.db', 'file:llm.jsonl'], h('span', { class: 'chip' }, '1 máy · 1 người dùng · không đăng nhập'),
        h('div', { class: 'card st-file' },
          h('div', { class: 'spread' }, h('span', { class: 'mono ops-path' }, 'data/tutor.db'), ui.store('db')),
          h('p', null, h('b', null, real.length + ' bảng + ' + views.length + ' view'), ' · ', h('b', { class: 'num' }, fmt.int(total)), ' dòng đã duyệt — chỉ commit node ghi vào đây.'),
          ui.table({
            columns: [
              { label: 'Bảng', render: function (t) { return h('span', { class: 'mono' }, t.name); } },
              { label: 'Nhóm', render: function (t) { return h('span', { class: 'ops-grp' }, GROUP_VI[t.group] || t.group); } },
              { label: 'Số dòng', align: 'right', render: function (t) { return fmt.int(count(t.name)); } },
              { label: 'Ai ghi', render: function (t) { return t.writer; } },
              { label: 'Ghi chú', render: function (t) { return h('span', { class: 'small muted' }, t.note); } }
            ], rows: tables, rowClass: function (t) { return t.group === 'view' ? 'is-dim' : null; }
          })),
        h('div', { class: 'grid cols-3' },
          file('data/checkpoints.db', 'Thread LangGraph + đề xuất chờ duyệt (chưa phải dữ liệu chính thức)', th.length + ' thread', byStatus, ['file:checkpoints.db']),
          file('data/inbox/', 'Bài làm HS chờ nộp + file ngân hàng (data/inbox/bank/)', (F.inbox || []).length + ' bài làm · ' + bank + ' file .tex', null, ['file:data/inbox/']),
          file('data/out/', 'File .md đã xuất (gợi ý bài, báo cáo tháng)', md + ' file .md', null, ['file:data/out/']),
          file('data/logs/llm.jsonl', 'Mỗi lời gọi LLM một dòng: agent, prompt_version, token, chi phí', fmt.int((F.llm_log || []).length) + ' lời gọi', null, ['file:llm.jsonl']),
          file('data/backup/', 'Bản sao tutor.db (sqlite3 .backup)', (F.backups || []).length + ' bản', null, ['file:data/backup/'])));
    }

    function backupSec() {
      var b = M.files.backups || [];
      var now = ui.button('Sao lưu ngay', function () {
        var list = M.files.backups || (M.files.backups = []);
        var path = (M.settings.backup_dir || 'data/backup/') + 'tutor-' + M.meta.today + '.db';
        var i = list.findIndex(function (x) { return x.path === path; });
        var size = (list[0] || {}).size_kb; // tutor.db ≈ newest backup size in the mock
        if (i >= 0) list.splice(i, 1);
        list.unshift({ path: path, at: nowISO(), size_kb: size == null ? null : size });
        ctx.toast((i >= 0 ? 'Ghi đè ' : 'Đã sao lưu ') + path + ' (sqlite3 .backup) — tutor.db không đổi.', { kind: 'ok' });
        ctx.refresh();
      }, { kind: 'primary' });
      return sec('backup', 'Sao lưu', ['file:data/backup/', 'file:tutor.db'], now,
        h('p', { class: 'small muted' }, 'Tự sao lưu trước mỗi lần ghi G1 (tài liệu thiết kế §8.7); nút này sao lưu thủ công. Dùng sqlite3 .backup nên chép an toàn cả khi app đang mở.'),
        b.length ? ui.table({
          columns: [
            { label: 'Tệp', render: function (x) { return h('span', { class: 'mono' }, x.path); } },
            { label: 'Lúc', render: function (x) { return h('span', { class: 'nowrap' }, fmt.dt(x.at)); } },
            { label: 'Dung lượng', align: 'right', render: function (x) { return x.size_kb == null ? '—' : fmt.int(x.size_kb) + ' KB'; } },
            { label: '', render: function (x) { return fmt.ago(x.at); } }
          ], rows: b
        }) : ui.empty('Chưa sao lưu lần nào.'));
    }

    function settingsSec() {
      var s = M.settings;
      if (!S.draft) {
        var r = s.reco;
        S.draft = { review: Math.round(r.ratios.review * 100), zpd: Math.round(r.ratios.zpd * 100), challenge: Math.round(r.ratios.challenge * 100), n: r.n_problems,
          lowconf: s.review.low_confidence, budget: s.budget_usd_month, models: Object.assign({}, s.models) };
      }
      var D = S.draft, R = s.reco, preview = h('p', { class: 'ops-preview' }), errs = h('div', { class: 'ops-err', role: 'alert' });
      var check = function () {
        var e = [], sum = D.review + D.zpd + D.challenge;
        if (sum !== 100) e.push('Tổng tỉ lệ phải bằng 100% (đang ' + sum + '%).');
        if (!(D.n >= 1)) e.push('Số bài mỗi buổi phải ≥ 1.');
        if (!(D.n >= R.min_kc_mix)) e.push('Số bài mỗi buổi phải ≥ ' + R.min_kc_mix + ' để trộn đủ ' + R.min_kc_mix + ' KC (spec §9).');
        if (!(D.lowconf > 0 && D.lowconf < 1)) e.push('Ngưỡng độ tin cậy phải trong (0, 1).');
        if (!(D.budget >= 0)) e.push('Ngân sách phải ≥ 0.');
        return e;
      };
      var split = function () { var c = ctx.calc.largestRemainder(D.n, [D.review / 100, D.zpd / 100, D.challenge / 100]); return D.n + ' bài = ' + c[0] + ' ôn / ' + c[1] + ' vừa sức / ' + c[2] + ' thử thách'; };
      var upd = function () {
        var e = check();
        preview.replaceChildren(e.length && D.review + D.zpd + D.challenge !== 100 ? h('span', { class: 'muted' }, '—') : h('b', null, split()), ' ', ui.prov('code'));
        errs.replaceChildren.apply(errs, e.map(function (x) { return h('p', null, x); }));
      };
      var num = function (label, key, o) {
        o = o || {};
        var inp = h('input', { type: 'number', value: D[key], step: o.step || 1, min: o.min, max: o.max, 'aria-label': label });
        inp.addEventListener('input', function () { D[key] = inp.value === '' ? NaN : +inp.value; upd(); });
        return h('label', { class: 'field' }, h('span', null, label), inp, o.hint ? h('span', { class: 'small muted' }, o.hint) : null);
      };
      var fixed = function (label, value) { return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label), h('span', { class: 'kpi-value' }, value), h('span', { class: 'kpi-sub' }, 'cố định theo spec §9 · chỉ đọc')); };
      var splitWhy = ui.why(function () {
        var raw = [D.review, D.zpd, D.challenge].map(function (x) { return D.n * x / 100; }), c = ctx.calc.largestRemainder(D.n, [D.review / 100, D.zpd / 100, D.challenge / 100]);
        var names = ['ôn', 'vừa sức', 'thử thách'];
        return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'select.py chia ' + D.n + ' bài theo tỉ lệ, làm tròn theo phần dư lớn nhất (giả định của bản nháp):'),
          raw.map(function (x, i) { return h('p', { class: 'mono' }, D.n + ' × ' + ([D.review, D.zpd, D.challenge][i] / 100) + ' = ' + (+x.toFixed(2)) + ' → ' + c[i] + ' ' + names[i]); }),
          h('p', { class: 'small muted' }, 'Phần nguyên trước, số bài còn thiếu cho nhóm có phần lẻ lớn nhất.'));
      });
      var models = Array.from(new Set(Object.values(s.models).concat((M.files.llm_log || []).map(function (c) { return c.model; })).filter(Boolean)));
      var mTable = ui.table({
        columns: [
          { label: 'Agent', render: function (a) { return ui.chip(a.id + ' ' + a.name, 'agent' + a.id); } },
          { label: 'Việc', render: function (a) { return h('span', { class: 'small' }, a.role_vi); } },
          { label: 'Model', render: function (a) {
            return h('select', { 'aria-label': 'Model cho agent ' + a.id, onchange: function (e) { D.models[a.id] = e.target.value; } },
              models.map(function (m) { return h('option', { value: m, selected: D.models[a.id] === m }, m); }));
          } }
        ], rows: M.meta.agents || []
      });
      var save = ui.button('Lưu cài đặt', function () {
        var e = check();
        upd();
        if (e.length) { ctx.toast('Chưa lưu: ' + e[0], { kind: 'error' }); return; }
        s.reco.ratios = { review: D.review / 100, zpd: D.zpd / 100, challenge: D.challenge / 100 };
        s.reco.n_problems = D.n;
        s.review.low_confidence = D.lowconf; s.budget_usd_month = D.budget; Object.assign(s.models, D.models);
        ctx.toast('Đã lưu cài đặt — Gợi ý bài: ' + split() + ' · ngân sách ' + fmt.usd(D.budget) + '/tháng.', { kind: 'ok' });
        ctx.refresh();
      }, { kind: 'primary' });
      upd();
      return sec('settings', 'Cài đặt', null, null,
        h('div', { class: 'row' }, note('select.py', 'Code chọn bài gợi ý (G4) đọc tỉ lệ, số bài, lọc 30 ngày, trộn KC'), note('elo.py', 'Code tính Elo: K và θ ban đầu, cố định theo spec'), note('llm.py', 'Cổng gọi API: model cho từng agent, ngân sách')),
        h('h3', null, 'Gợi ý bài (select.py)'),
        h('div', { class: 'grid cols-4' },
          num('Ôn lại (%)', 'review', { min: 0, max: 100 }), num('Vừa sức (%)', 'zpd', { min: 0, max: 100 }), num('Thử thách (%)', 'challenge', { min: 0, max: 100 }),
          num('Số bài mỗi buổi', 'n', { min: R.min_kc_mix, max: 20 }),
          fixed('Không lặp lại trong', R.no_repeat_days + ' ngày'), fixed('Trộn ít nhất', R.min_kc_mix + ' KC'),
          fixed('Vùng vừa sức (θ − δ)', '[' + R.zpd_window.map(function (v) { return (v < 0 ? '−' : '') + fmt.num(Math.abs(v), 1); }).join(', ') + ']')),
        h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Xem trước:'), preview, splitWhy),
        h('h3', null, 'Chấm & duyệt'),
        h('div', { class: 'grid cols-4' },
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'K của Elo'), h('span', { class: 'kpi-value' }, String(s.elo.K)), h('span', { class: 'kpi-sub' }, 'cố định theo spec §8 · chỉ đọc')),
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Ngưỡng “lỗi đã hết”'), h('span', { class: 'kpi-value' }, s.misconception.resolve_streak + ' lần'), h('span', { class: 'kpi-sub' }, 'đúng liên tiếp · cố định theo spec §8 · chỉ đọc')),
          num('Ngưỡng độ tin cậy thấp', 'lowconf', { step: 0.05, min: 0, max: 1, hint: 'đề xuất dưới ngưỡng lên đầu hàng duyệt · giả định của bản nháp, spec chưa đặt' }),
          num('Ngân sách tháng (USD)', 'budget', { step: 1, min: 0, hint: 'chưa chốt (tài liệu thiết kế §11.1) · thanh chi phí trên cùng đọc số này' })),
        h('h3', null, 'Model cho từng agent (llm.py)'),
        h('p', { class: 'small muted' }, 'Danh sách model chưa chốt (tài liệu thiết kế §11.2 #3) — bản nháp chỉ liệt kê model đang dùng trong nhật ký.'),
        mTable, errs, save);
    }

    function privacySec() {
      var pv = M.settings.privacy || (M.settings.privacy = { send_code_only: true }), on = !!pv.send_code_only;
      var samples = M.ui.api_payload_samples || {}, agents = (M.meta.agents || []).filter(function (a) { return samples[a.id]; });
      if (!samples[S.pAgent] && agents[0]) S.pAgent = agents[0].id;
      var sw = h('button', { type: 'button', class: 'switch', 'aria-pressed': String(on) }, 'Chỉ gửi mã HS lên API');
      sw.addEventListener('click', function () {
        pv.send_code_only = !on;
        ctx.toast(pv.send_code_only ? 'Bật lại: prompt chỉ chứa mã HS (NFR7).' : 'Đã tắt (thử): prompt có thể chứa tên học sinh — trái NFR7. Bản nháp vẫn chỉ gửi mã.', { kind: pv.send_code_only ? 'ok' : 'warn' });
        paint();
      });
      var aSel = h('select', { 'aria-label': 'Agent', onchange: function (e) { S.pAgent = e.target.value; } }, agents.map(function (a) { return h('option', { value: a.id, selected: a.id === S.pAgent }, a.id + ' ' + a.name); }));
      var sSel = h('select', { 'aria-label': 'Học sinh', onchange: function (e) { S.pCode = e.target.value; } }, db.student.map(function (st) { var c = L.studentCode(st); return h('option', { value: c, selected: c === S.pCode }, c); }));
      var untrusted = String((samples['03'] || {}).untrusted || '<UNTRUSTED INPUT student="{code}">…</UNTRUSTED INPUT>').split('{code}').join('HS-03');
      return sec('privacy', 'Riêng tư & an toàn', ['UNTRUSTED INPUT', 'file:llm.jsonl'], null,
        h('div', { class: 'row' }, sw, ui.chip('NFR7 · ' + (pv.status || 'đề xuất, chờ chốt'), 'warn')),
        on ? null : h('div', { class: 'callout callout-crit' }, h('p', null, 'Đang tắt: prompt có thể chứa tên học sinh — trái NFR7. (Bản nháp vẫn chỉ gửi mã.)')),
        h('div', { class: 'grid cols-2' },
          h('div', { class: 'stack', style: 'gap:6px' }, h('h3', null, 'Tên ↔ mã học sinh'), h('p', { class: 'small muted' }, 'Bảng này chỉ trên máy này; API chỉ thấy cột mã.'),
            ui.table({
              columns: [
                { label: 'Mã gửi API', render: function (st) { return h('b', { class: 'mono' }, L.studentCode(st)); } },
                { label: 'Tên (chỉ trên máy này)', render: function (st) { return st.name; } },
                { label: 'Lớp', align: 'right', render: function (st) { return st.grade; } }
              ], rows: db.student
            })),
          h('div', { class: 'stack', style: 'gap:6px' }, h('h3', null, 'Khung UNTRUSTED INPUT (NFR6)'),
            h('p', { class: 'small muted' }, 'Bài làm học sinh luôn được bọc trong khung này; agent được dặn coi mọi chữ bên trong là dữ liệu, không làm theo lệnh nào trong đó.'),
            h('pre', { class: 'code untrusted' }, untrusted),
            h('div', { class: 'row' }, aSel, sSel, ui.button('Xem nội dung gửi API', function () { ui.payloadModal(S.pAgent, S.pCode); }), ui.privacy(S.pCode)))));
    }

    /* ---------- paint ---------- */
    var content = h('div', { class: 'stack' }), lastSig = null;
    function sig() {
      var b = M.files.backups || [];
      return JSON.stringify([threads().map(function (t) { return [t.thread_id, t.status, t.current_node, t.interrupted_at]; }), b.length, (b[0] || {}).at]);
    }
    function paint() {
      ctx.queue.list(); // refresh locked flags
      lastSig = sig();
      content.replaceChildren(failedBox(), lanesSec(), threadSec(), rulesSec(), storageSec(), backupSec(), settingsSec(), privacySec());
      if (S.dr) drawThread();
    }
    function jump(id) {
      var el = content.querySelector('[data-ops-section="' + id + '"]');
      if (!el) return;
      el.scrollIntoView({ block: 'start' });
      el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
    }
    root.append(ui.pageHead({
      lead: 'Phần máy đang chạy: mọi thread của G1–G5 dừng ở đâu, checkpoint, chạy lại từ chỗ hỏng, lưu trữ, sao lưu, cài đặt, riêng tư.',
      annot: ['file:checkpoints.db', 'file:tutor.db', 'checkpoint']
    }), content);
    paint();
    // Repaint on shell refresh only when threads or backups changed (keeps focus/scroll otherwise).
    ctx.queue.on(function () { if (sig() !== lastSig) paint(); });
    if (p.section) timers.push(setTimeout(function () { jump(p.section === 'budget' ? 'settings' : p.section); }, 60));
    if (p.thread && L.thread(p.thread)) timers.push(setTimeout(function () { openThread(p.thread); }, 60));
    return function () { timers.forEach(clearTimeout); S.dr = null; };
  }
})();
