/* Tab Ngân hàng bài: filter + browse, problem view, edit skill / level / rubric. Every server string goes through U.esc / U.texHtml. */
(function () {
  var PAGE = 12, LEVELS = ['dễ', 'vừa', 'khó'], NO_LEVEL = 'chưa có mức';
  var SAVE_ERR = {
    validation_error: 'Chưa lưu được: kiểm tra lại kỹ năng và cách chấm, mỗi ý cần có chữ và điểm lớn hơn 0.',
    not_found: 'Bài này không còn trong ngân hàng.'
  };
  var panel = null, kcs = [], counts = null, topicsDrawn = false;
  var items = [], total = 0, bankTotal = 0, failed = false, seq = 0, openSeq = 0, timer = 0;
  var f = { q: '', topic: '', grade: '', kc: '', level: '' };
  var cur = null, edit = null;

  function $(id) { return document.getElementById(id); }
  function pts(n) { return String(n).replace('.', ',') + ' điểm'; }
  function levelChip(lv) { return lv ? '<span class="chip">' + U.esc(lv) + '</span>' : '<span class="chip chip-warn">' + NO_LEVEL + '</span>'; }
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
    $('b-head').textContent = bankTotal + ' bài · ' + Object.keys(counts || {}).length + ' chủ đề';
    if (added) grid.insertAdjacentHTML('beforeend', added.map(cardHTML).join(''));
    else grid.innerHTML = items.map(cardHTML).join('');
    U.typeset(grid);
    $('b-foot').innerHTML = failed
      ? '<div class="empty"><p>Không tải được danh sách bài.</p><button type="button" class="btn" data-act="b-reload">Tải lại</button></div>'
      : !items.length ? '<div class="empty">Không có bài nào khớp bộ lọc. Thử bỏ bớt điều kiện.</div>'
      : items.length < total ? '<div class="row b-more"><button type="button" class="btn" data-act="b-more">Xem thêm (còn ' + (total - items.length) + ' bài)</button></div>' : '';
    if (added && added.length) grid.querySelector('[data-pid="' + added[0].id + '"] .ref').focus();
  }
  function load(more) {
    clearTimeout(timer);
    var my = ++seq;  // an answer that is not for the latest request is dropped
    return U.api.get('/bank/problems?' + query(more ? items.length : 0)).then(function (r) {
      if (my !== seq) return;
      failed = false; total = r.total; counts = r.topic_counts;
      if (!f.q.trim() && !f.topic && !f.grade && !f.kc && !f.level) bankTotal = r.total;
      items = more ? items.concat(r.items) : r.items;
      drawTopics(); drawList(more ? r.items : null);
    }, function () {
      if (my !== seq) return;
      if (more) { U.toast('Không tải thêm được. Thử lại sau.', 'warn'); return; }
      failed = true; items = []; total = 0; drawList();
    });
  }
  function loadCatalog() {
    return U.api.get('/catalog/kc').then(function (k) { kcs = k; drawTopics(); drawSkills(); });
  }
  function drawTopics() {
    if (topicsDrawn || !kcs.length || !counts) return;
    topicsDrawn = true;
    $('b-topic').innerHTML = '<option value="">Tất cả chủ đề</option>' + kcs.filter(function (k) { return k.parent_id == null && counts[k.id]; })
      .map(function (k) { return '<option value="' + k.id + '">' + U.esc(k.name) + '</option>'; }).join('');
  }
  function drawSkills() {
    var t = +f.topic, g = +f.grade;
    var list = kcs.filter(function (k) { return k.parent_id != null && (!t || k.parent_id === t) && (!g || k.lop === g); });
    if (f.kc && !list.some(function (k) { return String(k.id) === f.kc; })) f.kc = '';
    $('b-skill').innerHTML = '<option value="">Tất cả kỹ năng</option>' + list.map(function (k) { return '<option value="' + k.id + '">' + U.esc(k.name) + '</option>'; }).join('');
    $('b-skill').value = f.kc;
  }
  function syncControls() {
    $('b-q').value = f.q; $('b-topic').value = f.topic; $('b-grade').value = f.grade; $('b-skill').value = f.kc;
    panel.querySelectorAll('[data-act="b-level"]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.v === f.level ? 'true' : 'false'); });
  }
  function shell() {
    return '<div class="page"><div class="page-head"><div><h1>Ngân hàng bài</h1><p id="b-head"></p></div></div>' +
      '<section class="section"><div class="filters">' +
      '<label class="field wide"><span>Tìm</span><input type="search" id="b-q" autocomplete="off" placeholder="Mã bài, chữ trong đề hoặc tên kỹ năng"></label>' +
      '<label class="field"><span>Chủ đề</span><select id="b-topic"><option value="">Tất cả chủ đề</option></select></label>' +
      '<label class="field"><span>Lớp</span><select id="b-grade"><option value="">Tất cả</option><option value="8">Lớp 8</option><option value="9">Lớp 9</option></select></label>' +
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
      return k.parent_id != null && (edit.kc.indexOf(k.id) >= 0 || (edit.all ? !p.grade || k.lop <= p.grade : k.parent_id === tid));
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
