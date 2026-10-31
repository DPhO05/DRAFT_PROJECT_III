/* Danh mục (FR9, P1-T04 · P2-T07): nhóm → KC, tiên quyết, mã lỗi, nhập / xuất CSV — đọc và ghi qua /api/catalog. */
(function () {
  'use strict';
  var CAT = { computational: 'Tính toán', conceptual: 'Khái niệm', notational: 'Ký hiệu', presentation: 'Trình bày', other: 'Khác' };
  var SUBS = [{ id: 'kc', label: 'Kỹ năng (KC)' }, { id: 'prereq', label: 'Tiên quyết' }, { id: 'codes', label: 'Mã lỗi' }];
  var LOCKED = 'other.unclear';
  // Kept across navigations: sub-tab, selected KC, filters, prompt-03-changed banner.
  var S = { sub: 'kc', kc: null, lop: '', q: '', edit: false, pick: null, banner: false };

  function fold(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd'); }
  function pad2(n) { return String(n).padStart(2, '0'); }
  // Server error → text; a prerequisite loop comes back as detail.cycle (codes).
  function errText(e) {
    var c = e && e.detail && e.detail.cycle;
    if (!c) return (e && e.message) || String(e);
    return (c.length === 2 && c[0] === c[1] ? 'KC không thể là tiên quyết của chính nó: ' : 'Tạo vòng tiên quyết: ') + c.join(' → ');
  }

  App.registerTab('catalog', { title: 'Danh mục', render: render });

  function render(root, ctx) {
    var ui = ctx.ui, h = ui.h, p = ctx.params;
    var KCS = [], byId = new Map(), want = p.kc || null, CODES = [], wantCode = p.code || null;
    if (SUBS.some(function (s) { return s.id === p.tab; })) S.sub = p.tab;
    if (wantCode) S.sub = 'codes';

    function groups() { return KCS.filter(function (k) { return k.parent_id == null; }); }
    function leaves() { return KCS.filter(function (k) { return k.parent_id != null; }); }
    function leavesOf(gid) { return KCS.filter(function (k) { return k.parent_id === gid; }); }
    function code(id) { var k = byId.get(id); return k ? k.code : '#' + id; }
    function dependents(id) { return KCS.filter(function (k) { return k.prereq_ids.indexOf(id) >= 0; }); }
    function field(label, input, hint) { return h('label', { class: 'field' }, h('span', null, label), input, hint || null); }
    function errEl() { return h('p', { class: 'cat-err', role: 'alert' }); }
    function lopSelect(value, label) {
      return h('select', { 'aria-label': label }, ['', '8', '9'].map(function (v) { return h('option', { value: v, selected: String(value == null ? '' : value) === v }, v ? 'Lớp ' + v : '—'); }));
    }
    function wrote(title, rows) { ctx.receipt(title, rows, {}); TutorApi.refreshCounts(); return reload(); }

    /* ---------- page ---------- */
    var exportRow = h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Xuất CSV'),
      h('a', { class: 'btn btn-secondary btn-sm', href: '/api/catalog/export?file=kc', download: 'kc.csv' }, 'kc.csv'),
      h('a', { class: 'btn btn-secondary btn-sm', href: '/api/catalog/export?file=prereq', download: 'kc_prereq.csv' }, 'kc_prereq.csv'),
      h('a', { class: 'btn btn-secondary btn-sm', href: '/api/catalog/export?file=error_code', download: 'error_code.csv' }, 'error_code.csv'));
    root.append(ui.pageHead({
      lead: 'Danh mục thầy/cô tự giữ: kỹ năng (KC), quan hệ tiên quyết, mã lỗi kèm ví dụ. Agent đọc thẳng từ đây: 03 Diagnoser (mã lỗi + ví dụ trong prompt).',
      annot: ['table:kc', 'table:kc_prereq', 'table:error_code', 'agent:03'],
      actions: [ui.button('Nhập từ CSV', openImport, { kind: 'primary' }), exportRow]
    }));
    var body = h('div', { class: 'stack' }, h('p', { class: 'muted' }, 'Đang tải danh mục…'));
    root.append(body);
    return reload();

    function reload() {
      return Promise.all([api.get('/catalog/kc'), api.get('/catalog/error-codes')]).then(function (r) {
        var list = r[0];
        CODES = r[1];
        KCS = list; byId = new Map(list.map(function (k) { return [k.id, k]; }));
        if (want) {
          var w = list.find(function (k) { return k.code === want || String(k.id) === want; });
          if (w) { S.kc = w.id; S.edit = false; S.pick = null; }
          want = null;
        }
        if (!byId.has(S.kc)) { var d0 = leaves()[0] || KCS[0]; S.kc = d0 ? d0.id : null; S.edit = false; }
        drawAll();
        if (wantCode) { var c = wantCode; wantCode = null; if (codeOf(c)) openCode(c); }
      }, function (e) {
        body.replaceChildren(h('div', { class: 'callout callout-crit', role: 'alert' },
          h('strong', null, 'Không tải được danh mục.'), h('p', { class: 'mono small' }, errText(e)), h('div', null, ui.button('Thử lại', reload))));
      });
    }

    function drawAll() {
      var lv = leaves(), edges = KCS.reduce(function (n, k) { return n + k.prereq_ids.length; }, 0);
      var kpi = function (label, value, sub) { return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label), h('span', { class: 'kpi-value' }, value), h('span', { class: 'kpi-sub' }, sub)); };
      body.replaceChildren(
        h('div', { class: 'grid cat-kpis' },
          kpi('Kỹ năng (KC)', String(lv.length), 'trong ' + groups().length + ' nhóm'),
          kpi('Quan hệ tiên quyết', String(edges), 'server chặn quan hệ tạo vòng'),
          kpi('Mã lỗi', String(CODES.length), CODES.filter(function (e) { return e.active; }).length + ' đang bật · 5 nhóm')),
        ui.segmented(SUBS, S.sub, function (id) { S.sub = id; drawAll(); }),
        S.sub === 'codes' ? codesView()
          : !KCS.length ? ui.empty('Chưa có KC nào trong danh mục. Bấm “Nhập từ CSV” để nạp kc.csv + kc_prereq.csv, hoặc thêm từng KC.',
            h('div', { class: 'row' }, ui.button('Nhập từ CSV', openImport, { kind: 'primary' }), ui.button('Thêm KC', openAddKc)))
          : S.sub === 'prereq' ? prereqView() : kcView());
      ctx.tex(body);
    }

    /* ---------- Kỹ năng (KC) ---------- */
    function kcView() {
      var tree = h('div', { class: 'cat-tree' }), detail = h('div', { class: 'stack' });
      var lopSel = h('select', { 'aria-label': 'Lọc theo lớp', onchange: function (e) { S.lop = e.target.value; drawTree(); } },
        ['', '8', '9'].map(function (v) { return h('option', { value: v, selected: S.lop === v }, v ? 'Lớp ' + v : 'Tất cả lớp'); }));
      var qIn = h('input', { type: 'search', value: S.q, placeholder: 'Tìm mã hoặc tên KC…', 'aria-label': 'Tìm KC', oninput: function (e) { S.q = e.target.value; drawTree(); } });
      function select(k) {
        S.kc = k.id; S.edit = false; S.pick = null; drawTree(); drawDetail();
        if (window.innerWidth < 900) detail.scrollIntoView({ block: 'start' });
      }
      function item(k, label) {
        var b = ui.button(label, function () { select(k); }, { kind: 'ghost' });
        b.classList.add('cat-leaf'); b.setAttribute('aria-pressed', String(k.id === S.kc));
        return b;
      }

      function drawTree() {
        var q = fold(S.q).trim();
        var gs = groups().filter(function (g) { return !S.lop || g.lop == null || String(g.lop) === S.lop; }).map(function (g) {
          var all = leavesOf(g.id), kids = all.filter(function (k) { return !q || fold(k.code + ' ' + k.name).indexOf(q) >= 0; });
          if (q && !kids.length) { if (fold(g.code + ' ' + g.name).indexOf(q) < 0) return null; kids = all; }
          var box = h('div', { class: 'cat-leaves' });
          var det = h('details', { class: 'cat-group', open: !!q || g.id === S.kc || kids.some(function (k) { return k.id === S.kc; }) },
            h('summary', null, h('span', { class: 'mono' }, g.code), h('b', null, g.name), h('span', { class: 'muted small' }, (g.lop ? 'lớp ' + g.lop + ' · ' : '') + all.length + ' KC')), box);
          // Leaves exist only while the group is open: no hidden buttons in closed groups.
          var fill = function () {
            box.replaceChildren.apply(box, !det.open ? [] : kids.map(function (k) {
              return item(k, [h('span', { class: 'mono' }, k.code), h('span', null, k.name)]);
            }).concat([item(g, h('span', { class: 'small' }, all.length ? 'Thông tin nhóm ' + g.code : 'Nhóm chưa có KC con — xem / sửa nhóm'))]));
          };
          det.addEventListener('toggle', fill); fill();
          return det;
        }).filter(Boolean);
        tree.replaceChildren.apply(tree, gs);
        if (!gs.length) tree.append(ui.empty(S.q ? 'Không tìm thấy KC nào khớp “' + S.q + '”.' : 'Không có nhóm nào ở lớp ' + S.lop + '.'));
      }

      function drawDetail() {
        var k = byId.get(S.kc);
        if (!k) { detail.replaceChildren(ui.empty('Chọn một KC bên trái.')); return; }
        var g = byId.get(k.parent_id), kids = leavesOf(k.id), dep = dependents(k.id), main;
        if (S.edit) {
          var nameIn = h('input', { value: k.name, 'aria-label': 'Tên KC' }), lopIn = lopSelect(k.lop, 'Lớp');
          var descIn = h('textarea', { rows: 4, value: k.description, 'aria-label': 'Mô tả KC' }), err = errEl();
          main = h('div', { class: 'stack' }, field('Tên', nameIn), field('Mô tả', descIn),
            field('Lớp', lopIn), err,
            h('div', { class: 'row' }, ui.button('Lưu', function () {
              var patch = {}, nn = nameIn.value.trim(), nd = descIn.value.trim(), nl = lopIn.value ? +lopIn.value : null;
              if (!nn || !nd) { err.textContent = 'Tên và mô tả không được trống.'; return; }
              if (nn !== k.name) patch.name = nn;
              if (nd !== k.description) patch.description = nd;
              if (nl !== k.lop) patch.lop = nl;
              if (!Object.keys(patch).length) { S.edit = false; ctx.toast('Không có thay đổi — tutor.db giữ nguyên.', { kind: 'info' }); drawDetail(); return; }
              err.textContent = 'Đang lưu…';
              return api.send('PATCH', '/catalog/kc/' + k.id, patch).then(function () {
                S.edit = false;
                return wrote('Danh mục: sửa KC ' + k.code, [['kc', Object.keys(patch).join(', ') + ' đổi']]);
              }, function (e) { err.textContent = errText(e); });
            }, { kind: 'primary' }), ui.button('Huỷ', function () { S.edit = false; drawDetail(); })));
        } else {
          main = h('div', { class: 'stack' }, ui.kv([
            ['Mã', h('span', { class: 'mono' }, k.code)],
            ['Tên', k.name],
            ['Mô tả', k.description],
            ['Nhóm', g ? g.code + ' · ' + g.name : kids.length + ' KC con (đây là nhóm)'],
            ['Lớp', k.lop == null ? '—' : String(k.lop)],
            ['Tiên quyết', h('div', { class: 'stack', style: 'gap:6px' },
              k.prereq_ids.length ? h('div', { class: 'row', style: 'gap:4px' }, k.prereq_ids.map(function (id) { return h('span', { class: 'chip mono' }, code(id)); }))
                : h('span', { class: 'muted' }, 'Không cần KC nào trước.'),
              h('div', { class: 'row' }, h('span', { class: 'small muted' }, dep.length + ' KC phụ thuộc'),
                ui.button('Sửa tiên quyết', function () { S.sub = 'prereq'; S.pick = null; drawAll(); }, { kind: 'ghost', size: 'sm' })))]
          ]), h('div', { class: 'row' }, ui.button('Sửa KC', function () { S.edit = true; drawDetail(); })));
        }
        detail.replaceChildren(h('section', { class: 'section' },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, h('span', { class: 'mono' }, k.code), ' · ', k.name), ui.annot(['table:kc'])),
            k.lop != null ? ui.chip('lớp ' + k.lop, 'info') : null),
          main));
      }

      drawTree(); drawDetail();
      return h('div', { class: 'stack' },
        h('div', { class: 'spread' }, h('div', { class: 'row' }, lopSel, qIn), ui.button('Thêm KC', openAddKc)),
        h('div', { class: 'cat-split' }, h('div', { class: 'stack', style: 'gap:6px' },
          h('p', { class: 'small muted' }, groups().length + ' nhóm → ' + leaves().length + ' KC. Mở nhóm để chọn KC.'), tree), detail));
    }

    function openAddKc() {
      var F = {};
      ctx.modal({
        title: 'Thêm KC',
        body: function (el) {
          var cur = byId.get(S.kc), gsel = cur ? (cur.parent_id != null ? cur.parent_id : cur.id) : null;
          F.g = h('select', { 'aria-label': 'Nhóm' }, h('option', { value: '' }, '— Không có (KC này là một nhóm mới) —'),
            groups().map(function (g) { return h('option', { value: g.id, selected: g.id === gsel }, g.code + ' · ' + g.name); }));
          F.code = h('input', { 'aria-label': 'Mã KC', placeholder: 'VD: 9DS-PT2-07' }); F.name = h('input', { 'aria-label': 'Tên KC' });
          F.desc = h('textarea', { rows: 3, 'aria-label': 'Mô tả KC' }); F.lop = lopSelect('', 'Lớp'); F.err = errEl();
          var touched = false;
          F.code.addEventListener('input', function () { touched = true; });
          var sync = function () {
            var g = byId.get(+F.g.value);
            if (!g) { if (!touched) F.code.value = ''; return; }
            F.lop.value = g.lop == null ? '' : String(g.lop);
            var n = leavesOf(g.id).reduce(function (m, k) { var x = parseInt(String(k.code).split('-').pop(), 10); return isNaN(x) ? m : Math.max(m, x); }, 0) + 1;
            if (!touched) F.code.value = g.code + '-' + pad2(n);
          };
          F.g.addEventListener('change', sync); sync();
          el.append(field('Nhóm', F.g), field('Mã (không trùng)', F.code), field('Tên', F.name),
            field('Mô tả', F.desc), field('Lớp', F.lop), F.err);
        },
        actions: [{ label: 'Thêm KC', kind: 'primary', onClick: function (close) {
          var b = { code: F.code.value.trim(), name: F.name.value.trim(), description: F.desc.value.trim(), parent_id: F.g.value ? +F.g.value : null, lop: F.lop.value ? +F.lop.value : null };
          var bad = !b.code ? 'Cần mã KC.' : !b.name ? 'Cần tên KC.' : !b.description ? 'Cần mô tả.' : null;
          if (bad) { F.err.textContent = bad; return; }
          F.err.textContent = 'Đang lưu…';
          return api.send('POST', '/catalog/kc', b).then(function (k) {
            close();
            S.kc = k.id; S.sub = 'kc'; S.edit = false; S.q = ''; S.lop = '';
            return wrote('Danh mục: thêm KC ' + k.code, [['kc', 1]]);
          }, function (e) { F.err.textContent = errText(e); });
        } }, { label: 'Huỷ' }]
      });
    }

    /* ---------- Tiên quyết ---------- */
    function kcSelect(value, onChange, label) {
      return h('select', { 'aria-label': label, onchange: function (e) { onChange(+e.target.value); } }, groups().map(function (g) {
        return h('optgroup', { label: g.code + ' · ' + g.name }, [g].concat(leavesOf(g.id)).map(function (k) {
          return h('option', { value: k.id, selected: k.id === value }, k.code + ' · ' + k.name + (k === g ? ' (nhóm)' : ''));
        }));
      }));
    }
    function kcPick(k) {
      return ui.button([h('span', { class: 'mono' }, k.code), ' ', k.name], function () { S.kc = k.id; S.pick = null; drawAll(); }, { kind: 'ghost', size: 'sm', title: 'Chọn ' + k.code });
    }
    function prereqView() {
      var k = byId.get(S.kc);
      if (!k) return ui.empty('Chọn một KC ở tab Kỹ năng.');
      var pre = k.prereq_ids.map(function (id) { return byId.get(id); }).filter(Boolean), dep = dependents(k.id);
      if (S.pick == null || !byId.has(S.pick) || S.pick === k.id || k.prereq_ids.indexOf(S.pick) >= 0) {
        var cand = leavesOf(k.parent_id).concat(leaves()).find(function (x) { return x.id !== k.id && k.prereq_ids.indexOf(x.id) < 0; });
        S.pick = cand ? cand.id : k.id;
      }
      var err = errEl();
      var add = function () {
        var pid = S.pick;
        if (k.prereq_ids.indexOf(pid) >= 0) { ctx.toast('Đã có: ' + k.code + ' cần ' + code(pid) + '.', { kind: 'warn' }); return; }
        err.textContent = '';
        return api.send('POST', '/catalog/kc/' + k.id + '/prereqs', { prereq_id: pid }).then(function () {
          S.pick = null;
          return wrote('Danh mục: ' + k.code + ' cần biết trước ' + code(pid), [['kc_prereq', 1]]);
        }, function (e) {
          err.textContent = 'Không thêm: ' + errText(e);
          ctx.toast(errText(e), { kind: 'error', title: 'Không thêm tiên quyết' });
        });
      };
      var del = function (x) {
        return ctx.confirm('Bỏ quan hệ: ' + k.code + ' cần biết trước ' + x.code + '?', { title: 'Xoá tiên quyết', ok: 'Xoá', danger: true }).then(function (yes) {
          if (!yes) return;
          return api.send('DELETE', '/catalog/kc/' + k.id + '/prereqs/' + x.id).then(function () {
            return wrote('Danh mục: bỏ tiên quyết ' + k.code + ' ← ' + x.code, [['kc_prereq', 'xoá 1 dòng']]);
          }, function (e) { ctx.toast(errText(e), { kind: 'error', title: 'Không xoá được' }); });
        });
      };
      var col = function (title, sub, list) { return h('div', { class: 'card cat-rel-col' }, h('h3', null, title), h('p', { class: 'small muted' }, sub), list); };
      var edges = [];
      KCS.forEach(function (a) { a.prereq_ids.forEach(function (b) { edges.push({ kc_id: a.id, prereq_id: b }); }); });
      var full = ui.table({
        columns: [
          { label: 'KC', render: function (e) { return h('span', { class: 'mono' }, code(e.kc_id)); } },
          { label: 'Tên', render: function (e) { return (byId.get(e.kc_id) || {}).name; } },
          { label: 'Cần biết trước', render: function (e) { return h('span', { class: 'mono' }, code(e.prereq_id)); } },
          { label: 'Tên', render: function (e) { return (byId.get(e.prereq_id) || {}).name; } }
        ],
        rows: edges, empty: 'Chưa có quan hệ tiên quyết nào.',
        rowClass: function (e) { return e.kc_id === k.id || e.prereq_id === k.id ? 'is-sel' : null; },
        onRow: function (e) { S.kc = e.kc_id; S.pick = null; drawAll(); }
      });
      var g = byId.get(k.parent_id);
      return h('div', { class: 'stack' },
        h('div', { class: 'spread' }, h('label', { class: 'field' }, h('span', null, 'KC đang xem'), kcSelect(k.id, function (v) { S.kc = v; S.pick = null; drawAll(); }, 'KC đang xem')),
          h('div', { class: 'row' }, h('span', { class: 'small muted' }, edges.length + ' quan hệ · bảng kc_prereq'), ui.annot(['table:kc_prereq']))),
        h('div', { class: 'cat-rel' },
          col('KC tiên quyết', 'cần biết trước ' + k.code, pre.length ? h('div', { class: 'cat-list' }, pre.map(function (x) {
            return h('div', { class: 'cat-list-row' }, kcPick(x), ui.button('Xoá', function () { return del(x); }, { kind: 'danger', size: 'sm', title: 'Xoá quan hệ ' + k.code + ' ← ' + x.code }));
          })) : h('p', { class: 'muted' }, 'Không cần KC nào trước.')),
          h('div', { class: 'card cat-rel-col cat-rel-mid' }, h('h3', null, 'KC đang chọn'),
            h('p', null, h('b', { class: 'mono' }, k.code), ' · ', k.name), h('p', { class: 'small muted' }, (g ? g.name : 'nhóm') + (k.lop != null ? ' · lớp ' + k.lop : '')),
            h('label', { class: 'field' }, h('span', null, 'Thêm KC cần biết trước'), kcSelect(S.pick, function (v) { S.pick = v; err.textContent = ''; }, 'KC tiên quyết mới')),
            ui.button('Thêm tiên quyết', add, { kind: 'primary' }), err,
            h('p', { class: 'small muted' }, 'Server chặn KC tự trỏ chính nó và quan hệ tạo vòng; lỗi hiện đường vòng.')),
          col('KC phụ thuộc', 'cần ' + k.code + ' trước', dep.length ? h('div', { class: 'cat-list' }, dep.map(kcPick)) : h('p', { class: 'muted' }, 'Chưa KC nào cần KC này.'))),
        h('details', { class: 'cat-details' }, h('summary', null, 'Bảng kc_prereq đầy đủ (' + edges.length + ' dòng) — bấm một dòng để chọn KC'), full));
    }

    /* ---------- Mã lỗi ---------- */
    function codeOf(c) { return CODES.find(function (e) { return e.code === c; }) || null; }
    function codePath(c) { return '/catalog/error-codes/' + encodeURIComponent(c); }
    // Any taxonomy edit changes 03's prompt, so its stability check (NFR8) must run again.
    function promptChanged(what, version) {
      S.banner = version || true;
      ctx.toast(what + ' — prompt 03 đổi, chưa kiểm 3 lần: chạy kiểm tra ổn định 3 lần trước khi dùng.', { kind: 'warn' });
    }
    function codesView() {
      var noEx = CODES.filter(function (e) { return !e.example; }).length;
      var blocks = Object.keys(CAT).map(function (c) {
        var rows = CODES.filter(function (e) { return e.category === c; });
        if (!rows.length) return null;
        return h('div', { class: 'stack', style: 'gap:6px' },
          h('h3', null, CAT[c] + ' ', h('span', { class: 'mono muted small' }, c), h('span', { class: 'muted small' }, ' · ' + rows.length + ' mã')),
          ui.table({
            columns: [
              { label: 'Mã', render: function (e) { return h('div', { class: 'stack', style: 'gap:2px' }, h('span', { class: 'mono' }, e.code), e.code === LOCKED ? h('span', { class: 'chip', title: 'Mã dự phòng — không tắt được' }, 'bắt buộc giữ') : null); } },
              { label: 'Mô tả', render: function (e) { return h('span', { class: 'cat-w' }, e.description); } },
              { label: 'Ví dụ · đưa vào prompt 03', render: function (e) { return h('div', { class: 'cat-w2' }, e.example ? ui.latex(e.example) : ui.chip('chưa có ví dụ', 'warn')); } },
              { label: 'Bật/tắt', render: function (e) { return e.active ? ui.chip('bật', 'ok') : ui.chip('tắt'); } },
              { label: '', render: function (e) { return ui.button('Mở', function () { openCode(e.code); }, { size: 'sm', title: 'Xem / sửa mã ' + e.code }); } }
            ],
            rows: rows, rowClass: function (e) { return e.active ? null : 'is-dim'; }
          }));
      });
      return h('div', { class: 'stack' },
        S.banner ? h('div', { class: 'callout callout-info' }, h('p', null, h('b', null, 'Prompt 03 đổi'), typeof S.banner === 'string' ? [' → ', h('code', null, S.banner)] : null, ' (mã lỗi / ví dụ vừa sửa) ', ui.chip('chưa kiểm 3 lần', 'warn'),
          ' · chạy kiểm tra ổn định 3 lần trước khi dùng (NFR8, tab Nhật ký).')) : null,
        noEx ? h('div', { class: 'callout callout-warn' }, h('p', null, h('b', null, noEx + '/' + CODES.length + ' mã chưa có ví dụ'),
          ' (FERMAT: có ví dụ thì chính xác hơn ~0.03). Ví dụ được đưa nguyên văn vào prompt 03.')) : null,
        h('div', { class: 'spread' },
          h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Mã đang bật + ví dụ nằm trong prompt 03 Diagnoser.'), ui.annot(['table:error_code', 'agent:03', 'table:mistake'])),
          ui.button('Thêm mã lỗi', openAddCode)),
        h('p', { class: 'small muted' }, 'Không có nút xoá: lỗi cũ còn tham chiếu mã (mistake.code). Muốn ngừng dùng → Tắt; mã tắt biến mất khỏi danh sách “Sửa (E)” và khỏi prompt 03.'),
        blocks);
    }

    function openCode(cd) {
      var mode = null, el = null, list = null;  // mode: 'description' | 'example'; list: null | 'loading' | rows | {err}
      ctx.drawer({ title: 'Mã lỗi ' + cd, body: function (b) { el = b; paint(true); } });
      function save(patch, title, what) {
        return api.send('PATCH', codePath(cd), patch).then(function (r) {
          promptChanged('Đã lưu ' + cd, r.prompt_version);
          return wrote(title, [['error_code', what]]);
        });
      }
      function paint(first) {
        var e = codeOf(cd);
        if (!e || !el || (!first && !el.isConnected)) return;
        var editor = null;
        if (mode) {
          var isEx = mode === 'example', ta = h('textarea', { rows: isEx ? 3 : 2, value: e[mode] || '', 'aria-label': isEx ? 'Ví dụ LaTeX' : 'Mô tả mã lỗi' });
          var prev = h('div', { class: 'cat-preview' }), err = errEl(), tm = null;
          var show = function () { prev.replaceChildren(ta.value.trim() ? ui.latex(ta.value) : h('span', { class: 'muted small' }, '(trống — mã sẽ không có ví dụ)')); ctx.tex(prev); };
          if (isEx) { ta.addEventListener('input', function () { clearTimeout(tm); tm = setTimeout(show, 250); }); show(); }
          editor = h('div', { class: 'card stack', style: 'gap:8px' },
            field(isEx ? 'Ví dụ (LaTeX trong $…$) — đưa vào prompt 03' : 'Mô tả mã', ta), isEx ? h('div', null, h('span', { class: 'small muted' }, 'Xem trước:'), prev) : null, err,
            h('div', { class: 'row' }, ui.button('Lưu', function () {
              var v = ta.value.trim(), patch = {};
              if (!isEx && !v) { err.textContent = 'Mô tả không được trống.'; return; }
              if (v === (e[mode] || '')) { mode = null; ctx.toast('Không có thay đổi — prompt 03 giữ nguyên.', { kind: 'info' }); paint(); return; }
              patch[mode] = v; err.textContent = 'Đang lưu…';
              return save(patch, 'Danh mục: sửa ' + (isEx ? 'ví dụ' : 'mô tả') + ' ' + cd, isEx ? 'ví dụ đổi' : 'mô tả đổi')
                .then(function () { mode = null; paint(); }, function (x) { err.textContent = errText(x); });
            }, { kind: 'primary' }), ui.button('Huỷ', function () { mode = null; paint(); })));
        }
        el.replaceChildren(h('div', { class: 'stack' },
          ui.kv([
            ['Mã', h('span', { class: 'mono' }, e.code)],
            ['Nhóm', e.category + ' — ' + CAT[e.category]],
            ['Mô tả', e.description],
            ['Ví dụ', e.example ? ui.latex(e.example, { block: true }) : ui.chip('chưa có ví dụ', 'warn')],
            ['Trạng thái', e.active ? ui.chip('bật', 'ok') : ui.chip('tắt')]
          ]),
          editor,
          h('div', { class: 'row' },
            ui.button('Sửa mô tả', function () { mode = 'description'; paint(); }),
            ui.button(e.example ? 'Sửa ví dụ' : 'Thêm ví dụ', function () { mode = 'example'; paint(); }),
            e.code === LOCKED
              ? ui.button('Tắt', null, { disabledReason: 'other.unclear khoá, không tắt được — mã dự phòng khi 03 không xếp được lỗi vào mã nào' })
              : ui.button(e.active ? 'Tắt' : 'Bật', function () {
                return save({ active: !e.active }, 'Danh mục: ' + (e.active ? 'tắt' : 'bật') + ' mã ' + cd, 'active = ' + (e.active ? 0 : 1))
                  .then(function () { paint(); }, function (x) { ctx.toast(errText(x), { kind: 'error', title: 'Không lưu được' }); });
              }, { kind: e.active ? 'danger' : 'secondary' }),
            ui.button(list ? 'Ẩn lỗi mang mã này' : 'Lỗi mang mã này', function () {
              if (list) { list = null; paint(); return; }
              list = 'loading'; paint();
              return api.get(codePath(cd) + '/mistakes').then(function (rows) { list = rows; paint(); }, function (x) { list = { err: errText(x) }; paint(); });
            })),
          h('p', { class: 'small muted' }, 'Sửa mô tả / ví dụ / bật-tắt đều đổi prompt 03 → cần chạy kiểm tra ổn định 3 lần (NFR8, tab Nhật ký).'),
          mistakesEl()));
        ctx.tex(el);
      }
      function mistakesEl() {
        if (!list) return null;
        if (list === 'loading') return h('p', { class: 'muted' }, 'Đang tải lỗi mang mã ' + cd + '…');
        if (list.err) return h('p', { class: 'cat-err', role: 'alert' }, list.err);
        return h('div', { class: 'stack', style: 'gap:6px' }, h('h3', null, 'Lỗi mang mã ' + cd), ui.annot(['table:mistake']),
          h('p', { class: 'small muted' }, list.length + ' lỗi đang có hiệu lực (view mistake_current: không tính lỗi bị bỏ hoặc đã bị thay).' + (list.length ? ' Bấm một dòng để mở buổi học.' : '')),
          ui.table({
            columns: [
              { label: 'HS', render: function (r) { return h('b', { class: 'mono' }, r.student_code); } },
              { label: 'Buổi', render: function (r) { return ui.fmt.date(r.held_on); } },
              { label: 'Bài', render: function (r) { return h('span', { class: 'mono' }, r.ref); } },
              { label: 'Bước', key: 'step_idx', align: 'right' },
              { label: 'Trạng thái', render: function (r) { return ui.status(r.status); } },
              { label: 'Mô tả', render: function (r) { return h('span', { class: 'cat-w' }, r.description); } }
            ],
            rows: list, empty: 'Chưa có lỗi nào mang mã này.',
            onRow: function (r) { ctx.nav('session', { thread: r.thread_id }); }
          }));
      }
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
          el.append(field('Nhóm (5 nhóm cố định)', F.cat), field('Tên con (chữ thường, số, dấu _)', F.sub), h('p', null, 'Mã sẽ là: ', F.code),
            field('Mô tả', F.desc), field('Ví dụ (không bắt buộc) — đưa vào prompt 03', F.ex), F.err);
        },
        actions: [{ label: 'Thêm mã', kind: 'primary', onClick: function (close) {
          var sub = F.sub.value.trim(), c = F.cat.value + '.' + sub, ds = F.desc.value.trim();
          var bad = !/^[a-z][a-z0-9_]*$/.test(sub) ? 'Tên con bắt đầu bằng chữ thường a–z, chỉ gồm a–z, số và dấu _ (VD: sign_rule).' : !ds ? 'Cần mô tả.' : null;
          if (bad) { F.err.textContent = bad; return; }
          F.err.textContent = 'Đang lưu…';
          return api.send('POST', '/catalog/error-codes', { code: c, category: F.cat.value, description: ds, example: F.ex.value.trim() || null }).then(function (r) {
            close(); S.sub = 'codes';
            promptChanged('Đã thêm ' + c, r.prompt_version);
            return wrote('Danh mục: thêm mã lỗi ' + c, [['error_code', 1]]);
          }, function (e) { F.err.textContent = errText(e); });
        } }, { label: 'Huỷ' }]
      });
    }

    /* ---------- Nhập từ CSV ---------- */
    function openImport() {
      var box = function (name, cols) {
        var ta = h('textarea', { rows: 6, class: 'mono cat-csv', placeholder: 'hoặc dán nội dung ' + name + '…', 'aria-label': 'Nội dung ' + name });
        var fi = h('input', { type: 'file', accept: '.csv,text/csv', 'aria-label': 'Chọn tệp ' + name });
        fi.addEventListener('change', function () {
          var f = fi.files && fi.files[0]; if (!f) return;
          f.text().then(function (t) { ta.value = t; stale(); }, function (e) { err.textContent = 'Không đọc được tệp: ' + errText(e); });
        });
        ta.addEventListener('input', stale);
        return { ta: ta, el: h('div', { class: 'card' }, h('b', { class: 'mono' }, name), h('span', { class: 'small muted' }, cols), fi, ta) };
      };
      var err = errEl(), out = h('div', { class: 'stack' });
      var kc = box('kc.csv', 'code, name, description, parent_code, lop'), pr = box('kc_prereq.csv', 'kc_code, prereq_code');
      function stale() { err.textContent = ''; out.replaceChildren(); }
      function payload() { return { kc_csv: kc.ta.value, prereq_csv: pr.ta.value }; }
      var codes = function (list) { return h('div', { class: 'cat-codes' }, list.map(function (c) { return h('span', { class: 'chip mono' }, c); })); };
      var m = ctx.modal({
        title: 'Nhập danh mục từ CSV', wide: true,
        body: h('div', { class: 'stack' },
          h('p', { class: 'small muted' }, 'Chọn tệp hoặc dán nội dung (UTF-8, có BOM cũng được). Có thể nhập một trong hai tệp. Nhập chỉ thêm / sửa — không xoá KC hay quan hệ nào.'),
          h('div', { class: 'grid cols-2' }, kc.el, pr.el), err, out),
        actions: [{ label: 'Xem trước', kind: 'primary', onClick: preview }, { label: 'Đóng' }]
      });
      function preview() {
        var b = payload();
        if (!b.kc_csv.trim() && !b.prereq_csv.trim()) { stale(); err.textContent = 'Chọn tệp hoặc dán nội dung ít nhất một tệp CSV.'; return; }
        stale(); out.append(h('p', { class: 'muted' }, 'Đang so với tutor.db…'));
        return api.send('POST', '/catalog/import/preview', b).then(function (r) {
          var n = r.new_kc.length + r.changed_kc.length + r.new_prereq.length;
          var block = function (title, list) { return list.length ? h('div', { class: 'stack', style: 'gap:4px' }, h('b', null, title + ' (' + list.length + ')'), codes(list)) : null; };
          out.replaceChildren(h('div', { class: 'stack' },
            h('p', null, h('b', null, 'So với tutor.db: '), r.new_kc.length + ' KC mới · ' + r.changed_kc.length + ' KC đổi · ' + r.new_prereq.length + ' quan hệ mới'),
            n ? null : h('p', { class: 'muted' }, 'CSV khớp tutor.db — không có gì để áp dụng.'),
            block('KC mới', r.new_kc), block('KC đổi', r.changed_kc),
            block('Quan hệ mới (KC cần biết trước)', r.new_prereq.map(function (x) { return x[0] + ' ← ' + x[1]; })),
            n ? h('div', null, ui.button('Áp dụng ' + n + ' thay đổi', function () { return apply(b); }, { kind: 'primary' })) : null));
        }, function (e) { out.replaceChildren(); err.textContent = errText(e); });
      }
      function apply(b) {
        return api.send('POST', '/catalog/import', b).then(function (res) {
          m.close();
          return wrote('Nhập danh mục từ CSV', [['kc', res.new_kc.length], ['kc', res.changed_kc.length + ' dòng đổi'], ['kc_prereq', res.new_prereq.length]]);
        }, function (e) { out.replaceChildren(); err.textContent = errText(e); });
      }
    }
  }
})();
