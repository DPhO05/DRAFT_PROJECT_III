/* Danh mục (FR9): KC, tiên quyết, mã lỗi — bảng kc, kc_prereq, error_code do GV giữ. */
(function () {
  'use strict';
  var CAT = { computational: 'Tính toán', conceptual: 'Khái niệm', notational: 'Ký hiệu', presentation: 'Trình bày', other: 'Khác' };
  var SUBS = [{ id: 'kc', label: 'Kỹ năng (KC)' }, { id: 'prereq', label: 'Tiên quyết' }, { id: 'codes', label: 'Mã lỗi' }];
  var DEFAULT_KC = '9DS-PT2-02';
  var LOCK = '<svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="5.5" width="8" height="5.5" rx="1" fill="currentColor"/><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';
  // Kept across navigations: last sub-tab, selected KC, filters, prompt banner.
  var S = { sub: 'kc', kc: null, lop: '', q: '', edit: false, pick: null, banner: null };

  function fold(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd'); }
  function csvCell(v) { var s = v == null ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function csv(header, rows) { return '﻿' + [header].concat(rows).map(function (r) { return r.map(csvCell).join(','); }).join('\n') + '\n'; }
  function pad2(n) { return String(n).padStart(2, '0'); }

  App.registerTab('catalog', { title: 'Danh mục', render: render });

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, fmt = ui.fmt, L = ctx.lookup, M = ctx.data, db = M.db;
    var p = ctx.params;
    if (SUBS.some(function (s) { return s.id === p.tab; })) S.sub = p.tab;
    var pk = p.kc && (L.kcByCode(p.kc) || L.kc(p.kc));
    if (pk && pk.parent_id != null) { S.kc = pk.id; S.edit = false; S.pick = null; if (!p.tab) S.sub = 'kc'; }
    if (p.code && L.errorCode(p.code)) S.sub = 'codes';
    if (S.kc == null || !L.kc(S.kc)) { var d0 = L.kcByCode(DEFAULT_KC) || leaves()[0]; S.kc = d0 ? d0.id : null; }

    function groups() { return db.kc.filter(function (k) { return k.parent_id == null; }); }
    function leaves() { return db.kc.filter(function (k) { return k.parent_id != null; }); }
    function leavesOf(gid) { return db.kc.filter(function (k) { return k.parent_id === gid; }); }
    function code(id) { var k = L.kc(id); return k ? k.code : '#' + id; }
    function nowISO() { var n = new Date(); return M.meta.today + 'T' + pad2(n.getHours()) + ':' + pad2(n.getMinutes()) + ':' + pad2(n.getSeconds()) + 'Z'; }
    function field(label, input, hint) { return h('label', { class: 'field' }, h('span', null, label), input, hint ? h('span', { class: 'small muted' }, hint) : null); }
    function errEl() { return h('p', { class: 'cat-err', role: 'alert' }); }
    function prompt03() { return (M.ui.prompt_versions || []).find(function (v) { return v.agent === '03'; }) || null; }

    function embedChip(k, short) {
      if (!k.embed_model) return ui.chip(short ? 'chưa embedding' : 'chưa có — chạy 06 (G2)', 'warn');
      if (k.embedding_stale) return ui.chip(short ? 'embedding cũ' : 'cũ — cần chạy lại 06', 'warn');
      return short ? null : ui.chip(k.embed_model, 'ok');
    }
    function dag() {
      // Kahn: peel KCs with no remaining prerequisite; leftovers = a cycle.
      var nodes = new Set(), indeg = new Map(), out = new Map();
      db.kc_prereq.forEach(function (e) {
        nodes.add(e.kc_id); nodes.add(e.prereq_id);
        indeg.set(e.kc_id, (indeg.get(e.kc_id) || 0) + 1);
        (out.get(e.prereq_id) || out.set(e.prereq_id, []).get(e.prereq_id)).push(e.kc_id);
      });
      var q = Array.from(nodes).filter(function (n) { return !indeg.get(n); }), seen = 0;
      while (q.length) { var n = q.shift(); seen++; (out.get(n) || []).forEach(function (m) { indeg.set(m, indeg.get(m) - 1); if (!indeg.get(m)) q.push(m); }); }
      return { ok: seen === nodes.size, nodes: nodes.size, edges: db.kc_prereq.length };
    }
    function findPath(from, to) {
      // DFS along "cần biết trước" edges; returns [from, …, to] or null.
      var seen = new Set();
      function go(u, path) {
        if (u === to) return path;
        if (seen.has(u)) return null; seen.add(u);
        var nx = db.kc_prereq.filter(function (e) { return e.kc_id === u; });
        for (var i = 0; i < nx.length; i++) { var r = go(nx[i].prereq_id, path.concat([nx[i].prereq_id])); if (r) return r; }
        return null;
      }
      return go(from, [from]);
    }
    function codeStats() {
      var att = new Map(db.attempt.map(function (a) { return [a.id, a]; })), ses = new Map(db.session.map(function (s) { return [s.id, s]; }));
      var cur = new Set(ctx.calc.currentMistakes(db).map(function (m) { return m.id; })), out = {};
      var get = function (c) { return out[c] || (out[c] = { months: {}, ids: [], proposed: 0, rejected: 0 }); };
      db.mistake.forEach(function (m) {
        var a = att.get(m.attempt_id), s = a && ses.get(a.session_id);
        if (cur.has(m.id) && s) { var o = get(m.code), mo = String(s.held_on).slice(0, 7); o.months[mo] = (o.months[mo] || 0) + 1; o.ids.push(m.id); }
        if (m.llm_json) { var o2 = get(m.llm_json.code || m.code); o2.proposed++; if (m.status === 'rejected') o2.rejected++; }
      });
      return out;
    }
    function bumpPrompt() {
      var pv = prompt03(); if (!pv) return;
      var from = pv.version, n = +((/-v(\d+)$/.exec(from) || [0, 0])[1]) + 1;
      pv.version = '03-v' + n; pv.changed_at = nowISO();
      pv.stability = { status: 'not_run', runs: 0, pass3: false, changed_criteria_pct: 0 };
      S.banner = { from: S.banner ? S.banner.from : from, to: pv.version };
    }

    /* ---------- page ---------- */
    var exportRow = h('div', { class: 'row', 'data-no-autoclick': '' }, h('span', { class: 'small muted' }, 'Xuất CSV'),
      ui.button('kc.csv', function () {
        var rows = db.kc.map(function (k) { var g = k.parent_id != null ? L.kc(k.parent_id) : null; return [k.code, k.name, k.description, g ? g.code : '', k.lop]; });
        ui.download('kc.csv', csv(['code', 'name', 'description', 'parent_code', 'lop'], rows));
      }, { size: 'sm', noAutoclick: true, title: 'Xuất bảng kc' }),
      ui.button('kc_prereq.csv', function () {
        ui.download('kc_prereq.csv', csv(['kc_code', 'prereq_code'], db.kc_prereq.map(function (e) { return [code(e.kc_id), code(e.prereq_id)]; })));
      }, { size: 'sm', noAutoclick: true, title: 'Xuất bảng kc_prereq' }),
      ui.button('error_code.csv', function () {
        ui.download('error_code.csv', csv(['code', 'category', 'description', 'example', 'active'], db.error_code.map(function (e) { return [e.code, e.category, e.description, e.example, e.active]; })));
      }, { size: 'sm', noAutoclick: true, title: 'Xuất bảng error_code' }));

    root.append(ui.pageHead({
      lead: 'Danh mục thầy/cô tự giữ: kỹ năng (KC), quan hệ tiên quyết, mã lỗi kèm ví dụ. Agent đọc thẳng từ đây: 06 Tagger (mô tả KC → embedding, gợi ý top-5), 03 Diagnoser (mã lỗi + ví dụ trong prompt), select.py (tiên quyết khi chọn bài thử thách).',
      annot: ['table:kc', 'table:kc_prereq', 'table:error_code', 'agent:06', 'agent:03'],
      actions: [ui.button('Nhập từ CSV', openImport, { kind: 'primary' }), exportRow]
    }));
    root.append(h('div', { class: 'callout callout-warn' }, h('p', null, h('b', null, 'Cách nhập chưa chốt — đề xuất CSV/YAML + lệnh import (tài liệu thiết kế §11.4).'),
      ' Bản nháp đọc data/inbox/bank/kc.csv và kc_prereq.csv (UTF-8 BOM). Sửa trực tiếp trên màn hình này ghi thẳng vào tutor.db (bảng do GV nhập, không qua graph).')));
    var body = h('div', { class: 'stack' });
    root.append(body);
    drawAll();
    if (p.code && L.errorCode(p.code)) openCode(p.code);

    function drawAll() {
      var lv = leaves(), d = dag(), ec = db.error_code, noEx = ec.filter(function (e) { return !e.example; }).length;
      var kpi = function (label, value, sub) { return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label), h('span', { class: 'kpi-value' }, value), h('span', { class: 'kpi-sub' }, sub)); };
      body.replaceChildren(
        h('div', { class: 'grid cat-kpis' },
          kpi('Kỹ năng (KC)', String(lv.length), 'trong ' + groups().length + ' nhóm · lớp 8 và 9'),
          kpi('Quan hệ tiên quyết', String(d.edges), d.ok ? 'không có vòng ✓' : 'CÓ VÒNG — cần sửa'),
          kpi('Mã lỗi', String(ec.length), ec.filter(function (e) { return e.active; }).length + ' đang bật · 5 nhóm'),
          kpi('Mã chưa có ví dụ', noEx + '/' + ec.length, 'ví dụ giúp 03 chính xác hơn')),
        ui.segmented(SUBS, S.sub, function (id) { S.sub = id; drawAll(); }),
        S.sub === 'prereq' ? prereqView() : S.sub === 'codes' ? codesView() : kcView());
      ctx.tex(body);
    }

    /* ---------- Kỹ năng (KC) ---------- */
    function kcView() {
      var tree = h('div', { class: 'cat-tree' }), detail = h('div', { class: 'stack' });
      var lopSel = h('select', { 'aria-label': 'Lọc theo lớp', onchange: function (e) { S.lop = e.target.value; drawTree(); } },
        ['', '8', '9'].map(function (v) { return h('option', { value: v, selected: S.lop === v }, v ? 'Lớp ' + v : 'Tất cả lớp'); }));
      var qIn = h('input', { type: 'search', value: S.q, placeholder: 'Tìm mã hoặc tên KC…', 'aria-label': 'Tìm KC', oninput: function (e) { S.q = e.target.value; drawTree(); } });

      function drawTree() {
        var q = fold(S.q).trim(), any = false;
        var gs = groups().filter(function (g) { return !S.lop || String(g.lop) === S.lop; }).map(function (g) {
          var all = leavesOf(g.id), kids = all.filter(function (k) { return !q || fold(k.code + ' ' + k.name).indexOf(q) >= 0; });
          if (q && !kids.length) { if (fold(g.code + ' ' + g.name).indexOf(q) < 0) return null; kids = all; }
          any = true;
          var box = h('div', { class: 'cat-leaves' });
          var det = h('details', { class: 'cat-group', open: !!q || kids.some(function (k) { return k.id === S.kc; }) },
            h('summary', null, h('span', { class: 'mono' }, g.code), h('b', null, g.name), h('span', { class: 'muted small' }, 'lớp ' + g.lop + ' · ' + all.length + ' KC')), box);
          // Leaves exist only while the group is open: no hidden buttons in closed groups.
          var fill = function () {
            box.replaceChildren.apply(box, !det.open ? [] : kids.map(function (k) {
              var b = ui.button([h('span', { class: 'mono' }, k.code), h('span', null, k.name), embedChip(k, true)], function () {
                S.kc = k.id; S.edit = false; S.pick = null; drawTree(); drawDetail();
                if (window.innerWidth < 900) detail.scrollIntoView({ block: 'start' });
              }, { kind: 'ghost' });
              b.classList.add('cat-leaf'); b.setAttribute('aria-pressed', String(k.id === S.kc));
              return b;
            }));
          };
          det.addEventListener('toggle', fill); fill();
          return det;
        }).filter(Boolean);
        tree.replaceChildren.apply(tree, gs);
        if (!any) tree.append(ui.empty('Không tìm thấy KC nào khớp “' + S.q + '”.'));
      }

      function drawDetail() {
        var k = L.kc(S.kc);
        if (!k) { detail.replaceChildren(ui.empty('Chọn một KC bên trái.')); return; }
        var g = L.kc(k.parent_id) || {};
        var probs = new Set(db.problem_kc.filter(function (x) { return x.kc_id === k.id; }).map(function (x) { return x.problem_id; }));
        var pre = db.kc_prereq.filter(function (e) { return e.kc_id === k.id; }), dep = db.kc_prereq.filter(function (e) { return e.prereq_id === k.id; });
        var pend = (M.checkpoints.threads || []).filter(function (t) { return t.graph === 'G2' && t.status === 'awaiting_review'; }).map(function (t) {
          var refs = new Set();
          ((t.state || {}).proposals || []).forEach(function (pp) { if (pp.kind === 'kc_tag' && (pp.candidates || []).some(function (c) { return c.kc_id === k.id; })) refs.add(pp.problem_ref); });
          return { t: t, n: refs.size };
        }).filter(function (x) { return x.n; });
        var main;
        if (S.edit) {
          var nameIn = h('input', { value: k.name, 'aria-label': 'Tên KC' }), descIn = h('textarea', { rows: 3, value: k.description, 'aria-label': 'Mô tả KC' }), err = errEl();
          main = h('div', { class: 'stack' }, field('Tên', nameIn), field('Mô tả', descIn, 'dùng để embedding cho 06 — đổi mô tả thì embedding thành “cũ”'), err,
            h('div', { class: 'row' }, ui.button('Lưu', function () {
              var nn = nameIn.value.trim(), nd = descIn.value.trim();
              if (!nn || !nd) { err.textContent = 'Tên và mô tả không được trống (kc.name, kc.description NOT NULL).'; return; }
              var dCh = nd !== k.description, nCh = nn !== k.name;
              S.edit = false;
              if (!dCh && !nCh) { ctx.toast('Không có thay đổi — tutor.db giữ nguyên.', { kind: 'info' }); drawDetail(); return; }
              k.name = nn;
              if (dCh) { k.description = nd; k.embedding_stale = true; }
              ctx.receipt('Danh mục: sửa KC ' + k.code, [['kc', dCh ? 'mô tả đổi' : 'tên đổi']], {});
              if (dCh) ctx.toast('Embedding của ' + k.code + ' giờ là “cũ” — chạy lại 06 (G2) để cập nhật embedding.', { kind: 'warn' });
              drawTree(); drawDetail();
            }, { kind: 'primary' }), ui.button('Huỷ', function () { S.edit = false; drawDetail(); })));
        } else {
          main = h('div', { class: 'stack' }, ui.kv([
            ['Mã', h('span', { class: 'mono' }, k.code)],
            ['Tên', k.name],
            ['Mô tả', h('div', null, h('p', null, k.description), h('p', { class: 'small muted' }, 'dùng để embedding cho 06'))],
            ['Nhóm', g.code + ' · ' + g.name],
            ['Lớp', String(k.lop)],
            ['Embedding', embedChip(k)],
            ['Tiên quyết', h('div', { class: 'row' }, h('span', null, pre.length + ' KC cần trước · ' + dep.length + ' KC phụ thuộc'),
              ui.button('Xem quan hệ', function () { S.sub = 'prereq'; drawAll(); }, { kind: 'ghost', size: 'sm' }))],
            ['Số bài gắn KC', h('div', { class: 'stack', style: 'gap:6px' },
              probs.size ? h('div', { class: 'row' }, h('b', { class: 'num' }, probs.size + ' bài đã duyệt'), ui.store('db'),
                ui.button('Xem trong Ngân hàng bài', function () { ctx.nav('bank', { kc: k.code }); }, { kind: 'ghost', size: 'sm' }))
                : h('span', { class: 'muted' }, 'Chưa có bài gắn KC này'),
              pend.map(function (x) {
                return h('div', { class: 'row' }, h('span', null, '+' + x.n + ' bài ứng viên trong lô chờ duyệt tag'), ui.store('checkpoint'),
                  ui.button('Mở duyệt tag', function () { ctx.queue.open(x.t.thread_id); }, { kind: 'ghost', size: 'sm', cli: 'tutor review ' + x.t.thread_id }));
              }))]
          ]), h('div', { class: 'row' }, ui.button('Sửa KC', function () { S.edit = true; drawDetail(); })));
        }
        var stale = (!k.embed_model || k.embedding_stale) ? h('div', { class: 'callout callout-warn' },
          h('p', null, k.embed_model ? 'Embedding cũ — chạy lại 06 (G2) để cập nhật embedding. Tới lúc đó 06 vẫn so khớp bằng vector cũ.' : 'KC mới chưa có embedding — 06 tính khi chạy G2 lần tới; trước đó KC này không xuất hiện trong top-5.'),
          ui.cli('tutor bank tag <bank.tex>')) : null;
        var studs = db.student.filter(function (s) { return !s.archived_at && +s.grade === +k.lop; });
        var thetaWhy = ui.why(function () {
          return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'θ = cột theta của skill_state (HS, KC). Code 05 Profiler cập nhật sau mỗi buổi đã duyệt:'),
            h('p', { class: 'mono' }, 'P = 1/(1+e^−(θ−δ)) · θ mới = θ + ' + M.settings.elo.K + '·(X − P)'),
            h('p', null, 'Chưa có dòng nào → θ = ' + M.settings.elo.theta0 + ' (không cần train, NFR2). Chỉ HS lớp ' + k.lop + ' làm KC này.'));
        });
        var th = ui.table({
          columns: [
            { label: 'Học sinh', render: function (r) { return [h('b', { class: 'mono' }, L.studentCode(r.s)), ' ', r.s.name]; } },
            { label: h('span', null, 'θ ', thetaWhy), render: function (r) { return r.st ? h('div', { class: 'row cat-theta' }, ui.bar(r.st.theta, 1, { signed: true }), h('span', { class: 'num' }, fmt.signed(r.st.theta))) : h('span', { class: 'muted small' }, 'chưa có dữ liệu (θ = 0)'); } },
            { label: 'Số lần', align: 'right', render: function (r) { return r.st ? r.st.n_attempts : '—'; } },
            { label: 'Đúng liên tiếp', align: 'right', render: function (r) { return r.st ? r.st.correct_streak : '—'; } },
            { label: 'Gần nhất', render: function (r) { return r.st ? fmt.date(r.st.last_seen) : '—'; } }
          ],
          rows: studs.map(function (s) { return { s: s, st: db.skill_state.find(function (x) { return x.student_id === s.id && x.kc_id === k.id; }) }; }),
          empty: 'Chưa có học sinh lớp ' + k.lop + '.',
          onRow: function (r) { ctx.nav('students', { student: r.s.id, tab: 'skills', kc: k.code }); }
        });
        detail.replaceChildren(h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, h('span', { class: 'mono' }, k.code), ' · ', k.name), ui.annot(['table:kc', 'agent:06', 'G2'])), ui.chip('lớp ' + k.lop, 'info')),
          stale, main),
          h('section', { class: 'section' }, h('div', { class: 'section-head' }, h('div', null, h('h3', null, 'θ của từng HS trên KC này'), ui.annot(['table:skill_state', 'agent:05'])), ui.prov('code')),
            h('p', { class: 'small muted' }, 'Bấm một dòng để mở hồ sơ học sinh ở tab Kỹ năng (Elo).'), th));
        ctx.tex(detail);
      }

      drawTree(); drawDetail();
      return h('div', { class: 'stack' },
        h('div', { class: 'spread' }, h('div', { class: 'row' }, lopSel, qIn), ui.button('Thêm KC', openAddKc)),
        h('div', { class: 'cat-split' }, h('div', { class: 'stack', style: 'gap:6px' }, h('p', { class: 'small muted' }, groups().length + ' nhóm → ' + leaves().length + ' KC (từ kc.csv). Mở nhóm để chọn KC.'), tree), detail));
    }

    function openAddKc() {
      var F = {};
      ctx.modal({
        title: 'Thêm KC',
        body: function (el) {
          var cur = L.kc(S.kc);
          F.g = h('select', { 'aria-label': 'Nhóm' }, groups().map(function (g) { return h('option', { value: g.id, selected: cur && g.id === cur.parent_id }, g.code + ' · ' + g.name); }));
          F.code = h('input', { 'aria-label': 'Mã KC' }); F.name = h('input', { 'aria-label': 'Tên KC', placeholder: 'VD: Tính Δ khi hệ số âm' });
          F.desc = h('textarea', { rows: 3, 'aria-label': 'Mô tả KC' }); F.lop = h('span', { class: 'chip' }); F.err = errEl();
          var touched = false;
          F.code.addEventListener('input', function () { touched = true; });
          var sync = function () {
            var g = L.kc(+F.g.value), n = leavesOf(g.id).reduce(function (m, k) { var x = parseInt(String(k.code).split('-').pop(), 10); return isNaN(x) ? m : Math.max(m, x); }, 0) + 1;
            F.lop.textContent = 'lớp ' + g.lop;
            if (!touched) F.code.value = g.code + '-' + pad2(n);
          };
          F.g.addEventListener('change', sync); sync();
          el.append(field('Nhóm', F.g), h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Lớp theo nhóm:'), F.lop),
            field('Mã (do thầy/cô đặt, không trùng)', F.code), field('Tên', F.name), field('Mô tả', F.desc, 'dùng để embedding cho 06 — viết rõ kỹ năng làm gì'), F.err);
        },
        actions: [{ label: 'Thêm KC', kind: 'primary', onClick: function (close) {
          var g = L.kc(+F.g.value), c = F.code.value.trim(), nm = F.name.value.trim(), ds = F.desc.value.trim();
          var bad = !c ? 'Cần mã KC.' : c.indexOf(g.code + '-') !== 0 ? 'Mã phải bắt đầu bằng “' + g.code + '-”.' : L.kcByCode(c) ? 'Mã ' + c + ' đã có (kc.code UNIQUE).' : !nm ? 'Cần tên KC.' : !ds ? 'Cần mô tả — 06 dùng mô tả để tính embedding.' : null;
          if (bad) { F.err.textContent = bad; return; }
          var id = db.kc.reduce(function (m, k) { return Math.max(m, k.id); }, 0) + 1;
          db.kc.push({ id: id, code: c, name: nm, description: ds, parent_id: g.id, embed_model: null, created_at: nowISO(), lop: g.lop, embedding_stale: false });
          close();
          S.kc = id; S.sub = 'kc'; S.edit = false; S.q = ''; S.lop = '';
          ctx.receipt('Danh mục: thêm KC ' + c, [['kc', 1]], {});
          ctx.toast(c + ' chưa có embedding — 06 tính khi chạy G2 lần tới; sau đó KC xuất hiện trong top-5.', { kind: 'info' });
          drawAll();
        } }, { label: 'Huỷ' }]
      });
    }

    /* ---------- Tiên quyết ---------- */
    function kcSelect(value, onChange, label) {
      return h('select', { 'aria-label': label, onchange: function (e) { onChange(+e.target.value); } }, groups().map(function (g) {
        return h('optgroup', { label: g.code + ' · ' + g.name }, leavesOf(g.id).map(function (k) { return h('option', { value: k.id, selected: k.id === value }, k.code + ' · ' + k.name); }));
      }));
    }
    function kcPick(k) {
      return ui.button([h('span', { class: 'mono' }, k.code), ' ', k.name], function () { S.kc = k.id; S.pick = null; drawAll(); }, { kind: 'ghost', size: 'sm', title: 'Chọn ' + k.code });
    }
    function prereqView() {
      var k = L.kc(S.kc);
      if (!k) return ui.empty('Chưa có KC nào trong danh mục — bấm “Nhập từ CSV”.');
      var d = dag(), E = db.kc_prereq;
      var pre = E.filter(function (e) { return e.kc_id === k.id; }), dep = E.filter(function (e) { return e.prereq_id === k.id; });
      if (S.pick == null || S.pick === k.id || pre.some(function (e) { return e.prereq_id === S.pick; })) {
        var cand = leavesOf(k.parent_id).concat(leaves()).find(function (x) { return x.id !== k.id && !pre.some(function (e) { return e.prereq_id === x.id; }); });
        S.pick = cand ? cand.id : k.id;
      }
      var add = function () {
        var pid = S.pick, A = k.code, B = code(pid);
        if (pid === k.id) { ctx.toast('Không thêm được: CHECK kc_id <> prereq_id — một KC không thể là tiên quyết của chính nó.', { kind: 'error' }); return; }
        if (E.some(function (e) { return e.kc_id === k.id && e.prereq_id === pid; })) { ctx.toast('Đã có: ' + A + ' cần ' + B + ' (khoá chính kc_id, prereq_id).', { kind: 'warn' }); return; }
        var path = findPath(pid, k.id);
        if (path) { ctx.toast('Tạo vòng: ' + path.concat([pid]).map(code).join(' → ') + ' — không thêm (danh mục tiên quyết phải không có vòng).', { kind: 'error' }); return; }
        E.push({ kc_id: k.id, prereq_id: pid });
        S.pick = null;
        ctx.receipt('Danh mục: ' + A + ' cần biết trước ' + B, [['kc_prereq', 1]], {});
        drawAll();
      };
      var del = function (e) {
        var i = E.indexOf(e); if (i < 0) return;
        E.splice(i, 1);
        ctx.receipt('Danh mục: bỏ tiên quyết ' + code(e.kc_id) + ' ← ' + code(e.prereq_id), [['kc_prereq', 'xoá 1 dòng']], {});
        drawAll();
      };
      var col = function (title, sub, list) { return h('div', { class: 'card cat-rel-col' }, h('h3', null, title), h('p', { class: 'small muted' }, sub), list); };
      var dagWhy = ui.why(function () {
        return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, 'Code kiểm tra bằng sắp xếp topo (Kahn): lần lượt bỏ các KC không còn KC tiên quyết nào chưa bỏ.'),
          h('p', null, d.nodes + ' KC có trong ' + d.edges + ' quan hệ — ' + (d.ok ? 'bỏ được hết → không có vòng.' : 'còn KC không bỏ được → có vòng.')),
          h('p', { class: 'small muted' }, 'Cùng kiểm tra này chặn mọi lần “Thêm tiên quyết” tạo vòng (06 bước 4).'));
      });
      var full = ui.table({
        columns: [
          { label: 'KC', render: function (e) { return h('span', { class: 'mono' }, code(e.kc_id)); } },
          { label: 'Tên', render: function (e) { return (L.kc(e.kc_id) || {}).name; } },
          { label: 'Cần biết trước', render: function (e) { return h('span', { class: 'mono' }, code(e.prereq_id)); } },
          { label: 'Tên', render: function (e) { return (L.kc(e.prereq_id) || {}).name; } }
        ],
        rows: E, rowClass: function (e) { return e.kc_id === k.id || e.prereq_id === k.id ? 'is-sel' : null; },
        onRow: function (e) { S.kc = e.kc_id; S.pick = null; drawAll(); }
      });
      return h('div', { class: 'stack' },
        h('div', { class: 'spread' }, h('label', { class: 'field' }, h('span', null, 'KC đang xem'), kcSelect(k.id, function (v) { S.kc = v; S.pick = null; drawAll(); }, 'KC đang xem')),
          h('div', { class: 'row' }, ui.chip(d.ok ? 'Không có vòng ✓' : 'Có vòng ✗', d.ok ? 'ok' : 'danger'), dagWhy, h('span', { class: 'small muted' }, d.edges + ' quan hệ · bảng kc_prereq'), ui.annot(['table:kc_prereq', 'agent:06']))),
        h('div', { class: 'cat-rel' },
          col('KC tiên quyết', 'cần biết trước ' + k.code, pre.length ? h('div', { class: 'cat-list' }, pre.map(function (e) {
            return h('div', { class: 'cat-list-row' }, kcPick(L.kc(e.prereq_id)), ui.button('Xoá', function () { del(e); }, { kind: 'danger', size: 'sm', title: 'Xoá quan hệ ' + k.code + ' ← ' + code(e.prereq_id) }));
          })) : h('p', { class: 'muted' }, 'Không cần KC nào trước.')),
          h('div', { class: 'card cat-rel-col cat-rel-mid' }, h('h3', null, 'KC đang chọn'),
            h('p', null, h('b', { class: 'mono' }, k.code), ' · ', k.name), h('p', { class: 'small muted' }, (L.kc(k.parent_id) || {}).name + ' · lớp ' + k.lop),
            h('label', { class: 'field' }, h('span', null, 'Thêm KC cần biết trước'), kcSelect(S.pick, function (v) { S.pick = v; }, 'KC tiên quyết mới')),
            ui.button('Thêm tiên quyết', add, { kind: 'primary' }),
            h('p', { class: 'small muted' }, 'Chặn: KC tự trỏ chính nó (CHECK kc_id <> prereq_id) và quan hệ tạo vòng.')),
          col('KC phụ thuộc', 'cần ' + k.code + ' trước', dep.length ? h('div', { class: 'cat-list' }, dep.map(function (e) { return kcPick(L.kc(e.kc_id)); })) : h('p', { class: 'muted' }, 'Chưa KC nào cần KC này.'))),
        h('div', { class: 'callout callout-info' }, h('p', null, 'Ai dùng quan hệ này: ', h('b', null, '06 Tagger'), ' cảnh báo khi gắn một KC mà bài chưa có KC tiên quyết; ',
          h('b', null, 'select.py'), ' chỉ chọn bài thử thách cho KC mà mọi KC tiên quyết có θ ≥ 0 (giả định của bản nháp).')),
        h('details', { class: 'cat-details' }, h('summary', null, 'Bảng kc_prereq đầy đủ (' + E.length + ' dòng) — bấm một dòng để chọn KC'), full));
    }

    /* ---------- Mã lỗi ---------- */
    function codesView() {
      var st = codeStats(), ec = db.error_code, months = M.meta.months || [], pv = prompt03();
      var noEx = ec.filter(function (e) { return !e.example; }).length;
      var rejWhy = ui.why(function () {
        return h('div', { class: 'stack', style: 'gap:6px' }, h('p', null, '% bị GV bỏ = số đề xuất của 03 mang mã này bị thầy/cô bỏ (status rejected) ÷ số đề xuất của 03 mang mã này.'),
          h('p', null, 'Mã gốc lấy từ mistake.llm_json (đề xuất trước khi GV sửa). Lỗi GV tự thêm không tính.'),
          h('p', null, 'Dùng tháng = số lỗi đang có hiệu lực (view mistake_current) mang mã này, theo ngày buổi học.'));
      });
      var blocks = Object.keys(CAT).map(function (c) {
        var rows = ec.filter(function (e) { return e.category === c; });
        if (!rows.length) return null;
        var cols = [
          { label: 'Mã', render: function (e) { return h('div', { class: 'stack', style: 'gap:2px' }, h('span', { class: 'mono' }, e.code), e.code === 'other.unclear' ? h('span', { class: 'chip', title: 'Mã dự phòng — không tắt được' }, ui.svg(LOCK), 'bắt buộc giữ') : null); } },
          { label: 'Mô tả', render: function (e) { return h('span', { class: 'cat-w' }, e.description); } },
          { label: 'Ví dụ · đưa vào prompt 03', render: function (e) { return h('div', { class: 'cat-w2' }, e.example ? ui.latex(e.example) : ui.chip('chưa có ví dụ', 'warn')); } },
          { label: 'Bật/tắt', render: function (e) { return e.active ? ui.chip('bật', 'ok') : ui.chip('tắt'); } }
        ].concat(months.map(function (m) {
          return { label: 'Dùng ' + fmt.month(m), align: 'right', render: function (e) { return String(((st[e.code] || {}).months || {})[m] || 0); } };
        })).concat([
          { label: '% bị GV bỏ', align: 'right', render: function (e) { var o = st[e.code]; return o && o.proposed ? fmt.pct(o.rejected / o.proposed) + ' (' + o.rejected + '/' + o.proposed + ')' : '—'; } },
          { label: '', render: function (e) { return ui.button('Mở', function () { openCode(e.code); }, { size: 'sm', title: 'Xem / sửa mã ' + e.code }); } }
        ]);
        return h('div', { class: 'stack cat-block', style: 'gap:6px' },
          h('h3', null, CAT[c] + ' ', h('span', { class: 'mono muted small' }, c), h('span', { class: 'muted small' }, ' · ' + rows.length + ' mã')),
          ui.table({ columns: cols, rows: rows, rowClass: function (e) { return e.active ? null : 'is-dim'; } }));
      });
      return h('div', { class: 'stack' },
        S.banner ? h('div', { class: 'callout callout-info' }, h('p', null, h('b', null, 'Prompt 03 đổi: ' + S.banner.from + ' → ' + S.banner.to), ' · chạy kiểm tra ổn định 3 lần trước khi dùng (NFR8).'),
          ui.button('Mở Nhật ký › Prompt', function () { ctx.nav('logs', { agent: '03', section: 'prompts' }); }, { kind: 'secondary', size: 'sm' })) : null,
        noEx ? h('div', { class: 'callout callout-warn' }, h('p', null, h('b', null, noEx + '/' + ec.length + ' mã chưa có ví dụ'), ' (FERMAT: có ví dụ thì chính xác hơn ~0.03). Ví dụ được đưa nguyên văn vào prompt 03.')) : null,
        h('div', { class: 'spread' },
          h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Prompt 03 hiện tại:'), ui.chip(pv ? pv.version : '—', 'agent03'),
            pv && pv.stability && pv.stability.status === 'passed' ? ui.chip('đã kiểm 3 lần ✓', 'ok') : ui.chip('chưa kiểm 3 lần', 'warn'),
            h('span', { class: 'small muted' }, 'Cột dùng / % bị bỏ'), rejWhy, ui.annot(['table:error_code', 'agent:03', 'table:mistake'])),
          ui.button('Thêm mã lỗi', openAddCode)),
        h('p', { class: 'small muted' }, 'Không có nút xoá: lỗi cũ còn tham chiếu mã (mistake.code). Muốn ngừng dùng → Tắt; mã tắt biến mất khỏi danh sách “Sửa (E)” và khỏi prompt 03.'),
        blocks,
        h('details', { class: 'cat-details' }, h('summary', null, 'Xem trước prompt 03: taxonomy + ví dụ (prompt_version ' + (pv ? pv.version : '—') + ')'),
          h('pre', { class: 'code' }, promptText(pv))));
    }
    function promptText(pv) {
      var on = db.error_code.filter(function (e) { return e.active; }), off = db.error_code.length - on.length;
      var lines = ['# Phần cố định của prompt 03 Diagnoser (được cache) — ' + (pv ? pv.version : ''), '# Taxonomy: ' + on.length + ' mã đang bật' + (off ? ' (' + off + ' mã tắt không đưa vào)' : ''), ''];
      Object.keys(CAT).forEach(function (c) {
        var rows = on.filter(function (e) { return e.category === c; });
        if (!rows.length) return;
        lines.push('## ' + c + ' — ' + CAT[c]);
        rows.forEach(function (e) { lines.push('- ' + e.code + ': ' + e.description); if (e.example) lines.push('  Ví dụ: ' + e.example); });
        lines.push('');
      });
      lines.push('# + 5 lỗi đã duyệt gần nhất của học sinh (lấy bằng SQL lúc chạy)');
      return lines.join('\n');
    }

    function openCode(cd) {
      var mode = null, el = null, dr, list = false;
      dr = ctx.drawer({ title: 'Mã lỗi ' + cd, body: function (b) { el = b; paint(true); } });
      function paint(first) {
        var e = L.errorCode(cd);
        if (!e || !el || (!first && !el.isConnected)) return;
        var o = codeStats()[cd] || { months: {}, ids: [], proposed: 0, rejected: 0 }, months = M.meta.months || [];
        var editor = null;
        if (mode) {
          var isEx = mode === 'example', ta = h('textarea', { rows: isEx ? 3 : 2, value: (isEx ? e.example : e.description) || '', 'aria-label': isEx ? 'Ví dụ LaTeX' : 'Mô tả mã lỗi' });
          var prev = h('div', { class: 'cat-preview' }), err = errEl(), tm = null;
          var show = function () { prev.replaceChildren(ta.value.trim() ? ui.latex(ta.value) : h('span', { class: 'muted small' }, '(trống — mã sẽ không có ví dụ)')); ctx.tex(prev); };
          if (isEx) { ta.addEventListener('input', function () { clearTimeout(tm); tm = setTimeout(show, 250); }); show(); }
          editor = h('div', { class: 'card st-pending stack', style: 'gap:8px' },
            field(isEx ? 'Ví dụ (LaTeX trong $…$) — đưa vào prompt 03' : 'Mô tả mã', ta), isEx ? h('div', null, h('span', { class: 'small muted' }, 'Xem trước:'), prev) : null, err,
            h('div', { class: 'row' }, ui.button('Lưu', function () {
              var v = ta.value.trim();
              if (!isEx && !v) { err.textContent = 'Mô tả không được trống (error_code.description NOT NULL).'; return; }
              var old = isEx ? (e.example || '') : e.description;
              mode = null;
              if (v === old) { ctx.toast('Không có thay đổi — prompt 03 giữ nguyên.', { kind: 'info' }); paint(); return; }
              if (isEx) e.example = v || null; else e.description = v;
              bumpPrompt();
              ctx.receipt('Danh mục: sửa ' + (isEx ? 'ví dụ' : 'mô tả') + ' ' + cd, [['error_code', isEx ? 'ví dụ đổi' : 'mô tả đổi']], {});
              ctx.toast('Prompt 03 đổi: ' + S.banner.from + ' → ' + S.banner.to + ' · chạy kiểm tra ổn định 3 lần trước khi dùng.', { kind: 'warn' });
              paint(); drawAll();
            }, { kind: 'primary' }), ui.button('Huỷ', function () { mode = null; paint(); })));
        }
        el.replaceChildren(h('div', { class: 'stack' },
          ui.kv([
            ['Mã', h('span', { class: 'mono' }, e.code)],
            ['Nhóm', e.category + ' — ' + CAT[e.category]],
            ['Mô tả', e.description],
            ['Ví dụ', e.example ? ui.latex(e.example, { block: true }) : ui.chip('chưa có ví dụ', 'warn')],
            ['Trạng thái', e.active ? ui.chip('bật', 'ok') : ui.chip('tắt')],
            ['Đang dùng', months.map(function (m) { return fmt.month(m) + ': ' + (o.months[m] || 0); }).join(' · ') + ' lỗi'],
            ['% bị GV bỏ', o.proposed ? fmt.pct(o.rejected / o.proposed) + ' (' + o.rejected + '/' + o.proposed + ' đề xuất của 03)' : 'chưa có đề xuất nào']
          ]),
          editor,
          h('div', { class: 'row' },
            ui.button('Sửa mô tả', function () { mode = 'desc'; paint(); }),
            ui.button(e.example ? 'Sửa ví dụ' : 'Thêm ví dụ', function () { mode = 'example'; paint(); }),
            e.code === 'other.unclear'
              ? ui.button('Tắt', null, { disabledReason: 'bắt buộc giữ — mã dự phòng khi 03 không xếp được lỗi vào mã nào' })
              : ui.button(e.active ? 'Tắt' : 'Bật', function () {
                e.active = e.active ? 0 : 1;
                bumpPrompt();
                ctx.receipt('Danh mục: ' + (e.active ? 'bật' : 'tắt') + ' mã ' + cd, [['error_code', 'active = ' + e.active]], {});
                ctx.toast(e.active ? cd + ' bật lại — có trong “Sửa (E)” và prompt 03.' : 'Đã tắt ' + cd + ' — biến mất khỏi “Sửa (E)” và prompt 03; lỗi cũ mang mã này vẫn giữ.', { kind: 'info' });
                paint(); drawAll();
              }, { kind: e.active ? 'danger' : 'secondary' }),
            ui.button(list ? 'Ẩn danh sách lỗi' : 'Xem lỗi mang mã này (' + o.ids.length + ')', function () { list = !list; paint(); })),
          h('p', { class: 'small muted' }, 'Sửa mô tả / ví dụ / bật-tắt đều đổi prompt 03 → cần chạy kiểm tra ổn định 3 lần (NFR8, tab Nhật ký).'),
          list ? mistakesOf(cd) : null));
        ctx.tex(el);
      }
      return dr;
    }
    function mistakesOf(cd) {
      var att = new Map(db.attempt.map(function (a) { return [a.id, a]; })), ses = new Map(db.session.map(function (s) { return [s.id, s]; }));
      var rows = ctx.calc.currentMistakes(db).filter(function (m) { return m.code === cd; }).map(function (m) {
        var a = att.get(m.attempt_id) || {}, s = ses.get(a.session_id) || {};
        return { m: m, s: s, st: L.student(s.student_id), pr: L.problem(a.problem_id) };
      }).sort(function (x, y) { return String(y.s.held_on).localeCompare(String(x.s.held_on)); });
      return h('div', { class: 'stack', style: 'gap:6px' }, h('h3', null, 'Lỗi mang mã ' + cd), ui.annot(['table:mistake']),
        h('p', { class: 'small muted' }, rows.length + ' lỗi đang có hiệu lực (view mistake_current: không tính lỗi bị bỏ hoặc đã bị thay). Bấm một dòng để mở buổi học.'),
        ui.table({
          columns: [
            { label: 'HS', render: function (r) { return r.st ? h('span', { class: 'nowrap' }, h('b', { class: 'mono' }, L.studentCode(r.st)), ' ', r.st.name) : '—'; } },
            { label: 'Buổi', render: function (r) { return fmt.date(r.s.held_on); } },
            { label: 'Bài', render: function (r) { return h('span', { class: 'mono' }, r.pr ? r.pr.ref : '—'); } },
            { label: 'Bước', align: 'right', render: function (r) { return r.m.step_idx; } },
            { label: 'Trạng thái', render: function (r) { return ui.status(r.m.status); } }
          ],
          rows: rows, empty: 'Chưa có lỗi nào mang mã này.',
          onRow: function (r) { if (r.s.id != null) ctx.nav('session', { session: r.s.id }); }
        }));
    }
    function openAddCode() {
      var F = {};
      ctx.modal({
        title: 'Thêm mã lỗi',
        body: function (el) {
          F.cat = h('select', { 'aria-label': 'Nhóm lỗi' }, Object.keys(CAT).map(function (c) { return h('option', { value: c }, c + ' — ' + CAT[c]); }));
          F.sub = h('input', { 'aria-label': 'Tên con', placeholder: 'VD: sign_rule' }); F.desc = h('input', { 'aria-label': 'Mô tả' });
          F.ex = h('textarea', { rows: 2, 'aria-label': 'Ví dụ LaTeX', placeholder: 'VD: $-(x - 3) = -x - 3$' }); F.code = h('b', { class: 'mono' }); F.err = errEl();
          var sync = function () { F.code.textContent = F.cat.value + '.' + (F.sub.value.trim() || '…'); };
          F.cat.addEventListener('change', sync); F.sub.addEventListener('input', sync); sync();
          el.append(field('Nhóm (CHECK category: 5 nhóm cố định)', F.cat), field('Tên con (chữ thường, dấu _)', F.sub), h('p', null, 'Mã sẽ là: ', F.code),
            field('Mô tả', F.desc), field('Ví dụ (không bắt buộc) — đưa vào prompt 03', F.ex), F.err);
        },
        actions: [{ label: 'Thêm mã', kind: 'primary', onClick: function (close) {
          var sub = F.sub.value.trim(), c = F.cat.value + '.' + sub, ds = F.desc.value.trim();
          var bad = !/^[a-z][a-z_]*$/.test(sub) ? 'Tên con chỉ gồm chữ thường a–z và dấu _ (VD: sign_rule).' : L.errorCode(c) ? 'Mã ' + c + ' đã có.' : !ds ? 'Cần mô tả.' : null;
          if (bad) { F.err.textContent = bad; return; }
          db.error_code.push({ code: c, category: F.cat.value, description: ds, example: F.ex.value.trim() || null, active: 1 });
          close();
          bumpPrompt(); S.sub = 'codes';
          ctx.receipt('Danh mục: thêm mã lỗi ' + c, [['error_code', 1]], {});
          ctx.toast('Prompt 03 đổi: ' + S.banner.from + ' → ' + S.banner.to + ' · chạy kiểm tra ổn định 3 lần trước khi dùng.', { kind: 'warn' });
          drawAll();
        } }, { label: 'Huỷ' }]
      });
    }

    /* ---------- Nhập từ CSV ---------- */
    function openImport() {
      var pv = M.ui.catalog_import_preview || {};
      var changed = (pv.kc_changed || []).filter(function (c) { var k = L.kcByCode(c.code); return k && k[c.field] !== c.new; });
      var added = (pv.kc_added || []).filter(function (c) { return !L.kcByCode(c.code); });
      var pAdd = pv.prereq_added || [], pDel = pv.prereq_removed || [];
      var n = changed.length + added.length + pAdd.length + pDel.length;
      var summary = added.length + ' KC mới · ' + changed.length + ' mô tả đổi · ' + pAdd.length + ' quan hệ mới' + (pDel.length ? ' · ' + pDel.length + ' quan hệ bỏ' : '');
      var file = function (path, note) { return h('div', { class: 'card st-file', style: 'gap:2px' }, h('span', { class: 'mono' }, path), h('span', { class: 'small muted' }, note)); };
      ctx.modal({
        title: 'Nhập danh mục từ CSV', wide: true,
        body: h('div', { class: 'stack' },
          h('div', { class: 'callout callout-warn' }, h('p', null, 'Cách nhập chưa chốt — đề xuất CSV/YAML + lệnh import (tài liệu thiết kế §11.4).')),
          h('div', { class: 'grid cols-2' }, file('data/inbox/bank/kc.csv', 'code, name, description, parent_code, lop · UTF-8 BOM'), file('data/inbox/bank/kc_prereq.csv', 'kc_code, prereq_code · UTF-8 BOM')),
          h('p', null, h('b', null, 'So với tutor.db: '), summary, ' ', ui.prov('code')),
          changed.length ? ui.table({
            columns: [
              { label: 'KC', render: function (c) { return h('span', { class: 'mono' }, c.code); } },
              { label: 'Trường', render: function (c) { return c.field; } },
              { label: 'Đang có', render: function (c) { return h('span', { class: 'muted' }, L.kcByCode(c.code)[c.field]); } },
              { label: 'Trong CSV', render: function (c) { return h('mark', { class: 'cat-mark' }, c.new); } }
            ], rows: changed
          }) : h('p', { class: 'muted' }, 'CSV khớp tutor.db — không có gì để áp dụng.'),
          changed.length ? h('p', { class: 'small muted' }, 'KC đổi mô tả → embedding thành “cũ”, cần chạy lại 06 (G2).') : null),
        actions: [{ label: 'Áp dụng', kind: 'primary', disabledReason: n ? null : 'không có thay đổi', onClick: function (close) {
          var stale = [];
          added.forEach(function (c) {
            var g = L.kcByCode(c.parent_code), id = db.kc.reduce(function (m, k) { return Math.max(m, k.id); }, 0) + 1;
            db.kc.push({ id: id, code: c.code, name: c.name, description: c.description, parent_id: g ? g.id : null, embed_model: null, created_at: nowISO(), lop: c.lop || (g && g.lop), embedding_stale: false });
          });
          changed.forEach(function (c) { var k = L.kcByCode(c.code); k[c.field] = c.new; if (c.field === 'description') { k.embedding_stale = true; stale.push(k); } });
          pAdd.forEach(function (e) { var a = L.kcByCode(e.kc_code), b = L.kcByCode(e.prereq_code); if (a && b) db.kc_prereq.push({ kc_id: a.id, prereq_id: b.id }); });
          pDel.forEach(function (e) { var a = L.kcByCode(e.kc_code), b = L.kcByCode(e.prereq_code), i = db.kc_prereq.findIndex(function (x) { return a && b && x.kc_id === a.id && x.prereq_id === b.id; }); if (i >= 0) db.kc_prereq.splice(i, 1); });
          close();
          ctx.receipt('Nhập danh mục từ CSV', [['kc', summary]], {});
          if (stale.length) { S.kc = stale[0].id; S.sub = 'kc'; S.edit = false; ctx.toast(stale.map(function (k) { return k.code; }).join(', ') + ': embedding cũ — chạy lại 06 (G2) để cập nhật.', { kind: 'warn' }); }
          drawAll();
        } }, { label: 'Huỷ' }]
      });
    }
  }
})();
