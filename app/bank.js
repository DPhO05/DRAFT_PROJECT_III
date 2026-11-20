/* Tab Ngân hàng bài: filter + browse, problem view, edit skill / level / rubric, import a .tex (G2). Every server string goes through U.esc / U.texHtml. */
(function () {
  var PAGE = 12, LEVELS = ['dễ', 'vừa', 'khó'], NO_LEVEL = 'chưa có mức';
  var SAVE_ERR = {
    validation_error: 'Chưa lưu được: kiểm tra lại kỹ năng và cách chấm, mỗi ý cần có chữ và điểm lớn hơn 0.',
    not_found: 'Bài này không còn trong ngân hàng.'
  };
  var panel = null, kcs = [], counts = null, topicsDrawn = false;
  var items = [], listKey = '', total = 0, bankTotal = 0, failed = false, seq = 0, openSeq = 0, timer = 0;
  var f = { q: '', topic: '', grade: '', kc: '', level: '' };
  var cur = null, edit = null;

  function $(id) { return document.getElementById(id); }
  function pts(n) { return String(n).replace('.', ',') + ' điểm'; }
  function levelChip(lv) { return lv ? '<span class="chip">' + U.esc(lv) + '</span>' : '<span class="chip chip-warn">' + NO_LEVEL + '</span>'; }
  function isSkill(k) { return k.parent_id != null || !kcs.some(function (c) { return c.parent_id === k.id; }); }  // a topic with no skills under it is a skill itself
  function kcChips(list) {
    return list.length ? list.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(k.name) + '</span>'; }).join('') : '<span class="chip chip-warn">chưa gắn kỹ năng</span>';
  }

  // ---- list ----
  function query(offset) {
    var p = new URLSearchParams({ view: 'teacher', limit: PAGE, offset: offset });
    Object.keys(f).forEach(function (k) { var v = k === 'q' ? f[k].trim() : f[k]; if (v) p.set(k, v); });
    return p.toString();
  }
  function cardHTML(p) {
    var where = [p.topic ? p.topic.name : '', p.grade ? 'lớp ' + p.grade : ''].filter(Boolean).join(' · ');
    return '<article class="card bcard" data-act="b-open" data-pid="' + p.id + '"><div class="spread">' +
      '<button type="button" class="ref ref-btn" data-act="b-open" data-pid="' + p.id + '">' + U.esc(p.ref) + '</button>' +
      '<span class="row">' + (p.is_new ? '<span class="chip chip-info">Mới</span>' : '') + levelChip(p.level) + (p.has_rubric ? '' : '<span class="chip chip-warn">chưa có cách chấm</span>') + '</span></div>' +
      '<div class="small muted">' + U.esc(where) + '</div><div class="row">' + kcChips(p.kcs) + '</div>' +
      '<div class="clamp">' + U.texHtml(p.statement_latex) + '</div></article>';
  }
  function drawList(added) {
    var grid = $('b-grid');
    $('b-count').innerHTML = failed ? '' : '<b>' + total + ' bài</b> khớp';
    if (added) grid.insertAdjacentHTML('beforeend', added.map(cardHTML).join(''));
    else grid.innerHTML = items.map(cardHTML).join('');
    U.typeset(grid);
    $('b-foot').innerHTML = failed
      ? '<div class="empty"><p>Không tải được danh sách bài.</p><button type="button" class="btn" data-act="b-reload">Tải lại</button></div>'
      : !items.length ? '<div class="empty">Không có bài nào khớp bộ lọc. Thử bỏ bớt điều kiện.</div>'
      : items.length < total ? '<div class="row b-more"><button type="button" class="btn" data-act="b-more">Xem thêm (còn ' + (total - items.length) + ' bài)</button></div>' : '';
    if (added && added.length) grid.querySelector('[data-pid="' + added[0].id + '"] .ref').focus();
  }
  function drawHead() { $('b-head').textContent = bankTotal + ' bài · ' + Object.keys(counts || {}).length + ' chủ đề'; }
  function load(more) {
    var key = query(0);
    if (more && key !== listKey) return;  // the list on screen is for older filters: the pending answer or search replaces it
    clearTimeout(timer);
    var plain = !f.q.trim() && !f.topic && !f.grade && !f.kc && !f.level, my = ++seq;  // an answer that is not for the latest request is dropped
    return U.api.get('/bank/problems?' + query(more ? items.length : 0)).then(function (r) {
      counts = r.topic_counts;  // bank-wide, so a dropped answer still tells the truth
      if (plain) bankTotal = r.total;
      drawHead(); drawTopics();
      if (my !== seq) return;
      failed = false; total = r.total; listKey = key;
      items = more ? items.concat(r.items) : r.items;
      drawList(more ? r.items : null);
    }, function () {
      if (my !== seq) return;
      if (more) { U.toast('Không tải thêm được. Thử lại sau.', 'warn'); return; }
      failed = true; items = []; total = 0; listKey = ''; drawList();
    });
  }
  function loadCatalog() {
    return U.api.get('/catalog/kc').then(function (k) { kcs = k; drawGrades(); drawTopics(); drawSkills(); });
  }
  function drawGrades() {
    var gs = kcs.map(function (k) { return k.lop; }).filter(function (l, i, a) { return l != null && a.indexOf(l) === i; }).sort(function (a, b) { return a - b; });
    $('b-grade').innerHTML = '<option value="">Tất cả</option>' + gs.map(function (l) { return '<option value="' + l + '">Lớp ' + l + '</option>'; }).join('');
    $('b-grade').value = f.grade;
  }
  function drawTopics() {
    if (topicsDrawn || !kcs.length || !counts) return;
    topicsDrawn = true;
    $('b-topic').innerHTML = '<option value="">Tất cả chủ đề</option>' + kcs.filter(function (k) { return k.parent_id == null && counts[k.id]; })
      .map(function (k) { return '<option value="' + k.id + '">' + U.esc(k.name) + '</option>'; }).join('');
    $('b-topic').value = f.topic;
  }
  function drawSkills() {
    var t = +f.topic, g = +f.grade;
    var list = kcs.filter(function (k) { return isSkill(k) && (!t || k.parent_id === t || k.id === t) && (!g || k.lop === g); });
    if (f.kc && !list.some(function (k) { return String(k.id) === f.kc; })) f.kc = '';
    $('b-skill').innerHTML = '<option value="">Tất cả kỹ năng</option>' + list.map(function (k) { return '<option value="' + k.id + '">' + U.esc(k.name) + '</option>'; }).join('');
    $('b-skill').value = f.kc;
  }
  function syncControls() {
    $('b-q').value = f.q; $('b-topic').value = f.topic; $('b-grade').value = f.grade; $('b-skill').value = f.kc;
    panel.querySelectorAll('[data-act="b-level"]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.v === f.level ? 'true' : 'false'); });
  }
  function shell() {
    return '<div class="page"><div class="page-head"><div><h1>Ngân hàng bài</h1><p id="b-head"></p></div><button type="button" class="btn btn-primary" data-act="b-import">Nạp bài mới</button></div>' +
      '<section class="section"><div class="filters">' +
      '<label class="field wide"><span>Tìm</span><input type="search" id="b-q" autocomplete="off" placeholder="Mã bài, chữ trong đề hoặc tên kỹ năng"></label>' +
      '<label class="field"><span>Chủ đề</span><select id="b-topic"><option value="">Tất cả chủ đề</option></select></label>' +
      '<label class="field"><span>Lớp</span><select id="b-grade"><option value="">Tất cả</option></select></label>' +
      '<label class="field"><span>Kỹ năng</span><select id="b-skill"><option value="">Tất cả kỹ năng</option></select></label>' +
      '<div class="field wide"><span>Mức</span><div class="seg" role="group" aria-label="Mức độ khó">' +
      [['', 'Tất cả'], ['dễ', 'dễ'], ['vừa', 'vừa'], ['khó', 'khó'], ['none', NO_LEVEL]].map(function (l) {
        return '<button type="button" class="seg-btn" data-act="b-level" data-v="' + l[0] + '" aria-pressed="' + (l[0] === f.level) + '">' + l[1] + '</button>'; }).join('') + '</div></div>' +
      '</div><div class="spread"><p id="b-count"></p><button type="button" class="btn btn-ghost btn-sm" data-act="b-clear">Xoá lọc</button></div></section>' +
      '<div class="grid" id="b-grid"></div><div id="b-foot"><p class="muted">Đang tải…</p></div></div>';
  }

  // ---- view ----
  function rubricHTML(r) {
    if (!r || !r.items.length) return '<p class="muted">Chưa có cách chấm — trợ lý soạn bản nháp khi chấm lần đầu</p>';
    return '<ul class="rub-list">' + r.items.map(function (it, i) {
      return '<li><span class="rub-n muted small">Ý ' + (i + 1) + '</span>' + U.texHtml(it.text) + '<span class="chip">' + U.esc(pts(it.points)) + '</span></li>';
    }).join('') + '</ul><p class="small muted">Tổng ' + r.items.length + ' ý.</p>';
  }
  function showProblem(p) {
    cur = p;
    U.modal({ title: 'Bài ' + U.esc(p.ref), wide: true, body:
      '<div class="row">' + levelChip(p.level) + (p.grade ? '<span class="chip">lớp ' + U.esc(p.grade) + '</span>' : '') + (p.topic ? '<span class="chip">' + U.esc(p.topic.name) + '</span>' : '') + (p.is_new ? '<span class="chip chip-info">Mới</span>' : '') + '</div>' +
      '<div class="field"><span>Kỹ năng</span><div class="row">' + kcChips(p.kcs) + '</div></div>' +
      '<h3>Đề bài</h3>' + U.texHtml(p.statement_latex) +
      (p.solution_steps.length ? '<details><summary><b>Lời giải</b></summary><div class="sol">' + p.solution_steps.map(U.texHtml).join('') + '</div></details>' : '') +
      '<h3>Cách chấm</h3>' + rubricHTML(p.rubric) + '<p class="small muted">Nguồn: ' + U.esc(p.source) + '</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button><button type="button" class="btn btn-primary" data-act="b-edit">Sửa kỹ năng, mức, cách chấm</button>' });
  }

  // ---- edit ----
  function editBody() {
    var p = edit.p, tid = p.topic && p.topic.id;
    var sk = kcs.filter(function (k) {
      return edit.kc.indexOf(k.id) >= 0 || (isSkill(k) && (edit.all ? !p.grade || k.lop <= p.grade : k.parent_id === tid));
    });
    return '<p><span class="ref">' + U.esc(p.ref) + '</span></p>' +
      '<div class="field"><span>Kỹ năng của bài</span><div class="skill-checks">' + sk.map(function (k) {
        return '<label><input type="checkbox" data-sk="' + k.id + '"' + (edit.kc.indexOf(k.id) >= 0 ? ' checked' : '') + '> <span>' + U.esc(k.name) + '</span></label>'; }).join('') + '</div>' +
      (tid ? '<button type="button" class="btn btn-ghost btn-sm" data-act="e-all" style="align-self:flex-start">' + (edit.all ? 'Chỉ kỹ năng cùng chủ đề' : 'Hiện kỹ năng chủ đề khác') + '</button>' : '') + '</div>' +
      '<div class="field"><span>Mức</span><div class="seg" role="group" aria-label="Mức">' + LEVELS.map(function (lv) {
        return '<button type="button" class="seg-btn" data-act="e-level" data-v="' + lv + '" aria-pressed="' + (edit.level === lv) + '">' + lv + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><span>Cách chấm (mỗi ý một dòng)</span><div class="rub">' + edit.rubric.map(function (r, i) {
        return '<div class="rub-row"><span class="muted small" style="padding-top:7px">Ý ' + (i + 1) + '</span><textarea rows="3" data-rt="' + i + '" aria-label="Nội dung ý ' + (i + 1) + '">' + U.esc(r.text) + '</textarea>' +
          '<input type="number" min="0" step="0.5" data-rp="' + i + '" value="' + U.esc(r.pts) + '" aria-label="Điểm ý ' + (i + 1) + '"><button type="button" class="icon-btn icon-btn-sm" data-act="e-rdel" data-i="' + i + '" aria-label="Bỏ ý ' + (i + 1) + '">×</button></div>';
      }).join('') + '</div><button type="button" class="btn btn-sm" data-act="e-radd" style="align-self:flex-start">+ Thêm ý</button></div>' +
      '<p class="small muted">Áp dụng cho các lần chấm từ nay; kết quả đã lưu giữ nguyên.</p><p class="small err" id="e-err" role="alert" hidden></p>';
  }
  function readEdit() {
    var m = $('modal-body');
    edit.kc = Array.prototype.map.call(m.querySelectorAll('[data-sk]:checked'), function (x) { return +x.dataset.sk; });
    edit.rubric.forEach(function (r, i) { r.text = m.querySelector('[data-rt="' + i + '"]').value; r.pts = Number(m.querySelector('[data-rp="' + i + '"]').value) || 0; });
  }
  function rerender(focusSel) {
    var m = $('modal-body'); m.innerHTML = editBody();
    var n = focusSel && m.querySelector(focusSel); if (n) n.focus();
  }
  function problemWith(rub) {
    if (!edit.kc.length) return 'Chọn ít nhất 1 kỹ năng.';
    if (rub.some(function (r) { return !(r.pts > 0); })) return 'Mỗi ý cần có điểm lớn hơn 0.';
    if (!rub.length && edit.p.rubric) return 'Cách chấm cần ít nhất 1 ý.';
    return '';
  }
  function replaceCard(v) {
    var at = items.findIndex(function (x) { return x.id === v.id; }), node = $('b-grid').querySelector('.bcard[data-pid="' + v.id + '"]');
    if (at < 0 || !node) return;
    items[at] = v;  // shortcut: the card stays in the list even if it no longer matches the filters, until the next filter change
    node.outerHTML = cardHTML(v);
    U.typeset($('b-grid'));
    $('b-grid').querySelector('.bcard[data-pid="' + v.id + '"] .ref').focus();
  }

  ACT['b-open'] = function (el) {
    var my = ++openSeq;
    U.api.get('/bank/problems/' + el.dataset.pid).then(function (p) { if (my === openSeq) showProblem(p); },
      function () { U.toast('Không mở được bài này. Thử lại sau.', 'warn'); });
  };
  window.BANK = { open: function (id) { U.tab('ngan-hang'); ACT['b-open']({ dataset: { pid: id } }); } };  // chat's "Mở trong Ngân hàng"
  ACT['b-edit'] = function () {
    (kcs.length ? Promise.resolve() : loadCatalog()).then(function () {
      var p = cur;
      edit = { p: p, kc: p.kcs.map(function (k) { return k.id; }), level: p.level, all: !p.topic,
        rubric: p.rubric ? p.rubric.items.map(function (r) { return { text: r.text, pts: r.points }; }) : [] };
      U.modal({ title: 'Sửa bài ' + U.esc(p.ref), wide: true, body: editBody(),
        foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="e-save">Lưu thay đổi</button>' });
    }, function () { U.toast('Không mở được danh sách kỹ năng. Thử lại sau.', 'warn'); });
  };
  ACT['e-all'] = function () { readEdit(); edit.all = !edit.all; rerender('[data-act="e-all"]'); };
  ACT['e-level'] = function (el) { readEdit(); edit.level = el.dataset.v; rerender('[data-act="e-level"][data-v="' + el.dataset.v + '"]'); };
  ACT['e-radd'] = function () { readEdit(); edit.rubric.push({ text: '', pts: 1 }); rerender('[data-rt="' + (edit.rubric.length - 1) + '"]'); };
  ACT['e-rdel'] = function (el) { readEdit(); edit.rubric.splice(+el.dataset.i, 1); rerender('[data-act="e-radd"]'); };
  ACT['e-save'] = function (btn) {
    readEdit();
    var p = edit.p, err = $('e-err'), body = {};
    var rub = edit.rubric.filter(function (r) { return r.text.trim(); });
    var was = p.rubric ? p.rubric.items.map(function (r) { return { text: r.text, pts: r.points }; }) : [];
    var bad = problemWith(rub);
    if (bad) { err.textContent = bad; err.hidden = false; return; }
    if (edit.kc.slice().sort().join() !== p.kcs.map(function (k) { return k.id; }).sort().join()) body.kc_ids = edit.kc;
    if (edit.level && edit.level !== p.level) body.level = edit.level;
    if (JSON.stringify(rub) !== JSON.stringify(was)) body.rubric_items = rub.map(function (r) { return { text: r.text, points: r.pts }; });
    if (!Object.keys(body).length) { U.closeModal(); U.toast('Không có thay đổi nào.', 'info'); return; }
    btn.disabled = true;
    U.api.send('PATCH', '/bank/problems/' + p.id, body).then(function (v) {
      U.closeModal(); replaceCard(v);
      U.toast('Đã lưu bài ' + v.ref + '. Áp dụng cho các lần chấm từ nay.');
    }, function (e) {
      btn.disabled = false; err.textContent = SAVE_ERR[e.code] || 'Chưa lưu được. Thử lại sau.'; err.hidden = false;
    });
  };

  // ---- import (G2): pick a file, read it, fill the missing skills, save ----
  var imp = null;

  function live(s) { return s === imp && s.root.isConnected; }
  function impDraw(s, focusSel) {
    var body = $('modal-body');
    body.innerHTML = impBody(s); drawFoot(s); U.typeset(body);
    var n = focusSel && body.querySelector(focusSel); if (n) n.focus();
  }
  function drawFoot(s) { $('modal-foot').innerHTML = impFoot(s); }
  function skillOptions(sel) {
    var opt = function (k) { return '<option value="' + k.id + '"' + (k.id === sel ? ' selected' : '') + '>' + U.esc(k.name) + '</option>'; };
    return kcs.filter(function (t) { return t.parent_id == null; }).map(function (t) {
      var ks = kcs.filter(function (k) { return k.parent_id === t.id; });
      return ks.length ? '<optgroup label="' + U.esc(t.name) + '">' + ks.map(opt).join('') + '</optgroup>' : opt(t);
    }).join('');
  }
  function filesHTML(s) {
    if (s.files === null) return '<p class="muted" role="status">Đang tải…</p>';
    if (!s.files) return '<p class="err" role="alert">Không đọc được thư mục bài. Thử lại sau.</p>';
    var dir = '<b>' + U.esc(s.dir) + '/inbox/bank/</b>';
    if (!s.files.length) return '<div class="empty">Chưa có file .tex nào trong thư mục ' + dir + '.</div>';
    return '<p>File .tex trong thư mục ' + dir + ':</p><div class="stack" style="gap:6px">' + s.files.map(function (b, i) {
      var off = b.status === 'imported' || b.status === 'empty';
      return '<div class="file-row"><span class="grow"><b>' + U.esc(b.file) + '</b><br><span class="small muted">' + U.esc(b.title || 'Chưa có tiêu đề') + ' · ' + b.n_problems + ' bài' +
        (b.status === 'partly' ? ' (' + b.n_new + ' bài mới)' : '') + (b.imported_at ? ' · đã nạp ' + U.esc(U.d(b.imported_at)) : '') + '</span></span>' +
        '<button type="button" class="btn btn-sm' + (off ? '' : ' btn-primary') + '" data-act="imp-read" data-i="' + i + '"' + (off ? ' disabled' : '') + '>' +
        (b.status === 'imported' ? 'Đã nạp' : b.status === 'empty' ? 'Không có bài' : 'Đọc file') + '</button></div>';
    }).join('') + '</div>';
  }
  function warned(it) { return it.unknown_label && !it.invalid && !it.existing; }
  function rowHTML(s, it) {
    var ref = it.ref ? U.esc(it.ref) : '(chưa có mã)';
    if (it.invalid) return '<div class="imp-row"><div class="row"><span class="ref">' + ref + '</span><span class="chip chip-crit">bỏ qua</span><span class="small muted">' + U.esc(it.invalid) +
      '</span></div><div class="clamp">' + U.texHtml(it.statement_latex) + '</div></div>';
    var d = s.dec[it.ref] || {}, edKc = it.needs.indexOf('kc') >= 0, edLv = it.needs.indexOf('level') >= 0, need = edKc || edLv;
    var pickKc = edKc || warned(it);
    var noKc = edKc && !(d.kc_ids && d.kc_ids.length), noLv = edLv && !('level' in d);
    var tag = it.existing ? '<span class="chip">đã có trong ngân hàng</span>' : !need ? levelChip(it.level)
      : noKc || noLv ? '<span class="chip chip-warn">thiếu ' + [noKc ? 'kỹ năng' : '', noLv ? 'mức' : ''].filter(Boolean).join(' và ') + '</span>' : '<span class="chip chip-ok">đã chọn</span>';
    return '<div class="imp-row' + (noKc || noLv ? ' needs' : '') + '" data-row="' + U.esc(it.ref) + '"><div class="row"><span class="ref">' + ref + '</span>' + tag + '</div>' +
      (warned(it) ? '<p class="small"><span class="chip chip-warn chip-wrap">Nhãn kỹ năng ghi trong file không có trong danh mục — chọn lại kỹ năng</span></p>' : '') +
      (need ? U.texHtml(it.statement_latex) : '<div class="clamp">' + U.texHtml(it.statement_latex) + '</div>') +
      '<div class="row">' + (edKc || d.kc_ids ? '' : kcChips(it.kcs)) +
        (pickKc ? '<label class="field grow"><span>Kỹ năng</span><select data-imp-kc="' + U.esc(it.ref) + '"><option value="">' + (edKc ? '— chọn kỹ năng —' : '— giữ như đã đọc được —') + '</option>' + skillOptions(d.kc_ids && d.kc_ids[0]) + '</select></label>' : '') +
        (edLv ? '<div class="field"><span>Mức</span><div class="seg" role="group" aria-label="Mức bài ' + U.esc(it.ref) + '">' + LEVELS.concat('').map(function (l) {
          return '<button type="button" class="seg-btn" data-act="imp-level" data-ref="' + U.esc(it.ref) + '" data-v="' + l + '" aria-pressed="' + ('level' in d && (d.level || '') === l) + '">' + (l || 'để trống') + '</button>'; }).join('') + '</div></div>'
          : need ? levelChip(it.level) : '') + '</div></div>';
  }
  function previewHTML(s) {
    var c = s.card, need = c.items.filter(function (i) { return i.needs.length || warned(i); }), rows = s.only ? need : c.items;
    var extra = [c.n_existing ? c.n_existing + ' bài đã có trong ngân hàng, bỏ qua' : '', c.n_invalid ? c.n_invalid + ' khối không đọc được, bỏ qua' : ''].filter(Boolean).join(' · ');
    return '<p><b>' + U.esc(c.file) + '</b>: ' + c.n_total + ' bài · ' + c.n_ready + ' đã có kỹ năng và mức · <b>' + c.n_need + ' cần chọn</b></p>' + (extra ? '<p class="small muted">' + extra + '</p>' : '') +
      '<div class="seg" role="group" aria-label="Lọc bài" style="align-self:flex-start">' + [['1', 'Cần chọn (' + need.length + ')'], ['0', 'Tất cả (' + c.items.length + ')']].map(function (o) {
        return '<button type="button" class="seg-btn" data-act="imp-only" data-v="' + o[0] + '" aria-pressed="' + ((o[0] === '1') === s.only) + '">' + o[1] + '</button>'; }).join('') + '</div>' +
      '<div class="stack" style="gap:8px">' + (rows.length ? rows.map(function (it) { return rowHTML(s, it); }).join('') : '<div class="empty">Không còn bài nào cần chọn.</div>') + '</div>' +
      '<p class="small muted">Để trống mức thì tính như mức vừa.</p>';
  }
  function savedHTML(s) {
    var r = s.card.receipt || { added: 0, skipped_existing: 0 }, t = s.card.topic;
    return '<div class="callout callout-ok" role="status"><p><b>Đã thêm ' + r.added + ' bài vào ngân hàng</b>' + (t ? ' (chủ đề ' + U.esc(t.name) + ')' : '') + '.</p>' +
      (r.skipped_existing ? '<p class="small">' + r.skipped_existing + ' bài đã có trong ngân hàng, bỏ qua.</p>' : '') + '</div>' +
      (r.added && t ? '<div class="row"><button type="button" class="btn btn-primary" data-act="imp-show">Xem các bài mới</button></div>' : '');
  }
  function impBody(s) {
    if (s.stage === 'files') return filesHTML(s);
    if (s.stage === 'reading') return '<p class="muted" role="status">Đang đọc ' + U.esc(s.file) + '…</p>';
    if (s.stage === 'saving') return '<p class="muted" role="status">Đang lưu…</p>';
    if (s.stage === 'error') return '<div class="callout callout-crit" role="alert"><p><b>Không nạp được ' + U.esc(s.file) + '.</b> ' + s.err + '</p></div><div class="row">' + (s.retry ? '<button type="button" class="btn btn-primary" data-act="imp-retry">Thử lại</button><button type="button" class="btn" data-act="imp-drop">Bỏ</button>' : '') + '<button type="button" class="btn" data-act="imp-back">Chọn file khác</button></div>';
    return s.stage === 'saved' ? savedHTML(s) : previewHTML(s);
  }
  function impFoot(s) {
    if (s.stage !== 'preview') return '<button type="button" class="btn" data-act="modal-close">Đóng</button>';
    var why = s.pending > 0 ? 'Còn ' + s.pending + ' bài chưa chọn kỹ năng' : s.putErr ? 'Chưa lưu được lựa chọn. Chọn lại để thử tiếp.' : s.dirty ? 'Đang lưu lựa chọn…' : '';
    return '<button type="button" class="btn" data-act="modal-close">Thôi</button><span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="imp-save"' +
      (s.pending > 0 || s.dirty ? ' disabled' : '') + '>Lưu vào ngân hàng</button>' + (why ? '<span class="reason">' + why + '</span>' : '') + '</span>';
  }

  function impFiles(s) {
    s.stage = 'files'; s.files = null; impDraw(s);
    Promise.all([U.api.get('/bank/inbox'), U.api.get('/backup')]).catch(function () { return [false]; }).then(function (r) {
      if (!live(s) || s.stage !== 'files') return;
      s.files = r[0]; s.dir = r[1] && r[1].data_dir; impDraw(s, '[data-act="imp-read"]:not(:disabled)');
    });
  }
  function impFail(s, why, retry) { s.stage = 'error'; s.err = why; s.retry = retry || ''; impDraw(s, '[data-act="imp-retry"], [data-act="imp-back"]'); }
  function impPreview(s, c) {
    (kcs.length ? Promise.resolve() : loadCatalog()).then(function () {
      if (!live(s)) return;
      s.card = c; s.stage = 'preview'; s.only = c.n_need > 0;
      s.pending = c.items.filter(function (i) { return i.needs.indexOf('kc') >= 0; }).length;
      impDraw(s, '[data-act="imp-only"][aria-pressed="true"]');
    }, function () { if (live(s)) impFail(s, 'Không tải được danh sách kỹ năng. Thử lại sau.'); });
  }
  function savedAnswers(t) {
    var d = t.decisions_json ? JSON.parse(t.decisions_json) : {}, it = d && d.items === undefined ? {} : d && d.items;
    if (!it || typeof it !== 'object' || Array.isArray(it)) throw new Error('decisions');
    return it;
  }
  function impSaved(s, c) {
    s.card = c; s.stage = 'saved'; impDraw(s, '[data-act="imp-show"]');
    bankTotal += (c.receipt || {}).added || 0; topicsDrawn = false; load();
  }
  function impPoll(s) {
    U.api.get('/threads/' + s.tid + '?view=teacher').then(function (t) { return t.card; }, function (e) { return e.status === 404 ? { stage: 'gone' } : null; }).then(function (c) {
      if (!live(s)) return;
      var st = c && c.stage;
      if (st === 'preview' && s.stage === 'reading') return impPreview(s, c);
      if (st === 'saved') return impSaved(s, c);
      if (st === 'failed') return (c.items || []).length ? impFail(s, 'Chưa lưu được vào ngân hàng.', 'saving') : impFail(s, 'Không đọc được nội dung file.', 'reading');
      if (st === 'gone') return impFail(s, 'Việc nạp này không còn nữa. Chọn lại file.');
      setTimeout(function () { if (live(s)) impPoll(s); }, 1000);
    });
  }
  function impPut(s) {
    var my = ++s.putSeq;  // only the newest change decides the count and the button
    s.dirty = true; clearTimeout(s.timer); drawFoot(s);
    s.timer = setTimeout(function () {
      U.api.send('PUT', '/threads/' + s.tid + '/decisions', { items: s.dec }).then(function (r) {
        if (my !== s.putSeq) return;
        s.dirty = false; s.putErr = false; s.pending = r.pending; if (live(s)) drawFoot(s);
      }, function () {
        if (my !== s.putSeq) return;
        s.putErr = true; if (live(s)) drawFoot(s);
      });
    }, 500);
  }
  function impChoose(s, ref, edit, focusSel) {
    edit(s.dec[ref] = s.dec[ref] || {});
    var rowAt = function () { return Array.prototype.find.call($('modal-body').querySelectorAll('[data-row]'), function (n) { return n.dataset.row === ref; }); };
    rowAt().outerHTML = rowHTML(s, s.card.items.find(function (i) { return i.ref === ref; }));
    var row = rowAt(); U.typeset(row); row.querySelector(focusSel).focus();
    impPut(s);
  }

  ACT['b-import'] = function () {
    var s = imp = { stage: 'files', files: null, only: true, dec: {}, pending: 0, dirty: false, putErr: false, putSeq: 0, timer: 0 };
    s.root = U.modal({ title: 'Nạp bài mới', wide: true, body: impBody(s), foot: impFoot(s) });
    s.root.addEventListener('change', function (ev) {
      var ref = ev.target.dataset.impKc, v = ev.target.value;
      if (ref != null) impChoose(s, ref, function (d) { if (v) d.kc_ids = [+v]; else delete d.kc_ids; }, '[data-imp-kc]');
    });
    impFiles(s);
  };
  ACT['imp-read'] = function (el) {
    var s = imp, b = s.files[+el.dataset.i];
    s.file = b.file; s.stage = 'reading'; s.dec = {}; impDraw(s);
    U.api.send('POST', '/bank/imports', { file: b.file }).then(function (r) {
      if (!live(s)) return;
      s.tid = r.thread_id;
      // a thread kept from an earlier visit has saved answers and a PUT replaces them all, so an unreadable copy stops the flow
      var saved = r.status === 'running' ? Promise.resolve({}) : U.api.get('/threads/' + r.thread_id).then(savedAnswers);
      saved.then(function (dec) { if (live(s)) { s.dec = dec; impPoll(s); } },
        function () { if (live(s)) impFail(s, 'Không đọc được lựa chọn đã lưu lần trước. Thử lại sau.'); });
    }, function (e) { if (live(s)) impFail(s, e.status === 422 ? U.esc(e.message) : 'Thử lại sau.'); });
  };
  ACT['imp-back'] = function () { impFiles(imp); };
  ACT['imp-retry'] = function (btn) {
    var s = imp;
    btn.disabled = true;
    U.api.send('POST', '/threads/' + s.tid + '/resume').then(function () {
      if (live(s)) { s.stage = s.retry; impDraw(s); impPoll(s); }
    }, function () {
      if (live(s)) { btn.disabled = false; U.toast('Chưa thử lại được. Thử lại sau.', 'warn'); }
    });
  };
  ACT['imp-drop'] = function (btn) {
    var s = imp;
    btn.disabled = true;
    U.api.send('POST', '/threads/' + s.tid + '/cancel').then(function () { if (live(s)) impFiles(s); }, function (e) {
      if (!live(s)) return;
      if (e.status === 404) { impFiles(s); return; }  // already gone: the file list is where the teacher wants to be
      btn.disabled = false; U.toast('Chưa bỏ được. Thử lại sau.', 'warn');
    });
  };
  ACT['imp-only'] = function (el) { imp.only = el.dataset.v === '1'; impDraw(imp, '[data-act="imp-only"][aria-pressed="true"]'); };
  ACT['imp-level'] = function (el) {
    var v = el.dataset.v;
    impChoose(imp, el.dataset.ref, function (d) { d.level = v || null; }, '[data-act="imp-level"][data-v="' + v + '"]');
  };
  ACT['imp-save'] = function (btn) {
    var s = imp;
    btn.disabled = true;
    U.api.send('POST', '/threads/' + s.tid + '/resume').then(function () {
      if (live(s)) { s.stage = 'saving'; impDraw(s); impPoll(s); }
    }, function (e) {
      if (!live(s)) return;
      var n = e.code === 'undecided_items' && e.detail && e.detail.n;
      if (n) s.pending = n;
      U.toast(n ? 'Còn ' + n + ' bài chưa chọn kỹ năng.' : 'Chưa lưu được vào ngân hàng. Thử lại sau.', 'warn');
      drawFoot(s);
    });
  };
  ACT['imp-show'] = function () {
    var t = imp.card.topic;
    U.closeModal();
    f = { q: '', topic: String(t.id), grade: '', kc: '', level: '' };
    drawSkills(); syncControls(); load();
  };

  // ---- filters ----
  ACT['b-level'] = function (el) { f.level = el.dataset.v; syncControls(); load(); };
  ACT['b-clear'] = function () { f = { q: '', topic: '', grade: '', kc: '', level: '' }; drawSkills(); syncControls(); load(); };
  ACT['b-more'] = function () { load(true); };
  ACT['b-reload'] = function () { if (!kcs.length) loadCatalog().catch(function () { /* the filters stay short until the next try */ }); load(); };

  TABS['ngan-hang'] = {
    render: function (p) {
      panel = p; p.innerHTML = shell();
      p.addEventListener('change', function (ev) {
        var id = ev.target.id;
        if (id === 'b-topic') { f.topic = ev.target.value; drawSkills(); }
        else if (id === 'b-grade') { f.grade = ev.target.value; drawSkills(); }
        else if (id === 'b-skill') f.kc = ev.target.value;
        else return;
        load();
      });
      p.addEventListener('input', function (ev) {
        if (ev.target.id !== 'b-q') return;
        f.q = ev.target.value; clearTimeout(timer); timer = setTimeout(function () { load(); }, 300);
      });
      loadCatalog().catch(function () { /* b-edit asks again */ });
      load();
    }
  };
})();
