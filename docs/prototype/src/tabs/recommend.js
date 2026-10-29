/* tabs/recommend.js — Gợi ý bài (G4 recommend_graph, FR7, agent 08). Spec: IA §3.4.
   Params: thread (G4 thread id), student (id or "HS-02"), date (YYYY-MM-DD, for_date when no thread). */
(function () {
  'use strict';
  if (!window.App) return;

  var BVI = { review: 'ôn', zpd: 'vừa sức', challenge: 'thử thách' };
  var NO_BUCKET = 'GV tự chọn';   // same label as students › Gợi ý & báo cáo
  var ST_MD = { approved: 'duyệt', rejected: 'bỏ', added: 'GV thêm', undecided: 'chưa quyết' };
  var BKIND = { review: 'info', zpd: 'ok', challenge: 'warn' };
  var BRULE = {
    review: 'KC còn lỗi chưa hết (mọi mã, kể cả lỗi mới gặp 1 lần), xếp theo tổng số lần; lấy bài dễ nhất (δ nhỏ nhất) còn qua bộ lọc',
    zpd: 'θ − δ nằm trong vùng vừa sức; chọn bài có |θ − δ| nhỏ nhất',
    challenge: 'mọi KC tiên quyết có θ ≥ 0 (KC chưa có dữ liệu lấy θ0 mặc định); chọn bài có δ − θ > 0.5 nhỏ nhất'
  };
  // Per-viewer preview state; reset whenever the list or saved ratios change.
  var mem = { key: null, ratios: null, kc: null, busy: false };

  function addDays(d, n) { return new Date(Date.parse(d + 'T00:00:00Z') + n * 864e5).toISOString().slice(0, 10); }
  function nowISO(today) { return today + new Date().toISOString().slice(10, 19) + 'Z'; }
  function sgn2(x, d) { var s = (+x).toFixed(d || 2); return s.charAt(0) === '-' ? s : '+' + s; }        // python {:+.2f}
  function viNum(x, signed, d) { return (signed ? sgn2(x, d) : (+x).toFixed(d || 2)).replace('-', '−'); }   // gen_mock vi_num
  // Decimals for a value compared with a rule limit: 2, or 4 when 2 would round onto the limit (0.5002 → "0.50" reads as false).
  function dp(x, win) { var r = +(+x).toFixed(2); return [win[0], win[1], -0.5, 0.5].some(function (b) { return r === b && +x !== b; }) ? 4 : 2; }
  function winText(w) { return '[' + w.map(function (v) { return (v < 0 ? '−' : '') + Math.abs(v); }).join(', ') + ']'; }
  function pct(r) { return Math.round(r * 100) + '%'; }
  function ratioKey(r) { return [r.review, r.zpd, r.challenge].join('/'); }

  // Code reason for Bước 1 (select.py); mirrors sel_reason in mock/gen_mock.py. p.codeCount / p.noData come from enrich() in render.
  function selReason(p, win) {
    if (p.bucket === 'review') {
      var own = p.codeCount != null ? p.codeCount : p.count;
      return (own >= 2 ? 'lỗi lặp' : 'lỗi') + ' “' + String(p.codeDesc || p.code || '').toLowerCase() + '” chưa hết (' + own + ' lần)' + (p.count > own ? '; cả KC còn ' + p.count + ' lần lỗi chưa hết' : '');
    }
    if (p.bucket === 'challenge') {
      var pre = p.prereq || [], nd = p.noData || [];
      return (pre.length ? 'KC tiên quyết θ ≥ 0: ' + pre.map(function (c) { return preName(p, c) + (nd.indexOf(c) >= 0 ? ' (chưa có dữ liệu, tạm lấy θ0 = ' + (p.theta0 || 0) + ')' : ''); }).join(', ') : 'không có KC tiên quyết') +
        '; δ − θ = ' + (-p.gap).toFixed(dp(-p.gap, win)) + ' > 0.5';
    }
    var inWin = p.gap >= win[0] && p.gap <= win[1];
    return ('θ − δ = ' + sgn2(p.gap, dp(p.gap, win)) + (inWin ? ' ∈ ' : ' ∉ ') + winText(win) + (inWin ? '' : ' — hết bài trong vùng, lấy bài gần nhất'))
      .replace('-0.00', '0.00').replace('+0.00', '0.00').replace(/-/g, '−');
  }
  function preName(p, c) { return '“' + ((p.preNames || {})[c] || c) + '”'; }
  // 08 one-line reason (mock stand-in for the LLM); mirrors reco_reason in mock/gen_mock.py.
  function recoReason(p, kcName, win) {
    if (p.bucket === 'review') {
      var own = p.codeCount != null ? p.codeCount : p.count;
      return 'Ôn “' + kcName + '”: lỗi “' + String(p.codeDesc || p.code || '').toLowerCase() + '” chưa hết (' + own + ' lần' +
        (p.count > own ? '; cả KC còn ' + p.count + ' lần lỗi chưa hết' : '') + ').';
    }
    if (p.bucket === 'challenge') {
      var pre = p.prereq || [], nd = p.noData || [];
      var names = function (cs) { return cs.map(function (c) { return preName(p, c); }).join(', '); };
      var ok = pre.filter(function (c) { return nd.indexOf(c) < 0; }), parts = [];
      if (ok.length) parts.push('đã vững KC tiên quyết ' + names(ok));
      if (nd.length) parts.push('KC tiên quyết ' + names(nd) + ' chưa có dữ liệu (tạm lấy θ0 = ' + (p.theta0 || 0) + ')');
      return 'Thử thách: ' + (parts.join('; ') || 'không có KC tiên quyết') + '; δ − θ = ' + viNum(-p.gap, false, dp(-p.gap, win)) + '.';
    }
    return 'Vừa sức: θ − δ = ' + viNum(p.gap, true, dp(p.gap, win)).replace(/^[+−](0\.0+)$/, '$1') + ', sát năng lực hiện tại.';
  }
  function lastCommitted(db, sid) {
    return db.session.filter(function (s) { return s.student_id === sid && s.status === 'committed'; })
      .map(function (s) { return s.held_on; }).sort().pop() || null;
  }
  // IA: last committed held_on + 7; rolled forward by weeks past today and past the latest list (approved or pending), so "Tạo gợi ý" can run.
  function defaultDate(last, today, lastList) {
    var d = last ? addDays(last, 7) : today;
    while (d < today || (lastList && d <= lastList)) d = addDays(d, 7);
    return d;
  }
  function normRatios(r) {
    var s = (+r.review || 0) + (+r.zpd || 0) + (+r.challenge || 0);
    return s > 0 ? { review: r.review / s, zpd: r.zpd / s, challenge: r.challenge / s } : null;
  }

  App.registerTab('recommend', { title: 'Gợi ý bài', render: render, selReason: selReason });

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, lk = ctx.lookup, M = ctx.data, db = M.db;
    var S = M.settings || {}, R = S.reco || {}, today = (M.meta || {}).today || '2026-10-21';
    var P = ctx.params, calc = ctx.calc;
    var threads = (M.checkpoints || {}).threads || [];

    var badThread = null, thread = null;
    if (P.thread) {
      thread = lk.thread(P.thread);
      if (!thread || thread.graph !== 'G4') { badThread = P.thread; thread = null; }
    }
    var st = thread ? (thread.state || (thread.state = {})) : null;
    var student = thread ? lk.student(thread.student_id != null ? thread.student_id : st.student_id)
      : (P.student ? (/^HS-/i.test(P.student) ? lk.studentByCode(P.student.toUpperCase()) : lk.student(+P.student)) : null);
    var sid = student ? student.id : null;
    var code = student ? lk.studentCode(student) : null;
    var last = sid != null ? lastCommitted(db, sid) : null;
    var pendingFor = function (s) {
      return threads.filter(function (t) { return t.graph === 'G4' && t.student_id === s && (t.status === 'awaiting_review' || t.status === 'running'); });
    };
    var myPending = sid != null ? pendingFor(sid) : [];
    var validDate = /^\d{4}-\d{2}-\d{2}$/.test(P.date || '') ? P.date : null;
    var lastList = sid == null ? null : db.recommendation.filter(function (r) { return r.student_id === sid; }).map(function (r) { return r.for_date; })
      .concat(myPending.map(function (t) { return t.state.for_date; })).sort().pop() || null;
    var forDate = st ? st.for_date : (validDate || defaultDate(last, today, lastList));
    var savedRatios = R.ratios || { review: 0.4, zpd: 0.5, challenge: 0.1 };
    var key = (thread ? thread.thread_id : 's' + sid + '|' + forDate) + '|' + ratioKey(savedRatios);
    if (mem.key !== key) {
      var base = st && st.ratios ? st.ratios : savedRatios;
      mem = { key: key, ratios: { review: Math.round(base.review * 100), zpd: Math.round(base.zpd * 100), challenge: Math.round(base.challenge * 100) }, kc: null, busy: false };
    }
    var win = R.zpd_window || [-0.5, 0.5];
    var rep = sid != null ? calc.replay(db, sid, forDate, S) : null;   // state as of for_date (same input select.py reads)
    var thetaOf = {}, stateOf = {};
    if (rep) rep.skill_state.forEach(function (s) { thetaOf[s.kc_id] = s.theta; stateOf[s.kc_id] = s; });
    // select.py's count sums every open code on the KC, and a prereq with no data passes as θ0; name both in the reason.
    var enrich = function (p) {
      var o = Object.assign({}, p);
      if (p.bucket === 'review') {
        var m = (rep ? rep.misconception_log : []).filter(function (x) { return x.kc_id === p.kc_id && x.code === p.code && x.resolved_at == null; })[0];
        o.codeCount = m ? m.count : p.count;
        o.codeDesc = (lk.errorCode(p.code) || {}).description;
      }
      if (p.bucket === 'challenge') {
        o.noData = (p.prereq || []).filter(function (c) { var k = lk.kcByCode(c); return !k || !stateOf[k.id]; });
        o.preNames = {}; (p.prereq || []).forEach(function (c) { var k = lk.kcByCode(c); if (k) o.preNames[c] = k.name; });
        o.theta0 = (S.elo || {}).theta0 || 0;
      }
      return o;
    };
    var kcName = function (id) { var k = lk.kc(id); return k ? k.name : '#' + id; };
    var kcCode = function (id) { var k = lk.kc(id); return k ? k.code : '#' + id; };
    // select.py reason strings name raw error/KC codes: show the description or KC name, the code only as a small mono label.
    var reasonEl = function (s) {
      var out = [], last = 0;
      s.replace(/(misconception )?([\w-]+[.-][\w.-]+)/g, function (m, mis, id, at) {
        var e = lk.errorCode(id), k = !e && lk.kcByCode(id);
        if (!e && !k) return m;
        out.push(s.slice(last, at), mis ? 'Lỗi ' : '', '“' + (e ? e.description : k.name) + '” ', h('span', { class: 'mono muted' }, id));
        last = at + m.length; return m;
      });
      out.push(s.slice(last));
      return out;
    };
    var ref = function (pid) { var p = lk.problem(pid); return p ? p.ref : '#' + pid; };
    var dd = function (d) { return fmt.date(d).slice(0, 5); };
    var sec = function (title, annot, extra) {
      return h('section', { class: 'section' }, h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? ui.annot(annot) : null), extra || null));
    };
    var whyBtn = function (label, content, cls) {
      var b = ui.why(content); b.textContent = label; b.className = cls || 'btn btn-ghost btn-sm';
      b.setAttribute('aria-label', label); b.removeAttribute('title'); return b;
    };

    /* ---------- page head ---------- */
    root.append(ui.pageHead({
      lead: 'Trước buổi sau: code chọn KC và bài theo luật (select.py); 08 chỉ kiểm tra bài có hợp KC và viết lý do 1 dòng; thầy/cô duyệt, bỏ hoặc thay. Không gì vào tutor.db trước khi duyệt.',
      annot: ['G4', 'agent:08', 'table:recommendation', 'cli:tutor recommend <hs> [--date]'],
      actions: student ? [ui.button('Xem hồ sơ ' + code, function () { ctx.nav('students', { student: sid }); }, { kind: 'secondary' })] : null
    }));
    if (badThread) root.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'Không tìm thấy thread G4 “' + badThread + '”. Chọn học sinh bên dưới.')));

    /* ---------- 1. Chọn ---------- */
    var sel = h('select', { 'aria-label': 'Học sinh' }, h('option', { value: '' }, '— Chọn học sinh —'),
      db.student.filter(function (s) { return !s.archived_at || s.id === sid; }).map(function (s) {
        return h('option', { value: String(s.id), selected: s.id === sid }, lk.studentCode(s) + ' · ' + s.name + ' · lớp ' + s.grade);
      }));
    sel.addEventListener('change', function () { ctx.nav('recommend', sel.value ? { student: sel.value } : {}); });
    var dateIn = h('input', { type: 'date', value: forDate, 'aria-label': 'Ngày buổi sau', disabled: !student });
    dateIn.addEventListener('change', function () { if (/^\d{4}-\d{2}-\d{2}$/.test(dateIn.value)) ctx.nav('recommend', { student: sid, date: dateIn.value }); });
    var approvedSame = sid != null && db.recommendation.some(function (r) { return r.student_id === sid && r.for_date === forDate; });
    var pendingSame = myPending.filter(function (t) { return t.state.for_date === forDate; })[0] || null;
    var nr = normRatios(mem.ratios);
    var runReason = !student ? 'chọn học sinh trước'
      : pendingSame ? 'đã có danh sách chờ duyệt cho ' + fmt.date(forDate) + ' (' + pendingSame.thread_id + ')'
        : approvedSame ? 'đã duyệt danh sách cho ' + fmt.date(forDate) + ' — UNIQUE(student_id, for_date, problem_id); chọn ngày khác'
          : !nr ? 'tỉ lệ đang là 0% — kéo ít nhất một thanh' : null;
    var runBtn = ui.button('Tạo gợi ý', function () { run(); }, {
      kind: 'primary', disabledReason: runReason,
      cli: 'tutor recommend ' + (code || '<hs>') + ' --date ' + forDate, privacy: code || null
    });
    var s1 = sec('Chọn học sinh và buổi', ['G4', 'cli:tutor recommend <hs> [--date]']);
    s1.append(h('div', { class: 'rc-pick' },
      h('label', { class: 'field' }, h('span', null, 'Học sinh'), sel, code ? h('span', { class: 'small muted' }, 'API nhận: ' + code + ' (tên chỉ lưu trên máy)') : null),
      h('label', { class: 'field' }, h('span', null, 'Ngày buổi sau ', ui.annot(['for_date'])), dateIn,
        h('span', { class: 'small muted' }, 'ngày buổi sau do thầy/cô chọn',
          student ? [' · ', st ? 'ngày của danh sách này' : validDate ? 'thầy/cô đã chọn'
            : 'mặc định: ' + (last ? 'buổi đã duyệt gần nhất ' + fmt.date(last) + ' + 7 ngày' : 'hôm nay (chưa có buổi đã duyệt)') + ', dời từng tuần nếu đã qua hoặc chưa sau danh sách gần nhất', ' ',
            ui.why(function () {
              return h('div', { class: 'stack' }, ui.kv([
                ['Buổi đã duyệt gần nhất', last ? fmt.date(last) : 'chưa có'], ['+ 7 ngày', last ? fmt.date(addDays(last, 7)) : '—'],
                ['Hôm nay', fmt.date(today)], ['Danh sách gần nhất (đã duyệt hoặc chờ duyệt)', lastList ? fmt.date(lastList) : 'chưa có'], ['Mặc định', fmt.date(defaultDate(last, today, lastList))]]),
                h('p', { class: 'small muted' }, 'Nếu +7 ngày đã qua, hoặc chưa sau danh sách gần nhất, thì cộng tiếp từng tuần.'));
            })] : null)),
      runBtn));
    if (student && !last) s1.append(h('div', { class: 'callout callout-info' }, h('p', null, 'Chưa có buổi đã duyệt: θ = 0 mọi KC (NFR2) — luật vẫn chạy.')));
    if (sid != null) ctx.queue.list({ graph: 'G1', student_id: sid });   // sets t.locked
    var openG1 = sid == null ? [] : threads.filter(function (t) { return t.graph === 'G1' && t.student_id === sid && t.status !== 'committed' && ctx.queue.heldOn(t) < forDate; });
    if (openG1.length) {
      s1.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'θ chưa gồm buổi chưa duyệt — select.py chỉ đọc buổi đã duyệt trong tutor.db. Duyệt trước để gợi ý dùng θ mới.'),
        h('div', { class: 'stack' }, openG1.map(function (t) {
          return h('div', { class: 'row small' }, ui.status(t.locked ? 'locked' : t.status), 'Buổi ' + dd(ctx.queue.heldOn(t)) + ' chưa duyệt — θ chưa gồm buổi này',
            ui.button(t.status === 'awaiting_review' ? 'Duyệt trước' : 'Mở buổi', function () { ctx.queue.open(t.thread_id); }, { kind: 'secondary', size: 'sm' }));
        }))));
    }
    if (!thread && myPending.length) {
      s1.append(h('div', { class: 'callout callout-warn' }, h('p', null, code + ' có ' + myPending.length + ' danh sách đang chờ duyệt trong checkpoints.db:'),
        h('div', { class: 'row' }, myPending.map(function (t) {
          return ui.button('Mở danh sách ' + fmt.date(t.state.for_date), function () { if (!ctx.queue.open(t.thread_id)) ctx.nav('recommend', { thread: t.thread_id }); }, { kind: 'secondary', size: 'sm' });
        }))));
    }
    root.append(s1);

    /* ---------- G4 strip (also the run animation target) ---------- */
    var stripBox = h('div', { class: 'stack' });
    var strip = null;
    if (student) {
      var sg = sec('Graph G4 · recommend_graph', ['G4', 'interrupt', 'file:checkpoints.db']);
      strip = stripFor(thread);
      var calls = thread ? (M.files.llm_log || []).filter(function (c) { return c.thread_id === thread.thread_id; }) : [];
      sg.append(strip, h('div', { class: 'row small' },
        thread ? [ui.status(thread.status), h('span', { class: 'mono' }, thread.thread_id), ui.store(thread.status === 'committed' ? 'db' : 'checkpoint'),
          calls.length ? ui.costChip(calls) : null,
          calls.length ? ui.button('Xem lời gọi 08', function () { ctx.nav('logs', { thread: thread.thread_id, agent: '08' }); }, { kind: 'ghost', size: 'sm' }) : null]
          : h('span', { class: 'muted' }, 'Chưa chạy cho ' + code + ' · ' + fmt.date(forDate) + '. Bấm “Tạo gợi ý”: đọc skill_state → select.py → 08 → DỪNG.'),
        ui.button('Xem nội dung gửi API', function () { ui.payloadModal('08', code); }, { kind: 'ghost', size: 'sm' })));
      if (thread && thread.status === 'running') sg.append(h('div', { class: 'callout callout-info' }, h('p', null, 'Đang chạy — kết quả sẽ hiện khi graph tới DỪNG.')));
      stripBox.append(sg);
    }
    root.append(stripBox);

    /* ---------- 2. Luật ---------- */
    var ruleSec = sec('Luật (code · select.py)', ['select.py', 'table:skill_state', 'table:misconception_log'], ui.prov('code'));
    var splitBox = h('div', { class: 'stack rc-split-box' });
    var sliders = h('div', { class: 'rc-sliders' }, ['review', 'zpd', 'challenge'].map(function (b) {
      var out = h('b', { class: 'num' }, mem.ratios[b] + '%');
      var inp = h('input', { type: 'range', min: 0, max: 100, step: 5, value: mem.ratios[b], 'aria-label': 'Tỉ lệ ' + BVI[b] });
      inp.addEventListener('input', function () { mem.ratios[b] = +inp.value; out.textContent = inp.value + '%'; drawSplit(); drawStep1(); });
      return h('label', { class: 'rc-slider' }, h('span', { class: 'spread' }, h('span', null, ui.chip(BVI[b], BKIND[b]), ' ', ui.annot([b])), out), inp);
    }));
    ruleSec.append(h('p', { class: 'small muted' }, 'Kéo để xem trước — chỉ code, không gọi LLM. “Tạo gợi ý” dùng tỉ lệ đang hiển thị; muốn đổi mặc định thì lưu ở Vận hành › Cài đặt (đang lưu: ' + pct(savedRatios.review) + ' / ' + pct(savedRatios.zpd) + ' / ' + pct(savedRatios.challenge) + ').'),
      sliders, splitBox,
      h('div', { class: 'rc-filters' },
        h('span', { class: 'small muted' }, 'Bộ lọc ứng viên:'),
        ['đúng KC', 'chưa làm trong ' + R.no_repeat_days + ' ngày', 'có rubric', 'có δ đã duyệt'].map(function (f) { return ui.chip('✓ ' + f, 'neutral'); })),
      h('div', { class: 'rc-filters' },
        h('span', { class: 'small muted' }, 'Vùng vừa sức:'), ui.chip('θ − δ ∈ ' + winText(win), 'ok'),
        h('span', { class: 'small muted' }, 'Trộn KC:'), ui.chip('≥ ' + R.min_kc_mix + ' KC', 'info'),
        h('span', { class: 'small muted' }, 'Số bài/buổi:'), ui.chip(String(R.n_problems), 'neutral')),
      h('div', { class: 'row' },
        ui.button('Đặt lại ' + pct(savedRatios.review).replace('%', '') + '/' + pct(savedRatios.zpd).replace('%', '') + '/' + pct(savedRatios.challenge).replace('%', ''), function () {
          mem.ratios = { review: Math.round(savedRatios.review * 100), zpd: Math.round(savedRatios.zpd * 100), challenge: Math.round(savedRatios.challenge * 100) };
          ctx.rerender();
        }, { kind: 'secondary', size: 'sm', disabledReason: ratioKey(mem.ratios) === ratioKey({ review: Math.round(savedRatios.review * 100), zpd: Math.round(savedRatios.zpd * 100), challenge: Math.round(savedRatios.challenge * 100) }) ? 'đang dùng đúng tỉ lệ đã lưu' : null }),
        ui.button('Mở Vận hành › Cài đặt', function () { ctx.nav('ops', { section: 'settings' }); }, { kind: 'ghost', size: 'sm' })));
    root.append(ruleSec);

    function drawSplit() {
      var r = normRatios(mem.ratios);
      var sum = mem.ratios.review + mem.ratios.zpd + mem.ratios.challenge;
      splitBox.replaceChildren();
      if (!r) { splitBox.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'Tổng 0% — chưa chia được bài.'))); return; }
      var n = R.n_problems, raw = [r.review, r.zpd, r.challenge], cnt = calc.largestRemainder(n, raw);
      splitBox.append(
        h('div', { class: 'row' }, h('span', { class: 'rc-split' }, n + ' bài = ' + cnt[0] + ' ôn · ' + cnt[1] + ' vừa sức · ' + cnt[2] + ' thử thách'),
          ui.why(function () {
            return h('div', { class: 'stack' },
              h('div', { class: 'mono small' }, ['review', 'zpd', 'challenge'].map(function (b, i) {
                var x = n * raw[i];
                return h('div', null, n + ' × ' + (+raw[i].toFixed(3)) + ' = ' + (+x.toFixed(2)) + ' → ' + cnt[i] + ' ' + BVI[b]);
              })),
              h('p', { class: 'small' }, 'Làm tròn theo phần dư lớn nhất (largest remainder): lấy phần nguyên, phần còn thiếu chia cho nhóm có phần lẻ lớn nhất. Đây là giả định của bản nháp — spec chưa chốt cách làm tròn.'),
              ui.prov('code', 'select.py'));
          }),
          sum !== 100 ? ui.chip('tổng ' + sum + '% — code chuẩn hoá về 100%', 'warn') : ui.chip('tổng 100% ✓', 'ok')));
    }
    drawSplit();

    /* ---------- no student: overview ---------- */
    if (!student) {
      var ov = sec('Chọn học sinh', ['table:recommendation', 'table:session']);
      ov.append(h('p', { class: 'small muted' }, 'Cần danh sách = chưa có danh sách đã duyệt cho ngày sau buổi đã duyệt gần nhất.'),
        ui.table({
          columns: [
            { label: 'Học sinh', render: function (s) { return h('span', { class: 'nowrap' }, h('b', { class: 'mono' }, lk.studentCode(s)), ' ', s.name); } },
            { label: 'Lớp', key: 'grade', align: 'center' },
            { label: 'Buổi đã duyệt gần nhất', render: function (s) { return fmt.date(lastCommitted(db, s.id)); } },
            { label: 'Danh sách gần nhất', render: function (s) {
              var ds = db.recommendation.filter(function (r) { return r.student_id === s.id; }).map(function (r) { return r.for_date; }).sort();
              var d = ds[ds.length - 1];
              return d ? fmt.date(d) + ' · ' + ds.filter(function (x) { return x === d; }).length + ' dòng' : '—';
            } },
            { label: 'Buổi sau', render: function (s) {
              var l = lastCommitted(db, s.id);
              var has = db.recommendation.some(function (r) { return r.student_id === s.id && (!l || r.for_date > l); });
              return has ? ui.chip('đã có danh sách', 'ok') : ui.chip('cần danh sách', 'warn');
            } },
            { label: 'Chờ duyệt', render: function (s) {
              var p = pendingFor(s.id);
              return p.length ? h('span', { class: 'row' }, ui.chip('G4', 'G4'), fmt.date(p[0].state.for_date),
                ui.button('Mở', function () { if (!ctx.queue.open(p[0].thread_id)) ctx.nav('recommend', { thread: p[0].thread_id }); }, { kind: 'secondary', size: 'sm' })) : '—';
            } },
            { label: '', render: function (s) { return ui.button('Chọn', function () { ctx.nav('recommend', { student: s.id }); }, { kind: 'ghost', size: 'sm' }); } }
          ],
          rows: db.student.filter(function (s) { return !s.archived_at; })
        }));
      root.append(ov);
      return;
    }

    /* ---------- 3. Bước 1 — Chọn KC ---------- */
    var s3 = sec('Bước 1 — Chọn KC (code)', ['select.py', 'table:skill_state', 'table:misconception_log', 'table:kc_prereq'], ui.prov('code'));
    var step1Box = h('div', { class: 'stack' });
    s3.append(step1Box);
    root.append(s3);
    function drawStep1() {
      step1Box.replaceChildren();
      var r = normRatios(mem.ratios);
      var same = st && st.kc_selection && st.kc_selection.length && st.ratios && ratioKey(r || {}) === ratioKey(st.ratios);
      var rows = [], preview = null;
      if (r) {
        preview = calc.selectRecommendations(db, Object.assign({}, S, { reco: Object.assign({}, R, { ratios: r }) }), sid, forDate);
        rows = preview.picks.map(function (p) { return { kc_id: p.kc_id, bucket: p.bucket, theta: p.theta, reason: selReason(enrich(p), win) }; });
      }
      if (same) {
        var fresh = rows;
        rows = st.kc_selection.map(function (x) {
          var f = fresh.filter(function (y) { return y.kc_id === x.kc_id && y.bucket === x.bucket; })[0];
          return f ? Object.assign({}, x, { reason: f.reason }) : x;
        });
        preview = null;
      }
      if (!same) step1Box.append(h('div', { class: 'callout callout-info' }, h('p', null,
        st && (st.kc_selection || []).length ? 'Xem trước với tỉ lệ đang kéo (' + ratioKey(mem.ratios) + ') — danh sách chờ duyệt bên dưới vẫn theo tỉ lệ lúc chạy (' + ratioKey({ review: pct(st.ratios.review), zpd: pct(st.ratios.zpd), challenge: pct(st.ratios.challenge) }) + ').'
          : 'Xem trước: select.py sẽ chọn các KC này cho ' + code + ' · buổi ' + fmt.date(forDate) + '. Chưa tạo thread, chưa gọi LLM.')));
      if (preview && preview.picks.length < R.n_problems) {
        step1Box.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'Chỉ chọn được ' + preview.picks.length + '/' + R.n_problems + ' bài: thiếu bài sẵn sàng.'),
          ui.button('Mở Ngân hàng bài', function () { ctx.nav('bank', {}); }, { kind: 'secondary', size: 'sm' })));
      }
      step1Box.append(ui.table({
        columns: [
          { label: 'KC', render: function (x) { return h('span', null, h('span', { class: 'mono' }, kcCode(x.kc_id)), h('br'), h('span', { class: 'small muted' }, kcName(x.kc_id))); } },
          { label: 'θ', align: 'right', render: function (x) {
            var s = stateOf[x.kc_id];
            return h('span', { class: 'nowrap num' }, fmt.signed(x.theta), ' ', ui.why(function () {
              return h('div', { class: 'stack' }, ui.kv([['KC', kcCode(x.kc_id)], ['θ (skill_state)', fmt.signed(x.theta)],
                ['Số lần làm', s ? s.n_attempts : 0], ['Đúng liên tiếp', s ? s.correct_streak : 0], ['Lần gần nhất', s ? fmt.date(s.last_seen) : 'chưa làm'],
                ['K · θ0', (S.elo || {}).K + ' · ' + (S.elo || {}).theta0]]),
                h('p', { class: 'small muted' }, 'θ = θ sau sự kiện cuối của KC (Elo, elo.py), tính lại từ các buổi đã duyệt trước ' + fmt.date(forDate) + '.'), ui.prov('code'));
            }));
          } },
          { label: 'Nhóm', render: function (x) { return ui.chip(BVI[x.bucket] || x.bucket, BKIND[x.bucket]); } },
          { label: 'Lý do bằng số', render: function (x) { return h('span', { class: 'small' }, x.reason ? reasonEl(String(x.reason)) : '—'); } }
        ],
        rows: rows, empty: 'Không chọn được KC nào — kiểm tra Ngân hàng bài.'
      }));
      var mix = {}; rows.forEach(function (x) { mix[x.kc_id] = 1; });
      var nk = Object.keys(mix).length;
      step1Box.append(h('div', { class: 'row small' }, nk >= R.min_kc_mix ? ui.chip(nk + ' KC ✓ (≥ ' + R.min_kc_mix + ')', 'ok') : ui.chip(nk + ' KC < ' + R.min_kc_mix, 'warn'),
        h('span', { class: 'muted' }, 'Mỗi bài một KC khác nhau nên luật “≥ 3 KC” luôn đạt khi chọn đủ bài.')));
    }
    drawStep1();

    /* ---------- thread views ---------- */
    if (thread && thread.status !== 'running') {
      var hasProps = (st.proposals || []).length > 0;
      if ((st.candidates || []).length) root.append(step2());
      if (thread.status === 'awaiting_review' && hasProps) root.append(step3());
      if (thread.status === 'committed') root.append(committedList());
      if (thread.status === 'awaiting_review') root.append(fileSec());
    }

    /* ---------- 6. Lịch sử ---------- */
    root.append(history());

    /* ===== helpers that need render scope ===== */
    function stripFor(t) {
      var g = ((M.meta || {}).graphs || {}).G4, nodes = g ? g.nodes.map(function (n) { return n.id; }) : [];
      var o = {};
      if (t) {
        var done = (t.checkpoints || []).map(function (c) { return c.node; });
        if (t.status === 'committed') o.done = nodes;
        else if (t.status === 'awaiting_review') { o.done = done.filter(function (n) { return n !== 'g4.review'; }); o.current = 'g4.review'; }
        else if (t.status === 'failed') { o.done = done; o.failed = t.current_node; }
        else { o.done = done; o.current = t.current_node; }
      }
      var el = ui.graphStrip('G4', o);
      ((t && t.checkpoints) || []).forEach(function (c) {
        var m = el.querySelector('[data-node="' + c.node + '"] .gn-meta'), tok = (c.tokens_in || 0) + (c.tokens_out || 0);
        if (m && (c.ms || tok)) m.textContent = fmt.ms(c.ms) + (tok ? ' · ' + fmt.int(tok) + ' tok' : '');
      });
      return el;
    }

    function items() {
      var out = [];
      var dec = st.decisions || (st.decisions = {});
      (st.proposals || []).forEach(function (p) {
        var d = dec[p.pid] || {};
        if (d.action === 'reject') out.push({ kind: 'prop', p: p, problem_id: p.problem_id, kc_id: p.kc_id, bucket: p.bucket, status: 'rejected' });
        else if (d.action === 'replace') {
          out.push({ kind: 'prop', p: p, problem_id: p.problem_id, kc_id: p.kc_id, bucket: p.bucket, status: 'rejected', replacedBy: d.replacement_problem_id });
          out.push({ kind: 'repl', p: p, problem_id: d.replacement_problem_id, kc_id: p.kc_id, bucket: p.bucket, status: 'approved' });
        } else out.push({ kind: 'prop', p: p, problem_id: p.problem_id, kc_id: p.kc_id, bucket: p.bucket, status: 'undecided' });
      });
      (st.added || (st.added = [])).forEach(function (a) { out.push({ kind: 'added', a: a, problem_id: a.problem_id, kc_id: a.kc_id, bucket: null, status: 'added' }); });
      return out;
    }
    // Rejected rows are written too, so they still block the same problem (UNIQUE student_id, for_date, problem_id).
    function inList(pid) { return items().some(function (it) { return it.problem_id === pid; }); }
    function lastDoneMap() {
      var m = {};
      db.session.forEach(function (s) {
        if (s.student_id !== sid || s.status !== 'committed' || s.held_on >= forDate) return;
        db.attempt.forEach(function (a) { if (a.session_id === s.id && (!m[a.problem_id] || s.held_on > m[a.problem_id])) m[a.problem_id] = s.held_on; });
      });
      return m;
    }
    function lastDoneText(d) {
      if (!d) return 'chưa làm';
      var days = Math.round((Date.parse(forDate) - Date.parse(d)) / 864e5);
      return fmt.date(d) + ' (' + days + ' ngày trước buổi)';
    }

    function step2() {
      var s = sec('Bước 2 — Ứng viên đã lọc', ['table:problem_kc', 'table:rubric', 'table:attempt', 'select.py'], ui.prov('code'));
      var kcs = (st.kc_selection || []).map(function (x) { return x.kc_id; });
      if (mem.kc == null || kcs.indexOf(mem.kc) < 0) mem.kc = kcs[0];
      var cands = st.candidates || [];
      var ex = {}; cands.forEach(function (c) { if (c.excluded) { var k = c.excluded.replace(/ \d{4}-\d{2}-\d{2}/, ''); ex[k] = (ex[k] || 0) + 1; } });
      var nEx = cands.filter(function (c) { return c.excluded; }).length;
      s.append(h('p', { class: 'small muted' }, cands.length + ' ứng viên cho ' + kcs.length + ' KC · ' + nEx + ' bị loại (' +
        Object.keys(ex).map(function (k) { return ex[k] + ' ' + k; }).join(' · ') + '). Sắp theo |θ − δ| tăng dần.'));
      var box = h('div', { class: 'stack' });
      var draw = function () {
        box.replaceChildren();
        var rows = cands.filter(function (c) { return c.kc_id === mem.kc; });
        var active = items().filter(function (it) { return it.status !== 'rejected'; }).map(function (it) { return it.problem_id; });
        var ok = rows.filter(function (c) { return !c.excluded; });
        box.append(h('p', null, h('b', { class: 'mono' }, kcCode(mem.kc)), ' ', kcName(mem.kc), h('span', { class: 'muted small' }, ' · θ = ' + fmt.signed(thetaOf[mem.kc] || 0) + ' · ' + ok.length + '/' + rows.length + ' bài qua bộ lọc')));
        if (!ok.length) box.append(h('div', { class: 'callout callout-warn' }, h('p', null, 'Thiếu bài sẵn sàng cho KC này — mở Ngân hàng bài.'),
          ui.button('Mở Ngân hàng bài', function () { ctx.nav('bank', { kc: kcCode(mem.kc) }); }, { kind: 'secondary', size: 'sm' })));
        box.append(ui.table({
          columns: [
            { label: 'Bài', render: function (c) { return h('span', { class: 'mono' + (c.excluded ? ' rc-strike' : '') }, ref(c.problem_id)); } },
            { label: 'δ', align: 'right', render: function (c) { var p = lk.problem(c.problem_id); return p && p.delta != null ? fmt.signed(p.delta) : '—'; } },
            { label: 'θ − δ', align: 'right', render: function (c) { return c.gap == null ? '—' : fmt.signed(c.gap, dp(c.gap, win)); } },
            { label: '|θ − δ|', align: 'right', render: function (c) { return c.gap == null ? '—' : fmt.num(Math.abs(c.gap), dp(c.gap, win)); } },
            { label: 'Lần làm gần nhất', render: function (c) { return c.last_done ? fmt.date(c.last_done) : 'chưa làm'; } },
            { label: 'Rubric', render: function (c) { return c.rubric_version ? 'v' + c.rubric_version : '—'; } },
            { label: 'Bộ lọc', render: function (c) {
              if (c.excluded) return h('span', { class: 'small' }, '✕ ' + c.excluded.replace(/(\d{4}-\d{2}-\d{2})/, function (d) { return fmt.date(d); }));
              return active.indexOf(c.problem_id) >= 0 ? ui.chip('đang trong danh sách', 'warn') : h('span', { class: 'small muted' }, '✓ qua bộ lọc');
            } }
          ],
          rows: rows,
          rowClass: function (c) { return c.excluded ? 'is-dim' : active.indexOf(c.problem_id) >= 0 ? 'is-sel' : null; },
          empty: 'Không có bài nào gắn KC này.'
        }));
      };
      s.append(ui.segmented(kcs.map(function (k) { return { id: k, label: kcCode(k) }; }), mem.kc, function (k) { mem.kc = k; draw(); }), box);
      draw();
      return s;
    }

    function cardFor(it, lastDone) {
      var p = lk.problem(it.problem_id) || {};
      var theta = thetaOf[it.kc_id] || 0;
      var gap = p.delta != null ? theta - p.delta : null;
      var rub = lk.rubricFor(it.problem_id);
      var rejected = it.status === 'rejected';
      var head = h('div', { class: 'spread' },
        h('div', { class: 'row' },
          h('span', { class: 'mono small muted' }, it.kind === 'prop' ? it.p.pid : it.kind === 'repl' ? it.p.pid + '′' : '+'),
          h('b', { class: 'mono strike' }, p.ref || '#' + it.problem_id),
          it.bucket ? ui.chip(BVI[it.bucket], BKIND[it.bucket]) : ui.chip('không thuộc nhóm', 'neutral')),
        rejected ? ui.status('rejected') : it.kind === 'repl' ? h('span', { class: 'row' }, ui.chip('GV thay', 'neutral'), ui.status('approved'))
          : it.kind === 'added' ? ui.status('added') : ui.chip('chưa quyết · mặc định duyệt', 'warn'));
      var stats = h('div', { class: 'rc-stats' },
        [['δ', p.delta != null ? fmt.signed(p.delta) : '—'], ['θ', fmt.signed(theta)], ['θ − δ', gap == null ? '—' : fmt.signed(gap, dp(gap, win))],
          ['Rubric', rub ? 'v' + rub.version : '—'], ['Lần làm gần nhất', lastDoneText(lastDone[it.problem_id])]].map(function (kv) {
          return h('div', null, h('span', { class: 'small muted' }, kv[0]), h('b', { class: 'num' }, kv[1]));
        }));
      var reason = it.kind === 'prop' ? h('p', { class: 'rc-reason' }, ui.prov('llm', '08'), ' ', it.p.reason)
        : it.kind === 'repl' ? h('p', { class: 'rc-reason' }, ui.prov('gv'), ' GV thay cho ' + ref(it.p.problem_id) + ' — cùng KC, cùng nhóm ' + BVI[it.bucket] + '.')
          : h('p', { class: 'rc-reason' }, ui.prov('gv'), ' GV tự chọn — không qua select.py, không có lý do 08.');
      var acts = h('div', { class: 'row' });
      if (it.kind === 'prop') {
        acts.append(whyBtn('Vì sao bài này?', function () { return whyContent(it, p, theta, gap, lastDone); }));
        if (it.status === 'rejected') {
          acts.append(ui.button(it.replacedBy ? 'Hoàn tác thay bài' : 'Giữ lại', function () {
            delete st.decisions[it.p.pid]; ctx.toast(it.p.pid + ' ' + p.ref + ': về trạng thái chưa quyết.', { kind: 'info' }); ctx.rerender();
          }, { kind: 'secondary', size: 'sm' }));
          if (it.replacedBy) acts.append(h('span', { class: 'small muted' }, 'thay bằng ' + ref(it.replacedBy)));
        } else {
          acts.append(ui.button('Bỏ', function () { reject(it); }, { kind: 'danger', size: 'sm' }),
            ui.button('Thay bằng bài khác', function () { replaceModal(it); }, { kind: 'secondary', size: 'sm' }));
        }
      } else if (it.kind === 'repl') {
        acts.append(ui.button('Hoàn tác thay bài', function () {
          delete st.decisions[it.p.pid]; ctx.toast('Đã trả lại ' + ref(it.p.problem_id) + ' cho ' + it.p.pid + '.', { kind: 'info' }); ctx.rerender();
        }, { kind: 'secondary', size: 'sm' }));
      } else {
        acts.append(ui.button('Bỏ khỏi danh sách', function () {
          var i = st.added.indexOf(it.a); if (i >= 0) st.added.splice(i, 1);
          ctx.toast('Đã bỏ ' + p.ref + ' (GV thêm) khỏi danh sách.', { kind: 'info' }); ctx.rerender();
        }, { kind: 'secondary', size: 'sm' }));
      }
      return h('article', { class: 'card rc-card ' + (rejected ? 'st-rejected' : 'st-pending'), 'data-pid': it.kind === 'prop' ? it.p.pid : null },
        head,
        h('div', { class: 'rc-kc row' }, ui.chip(kcCode(it.kc_id), 'neutral'), h('span', { class: 'small' }, kcName(it.kc_id)), it.kind === 'prop' ? fitChip(it.p) : null),
        it.kind === 'prop' && it.p.fit === false ? h('div', { class: 'callout callout-crit' }, h('p', { class: 'small' }, '08 thấy bài không hợp KC' + (it.p.fit_note ? ': ' + it.p.fit_note : '') + '. Không tự thay — thầy/cô chọn Bỏ, Thay hoặc giữ.')) : null,
        h('div', { class: 'rc-stmt strike' }, ui.latex(p.statement_latex || '', { block: true })),
        stats, reason, acts);
    }

    // 08 output: fit=false flags a picked problem as off-KC; mock proposals carry no flag, i.e. 08 passed all.
    function fitChip(pr) { return pr.fit === false ? ui.chip('08: không hợp KC', 'danger') : ui.chip('08: hợp KC ✓', 'ok'); }

    function whyContent(it, p, theta, gap, lastDone) {
      var mis = (rep ? rep.misconception_log : []).filter(function (m) { return m.kc_id === it.kc_id && m.resolved_at == null; });
      var ld = lastDone[it.problem_id];
      var rub = lk.rubricFor(it.problem_id);
      return h('div', { class: 'stack' },
        h('p', null, h('b', null, 'Nhóm ' + BVI[it.bucket] + ': '), BRULE[it.bucket]),
        ui.kv([['θ (KC ' + kcCode(it.kc_id) + ')', fmt.signed(theta)], ['δ (bài ' + p.ref + ')', p.delta != null ? fmt.signed(p.delta) : '—'],
          ['θ − δ', gap == null ? '—' : fmt.signed(gap, dp(gap, win))], ['|θ − δ|', gap == null ? '—' : fmt.num(Math.abs(gap), dp(gap, win))],
          ['Lỗi chưa hết', mis.length ? mis.map(function (m) { return m.code + ' × ' + m.count; }).join(', ') : 'không có'],
          ['Lần làm gần nhất', lastDoneText(ld)]]),
        h('div', { class: 'rc-filters' }, ui.chip('✓ đúng KC', 'ok'),
          ui.chip((ld && (Date.parse(forDate) - Date.parse(ld)) / 864e5 < R.no_repeat_days ? '✕ ' : '✓ ') + 'không làm trong ' + R.no_repeat_days + ' ngày', 'ok'),
          ui.chip(rub ? '✓ rubric v' + rub.version : '✕ chưa có rubric', rub ? 'ok' : 'danger'),
          ui.chip(p.difficulty_approved_at ? '✓ δ đã duyệt ' + fmt.date(p.difficulty_approved_at) : '✕ δ chưa duyệt', p.difficulty_approved_at ? 'ok' : 'danger')),
        h('p', { class: 'small' }, ui.prov('llm', '08'), ' ', it.p.reason),
        h('p', { class: 'small' }, fitChip(it.p), ' 08 kiểm tra bài có hợp KC; thấy không hợp thì gắn cờ cho thầy/cô quyết, không tự thay bài.'),
        h('p', { class: 'small muted' }, 'Số do code tính (select.py, elo.py); 08 chỉ viết câu lý do.'));
    }

    function kcMix() {
      var m = {};
      items().forEach(function (it) { if (it.status !== 'rejected') m[it.kc_id] = 1; });
      return Object.keys(m).length;
    }
    function reject(it) {
      st.decisions[it.p.pid] = { action: 'reject', at: nowISO(today) };
      var n = kcMix();
      if (n < R.min_kc_mix) ctx.toast('Chỉ còn ' + n + ' KC < ' + R.min_kc_mix + ' — luật trộn KC không đạt; thêm hoặc thay bài.', { kind: 'warn' });
      else ctx.toast(it.p.pid + ' ' + ref(it.problem_id) + ': bỏ (vẫn ghi dòng rejected để đo độ chính xác). Còn ' + n + ' KC.', { kind: 'info' });
      ctx.rerender();
    }

    function replaceModal(it) {
      var opts = (st.candidates || []).filter(function (c) { return c.kc_id === it.kc_id && !c.excluded && !inList(c.problem_id); });
      ctx.modal({
        title: 'Thay ' + ref(it.problem_id) + ' · KC ' + kcCode(it.kc_id), wide: true,
        body: function (el, api) {
          el.append(h('p', { class: 'small muted' }, 'Chỉ các ứng viên Bước 2 của cùng KC, đã qua bộ lọc và chưa có trong danh sách. Bài mới giữ nhóm “' + BVI[it.bucket] + '”.'));
          if (!opts.length) {
            el.append(ui.empty('Không còn ứng viên dùng được cho KC này.', ui.button('Mở Ngân hàng bài', function () { ctx.nav('bank', { kc: kcCode(it.kc_id) }); }, { kind: 'secondary', size: 'sm' })));
            return;
          }
          el.append(h('div', { class: 'stack' }, opts.map(function (c) {
            var p = lk.problem(c.problem_id) || {};
            return h('div', { class: 'card rc-opt' },
              h('div', { class: 'spread' }, h('b', { class: 'mono' }, p.ref),
                h('span', { class: 'small muted num' }, 'δ ' + fmt.signed(p.delta) + ' · θ − δ ' + fmt.signed(c.gap, dp(c.gap, win)) + ' · ' + (c.last_done ? 'làm ' + fmt.date(c.last_done) : 'chưa làm') + ' · rubric v' + c.rubric_version)),
              h('div', { class: 'rc-stmt' }, ui.latex(p.statement_latex || '', { block: true })),
              ui.button('Chọn ' + p.ref, function () {
                st.decisions[it.p.pid] = { action: 'replace', replacement_problem_id: c.problem_id, at: nowISO(today) };
                api.close();
                ctx.toast(it.p.pid + ': thay ' + ref(it.problem_id) + ' bằng ' + p.ref + ' (cùng KC, nhóm ' + BVI[it.bucket] + ').', { kind: 'ok' });
                ctx.rerender();
              }, { kind: 'primary', size: 'sm' }));
          })));
        },
        actions: [{ label: 'Đóng' }]
      });
    }

    function addModal() {
      var lastDone = lastDoneMap();
      var pool = db.problem.filter(function (p) { return p.lop === student.grade && lk.problemStatus(p) === 'ready'; });
      var kcsOf = function (pid) {
        var o = []; db.problem_kc.forEach(function (r) { if (r.problem_id === pid && o.indexOf(r.kc_id) < 0) o.push(r.kc_id); }); return o;
      };
      ctx.modal({
        title: 'Thêm bài tự chọn cho ' + code, wide: true,
        body: function (el, api) {
          var q = h('input', { type: 'search', class: 'rc-search', placeholder: 'Tìm theo mã bài hoặc nội dung đề, ví dụ 9DS-PT2 hoặc “tham số”', 'aria-label': 'Tìm bài' });
          var list = h('div', { class: 'stack' });
          var draw = function () {
            var s = q.value.trim().toLowerCase();
            var hits = pool.filter(function (p) { return !inList(p.id) && (!s || p.ref.toLowerCase().indexOf(s) >= 0 || String(p.statement_latex).toLowerCase().indexOf(s) >= 0); });
            list.replaceChildren(h('p', { class: 'small muted' }, hits.length + ' bài sẵn sàng (có KC, rubric, δ đã duyệt) · lớp ' + student.grade + (hits.length > 8 ? ' · hiện 8 bài đầu' : '')));
            if (!hits.length) list.append(ui.empty('Không có bài nào khớp.'));
            hits.slice(0, 8).forEach(function (p) {
              var ks = kcsOf(p.id), ld = lastDone[p.id];
              var recent = ld && (Date.parse(forDate) - Date.parse(ld)) / 864e5 < R.no_repeat_days;
              list.append(h('div', { class: 'card rc-opt' },
                h('div', { class: 'spread' }, h('b', { class: 'mono' }, p.ref),
                  h('span', { class: 'row small' }, ks.map(function (k) { return ui.chip(kcCode(k), 'neutral'); }), h('span', { class: 'num muted' }, 'δ ' + fmt.signed(p.delta)),
                    recent ? ui.chip('đã làm ' + fmt.date(ld) + ' (< ' + R.no_repeat_days + ' ngày)', 'warn') : null)),
                h('div', { class: 'rc-stmt' }, ui.latex(p.statement_latex || '', { block: true })),
                ui.button('Thêm ' + p.ref, function () {
                  st.added.push({ problem_id: p.id, kc_id: ks[0] });
                  api.close();
                  ctx.toast('Đã thêm ' + p.ref + ' — trạng thái “added”, không thuộc nhóm nào.', { kind: 'ok' });
                  ctx.rerender();
                }, { kind: 'primary', size: 'sm' })));
            });
            ctx.tex(list);
          };
          q.addEventListener('input', draw);
          el.append(q, list);
          draw();
        },
        actions: [{ label: 'Đóng' }]
      });
    }

    function mdText() {
      var lines = ['# Gợi ý bài · ' + code + ' · buổi ' + fmt.date(forDate), '',
        '> Bản chờ duyệt — thread ' + thread.thread_id + ' (data/checkpoints.db). Thầy/cô duyệt trên màn hình Gợi ý bài; app xuất file này vào data/out/ sau khi duyệt.', '',
        '| # | bài | KC | nhóm | trạng thái | lý do |', '|---|---|---|---|---|---|'];
      items().forEach(function (it, i) {
        var stt = ST_MD[it.status] || it.status;
        var why = it.kind === 'prop' ? it.p.reason : it.kind === 'repl' ? 'GV thay cho ' + ref(it.p.problem_id) : '';
        lines.push('| ' + (i + 1) + ' | ' + ref(it.problem_id) + ' | ' + kcCode(it.kc_id) + ' | ' + (BVI[it.bucket] || NO_BUCKET) + ' | ' + stt + ' | ' + why + ' |');
      });
      return lines.join('\n');
    }

    function step3() {
      var s = sec('Bước 3 — Danh sách đề xuất', ['agent:08', 'file:checkpoints.db', 'interrupt'], h('span', { class: 'row' }, ui.store('checkpoint'), ui.chip('chưa ghi', 'warn')));
      var lastDone = lastDoneMap();
      var its = items();
      s.append(h('p', { class: 'small muted' }, (st.proposals || []).length + ' bài do code chọn; 08 chỉ kiểm tra và viết lý do 1 dòng. Bài chưa quyết sẽ được duyệt khi bấm “Duyệt danh sách”.'),
        h('div', { class: 'row' }, ui.button('Thêm bài tự chọn', addModal, { kind: 'secondary' })),
        h('div', { class: 'rc-cards' }, its.map(function (it) { return cardFor(it, lastDone); })));
      var n = kcMix();
      var cnt = { approved: 0, rejected: 0, added: 0 };
      its.forEach(function (it) { cnt[it.status === 'undecided' ? 'approved' : it.status] += 1; });
      s.append(h('div', { class: 'rc-foot' },
        h('div', { class: 'row' },
          n >= R.min_kc_mix ? ui.chip(n + ' KC ✓ (≥ ' + R.min_kc_mix + ')', 'ok') : ui.chip(n + ' KC < ' + R.min_kc_mix + ' — luật trộn KC không đạt', 'danger'),
          h('span', { class: 'small' }, 'Sẽ ghi ' + its.length + ' dòng: ' + cnt.approved + ' duyệt · ' + cnt.rejected + ' bỏ · ' + cnt.added + ' GV thêm')),
        h('div', { class: 'row' },
          ui.button('Duyệt danh sách', approve, { kind: 'primary', cli: 'tutor review ' + thread.thread_id }))));
      return s;
    }

    function fileSec() {
      var s = sec('File .md (xuất sau khi duyệt)', ['file:data/out/', 'cli:tutor review <id>']);
      s.append(h('div', { class: 'row' }, h('span', { class: 'chip st-file mono' }, st.out_path || '—'), ui.store('file')),
        h('p', { class: 'small muted' }, 'Thầy/cô duyệt ngay trên màn hình này (bỏ / thay / thêm bài). Bấm “Duyệt danh sách” thì app ghi tutor.db rồi xuất file .md vào data/out/; dưới đây là bản xem trước. Lệnh CLI tương đương: tutor review <id>.'),
        h('div', { class: 'row' },
          ui.button('Xem file .md', function () {
            ctx.modal({ title: st.out_path, wide: true, body: h('pre', { class: 'code' }, mdText()), actions: [{ label: 'Đóng' }] });
          }, { kind: 'secondary' }),
          ui.button('Tải .md', function () { ui.download(String(st.out_path).split('/').pop(), mdText()); }, { kind: 'ghost', noAutoclick: true })));
      return s;
    }

    function approve() {
      if (thread.status !== 'awaiting_review') return;
      var its = items(), at = nowISO(today);
      var nextId = db.recommendation.reduce(function (m, r) { return Math.max(m, r.id || 0); }, 0);
      var rows = its.map(function (it) {
        var base = { student_id: sid, for_date: forDate, problem_id: it.problem_id, kc_id: it.kc_id, reviewed_at: at, id: ++nextId };
        if (it.kind === 'prop') return Object.assign(base, { bucket: it.bucket, reason: it.p.reason, status: it.status === 'rejected' ? 'rejected' : 'approved' });
        if (it.kind === 'repl') return Object.assign(base, { bucket: it.bucket, reason: 'GV thay cho ' + ref(it.p.problem_id), status: 'approved' });
        return Object.assign(base, { bucket: null, reason: null, status: 'added' });
      });
      Array.prototype.push.apply(db.recommendation, rows);
      var c = { approved: 0, rejected: 0, added: 0 };
      rows.forEach(function (r) { c[r.status] += 1; });
      var files = M.files || (M.files = {});
      (files.out || (files.out = [])).push({ path: st.out_path, kind: 'recommend', student_id: sid, key: forDate, text: mdText().replace(/^> Bản chờ duyệt.*\n\n/m, '') });
      (thread.checkpoints || (thread.checkpoints = [])).push({ node: 'g4.commit', at: at, ms: 40, tokens_in: 0, tokens_out: 0 });
      ctx.receipt('Duyệt danh sách gợi ý ' + code + ' · ' + fmt.date(forDate), [['recommendation', rows.length], ['(' + c.approved + ' approved, ' + c.rejected + ' rejected, ' + c.added + ' added)', 'cập nhật']], { graph: 'G4' });
      ctx.queue.resolve(thread.thread_id);
      ctx.rerender();
    }

    function groupTable(rows) {
      return ui.table({
        columns: [
          { label: '#', render: function (r) { return rows.indexOf(r) + 1; }, align: 'right' },
          { label: 'Bài', render: function (r) { return h('span', { class: 'mono' }, ref(r.problem_id)); } },
          { label: 'KC', render: function (r) { return h('span', { class: 'small' }, h('span', { class: 'mono' }, kcCode(r.kc_id)), ' ', kcName(r.kc_id)); } },
          { label: 'Nhóm', render: function (r) { return r.bucket ? ui.chip(BVI[r.bucket], BKIND[r.bucket]) : h('span', { class: 'small muted' }, NO_BUCKET); } },
          { label: 'Trạng thái', render: function (r) { return ui.status(r.status); } },
          { label: 'Lý do', render: function (r) { return h('span', { class: 'small' }, r.reason || '—'); } }
        ],
        rows: rows, rowClass: function (r) { return r.status === 'rejected' ? 'is-dim' : null; }
      });
    }

    function committedList() {
      var rows = db.recommendation.filter(function (r) { return r.student_id === sid && r.for_date === forDate; });
      var s = sec('Danh sách đã ghi · buổi ' + fmt.date(forDate), ['table:recommendation', 'file:tutor.db'], ui.store('db'));
      var cp = (thread.checkpoints || []).filter(function (c) { return c.node === 'g4.commit'; })[0];
      s.append(h('div', { class: 'callout callout-ok' }, h('p', null, 'Đã duyệt' + (cp ? ' lúc ' + fmt.dt(cp.at) : '') + ' — chỉ đọc. Muốn đổi: tạo danh sách cho ngày khác.')));
      s.classList.add('st-db');
      s.append(groupTable(rows));
      return s;
    }

    function history() {
      var s = sec('Lịch sử đã duyệt · ' + code, ['table:recommendation', 'file:tutor.db'], ui.store('db'));
      var rows = db.recommendation.filter(function (r) { return r.student_id === sid; });
      var dates = rows.map(function (r) { return r.for_date; }).filter(function (d, i, a) { return a.indexOf(d) === i; }).sort().reverse();
      if (!dates.length) { s.append(ui.empty('Chưa có danh sách nào đã duyệt cho ' + code + '.')); return s; }
      dates.forEach(function (d) {
        var g = rows.filter(function (r) { return r.for_date === d; });
        var c = { approved: 0, rejected: 0, added: 0 }; g.forEach(function (r) { c[r.status] = (c[r.status] || 0) + 1; });
        var f = ((M.files || {}).out || []).filter(function (o) { return o.kind === 'recommend' && o.student_id === sid && o.key === d; })[0];
        s.append(h('div', { class: 'rc-hist st-db' },
          h('div', { class: 'spread' },
            h('div', { class: 'row' }, h('b', null, 'Buổi ' + fmt.date(d)),
              h('span', { class: 'small muted' }, g.length + ' dòng · ' + c.approved + ' duyệt · ' + c.rejected + ' bỏ · ' + c.added + ' GV thêm · duyệt ' + fmt.dt(g[0].reviewed_at))),
            f ? h('div', { class: 'row' }, h('span', { class: 'chip st-file mono' }, f.path),
              ui.button('Xem .md ' + dd(d), function () { ctx.modal({ title: f.path, wide: true, body: h('pre', { class: 'code' }, f.text), actions: [{ label: 'Đóng' }] }); }, { kind: 'ghost', size: 'sm' })) : null),
          groupTable(g)));
      });
      return s;
    }

    function run() {
      if (mem.busy || runReason) return;
      var r = normRatios(mem.ratios);
      var cfg = Object.assign({}, S, { reco: Object.assign({}, R, { ratios: r }) });
      var res = calc.selectRecommendations(db, cfg, sid, forDate);
      var picks = res.picks.map(enrich);
      var id = 'g4-' + code.toLowerCase().replace('-', '') + '-' + forDate.replace(/-/g, '');
      if (lk.thread(id)) { ctx.toast('Thread ' + id + ' đã tồn tại.', { kind: 'warn' }); return; }
      // shortcut: token counts copied from the latest mock 08 call; a real run logs its own call.
      var log = (M.files || {}).llm_log || [];
      var tplCall = log.filter(function (c) { return c.agent === '08'; }).sort(function (a, b) { return a.ts < b.ts ? 1 : -1; })[0];
      var at = nowISO(today);
      var call = tplCall ? Object.assign({}, tplCall, { ts: at, thread_id: id, student_code: code, output_summary: res.picks.length + ' lý do 1 dòng · ' + res.picks.length + '/' + res.picks.length + ' bài hợp KC · 0 bài ngoài danh sách' }) : null;
      var t = {
        thread_id: id, graph: 'G4', subject: code + ' · gợi ý cho ' + fmt.date(forDate), student_id: sid, session_id: null, started_at: at,
        status: 'running', current_node: 'g4.read_state', interrupted_at: null, error: null, demo_run: null, checkpoints: [],
        state: {
          student_id: sid, for_date: forDate, ratios: r,
          kc_selection: picks.map(function (p) { return { kc_id: p.kc_id, bucket: p.bucket, theta: p.theta, reason: selReason(p, win) }; }),
          candidates: res.candidates,
          proposals: picks.map(function (p, i) {
            return { pid: 'r' + (i + 1), kind: 'recommendation', problem_id: p.problem_id, kc_id: p.kc_id, bucket: p.bucket, fit: true,
              reason: recoReason(p, kcName(p.kc_id), win), theta: p.theta, delta: p.delta, last_done: p.last_done, rubric_version: p.rubric_version };
          }),
          decisions: {}, added: [], out_path: 'data/out/recommend-' + code + '-' + forDate + '.md'
        }
      };
      mem.busy = true;
      var b = runBtn.button || runBtn; b.disabled = true; b.textContent = 'Đang chạy…';
      ctx.queue.add(t);
      var steps = [{ node: 'g4.read_state', ms: 30 }, { node: 'g4.select', ms: 70 },
        { node: 'g4.08_recommender', ms: call ? call.ms : 0, tokens_in: call ? call.tokens_in : 0, tokens_out: call ? call.tokens_out : 0 }, { node: 'g4.review' }];
      ctx.toast('G4 chạy cho ' + code + ' · buổi ' + fmt.date(forDate) + ': select.py chọn bài, 08 viết lý do.', { kind: 'info' });
      ui.animateGraph(strip, steps, { stepMs: 420 }).then(function () {
        steps.forEach(function (s) { t.checkpoints.push({ node: s.node, at: nowISO(today), ms: s.ms || 0, tokens_in: s.tokens_in || 0, tokens_out: s.tokens_out || 0 }); });
        if (call) log.push(call);
        t.status = 'awaiting_review'; t.current_node = 'g4.review'; t.interrupted_at = 'g4.review';
        mem.busy = false;
        ctx.refresh();
        ctx.toast('Sẵn sàng duyệt: ' + res.picks.length + ' bài · ' + res.kc_mix + ' KC · ' + code + ' ' + dd(forDate) + ' (file .md xuất sau khi duyệt).', { kind: 'ok' });
        if (strip && strip.isConnected) ctx.nav('recommend', { thread: id });
      });
    }
  }
})();
