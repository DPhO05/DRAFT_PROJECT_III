/* tabs/today.js — Hôm nay (IA §3.1): what needs the teacher now, warnings, the 4-moment routine. */
(function () {
  'use strict';
  var GLABEL = { G1: 'Lỗi buổi học', G2: 'Tag KC + rubric', G3: 'Độ khó', G4: 'Gợi ý', G5: 'Báo cáo' };
  var WEEKDAY = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  var arr = function (x) { return Array.isArray(x) ? x : []; };
  var dm = function (d) { var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(d || '')); return m ? m[2] + '/' + m[1] : String(d || ''); };

  function stopAt(t) {
    var cps = arr(t.checkpoints);
    var hit = t.interrupted_at ? cps.filter(function (c) { return c.node === t.interrupted_at; }).pop() : null;
    if (hit) return hit.at;
    return cps.reduce(function (m, c) { return c.at > m ? c.at : m; }, t.started_at || '');
  }

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, L = ctx.lookup, C = ctx.calc;
    var M = ctx.data, db = M.db || {}, meta = M.meta || {}, settings = M.settings || {};
    var today = meta.today || '2026-10-21';

    function sectionHead(title, extra, annot) {
      return h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), extra || null, annot ? ui.annot(annot) : null));
    }
    function who(t) {
      var s = t.student_id != null ? L.student(t.student_id) : null;
      if (!s) return h('b', null, t.subject || t.thread_id);
      return h('span', null, h('b', null, L.studentCode(s) + ' · ' + s.name), h('span', { class: 'muted' }, ' — ' + String(t.subject || '').replace(/^HS-\d+\s*·\s*/, '')));
    }
    var stageLabel = function (t) { return (meta.stage_labels || {})[t.interrupted_at || t.current_node] || ui.nodeName(t.current_node); };
    var committed = function (sid) {
      return arr(db.session).filter(function (s) { return s.student_id === sid && s.status === 'committed'; })
        .sort(function (a, b) { return a.held_on < b.held_on ? -1 : a.held_on > b.held_on ? 1 : 0; });
    };

    /* 1. Việc cần làm */
    function todo(queue) {
      var counts = {};
      queue.forEach(function (t) { counts[t.graph] = (counts[t.graph] || 0) + 1; });
      var chips = h('div', { class: 'row td-gchips' }, ['G1', 'G2', 'G3', 'G4', 'G5'].map(function (g) {
        return ui.button(h('span', { class: 'td-gchip', style: '--c: var(--' + g.toLowerCase() + ')' }, h('b', null, g), ' ' + GLABEL[g] + ' ', h('span', { class: 'td-n num' }, String(counts[g] || 0))),
          function () { ctx.nav('review', { graph: g }); }, { kind: 'secondary', size: 'sm', title: 'Mở Hộp duyệt, lọc ' + g });
      }));
      var open = queue.filter(function (t) { return !t.locked; }).sort(function (a, b) { return stopAt(a) < stopAt(b) ? -1 : 1; });
      var top = open.slice(0, 5);
      var list = top.length ? h('ol', { class: 'td-list' }, top.map(function (t) {
        var at = stopAt(t);
        return h('li', { class: 'td-item st-pending' },
          h('div', { class: 'td-item-main' },
            h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t)),
            h('div', { class: 'small td-meta' }, h('span', null, stageLabel(t)), h('span', { class: 'muted' }, ' · chờ từ ' + fmt.ago(at) + ' (' + fmt.dt(at) + ')'))),
          ui.button('Mở', function () { ctx.queue.open(t.thread_id); }, { kind: 'primary', size: 'sm', cli: 'tutor review ' + t.thread_id }));
      })) : ui.empty('Không có gì chờ duyệt. Mọi đề xuất đã vào tutor.db.');
      var lockedN = queue.length - open.length;
      return h('section', { class: 'section td-todo' },
        sectionHead('Việc cần làm', h('span', { class: 'num td-big' }, String(queue.length)), ['file:checkpoints.db', 'cli:tutor review']),
        h('p', { class: 'small td-sub' }, ui.store('checkpoint'), ' nằm trong checkpoints.db, chưa vào tutor.db'),
        chips,
        h('h3', { class: 'td-h3' }, '5 mục chờ lâu nhất', h('span', { class: 'small muted' }, ' (bỏ qua mục đang khoá)')),
        list,
        h('div', { class: 'row' },
          ui.button('Mở Hộp duyệt (' + queue.length + ')', function () { ctx.nav('review', {}); }, { kind: 'ghost', size: 'sm' }),
          open.length > top.length ? h('span', { class: 'small muted' }, '+' + (open.length - top.length) + ' mục khác') : null,
          lockedN ? h('span', { class: 'small muted' }, '· ' + lockedN + ' mục khoá') : null));
    }

    /* 2. Cảnh báo */
    function warnings(queue, threads) {
      var failed = threads.filter(function (t) { return t.status === 'failed'; });
      var running = threads.filter(function (t) { return t.status === 'running'; });
      var locked = queue.filter(function (t) { return t.locked; });
      var items = [];
      if (!failed.length) items.push(h('div', { class: 'callout callout-ok' }, h('p', null, 'Không có thread lỗi.')));
      failed.forEach(function (t) {
        items.push(h('div', { class: 'callout callout-crit' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('failed')),
          h('p', { class: 'small' }, 'Dừng ở ', h('b', null, ui.nodeName(t.current_node)), ' · ' + fmt.dt(stopAt(t))),
          h('code', { class: 'small td-err' }, t.error || 'Lỗi không rõ'),
          ui.button('Chạy lại từ checkpoint', function () { ctx.threads.resume(t.thread_id); }, { kind: 'primary', size: 'sm' }),
          h('p', { class: 'small muted' }, 'Chỉ chạy lại node lỗi trở đi; các bài đã xong giữ trong checkpoints.db.'),
          ui.annot(['checkpoint', 'table:session'])));
      });
      locked.forEach(function (t) {
        var b = L.thread(t.blocker);
        items.push(h('div', { class: 'callout callout-warn' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('locked')),
          h('p', { class: 'small' }, 'Chờ buổi ' + dm(b ? ctx.queue.heldOn(b) : '') + ' — ' + t.lock_reason + '.'),
          ui.button('Mở buổi ' + dm(b ? ctx.queue.heldOn(b) : ''), function () { ctx.queue.open(t.blocker); }, { kind: 'secondary', size: 'sm', cli: 'tutor review ' + t.blocker })));
      });
      running.forEach(function (t) {
        items.push(h('div', { class: 'callout callout-info' },
          h('div', { class: 'row td-tight' }, ui.chip(t.graph, t.graph), who(t), ui.status('running')),
          h('p', { class: 'small' }, 'Đang chạy tại ', h('b', null, ui.nodeName(t.current_node)), ' — chưa tới DỪNG, chưa có gì để duyệt.'),
          ui.button('Xem tiến trình', function () { ctx.nav('session', { thread: t.thread_id }); }, { kind: 'ghost', size: 'sm' })));
      });
      return h('section', { class: 'section td-warn' }, sectionHead('Cảnh báo', h('span', { class: 'small muted' }, failed.length + ' hỏng · ' + locked.length + ' khoá · ' + running.length + ' đang chạy'), ['G1', 'checkpoint']), items);
    }

    /* 3. Nhịp dùng */
    function routine(queue, threads, students) {
      var probs = arr(db.problem), ready = probs.filter(function (p) { return L.problemStatus(p) === 'ready'; }).length;
      var noRubric = probs.filter(function (p) { return L.problemStatus(p) === 'thieu_rubric'; }).length;
      var noDelta = probs.filter(function (p) { return L.problemStatus(p) === 'cho_do_kho'; }).length;
      var g2 = queue.filter(function (t) { return t.graph === 'G2'; }), g3 = queue.filter(function (t) { return t.graph === 'G3'; });
      var g2n = g2.reduce(function (s, t) { return s + arr(t.state && t.state.problems).length; }, 0);
      var g3n = g3.reduce(function (s, t) { return s + arr(t.state && t.state.proposals).reduce(function (a, x) { return a + arr(x.ranking).length; }, 0); }, 0);
      var total = probs.length + g2n;

      var g1 = queue.filter(function (t) { return t.graph === 'G1'; });
      var g1Locked = g1.filter(function (t) { return t.locked; }).length;
      var g1Match = g1.filter(function (t) { return t.interrupted_at === 'g1.confirm_match'; }).length;
      var inbox = arr((M.files || {}).inbox).filter(function (f) {
        return !arr(db.session).some(function (s) { return s.student_id === f.student_id && s.source_sha256 === f.sha256; });
      });
      // In-progress G1 review first (flow 2: "Tạm dừng, duyệt sau"), else the oldest unlocked G1 session.
      var g1Open = g1.filter(function (t) { return !t.locked; });
      var next = g1Open.find(function (t) { return Object.keys((t.state || {}).decisions || {}).length; }) ||
        g1Open.slice().sort(function (a, b) { return ctx.queue.heldOn(a) < ctx.queue.heldOn(b) ? -1 : 1; })[0] ||
        queue.find(function (t) { return !t.locked; }) || null;

      var need = students.map(function (s) {
        var ss = committed(s.id), last = ss.length ? ss[ss.length - 1].held_on : null;
        var latest = arr(db.recommendation).filter(function (r) { return r.student_id === s.id && r.status !== 'rejected'; })
          .reduce(function (m, r) { return r.for_date > m ? r.for_date : m; }, '');
        var g4 = queue.find(function (t) { return t.graph === 'G4' && t.student_id === s.id; });
        return { s: s, last: last, latest: latest, g4: g4, need: !last || !(latest > last) };
      });
      var needing = need.filter(function (x) { return x.need; });

      var months = arr(meta.months), prev = months[0] || '2026-09', curM = today.slice(0, 7);
      var approved = arr(db.report).filter(function (r) { return r.month === prev && r.approved_at; });
      var g5 = queue.filter(function (t) { return t.graph === 'G5' && t.state && t.state.month === prev; });
      var y = +curM.slice(0, 4), mo = +curM.slice(5, 7);
      var left = new Date(Date.UTC(y, mo, 0)).getUTCDate() - +today.slice(8, 10);
      var sCode = function (id) { return L.studentCode(L.student(id)); };

      var card = function (title, line, annot, body, actions) {
        return h('article', { class: 'card td-card' }, h('div', { class: 'td-card-head' }, h('h3', null, title), ui.annot(annot)),
          h('p', { class: 'small muted' }, line), h('div', { class: 'td-card-body' }, body), h('div', { class: 'td-card-acts' }, actions));
      };

      return h('section', { class: 'section' },
        sectionHead('Nhịp dùng', h('span', { class: 'small muted' }, '4 thời điểm trong tháng của thầy/cô')),
        h('div', { class: 'grid cols-4 td-cards' },
          card('Lần đầu / khi thêm bài', 'Nạp file .tex, 06 gắn KC + 02 viết rubric (G2), 07 xếp độ khó (G3).', ['G2', 'G3', 'table:problem'],
            [h('div', { class: 'kpi-value' }, ready + '/' + total, ' ', ui.why(function () {
              return h('div', { class: 'stack' }, h('p', null, 'Sẵn sàng = có KC đã duyệt + rubric + δ đã duyệt (code: problemStatus).'),
                ui.kv([['Trong tutor.db', probs.length + ' bài'], ['Sẵn sàng', ready + ' bài'], ['Chờ duyệt độ khó (δ)', noDelta + ' bài'], ['Thiếu rubric', noRubric + ' bài'], ['Đang trong thread G2', g2n + ' bài (chưa vào tutor.db)'], ['Tổng', ready + '/' + total + ' = ' + fmt.pct(total ? ready / total : 0)]]), ui.prov('code'));
            })),
            h('div', { class: 'small' }, 'bài sẵn sàng để chấm và gợi ý'), ui.bar(ready, total || 1, { kind: 'ok' }),
            h('div', { class: 'small td-lines' }, h('span', null, ui.chip('G2', 'G2'), ' ' + g2n + ' bài chờ chọn KC + rubric'), h('span', null, ui.chip('G3', 'G3'), ' ' + g3n + ' bài chờ duyệt độ khó'))],
            [ui.button('Mở Ngân hàng bài', function () { ctx.nav('bank', {}); }, { kind: 'primary', cli: 'tutor bank tag <bank.tex>' }), ui.cli('tutor bank difficulty')]),
          card('Sau mỗi buổi học', 'Nộp bài vừa học; 01–04 chấm và đề xuất lỗi; thầy/cô duyệt từng lỗi.', ['G1', 'cli:tutor ingest', 'table:session'],
            [h('div', { class: 'kpi-value' }, String(g1.length)), h('div', { class: 'small' }, 'buổi chờ duyệt (' + (g1.length - g1Match) + ' duyệt lỗi' + (g1Match ? ' · ' + g1Match + ' xác nhận khớp bài' : '') + (g1Locked ? '; ' + g1Locked + ' khoá theo thứ tự ngày' : '') + ')'),
              h('div', { class: 'small td-lines' }, inbox.length ? h('span', null, ui.store('file'), ' ' + inbox.length + ' file mới trong data/inbox: ' + inbox.map(function (f) { return f.path.split('/').pop(); }).join(', ')) : h('span', { class: 'muted' }, 'Không có file mới trong data/inbox.'))],
            [ui.button('Nộp bài vừa học', function () { ctx.nav('session', { step: 1 }); }, { kind: 'primary', cli: 'tutor ingest <hs> <file>' }),
              ui.button('Duyệt tiếp', function () { if (next) ctx.queue.open(next.thread_id); }, { kind: 'secondary', cli: 'tutor review', disabledReason: next ? null : 'Hộp duyệt trống' }),
              next ? h('span', { class: 'small muted' }, '→ ' + (next.subject || next.thread_id) + ' · ' + stageLabel(next)) : null]),
          card('Trước buổi sau', 'Code chọn ' + ((settings.reco || {}).n_problems || 6) + ' bài theo luật, 08 viết lý do 1 dòng, thầy/cô duyệt.', ['G4', 'agent:08', 'table:recommendation'],
            [h('div', { class: 'kpi-value' }, String(needing.length), ' ', ui.why(function () {
              return h('div', { class: 'stack' }, h('p', null, 'HS cần danh sách = chưa có recommendation đã duyệt với for_date sau buổi đã ghi gần nhất.'),
                ui.kv(need.map(function (x) { return [L.studentCode(x.s), 'buổi ghi gần nhất ' + fmt.date(x.last) + ' · danh sách gần nhất ' + (x.latest ? fmt.date(x.latest) : '—') + (x.need ? ' → cần' : ' → đủ')]; })), ui.prov('code'));
            })),
            h('div', { class: 'small' }, 'HS cần danh sách bài cho buổi sau'),
            h('div', { class: 'row td-tight' }, needing.map(function (x) {
              return ui.button(L.studentCode(x.s), function () { ctx.nav('recommend', { student: x.s.id }); }, { kind: 'ghost', size: 'sm', title: 'Gợi ý bài cho ' + L.studentCode(x.s) });
            })),
            needing.filter(function (x) { return x.g4; }).map(function (x) {
              return h('div', { class: 'small' }, ui.status('awaiting_review'), ' ' + L.studentCode(x.s) + ': danh sách ' + fmt.date(x.g4.state && x.g4.state.for_date) + ' đã tạo, chờ duyệt');
            })],
            [ui.button('Gợi ý bài', function () { ctx.nav('recommend', {}); }, { kind: 'primary', cli: 'tutor recommend <hs>' })]),
          card('Cuối tháng', 'Code tính số liệu, 09 viết, audit từng câu, thầy/cô sửa và duyệt.', ['G5', 'agent:09', 'table:report'],
            [h('div', { class: 'kpi-value' }, approved.length + '/' + students.length), h('div', { class: 'small' }, 'báo cáo tháng ' + fmt.month(prev) + ' đã duyệt'),
              h('div', { class: 'small td-lines' },
                g5.length ? h('span', null, ui.status('awaiting_review'), ' ' + g5.map(function (t) { return sCode(t.student_id); }).join(', ') + ' chờ duyệt') : null,
                h('span', null, 'Tháng ' + fmt.month(curM) + ': còn ' + left + ' ngày'))],
            [ui.button('Mở Báo cáo tháng', function () { ctx.nav('report', { month: prev }); }, { kind: 'primary', cli: 'tutor report <hs> <tháng>' })])));
    }

    /* 4. Học sinh cần chú ý */
    function attention(students, threads) {
      var rows = [];
      students.forEach(function (s) {
        var reasons = [], ss = committed(s.id), last = ss[ss.length - 1];
        if (last && C.deltaVsPrevious) {
          var dv = C.deltaVsPrevious(db, last.id), kcs = arr(dv && dv.kcs);
          var mean = kcs.length ? kcs.reduce(function (a, k) { return a + k.d; }, 0) / kcs.length : 0;
          if (kcs.length && mean < 0) reasons.push(h('span', { class: 'td-reason' }, ui.chip('Δθ TB ' + fmt.signed(mean) + ' · buổi ' + dm(last.held_on), 'danger'), ui.why(function () {
            return h('div', { class: 'stack' }, h('p', null, 'Δθ TB = trung bình theo KC của (θ sau buổi − θ trước buổi), buổi ' + fmt.date(last.held_on) + '.'),
              ui.kv(kcs.map(function (k) { var kc = L.kc(k.kc_id); return [kc ? kc.code : '#' + k.kc_id, fmt.signed(k.theta_before, 3) + ' → ' + fmt.signed(k.theta_after, 3) + ' (' + fmt.signed(k.d) + ')']; })),
              h('p', null, h('b', null, 'TB = ' + fmt.signed(mean)), ' · ' + kcs.length + ' KC'), ui.prov('code'));
          })));
        }
        var mis = arr(db.misconception_log).filter(function (m) { return m.student_id === s.id && m.count >= 2 && !m.resolved_at; })
          .sort(function (a, b) { return b.count - a.count; });
        var misChip = function (m) {
          var kc = m.kc_id != null ? L.kc(m.kc_id) : null, ec = L.errorCode(m.code), raw = m.code + (kc ? ' · ' + kc.code : '');
          return h('span', { class: 'td-reason', title: raw + (kc ? ' — ' + kc.name : '') },
            h('span', { class: 'chip chip-warn td-chip' }, h('b', null, ec ? ec.description : m.code), kc ? h('span', { class: 'td-kc' }, '· ' + kc.name) : null, h('span', null, '· ' + m.count + ' lần')),
            ui.annot([raw]));
        };
        mis.slice(0, 3).forEach(function (m) { reasons.push(misChip(m)); });
        if (mis.length > 3) {
          var more = ui.button('+' + (mis.length - 3), function () { more.replaceWith.apply(more, mis.slice(3).map(misChip)); }, { kind: 'ghost', size: 'sm', title: 'Xem thêm ' + (mis.length - 3) + ' lỗi lặp' });
          reasons.push(more);
        }
        threads.filter(function (t) { return t.status === 'failed' && t.student_id === s.id; }).forEach(function (t) {
          reasons.push(h('span', { class: 'td-reason' }, ui.chip('buổi ' + dm(ctx.queue.heldOn(t)) + ' lỗi ở ' + ui.nodeName(t.current_node), 'danger')));
        });
        if (reasons.length) rows.push({ s: s, reasons: reasons, n: reasons.length + Math.max(0, mis.length - 4), last: last });
      });
      rows.sort(function (a, b) { return b.n - a.n || a.s.id - b.s.id; });
      return h('section', { class: 'section' },
        sectionHead('Học sinh cần chú ý', h('span', { class: 'small muted' }, 'Δθ TB < 0 · lỗi lặp (cùng lỗi + KC, ≥ 2 lần, chưa hết) · buổi lỗi'), ['table:skill_state', 'table:misconception_log', 'agent:05']),
        rows.length ? h('div', { class: 'stack td-att' }, rows.map(function (r) {
          return h('div', { class: 'td-att-row' },
            h('div', { class: 'td-att-who' }, h('b', null, L.studentCode(r.s)), ' ', h('span', null, r.s.name), h('div', { class: 'small muted' }, 'lớp ' + r.s.grade + (r.last ? ' · buổi ghi gần nhất ' + fmt.date(r.last.held_on) : ''))),
            h('div', { class: 'row td-tight td-att-why' }, r.reasons),
            ui.button('Xem hồ sơ', function () { ctx.nav('students', { student: r.s.id }); }, { kind: 'secondary', size: 'sm' }));
        })) : ui.empty('Không có học sinh nào cần chú ý.'));
    }

    /* 5. Hệ thống */
    function system(threads) {
      var cands = [];
      arr(db.session).forEach(function (s) { if (s.committed_at) cands.push([s.committed_at, 'G1', L.studentCode(L.student(s.student_id)) + ' · buổi ' + fmt.date(s.held_on)]); });
      arr(db.recommendation).forEach(function (r) { if (r.reviewed_at) cands.push([r.reviewed_at, 'G4', L.studentCode(L.student(r.student_id)) + ' · gợi ý ' + fmt.date(r.for_date)]); });
      arr(db.report).forEach(function (r) { if (r.approved_at) cands.push([r.approved_at, 'G5', L.studentCode(L.student(r.student_id)) + ' · báo cáo ' + fmt.month(r.month)]); });
      var lastC = cands.sort(function (a, b) { return a[0] < b[0] ? 1 : -1; })[0];
      var bk = arr((M.files || {}).backups)[0];
      var month = today.slice(0, 7), calls = arr((M.files || {}).llm_log).filter(function (c) { return String(c.ts).slice(0, 7) === month; });
      var spent = calls.reduce(function (s, c) { return s + (+c.cost_usd || 0); }, 0), budget = settings.budget_usd_month;
      var open = threads.filter(function (t) { return t.status !== 'committed'; });
      var by = function (st) { return open.filter(function (t) { return t.status === st; }).length; };
      return h('section', { class: 'section' },
        sectionHead('Hệ thống', null, ['file:tutor.db', 'file:data/backup/', 'file:llm.jsonl']),
        ui.kv([
          ['Ghi tutor.db gần nhất', lastC ? h('span', null, fmt.dt(lastC[0]) + ' ', ui.chip(lastC[1], lastC[1]), ' ' + lastC[2]) : 'Chưa ghi lần nào'],
          ['Sao lưu gần nhất', bk ? h('span', null, h('code', { class: 'small' }, bk.path), ' · ' + fmt.dt(bk.at) + ' · ' + fmt.num(bk.size_kb / 1024, 1) + ' MB') : 'Chưa sao lưu lần nào'],
          ['Chi phí tháng ' + (+month.slice(5)), h('div', { class: 'stack td-cost' },
            h('span', null, h('b', { class: 'num' }, fmt.usd(spent)), ' / ' + (budget != null ? fmt.usd(budget) : 'chưa đặt') + ' ', h('span', { class: 'small muted' }, '(ngân sách chưa chốt)'), ' ',
              ui.why(function () {
                var p = settings.price_assumption || {};
                return h('div', { class: 'stack' }, h('p', null, 'Tổng cost_usd của ' + fmt.int(calls.length) + ' lời gọi trong data/logs/llm.jsonl có ts thuộc ' + fmt.month(month) + '.'),
                  ui.kv([['Đơn giá vào', '$' + p.input_per_mtok + ' / triệu token'], ['Đơn giá ra', '$' + p.output_per_mtok + ' / triệu token'], ['Đọc cache', '$' + p.cache_read_per_mtok + ' / triệu token']]),
                  h('p', { class: 'small muted' }, p.note || 'đơn giá giả định'), ui.prov('code'));
              })),
            budget ? ui.bar(spent, budget, { kind: spent > budget * 0.8 ? 'warn' : 'accent' }) : null)],
          ['checkpoints.db', open.length + ' thread đang mở: ' + by('awaiting_review') + ' chờ duyệt · ' + by('failed') + ' hỏng · ' + by('running') + ' đang chạy']
        ]),
        h('div', { class: 'row' },
          ui.button('Mở Vận hành', function () { ctx.nav('ops', {}); }, { kind: 'secondary', size: 'sm' }),
          ui.button('Mở Nhật ký & chi phí', function () { ctx.nav('logs', {}); }, { kind: 'secondary', size: 'sm' }),
          ui.button('Bản đồ hệ thống', function () { ctx.nav('map', {}); }, { kind: 'ghost', size: 'sm' })));
    }

    /* 6. Hoạt động gần đây */
    function activity() {
      var acts = arr((M.ui || {}).activity).slice().sort(function (a, b) { return a.at < b.at ? 1 : a.at > b.at ? -1 : 0; }).slice(0, 8);
      return h('section', { class: 'section' },
        sectionHead('Hoạt động gần đây', h('span', { class: 'small muted' }, acts.length + ' mục mới nhất')),
        acts.length ? h('ul', { class: 'td-acts' }, acts.map(function (a) {
          return h('li', null, h('span', { class: 'small muted nowrap td-act-at' }, fmt.dt(a.at)),
            h('span', { class: 'td-act-text' }, a.graph ? ui.chip(a.graph, a.graph) : ui.chip('GV', 'neutral'), ' ', a.text, ' ',
              ui.annot([a.graph, a.agent ? 'agent:' + a.agent : null, a.table ? 'table:' + a.table : null].filter(Boolean))));
        })) : ui.empty('Chưa có hoạt động.'));
    }

    function draw() {
      var queue = ctx.queue.list();
      var threads = arr((M.checkpoints || {}).threads);
      var students = arr(db.student).filter(function (s) { return !s.archived_at; });
      var wd = WEEKDAY[new Date(today + 'T00:00:00Z').getUTCDay()];
      root.replaceChildren(
        ui.pageHead({
          lead: wd + ', ' + fmt.date(today) + ' — việc cần thầy/cô quyết, cảnh báo và 4 nhịp dùng. Mọi đề xuất còn nằm trong checkpoints.db cho tới khi thầy/cô duyệt.',
          actions: [ui.button('Xem hành trình một bài làm', function () { App.tour.start(); }, { kind: 'secondary', noAutoclick: true, title: 'Chạy thử một vòng: G1 → G4 → G5 trên dữ liệu mẫu' })]
        }),
        h('div', { class: 'td-top' }, todo(queue), warnings(queue, threads)),
        routine(queue, threads, students),
        h('div', { class: 'td-pair' }, attention(students, threads), system(threads)),
        activity());
      ctx.tex(root);
    }

    ctx.queue.on(draw);
    draw();
  }

  App.registerTab('today', { title: 'Hôm nay', render: render });
})();
