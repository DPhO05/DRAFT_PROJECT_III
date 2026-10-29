/* tabs/report.js — Báo cáo tháng (G5 report_graph, FR8, agent 09). Spec: IA §3.5.
   Params: thread (G5 thread id), student (id or "HS-02"), month (YYYY-MM). */
(function () {
  'use strict';
  if (!window.App) return;

  var KIND_VI = { count: 'số bài', sessions: 'số buổi', rate: 'tỉ lệ', delta_theta: 'Δθ', top_code: 'mã lỗi nhiều nhất', recurring: 'lỗi lặp', resolved: 'lỗi đã hết' };
  var INSIGHT_VI = { trend: 'xu hướng', change_point: 'điểm đổi', outlier: 'ngoại lệ', majority: 'đa số' };
  var INSIGHT_WHY = {
    trend: 'KC có θ tăng nhiều nhất trong tháng',
    change_point: 'tuần θ đổi chiều',
    outlier: 'KC có θ giảm nhiều nhất (hoặc tăng ít nhất)',
    majority: 'mã lỗi xuất hiện nhiều nhất trong tháng'
  };
  // Mirrors SAFE_NAME in mock/gen_mock.py: audit.py counts every digit as a number, so KC names with digits get a digit-free name.
  var SAFE_NAME = { '8DS-PT1-02': 'Phương trình đưa được về dạng bậc nhất', '9DS-HSB2': 'Hàm số bậc hai dạng parabol', '9DS-HSB2-02': 'Tính chất và đồ thị của parabol' };
  var TONE_DRAFT = 'Em đã nắm rất vững kiến thức, kết quả rất đáng khen [F03].';   // 09 praise draft that the tone rule drops (same text as mock HS-04)
  var TONE_NOTE = 'Kiểm tra giọng (khen quá tay): cách làm chưa chốt — bản nháp giả lập. audit.py chỉ kiểm fact_id và số nên không bắt được câu khen; câu khen ở đây bị bỏ thẳng, không qua bước viết lại 1 lần.';
  var mem = { key: null, editing: null, showDropped: false, busy: false };

  function nowISO(today) { return today + new Date().toISOString().slice(10, 19) + 'Z'; }
  function r2(x) { return Math.floor(x * 100 + 0.5) / 100; }
  function viNum(x) { return (+x).toFixed(2).replace('-', '−'); }   // gen_mock vi_num; audit reads '−'
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function nextMonth(m) { var y = +m.slice(0, 4), mo = +m.slice(5, 7) + 1; if (mo > 12) { y += 1; mo = 1; } return y + '-' + String(mo).padStart(2, '0'); }
  function fmtFact(f, fmt) {
    if (!f) return '—';
    if (f.unit === '%') return Math.round(f.value * 100) + '%';
    if (f.kind === 'delta_theta') return fmt.signed(f.value);
    if (f.kind === 'recurring' || f.kind === 'resolved') return f.value + ' lỗi';   // counts (code, KC) pairs; older mock facts say 'lần'
    return f.value + (f.unit ? ' ' + f.unit : '');
  }

  // facts.py — same rules as month_facts in mock/gen_mock.py (self-checked against the mock reports).
  function monthFacts(db, calc, lk, sid, month) {
    var sess = db.session.filter(function (s) { return s.student_id === sid && s.status === 'committed' && String(s.held_on).slice(0, 7) === month; });
    var ids = {}; sess.forEach(function (s) { ids[s.id] = 1; });
    var sup = {}; db.attempt.forEach(function (a) { if (a.supersedes_id != null) sup[a.supersedes_id] = 1; });
    var atts = db.attempt.filter(function (a) { return ids[a.session_id] && !sup[a.id]; });
    if (!atts.length) return { facts: [], rate: 0, sessions: sess.length };
    var aid = {}; atts.forEach(function (a) { aid[a.id] = 1; });
    var rep = calc.replay(db, sid, nextMonth(month) + '-01');
    var per = {}, order = [];
    rep.skill_event.forEach(function (e) {
      if (!aid[e.attempt_id]) return;
      if (!per[e.kc_id]) { per[e.kc_id] = [e.theta_before, e.theta_after]; order.push(e.kc_id); }
      per[e.kc_id][1] = e.theta_after;
    });
    var code = function (k) { var x = lk.kc(k); return x ? x.code : String(k); };
    var kname = function (k) { var x = lk.kc(k); return x ? x.name : String(k); };
    var dth = order.map(function (k) { return [r2(per[k][1] - per[k][0]), k]; })
      .sort(function (a, b) { return (b[0] - a[0]) || cmp(code(a[1]), code(b[1])); });
    var codes = {};
    calc.currentMistakes(db).forEach(function (m) { if (aid[m.attempt_id]) codes[m.code] = (codes[m.code] || 0) + 1; });
    var top = Object.keys(codes).map(function (c) { return [c, codes[c]]; }).sort(function (a, b) { return (b[1] - a[1]) || cmp(a[0], b[0]); });
    var sc = 0, mx = 0; atts.forEach(function (a) { sc += a.score || 0; mx += a.max_score || 0; });
    var where = "s.student_id = " + sid + " AND strftime('%Y-%m', s.held_on) = '" + month + "'";
    var F = [
      { fact_id: 'F01', kind: 'count', label: 'Số bài đã làm', value: atts.length, unit: 'bài', sql: 'SELECT COUNT(*) FROM attempt_current a JOIN session s ON s.id = a.session_id WHERE ' + where },
      { fact_id: 'F02', kind: 'sessions', label: 'Số buổi đã duyệt', value: sess.length, unit: 'buổi', sql: "SELECT COUNT(*) FROM session s WHERE s.status = 'committed' AND " + where },
      { fact_id: 'F03', kind: 'rate', label: 'Tỉ lệ đạt các mục rubric', value: r2(sc / mx), unit: '%', sql: 'SELECT SUM(a.score) / SUM(a.max_score) FROM attempt_current a JOIN session s ON s.id = a.session_id WHERE ' + where }
    ];
    if (dth.length) {
      F.push({ fact_id: 'F04', kind: 'delta_theta', label: 'Δθ trong tháng · ' + kname(dth[0][1]), value: dth[0][0], kc_id: dth[0][1], insight: 'trend',
        sql: 'SELECT last.theta_after - first.theta_before FROM skill_event … WHERE student_id = ' + sid + ' AND kc_id = ' + dth[0][1] });
      var lo = dth[dth.length - 1];
      F.push({ fact_id: 'F05', kind: 'delta_theta', label: 'Δθ trong tháng · ' + kname(lo[1]), value: lo[0], kc_id: lo[1], insight: 'outlier',
        sql: 'SELECT last.theta_after - first.theta_before FROM skill_event … WHERE student_id = ' + sid + ' AND kc_id = ' + lo[1] });
    }
    if (top.length) {
      var ec = lk.errorCode(top[0][0]);
      F.push({ fact_id: 'F06', kind: 'top_code', label: 'Mã lỗi gặp nhiều nhất: ' + (ec ? ec.description : top[0][0]), value: top[0][1], unit: 'lần', code: top[0][0], insight: 'majority',
        sql: 'SELECT code, COUNT(*) FROM mistake_current m JOIN attempt a ON a.id = m.attempt_id JOIN session s ON s.id = a.session_id WHERE ' + where + ' GROUP BY code ORDER BY 2 DESC LIMIT 1' });
    }
    var rec = rep.misconception_log.filter(function (m) { return m.resolved_at == null && m.count >= 2; });
    var res = rep.misconception_log.filter(function (m) { return String(m.resolved_at || '').slice(0, 7) === month; });
    F.push({ fact_id: 'F07', kind: 'recurring', label: 'Số lỗi lặp chưa hết (cùng mã + KC, ≥ 2 lần)', value: rec.length, unit: 'lỗi', sql: 'SELECT COUNT(*) FROM misconception_log WHERE student_id = ' + sid + ' AND count >= 2 AND resolved_at IS NULL' });
    F.push({ fact_id: 'F08', kind: 'resolved', label: 'Số lỗi đã hết trong tháng', value: res.length, unit: 'lỗi', sql: 'SELECT COUNT(*) FROM misconception_log WHERE student_id = ' + sid + " AND resolved_at LIKE '" + month + "%'" });
    return { facts: F, rate: sc / mx, sessions: sess.length };
  }

  // 09 draft (mock: MOCK.ui.demo_runs['g5-new'] templates) → audit.py (ctx.calc.audit): 1 rewritten, 1 dropped, + tone drop when low.
  function draftSentences(g5, F, low, calc, lk) {
    var by = {}; F.forEach(function (f) { by[f.fact_id] = f; });
    var kcSafe = function (id) { var k = lk.kc(id); return k ? (SAFE_NAME[k.code] || k.name) : ''; };
    var fill = function (s) {
      return s.replace(/\{(F\d+)(?:\.(kc|code)|(\+2))?\}/g, function (m, id, sub, plus) {
        var f = by[id]; if (!f) return m;
        if (sub === 'kc') return kcSafe(f.kc_id);
        if (sub === 'code') { var e = lk.errorCode(f.code); return e ? e.description.toLowerCase() : f.code; }
        if (f.unit === '%') { var v = Math.floor(f.value * 100 + 0.5); return (plus ? (v <= 97 ? v + 2 : v - 2) : v) + '%'; }
        if (f.kind === 'delta_theta') return viNum(f.value);
        return String(f.value);
      });
    };
    var usable = function (t) { return (t.match(/\{F\d+/g) || []).every(function (x) { return by[x.slice(1)]; }); };
    var texts = (g5.sentence_templates || []).filter(usable).map(function (t) {
      if (/\{F05\}/.test(t) && by.F05 && by.F05.value >= 0) t = 'Không kỹ năng nào giảm θ; tăng ít nhất là “{F05.kc}” ({F05}) [F05].';
      return fill(t);
    });
    var rows = texts.map(function (text, i) { return { idx: i + 1, text: text, fact_ids: (text.match(/F\d+/g) || []), result: 'pass', reason: null, first_draft: null }; });
    var rw = g5.rewrite_example;
    if (rw && rows[rw.idx - 1]) {
      var draft = fill(rw.first_draft);
      var a = calc.audit(draft, F);
      if (!a.ok) { rows[rw.idx - 1].result = 'rewritten'; rows[rw.idx - 1].first_draft = draft; rows[rw.idx - 1].reason = a.reason; }
    }
    var dr = g5.drop_example;
    if (dr) rows.push({ idx: rows.length + 1, text: dr.text, fact_ids: [], result: 'dropped', reason: calc.audit(dr.text, F).reason || dr.reason, first_draft: dr.first_draft });
    if (low) rows.push({ idx: rows.length + 1, text: TONE_DRAFT, fact_ids: ['F03'], result: 'dropped', tone_flag: true, first_draft: null, reason: 'khen quá tay khi kết quả thấp (tỉ lệ đạt dưới ngưỡng)' });
    rows.forEach(function (r) {
      if (r.result === 'dropped') return;
      var x = calc.audit(r.text, F);
      if (!x.ok) { r.result = 'dropped'; r.reason = x.reason; }
    });
    return rows;
  }

  App.registerTab('report', { title: 'Báo cáo tháng', render: render, monthFacts: monthFacts, draftSentences: draftSentences });

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, lk = ctx.lookup, M = ctx.data, db = M.db, calc = ctx.calc;
    var S = M.settings || {}, meta = M.meta || {}, today = meta.today || '2026-10-21';
    var months = meta.months || ['2026-09', '2026-10'];
    var P = ctx.params;
    var threads = (M.checkpoints || {}).threads || [];

    var thread = null, badThread = null;
    if (P.thread) { thread = lk.thread(P.thread); if (!thread || thread.graph !== 'G5') { badThread = P.thread; thread = null; } }
    var student = thread ? lk.student(thread.student_id)
      : (P.student ? (/^HS-/i.test(P.student) ? lk.studentByCode(P.student.toUpperCase()) : lk.student(+P.student)) : null);
    var sid = student ? student.id : null;
    var month = thread ? (thread.state || {}).month : (/^\d{4}-\d{2}$/.test(P.month || '') ? P.month : (student ? months[months.length - 1] : null));
    var g5Of = function (s, m) {
      return threads.filter(function (t) { return t.graph === 'G5' && t.student_id === s && (t.state || {}).month === m && t.status !== 'committed'; })[0] || null;
    };
    var reportOf = function (s, m) { return db.report.filter(function (r) { return r.student_id === s && r.month === m; })[0] || null; };
    if (!thread && student && month) thread = g5Of(sid, month);
    var code = student ? lk.studentCode(student) : null;
    var key = (thread ? thread.thread_id : '') + '|' + sid + '|' + month;
    if (mem.key !== key) mem = { key: key, editing: null, showDropped: false, busy: false };
    var sec = function (title, annot, extra) {
      return h('section', { class: 'section' }, h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? ui.annot(annot) : null), extra || null));
    };
    var daysLeft = function (m) {
      if (m !== today.slice(0, 7)) return m < today.slice(0, 7) ? 0 : null;
      var end = new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7), 0)).getUTCDate();
      return end - +today.slice(8, 10);
    };
    var sessCount = function (s, m) { return db.session.filter(function (x) { return x.student_id === s && x.status === 'committed' && String(x.held_on).slice(0, 7) === m; }).length; };
    var cellState = function (s, m) { return reportOf(s, m) ? 'approved' : g5Of(s, m) ? 'pending' : 'none'; };

    /* ---------- head ---------- */
    root.append(ui.pageHead({
      lead: 'Cuối tháng: code lấy số liệu bằng SQL (mỗi số có fact_id), chọn 3 insight; 09 viết câu; audit.py kiểm từng câu — số phải khớp fact đã trích, trượt thì viết lại 1 lần, vẫn trượt thì bỏ. Kết quả thấp thì không khen quá tay. Thầy/cô sửa và duyệt.',
      annot: ['G5', 'agent:09', 'table:report', 'cli:tutor report <hs> <tháng>'],
      actions: student ? [ui.button('Xem hồ sơ ' + code, function () { ctx.nav('students', { student: sid, tab: 'outputs' }); }, { kind: 'secondary' })] : null
    }));
    if (badThread) root.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'Không tìm thấy thread G5 “' + badThread + '”.')));

    /* ---------- 1. grid ---------- */
    var gsec = sec('Bảng học sinh × tháng', ['table:report', 'table:session', 'file:checkpoints.db']);
    gsec.append(h('div', { class: 'rp-legend small' },
      h('span', { class: 'rp-dot rp-cell-none' }), 'chưa tạo', h('span', { class: 'rp-dot rp-cell-pending' }), 'chờ duyệt (checkpoints.db)',
      h('span', { class: 'rp-dot rp-cell-approved' }), 'đã duyệt (tutor.db)'));
    gsec.append(ui.table({
      columns: [{ label: 'Học sinh', render: function (s) { return h('span', { class: 'rp-who' }, h('b', { class: 'mono' }, lk.studentCode(s)), h('span', null, s.name), h('span', { class: 'muted small' }, 'lớp ' + s.grade)); } }]
        .concat(months.map(function (m) {
          var left = daysLeft(m);
          return {
            label: h('span', null, 'Tháng ' + fmt.month(m), left ? h('span', { class: 'rp-note' }, 'tháng chưa hết (còn ' + left + ' ngày)') : null),
            render: function (s) {
              var stt = cellState(s.id, m), n = sessCount(s.id, m);
              var t = g5Of(s.id, m);
              var label = { approved: 'đã duyệt', pending: t && t.status === 'running' ? 'đang chạy' : 'chờ duyệt', none: 'chưa tạo' }[stt];
              var b = h('button', { type: 'button', class: 'rp-cell rp-cell-' + stt, 'aria-pressed': String(s.id === sid && m === month),
                'aria-label': lk.studentCode(s) + ' · ' + fmt.month(m) + ' · ' + label },
                h('span', { class: 'rp-cell-st' }, label), h('span', { class: 'rp-cell-n' }, n + ' buổi đã duyệt'));
              b.addEventListener('click', function () { ctx.nav('report', t ? { thread: t.thread_id } : { student: s.id, month: m }); });
              return b;
            }
          };
        })),
      rows: db.student.filter(function (s) { return !s.archived_at || s.id === sid; }),
      rowClass: function (s) { return s.id === sid ? 'is-sel' : null; }
    }));
    gsec.classList.add('rp-gridsec');
    root.append(gsec);

    /* ---------- routes ---------- */
    if (!student) { root.append(overview(month)); return; }
    if (thread && thread.status !== 'committed') { renderThread(); return; }
    var rpt = reportOf(sid, month);
    if (rpt) { renderApproved(rpt, thread); return; }
    renderNone();

    /* ===== views ===== */
    function overview(m) {
      var ms = m ? [m] : months;
      var s = sec(m ? 'Tháng ' + fmt.month(m) : 'Tổng quan', ['G5', 'table:report']);
      if (!m) s.append(h('div', { class: 'callout callout-info' }, h('p', null, 'Chọn một ô trong bảng để mở báo cáo. Ô vàng nét đứt = chờ duyệt (còn trong checkpoints.db); ô xanh = đã duyệt (trong tutor.db).')));
      var studs = db.student.filter(function (x) { return !x.archived_at; });
      ms.forEach(function (mm) {
        var c = { approved: 0, pending: 0, none: 0 };
        studs.forEach(function (x) { c[cellState(x.id, mm)] += 1; });
        s.append(h('div', { class: 'rp-kpis' },
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Tháng ' + fmt.month(mm) + ' · đã duyệt'), h('span', { class: 'kpi-value' }, c.approved + '/' + studs.length)),
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Chờ duyệt'), h('span', { class: 'kpi-value' }, String(c.pending))),
          h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, 'Chưa tạo'), h('span', { class: 'kpi-value' }, String(c.none)),
            daysLeft(mm) ? h('span', { class: 'kpi-sub' }, 'tháng chưa hết (còn ' + daysLeft(mm) + ' ngày)') : null)));
      });
      var pend = threads.filter(function (t) { return t.graph === 'G5' && t.status === 'awaiting_review' && (!m || (t.state || {}).month === m); });
      s.append(h('h3', null, 'Đang chờ duyệt'), pend.length ? ui.table({
        columns: [
          { label: 'Thread', render: function (t) { return h('span', { class: 'mono small' }, t.thread_id); } },
          { label: 'Học sinh · tháng', key: 'subject' },
          { label: 'Tỉ lệ đạt', render: function (t) { var p = ((t.state || {}).proposals || [])[0]; return p && p.tone ? Math.round(p.tone.pass_rate * 100) + '%' : '—'; } },
          { label: 'Chờ từ', render: function (t) { var c = (t.checkpoints || []).slice(-1)[0]; return fmt.ago(c ? c.at : t.started_at); } },
          { label: '', render: function (t) { return ui.button('Mở', function () { if (!ctx.queue.open(t.thread_id)) ctx.nav('report', { thread: t.thread_id }); }, { kind: 'secondary', size: 'sm', cli: 'tutor review ' + t.thread_id }); } }
        ],
        rows: pend
      }) : ui.empty('Không có báo cáo nào chờ duyệt.'));
      return s;
    }

    function stripFor(t) {
      var g = (meta.graphs || {}).G5, nodes = g ? g.nodes.map(function (n) { return n.id; }) : [];
      var o = {};
      if (t) {
        var done = (t.checkpoints || []).map(function (c) { return c.node; });
        if (t.status === 'committed') o.done = nodes;
        else if (t.status === 'awaiting_review') { o.done = done.filter(function (n) { return n !== 'g5.review'; }); o.current = 'g5.review'; }
        else { o.done = done; o.current = t.current_node; }
      }
      var el = ui.graphStrip('G5', o);
      ((t && t.checkpoints) || []).forEach(function (c) {
        var m = el.querySelector('[data-node="' + c.node + '"] .gn-meta'), tok = (c.tokens_in || 0) + (c.tokens_out || 0);
        if (m && (c.ms || tok)) m.textContent = fmt.ms(c.ms) + (tok ? ' · ' + fmt.int(tok) + ' tok' : '');
      });
      return el;
    }

    function factChip(fid, facts) {
      var f = facts.filter(function (x) { return x.fact_id === fid; })[0];
      var b = ui.why(function () {
        var row = root.querySelector('tr.rp-f-' + fid);
        root.querySelectorAll('tr.rp-hl').forEach(function (r) { r.classList.remove('rp-hl'); });
        if (row) { row.classList.add('rp-hl'); row.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
        if (!f) return h('p', null, fid + ' không có trong facts — audit.py sẽ đánh trượt câu này.');
        return h('div', { class: 'stack' },
          ui.kv([['fact_id', f.fact_id], ['Nhãn', f.label], ['Giá trị', fmtFact(f, fmt)], ['Loại', KIND_VI[f.kind] || f.kind], f.insight ? ['Insight', INSIGHT_VI[f.insight]] : null]),
          h('pre', { class: 'code' }, f.sql), h('p', { class: 'small muted' }, ui.prov('code', 'facts.py'), ' số do SQL tính, 09 chỉ trích lại.'),
          ui.button('Xem nguồn', function () { ctx.nav('students', { student: sid, tab: 'history' }); }, { kind: 'secondary', size: 'sm' }));
      });
      b.textContent = '[' + fid + ']'; b.className = 'rp-fact'; b.setAttribute('aria-label', 'Fact ' + fid);
      return b;
    }
    function withChips(text, facts) {
      return String(text).split(/(\[F\d+\])/).filter(Boolean).map(function (part) {
        var m = /^\[(F\d+)\]$/.exec(part); return m ? factChip(m[1], facts) : part;
      });
    }

    function factsSec(facts, title) {
      var s = sec(title || 'Facts (code · SQL)', ['facts.py', 'table:attempt', 'table:skill_event', 'table:mistake', 'table:misconception_log', 'fact_id'], ui.prov('code', 'facts.py'));
      s.append(ui.table({
        columns: [
          { label: 'fact_id', render: function (f) { return h('span', { class: 'mono' }, f.fact_id); } },
          { label: 'Loại', render: function (f) { return KIND_VI[f.kind] || f.kind; } },
          { label: 'Nhãn', key: 'label' },
          { label: 'Giá trị', align: 'right', render: function (f) { return h('b', { class: 'num nowrap' }, fmtFact(f, fmt)); } },
          { label: 'Insight', render: function (f) { return f.insight ? ui.chip(INSIGHT_VI[f.insight] || f.insight, 'info') : '—'; } }
        ],
        rows: facts, rowClass: function (f) { return 'rp-f-' + f.fact_id; }
      }));
      return s;
    }

    function insightsSec(facts) {
      var ins = facts.filter(function (f) { return f.insight; });
      var s = sec('3 insight (code chọn)', ['g5.insights'], ui.prov('code'));
      var by = {}; facts.forEach(function (f) { by[f.fact_id] = f; });
      s.append(h('p', { class: 'small muted' }, 'Code chọn 3 điểm đáng nói từ facts; 09 chỉ viết câu cho những điểm này.'),
        h('div', { class: 'callout callout-warn' }, h('p', { class: 'small' }, 'Giả định bản nháp: gán cố định F04 = xu hướng (Δθ lớn nhất), F05 = ngoại lệ (Δθ nhỏ nhất, kể cả khi vẫn tăng), F06 = đa số. Chưa tính “điểm đổi”, chưa xếp hạng ứng viên để lấy 3 điểm đáng kể nhất — spec chưa chốt cách chọn.' +
          (by.F04 && by.F05 && by.F04.kc_id === by.F05.kc_id ? ' Tháng này chỉ có 1 KC nên xu hướng và ngoại lệ là cùng một KC.' : ''))),
        h('div', { class: 'grid cols-3' }, ins.map(function (f) {
          return h('div', { class: 'card' }, h('div', { class: 'row' }, ui.chip(INSIGHT_VI[f.insight] || f.insight, 'info'), h('span', { class: 'mono small' }, f.fact_id)),
            h('b', null, f.label + ' = ' + fmtFact(f, fmt)), h('span', { class: 'small muted' }, INSIGHT_WHY[f.insight] || ''));
        })));
      return s;
    }

    function headBox(t) {
      var calls = (M.files.llm_log || []).filter(function (c) { return c.thread_id === t.thread_id; });
      var last = (t.checkpoints || []).slice(-1)[0];
      var s = sec('Graph G5 · report_graph', ['G5', 'interrupt', 'file:checkpoints.db']);
      s.append(stripFor(t), h('div', { class: 'row small' }, ui.status(t.status), h('span', { class: 'mono' }, t.thread_id),
        ui.store(t.status === 'committed' ? 'db' : 'checkpoint'),
        t.status === 'awaiting_review' ? h('span', { class: 'muted' }, 'chờ từ ' + fmt.ago(last ? last.at : t.started_at)) : null,
        calls.length ? ui.costChip(calls) : null,
        calls.length ? ui.button('Xem lời gọi 09', function () { ctx.nav('logs', { thread: t.thread_id, agent: '09' }); }, { kind: 'ghost', size: 'sm' }) : null,
        ui.button('Xem nội dung gửi API', function () { ui.payloadModal('09', code); }, { kind: 'ghost', size: 'sm' })));
      return s;
    }

    function renderThread() {
      var t = thread, st = t.state || (t.state = {});
      root.append(headBox(t));
      if (t.status === 'running') { root.append(h('div', { class: 'callout callout-info' }, h('p', null, 'Đang chạy — bản nháp hiện khi graph tới DỪNG.'))); return; }
      var prop = (st.proposals || [])[0];
      if (!prop) { root.append(ui.empty('Thread không có bản nháp.')); return; }
      var dec = st.decisions || (st.decisions = {});
      var edits = dec.edits || (dec.edits = {}), audits = dec.audits || (dec.audits = {});
      var F = prop.facts_json || [];
      var tone = prop.tone || {};
      if (tone.low_results) {
        root.append(h('div', { class: 'callout callout-warn rp-tone' }, h('strong', null, 'Kết quả thấp (tỉ lệ đạt ' + Math.round(tone.pass_rate * 100) + '% < ' + Math.round(tone.threshold * 100) + '%) → không khen quá tay'),
          h('p', { class: 'small' }, 'Ngưỡng ' + Math.round(tone.threshold * 100) + '% là giả định của bản nháp (settings.report.low_pass_rate). ' + TONE_NOTE)));
      }
      root.append(factsSec(F), insightsSec(F));

      var draft = sec('Bản nháp', ['agent:09', 'audit.py', 'file:checkpoints.db'], h('span', { class: 'row' }, ui.prov('llm', '09'), ui.store('checkpoint'), ui.chip('chưa ghi', 'warn')));
      var rows = prop.audit_json || [];
      var kept = rows.filter(function (r) { return r.result !== 'dropped'; }), dropped = rows.filter(function (r) { return r.result === 'dropped'; });
      var fails = kept.filter(function (r) { return audits[r.idx] && !audits[r.idx].ok; });
      // spec §2: every sentence must trace to a fact; a number mismatch stays a warning.
      var unsourced = fails.filter(function (r) { return /fact_id/.test(audits[r.idx].reason); });
      var cnt = { pass: 0, rewritten: 0, dropped: dropped.length };
      kept.forEach(function (r) { if (fails.indexOf(r) < 0) cnt[r.result] = (cnt[r.result] || 0) + 1; });
      draft.append(h('div', { class: 'row small' }, ui.status('pass'), cnt.pass + ' câu', ui.status('rewritten'), cnt.rewritten + ' câu', ui.status('dropped'), cnt.dropped + ' câu',
        fails.length ? ui.chip(fails.length + ' câu GV sửa trượt re-audit', 'danger') : null));
      var list = h('div', { class: 'rp-sents' });
      kept.forEach(function (r) { list.append(sentRow(r, F, edits, audits)); });
      draft.append(list);
      draft.append(h('div', { class: 'row' },
        ui.button('Chạy lại audit', function () {
          var ok = 0, nf = 0;
          kept.forEach(function (r) { var x = calc.audit(edits[r.idx] != null ? edits[r.idx] : r.text, F); audits[r.idx] = x; if (x.ok) ok += 1; else if (/fact_id/.test(x.reason)) nf += 1; });
          dec.reaudit_at = nowISO(today);
          ctx.toast('audit.py: ' + ok + '/' + kept.length + ' câu đạt' + (ok < kept.length ? ' · ' + (kept.length - ok) + ' câu trượt' + (nf ? ' (' + nf + ' câu không truy được về fact — chặn duyệt)' : ' (chỉ cảnh báo)') : '') + '.', { kind: ok < kept.length ? 'warn' : 'ok' });
          ctx.rerender();
        }, { kind: 'secondary' }),
        ui.button((mem.showDropped ? 'Ẩn' : 'Xem') + ' câu bị bỏ (' + dropped.length + ')', function () { mem.showDropped = !mem.showDropped; ctx.rerender(); }, { kind: 'ghost', disabledReason: dropped.length ? null : 'không có câu bị bỏ' })));
      if (mem.showDropped && dropped.length) {
        draft.append(h('div', { class: 'rp-dropped' }, h('h3', null, 'Câu bị bỏ (' + dropped.length + ')'), dropped.map(function (r) {
          return h('div', { class: 'rp-drop st-rejected' + (r.tone_flag ? ' rp-tone-flag' : '') },
            h('div', { class: 'row' }, ui.status('dropped'), r.tone_flag ? ui.chip('khen quá tay', 'warn') : null, h('span', { class: 'small' }, 'lý do: ' + r.reason)),
            h('p', { class: 'strike' }, r.text), r.tone_flag ? h('p', { class: 'small muted' }, TONE_NOTE) : null, r.first_draft ? h('p', { class: 'small muted' }, 'Bản đầu: “' + r.first_draft + '” → viết lại 1 lần vẫn trượt → bỏ.') : null);
        })));
      }
      root.append(draft);

      var fs = sec('Duyệt và xuất file .md', ['file:data/out/', 'cli:tutor review <id>', 'table:report']);
      var md = mdText(prop, edits);
      fs.append(h('div', { class: 'row' }, h('span', { class: 'chip st-file mono' }, st.out_path || '—'), ui.store('file')),
        h('p', { class: 'small muted' }, 'Thầy/cô sửa câu và duyệt ngay trên màn hình này. Bấm “Duyệt & ghi report” thì app ghi tutor.db rồi xuất file .md vào data/out/; dưới đây là bản xem trước. Lệnh CLI tương đương: tutor review <id>.'),
        h('div', { class: 'row' },
          ui.button('Xem file .md', function () { ctx.modal({ title: st.out_path, wide: true, body: h('pre', { class: 'code' }, md), actions: [{ label: 'Đóng' }] }); }, { kind: 'secondary' }),
          ui.button('Tải .md', function () { ui.download(String(st.out_path).split('/').pop(), md); }, { kind: 'ghost', noAutoclick: true })),
        h('div', { class: 'rp-approve' }, ui.button('Duyệt & ghi report', function () { approve(prop, edits, audits, fails); }, { kind: 'primary', cli: 'tutor review ' + t.thread_id,
          disabledReason: unsourced.length ? 'câu ' + unsourced.map(function (r) { return r.idx; }).join(', ') + ': ' + audits[unsourced[0].idx].reason + ' — mọi câu phải truy được về fact (spec §2); thêm [Fxx] hoặc trả về bản 09' : null }),
          h('span', { class: 'small muted' }, 'Ghi 1 dòng report (facts_json, text_md, audit_json, approved_at) — UNIQUE(student_id, month).')));
      root.append(fs);
    }

    function sentRow(r, F, edits, audits) {
      var text = edits[r.idx] != null ? edits[r.idx] : r.text;
      var au = audits[r.idx];
      var editing = mem.editing === r.idx;
      var body = h('div', { class: 'rp-sent-body' });
      if (editing) {
        var ta = h('textarea', { rows: 3, value: text, 'aria-label': 'Sửa câu ' + r.idx });
        body.append(ta, h('div', { class: 'row' },
          ui.button('Lưu câu', function () {
            var v = ta.value.trim();
            if (!v) { ctx.toast('Câu không được để trống.', { kind: 'warn' }); return; }
            if (v === r.text) delete edits[r.idx]; else edits[r.idx] = v;
            var x = calc.audit(v, F); audits[r.idx] = x; mem.editing = null;
            ctx.toast(x.ok ? 'audit.py: câu ' + r.idx + ' đạt.' : 'Câu ' + r.idx + ': ' + x.reason + (/fact_id/.test(x.reason) ? ' — chặn duyệt.' : ' (chỉ cảnh báo).'), { kind: x.ok ? 'ok' : 'warn' });
            ctx.rerender();
          }, { kind: 'primary', size: 'sm' }),
          ui.button('Huỷ sửa', function () { mem.editing = null; ctx.rerender(); }, { kind: 'ghost', size: 'sm' })),
          h('p', { class: 'small muted' }, 'Giữ [Fxx] sau mỗi số; audit.py so số trong câu với fact đã trích.'));
        setTimeout(function () { if (ta.isConnected) ta.focus(); }, 0);
      } else {
        body.append(h('p', { class: 'rp-text' }, withChips(text, F)));
        if (r.result === 'rewritten' && r.first_draft) body.append(h('p', { class: 'small muted' }, 'Bản đầu (trượt audit): “' + r.first_draft + '” — ' + r.reason + ' → 09 viết lại 1 lần.'));
        if (edits[r.idx] != null) body.append(h('p', { class: 'small' }, ui.prov('gv'), ' GV sửa · bản 09: “' + r.text + '”'));
        if (au && !au.ok) body.append(h('p', { class: 'rp-fail-note' }, '✕ ' + au.reason + ' · re-audit bản GV sửa: đề xuất, spec chưa có'));
        else if (au && au.ok) body.append(h('p', { class: 'small rp-ok-note' }, '✓ audit lại: đạt'));
      }
      var badge = au && !au.ok ? ui.chip('trượt re-audit', 'danger') : ui.status(r.result);
      if (r.first_draft) badge.title = 'Bản đầu: ' + r.first_draft;
      return h('div', { class: 'rp-sent' + (au && !au.ok ? ' is-fail' : '') + (r.tone_flag ? ' rp-tone-flag' : '') },
        h('span', { class: 'rp-idx num' }, String(r.idx)), body,
        h('div', { class: 'rp-sent-side' }, badge, editing ? null : ui.button('Sửa câu', function () { mem.editing = r.idx; ctx.rerender(); }, { kind: 'ghost', size: 'sm' })));
    }

    function mdText(prop, edits) {
      var kept = (prop.audit_json || []).filter(function (r) { return r.result !== 'dropped'; }).map(function (r) { return edits && edits[r.idx] != null ? edits[r.idx] : r.text; });
      return '**Báo cáo tháng ' + fmt.month(month) + ' · ' + code + '**\n\n' + kept.join(' ');
    }

    function approve(prop, edits, audits, fails) {
      var t = thread;
      if (t.status !== 'awaiting_review') return;
      var go = function () {
        if (t.status !== 'awaiting_review') return;
        var at = nowISO(today);
        var rows = (prop.audit_json || []).map(function (r) {
          if (edits[r.idx] == null) return Object.assign({}, r);
          // † edited_by_gv / text_09: mock-only fields so the 09 sentence survives a teacher edit
          return Object.assign({}, r, { text: edits[r.idx], text_09: r.text, edited_by_gv: true, fact_ids: edits[r.idx].match(/F\d+/g) || [] });
        });
        var md = mdText(prop, edits);
        var id = db.report.reduce(function (m, x) { return Math.max(m, x.id || 0); }, 0) + 1;
        db.report.push({ id: id, student_id: sid, month: month, facts_json: prop.facts_json, text_md: md, audit_json: rows, approved_at: at });
        var files = M.files || (M.files = {});
        (files.out || (files.out = [])).push({ path: t.state.out_path, kind: 'report', student_id: sid, key: month, text: md });
        (t.checkpoints || (t.checkpoints = [])).push({ node: 'g5.commit', at: at, ms: 60, tokens_in: 0, tokens_out: 0 });
        ctx.receipt('Duyệt report ' + code + ' · ' + fmt.month(month), [['report', 1], ['(' + code + ' · ' + month + ')', 'cập nhật']], { graph: 'G5' });
        ctx.queue.resolve(t.thread_id);
        mem.editing = null;
        ctx.rerender();
      };
      if (!fails.length) { go(); return; }
      ctx.confirm('Còn ' + fails.length + ' câu GV sửa trượt re-audit: ' + fails.map(function (r) { return 'câu ' + r.idx + ' — ' + audits[r.idx].reason; }).join('; ') + '. Số không khớp chỉ là cảnh báo (re-audit bản GV sửa: đề xuất, spec chưa có) — vẫn duyệt?', { title: 'Duyệt & ghi report', ok: 'Vẫn duyệt' })
        .then(function (yes) { if (yes) go(); });
    }

    function renderApproved(r, t) {
      var ct = t || threads.filter(function (x) { return x.graph === 'G5' && x.student_id === sid && (x.state || {}).month === month && x.status === 'committed'; })[0];
      if (ct) root.append(headBox(ct));
      var s = sec('Đã duyệt · ' + code + ' · ' + fmt.month(month), ['table:report', 'file:tutor.db'], ui.store('db'));
      s.classList.add('st-db');
      var lines = String(r.text_md || '').split(/\n\s*\n/);
      var title = /^\*\*(.*)\*\*$/.exec(lines[0] || '');
      s.append(h('div', { class: 'callout callout-ok' }, h('p', null, 'Đã duyệt lúc ' + fmt.dt(r.approved_at) + ' — chỉ đọc. UNIQUE(student_id, month): không duyệt lại tháng này.')),
        title ? h('h3', null, title[1]) : null,
        h('div', { class: 'rp-final' }, (title ? lines.slice(1) : lines).map(function (p) { return h('p', null, withChips(p, r.facts_json || [])); })));
      var au = r.audit_json || [];
      var c = { pass: 0, rewritten: 0, dropped: 0 }; au.forEach(function (x) { c[x.result] = (c[x.result] || 0) + 1; });
      s.append(h('div', { class: 'row small' }, h('span', { class: 'muted' }, 'audit lúc duyệt:'), ui.status('pass'), c.pass + ' câu', ui.status('rewritten'), c.rewritten + ' câu', ui.status('dropped'), c.dropped + ' câu'));
      au.filter(function (x) { return x.result !== 'pass'; }).forEach(function (x) {
        s.append(h('p', { class: 'small muted' }, ui.status(x.result), ' ', x.result === 'dropped' ? '“' + x.text + '” — ' + x.reason : 'bản đầu “' + x.first_draft + '” — ' + x.reason, x.tone_flag ? ' · ' + TONE_NOTE : ''));
      });
      var f = ((M.files || {}).out || []).filter(function (o) { return o.kind === 'report' && o.student_id === sid && o.key === month; })[0];
      var md = f ? f.text : r.text_md;
      s.append(h('div', { class: 'row' }, h('span', { class: 'chip st-file mono' }, f ? f.path : 'data/out/report-' + code + '-' + month + '.md'),
        ui.button('Xem file .md', function () { ctx.modal({ title: f ? f.path : 'report.md', wide: true, body: h('pre', { class: 'code' }, md), actions: [{ label: 'Đóng' }] }); }, { kind: 'secondary', size: 'sm' }),
        ui.button('Tải .md', function () { ui.download('report-' + code + '-' + month + '.md', md); }, { kind: 'ghost', size: 'sm', noAutoclick: true }),
        ui.button('Duyệt & ghi report', function () {}, { kind: 'primary', size: 'sm', disabledReason: 'đã duyệt — UNIQUE(student_id, month), không duyệt lại' })));
      root.append(s, factsSec(r.facts_json || [], 'Facts lúc duyệt (code · SQL)'), insightsSec(r.facts_json || []));
    }

    function renderNone() {
      var n = sessCount(sid, month), left = daysLeft(month);
      var s = sec('Chưa tạo · ' + code + ' · tháng ' + fmt.month(month), ['G5', 'cli:tutor report <hs> <tháng>']);
      var reason = !n ? 'Không đủ dữ liệu: 0 buổi đã duyệt trong tháng' : null;
      var pre = n ? monthFacts(db, calc, lk, sid, month) : null;
      s.append(ui.kv([['Học sinh', code + ' (gửi API dưới mã này)'], ['Tháng', fmt.month(month) + (left ? ' · tháng chưa hết (còn ' + left + ' ngày)' : '')],
        ['Buổi đã duyệt trong tháng', String(n)], ['Bài đã làm', pre ? String(pre.facts[0].value) : '0']]));
      if (left) s.append(h('div', { class: 'callout callout-info' }, h('p', null, 'Tháng chưa hết: report tạo bây giờ chỉ gồm các buổi đã duyệt tới ' + fmt.date(today) + '.')));
      var strip = stripFor(null);
      var btn = ui.button('Tạo report', function () { run(strip, btn); }, { kind: 'primary', disabledReason: reason, cli: 'tutor report ' + code + ' ' + month, privacy: code });
      s.append(btn, strip);
      root.append(s);
      if (pre) {
        var fsec = factsSec(pre.facts, 'Xem trước facts (code · chưa chạy G5)');
        fsec.insertBefore(h('p', { class: 'small muted' }, 'Chỉ là SQL trên tutor.db — chưa gọi LLM, chưa tạo thread.'), fsec.children[1]);
        root.append(fsec);
      }
    }

    function run(strip, btn) {
      if (mem.busy) return;
      var res = monthFacts(db, calc, lk, sid, month);
      if (!res.sessions) { ctx.toast('Không đủ dữ liệu: 0 buổi đã duyệt trong tháng.', { kind: 'warn' }); return; }
      var id = 'g5-' + code.toLowerCase().replace('-', '') + '-' + month;
      if (lk.thread(id) && lk.thread(id).status !== 'committed') { ctx.toast('Thread ' + id + ' đã tồn tại.', { kind: 'warn' }); return; }
      var thr = (S.report || {}).low_pass_rate != null ? S.report.low_pass_rate : 0.5;
      var low = res.rate < thr;
      var g5 = (((M.ui || {}).demo_runs || {})['g5-new']) || {};
      var rows = draftSentences(g5, res.facts, low, calc, lk);
      var kept = rows.filter(function (r) { return r.result !== 'dropped'; }).map(function (r) { return r.text; });
      var at = nowISO(today);
      // shortcut: token counts copied from the latest mock 09 run (write + rewrite); a real run logs its own calls.
      var log = (M.files || {}).llm_log || [];
      var c09 = log.filter(function (c) { return c.agent === '09'; }).sort(function (a, b) { return a.ts < b.ts ? 1 : -1; });
      var srcThread = c09[0] ? c09[0].thread_id : null;
      var calls = c09.filter(function (c) { return c.thread_id === srcThread; }).map(function (c) {
        return Object.assign({}, c, { ts: at, thread_id: id, student_code: code });
      });
      var tok = calls.reduce(function (a, c) { a.ms += c.ms; a.i += c.tokens_in; a.o += c.tokens_out; return a; }, { ms: 0, i: 0, o: 0 });
      var t = {
        thread_id: id, graph: 'G5', subject: code + ' · báo cáo ' + fmt.month(month), student_id: sid, session_id: null, started_at: at,
        status: 'running', current_node: 'g5.facts', interrupted_at: null, error: null, demo_run: null, checkpoints: [],
        state: { student_id: sid, month: month, decisions: {}, out_path: 'data/out/report-' + code + '-' + month + '.md',
          proposals: [{ pid: 'p1', kind: 'report', facts_json: res.facts, audit_json: rows, text_md: '**Báo cáo tháng ' + fmt.month(month) + ' · ' + code + '**\n\n' + kept.join(' '),
            tone: { low_results: low, pass_rate: r2(res.rate), threshold: thr } }] }
      };
      mem.busy = true;
      var b = btn.button || btn; b.disabled = true; b.textContent = 'Đang chạy…';
      ctx.queue.add(t);
      ctx.toast('G5 chạy cho ' + code + ' · ' + fmt.month(month) + ': facts.py → 3 insight → 09 → audit.py.', { kind: 'info' });
      var steps = [{ node: 'g5.facts', ms: 110 }, { node: 'g5.insights', ms: 40 }, { node: 'g5.09_reporter', ms: tok.ms, tokens_in: tok.i, tokens_out: tok.o },
        { node: 'g5.audit', ms: 90 }, { node: 'g5.review' }];
      ui.animateGraph(strip, steps, { stepMs: 420 }).then(function () {
        steps.forEach(function (s) { t.checkpoints.push({ node: s.node, at: nowISO(today), ms: s.ms || 0, tokens_in: s.tokens_in || 0, tokens_out: s.tokens_out || 0 }); });
        Array.prototype.push.apply(log, calls);
        t.status = 'awaiting_review'; t.current_node = 'g5.review'; t.interrupted_at = 'g5.review';
        mem.busy = false;
        ctx.refresh();
        var nd = rows.filter(function (r) { return r.result === 'dropped'; }).length, nr = rows.filter(function (r) { return r.result === 'rewritten'; }).length;
        ctx.toast('Sẵn sàng duyệt: ' + kept.length + ' câu đạt audit · ' + nr + ' viết lại · ' + nd + ' bị bỏ' + (low ? ' · kết quả thấp' : '') + '.', { kind: 'ok' });
        if (strip.isConnected) ctx.nav('report', { thread: id });
      });
    }
  }
})();
