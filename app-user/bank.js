/* Tab Ngân hàng bài: browse + filter, problem view, edit skill / level / rubric, "Nạp bài mới" from data/inbox/bank/. */
var BANK = (function () {
  var C = {}, panel = null, f = { q: '', topic: 0, grade: 0, level: '', skill: 0 }, shown = 12, edit = null, imp = null;

  function filtered() {
    var q = U.norm(f.q.trim());
    return A.problems.filter(function (p) {
      if (f.topic && p.topic !== f.topic) return false;
      if (f.grade && p.grade !== f.grade) return false;
      if (f.level && p.level !== f.level) return false;
      if (f.skill && p.skills.indexOf(f.skill) < 0) return false;
      if (q && U.norm(p.ref + ' ' + p.statement + ' ' + p.skills.map(U.skillName).join(' ')).indexOf(q) < 0) return false;
      return true;
    });
  }
  function cardHTML(p) {
    return '<article class="card bcard" data-act="b-open" data-pid="' + p.id + '"><div class="spread"><button type="button" class="ref" style="border:0;background:none;padding:0;cursor:pointer" data-act="b-open" data-pid="' + p.id + '">' + p.ref + '</button>' +
      '<span class="row">' + (S.problemsNew[p.id] ? '<span class="chip chip-info">Mới</span>' : '') + U.diffChip(p.level) + (p.rubric ? '' : '<span class="chip chip-warn">chưa có cách chấm</span>') + '</span></div>' +
      '<div class="small muted">' + U.esc(A.TP[p.topic] ? A.TP[p.topic].name : '') + ' · lớp ' + p.grade + '</div>' +
      '<div class="row">' + p.skills.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(U.skillName(k)) + '</span>'; }).join('') + '</div>' +
      '<div class="clamp">' + U.texHtml(p.statement) + '</div></article>';
  }
  function draw() {
    if (!panel) return;
    var list = filtered(), topics = A.topics.filter(function (t) { return A.problems.some(function (p) { return p.topic === t.id; }); });
    var skills = A.skills.filter(function (k) { return (!f.topic || k.topic === f.topic) && (!f.grade || k.grade === f.grade); });
    panel.innerHTML = '<div class="page"><div class="page-head"><div><h1>Ngân hàng bài</h1><p>' + A.problems.length + ' bài · ' + topics.length + ' chủ đề</p></div>' +
      '<button type="button" class="btn btn-primary" data-act="imp-open">Nạp bài mới</button></div>' +
      '<section class="section"><div class="filters">' +
      '<label class="field wide"><span>Tìm</span><input type="search" id="b-q" placeholder="Mã bài, chữ trong đề hoặc tên kỹ năng" value="' + U.esc(f.q) + '"></label>' +
      '<label class="field"><span>Chủ đề</span><select id="b-topic"><option value="0">Tất cả chủ đề</option>' + topics.map(function (t) { return '<option value="' + t.id + '"' + (f.topic === t.id ? ' selected' : '') + '>' + U.esc(t.name) + '</option>'; }).join('') + '</select></label>' +
      '<label class="field"><span>Lớp</span><select id="b-grade"><option value="0">Tất cả</option><option value="8"' + (f.grade === 8 ? ' selected' : '') + '>Lớp 8</option><option value="9"' + (f.grade === 9 ? ' selected' : '') + '>Lớp 9</option></select></label>' +
      '<label class="field"><span>Kỹ năng</span><select id="b-skill"><option value="0">Tất cả kỹ năng</option>' + skills.map(function (k) { return '<option value="' + k.id + '"' + (f.skill === k.id ? ' selected' : '') + '>' + U.esc(k.name) + '</option>'; }).join('') + '</select></label>' +
      '<div class="field"><span>Mức</span><div class="seg" role="group" aria-label="Mức độ khó">' + [['', 'Tất cả'], ['de', 'dễ'], ['vua', 'vừa'], ['kho', 'khó']].map(function (l) {
        return '<button type="button" class="seg-btn" data-act="b-level" data-v="' + l[0] + '" aria-pressed="' + (f.level === l[0]) + '">' + l[1] + '</button>'; }).join('') + '</div></div>' +
      '</div><div class="spread"><p><b>' + list.length + ' bài</b> khớp</p><button type="button" class="btn btn-ghost btn-sm" data-act="b-clear">Xoá lọc</button></div></section>' +
      (list.length ? '<div class="grid">' + list.slice(0, shown).map(cardHTML).join('') + '</div>' : '<div class="empty">Không có bài nào khớp bộ lọc. Thử bỏ bớt điều kiện.</div>') +
      (list.length > shown ? '<div class="row" style="justify-content:center"><button type="button" class="btn" data-act="b-more">Xem thêm (còn ' + (list.length - shown) + ' bài)</button></div>' : '') + '</div>';
    U.typeset(panel);
  }

  // ---- problem view + edit ----
  function rubricHTML(p) {
    if (!p.rubric || !p.rubric.length) return '<p class="muted">Chưa có cách chấm. Trợ lý sẽ soạn bản nháp khi chấm bài này lần đầu, hoặc thầy/cô soạn ngay ở nút Sửa.</p>';
    var tot = p.rubric.reduce(function (n, r) { return n + r.pts; }, 0);
    return '<ol class="stack" style="gap:6px;margin:0;padding-left:20px">' + p.rubric.map(function (r) { return '<li><span class="tex">' + U.esc(r.text) + '</span> <span class="chip">' + r.pts + ' điểm</span></li>'; }).join('') + '</ol><p class="small muted">Tổng ' + tot + ' ý.</p>';
  }
  C.openProblem = function (pid) {
    var p = A.P[pid];
    U.modal({ title: 'Bài ' + p.ref, wide: true, body:
      '<div class="row">' + U.diffChip(p.level) + '<span class="chip">lớp ' + p.grade + '</span><span class="chip">' + U.esc(A.TP[p.topic] ? A.TP[p.topic].name : '') + '</span>' + (S.problemsNew[p.id] ? '<span class="chip chip-info">Mới</span>' : '') + '</div>' +
      '<div class="field"><span>Kỹ năng</span><div class="row">' + (p.skills.length ? p.skills.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(U.skillName(k)) + '</span>'; }).join('') : '<span class="chip chip-warn">chưa gắn kỹ năng</span>') + '</div></div>' +
      '<h3>Đề bài</h3>' + U.texHtml(p.statement) +
      '<details><summary><b>Lời giải</b></summary><div class="sol">' + p.solution.map(function (s) { return U.texHtml(s); }).join('') + '</div></details>' +
      '<h3>Cách chấm</h3>' + rubricHTML(p) + '<p class="small muted">Nguồn: ' + U.esc(p.source) + '</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button><button type="button" class="btn btn-primary" data-act="b-edit" data-pid="' + p.id + '">Sửa kỹ năng, mức, cách chấm</button>' });
  };
  function editBody() {
    var p = A.P[edit.pid], sk = A.skills.filter(function (k) { return k.topic === p.topic || edit.skills.indexOf(k.id) >= 0 || (edit.all && k.grade <= p.grade); });
    return '<p><span class="ref">' + p.ref + '</span></p>' +
      '<div class="field"><span>Kỹ năng của bài</span><div class="skill-checks">' + sk.map(function (k) {
        return '<label><input type="checkbox" data-sk="' + k.id + '"' + (edit.skills.indexOf(k.id) >= 0 ? ' checked' : '') + '> <span>' + U.esc(k.name) + '</span></label>'; }).join('') + '</div>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-act="e-all" style="align-self:flex-start">' + (edit.all ? 'Chỉ kỹ năng cùng chủ đề' : 'Hiện kỹ năng chủ đề khác') + '</button></div>' +
      '<div class="field"><span>Mức</span><div class="seg" role="group" aria-label="Mức">' + [['de', 'dễ'], ['vua', 'vừa'], ['kho', 'khó']].map(function (l) {
        return '<button type="button" class="seg-btn" data-act="e-level" data-v="' + l[0] + '" aria-pressed="' + (edit.level === l[0]) + '">' + l[1] + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><span>Cách chấm (mỗi ý một dòng)</span><div class="rub">' + edit.rubric.map(function (r, i) {
        return '<div class="rub-row"><span class="muted small" style="padding-top:7px">Ý ' + (i + 1) + '</span><textarea rows="2" data-rt="' + i + '" aria-label="Nội dung ý ' + (i + 1) + '">' + U.esc(r.text) + '</textarea>' +
          '<input type="number" min="0" max="10" data-rp="' + i + '" value="' + r.pts + '" aria-label="Điểm ý ' + (i + 1) + '"><button type="button" class="icon-btn icon-btn-sm" data-act="e-rdel" data-i="' + i + '" aria-label="Bỏ ý ' + (i + 1) + '">×</button></div>';
      }).join('') + '</div><button type="button" class="btn btn-sm" data-act="e-radd" style="align-self:flex-start">+ Thêm ý</button></div>' +
      '<p class="small muted">Thay đổi áp dụng cho các lần chấm từ nay; kết quả đã lưu giữ nguyên.</p><p class="small" id="e-err" style="color:var(--crit)" hidden></p>';
  }
  function readEdit() {
    var m = document.getElementById('modal-body'); if (!m || !edit) return;
    edit.skills = Array.prototype.map.call(m.querySelectorAll('[data-sk]:checked'), function (x) { return +x.dataset.sk; });
    edit.rubric.forEach(function (r, i) { var t = m.querySelector('[data-rt="' + i + '"]'), pt = m.querySelector('[data-rp="' + i + '"]'); if (t) r.text = t.value; if (pt) r.pts = +pt.value || 0; });
  }
  function showEdit() {
    U.modal({ title: 'Sửa bài ' + A.P[edit.pid].ref, wide: true, body: editBody(),
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="e-save">Lưu thay đổi</button>' });
  }
  function rerenderEdit() { var m = document.getElementById('modal-body'); m.innerHTML = editBody(); }
  ACT['b-open'] = function (el, ev) { if (ev) ev.stopPropagation(); C.openProblem(+el.dataset.pid); };
  ACT['b-edit'] = function (el) { var p = A.P[+el.dataset.pid]; edit = { pid: p.id, skills: p.skills.slice(), level: p.level || 'vua', rubric: (p.rubric || []).map(function (r) { return { text: r.text, pts: r.pts }; }), all: false }; showEdit(); };
  ACT['e-all'] = function () { readEdit(); edit.all = !edit.all; rerenderEdit(); };
  ACT['e-level'] = function (el) { readEdit(); edit.level = el.dataset.v; rerenderEdit(); };
  ACT['e-radd'] = function () { readEdit(); edit.rubric.push({ text: '', pts: 1 }); rerenderEdit(); var t = document.querySelector('[data-rt="' + (edit.rubric.length - 1) + '"]'); if (t) t.focus(); };
  ACT['e-rdel'] = function (el) { readEdit(); edit.rubric.splice(+el.dataset.i, 1); rerenderEdit(); };
  ACT['e-save'] = function () {
    readEdit();
    var err = document.getElementById('e-err');
    if (!edit.skills.length) { err.hidden = false; err.textContent = 'Chọn ít nhất 1 kỹ năng.'; return; }
    var rub = edit.rubric.filter(function (r) { return r.text.trim(); });
    var p = A.P[edit.pid];
    p.skills = edit.skills; p.level = edit.level; p.rubric = rub.length ? rub : null;
    U.closeModal(); draw(); U.toast('Đã lưu bài ' + p.ref + '. Áp dụng cho các lần chấm từ nay.');
  };

  // ---- import (G2) ----
  function needsPick(p) { return !p.skills.length || !p.level; }
  function pickOf(p) {  // the teacher's choice, starting from whatever label the file already had
    if (!imp.pick[p.id]) imp.pick[p.id] = { skill: p.skills[0] || null, level: p.level || '' };
    return imp.pick[p.id];
  }
  function impBody() {
    if (imp.stage === 'files') {
      return '<p>File .tex trong thư mục <b>data/inbox/bank/</b>:</p><div class="stack" style="gap:6px">' + A.bankInbox.map(function (b, i) {
        return '<div class="file-row"><span>📄 <b>' + U.esc(b.file) + '</b><br><span class="small muted">' + U.esc(b.title) + (b.imported ? ' · đã nạp ' + U.d(b.imported) : '') + '</span></span>' +
          '<button type="button" class="btn btn-sm' + (b.imported ? '' : ' btn-primary') + '" data-act="imp-read" data-i="' + i + '"' + (b.imported ? ' disabled' : '') + '>' + (b.imported ? 'Đã nạp' : 'Đọc file') + '</button></div>';
      }).join('') + '</div><p class="small muted">Mỗi bài trong file là một khối <span class="mono">\\begin{problem}[mã]</span>. Nạp bài không dùng trợ lý AI.</p>';
    }
    var b = A.bankInbox[imp.file];
    if (imp.stage === 'reading') return '<p class="typing">Đang đọc ' + U.esc(b.file) + '</p>';
    if (imp.stage === 'error') return '<div class="callout callout-crit"><p><b>Không nạp được ' + U.esc(b.file) + '.</b> ' + U.esc(b.error) + '</p></div><div class="row"><button type="button" class="btn" data-act="imp-back">Chọn file khác</button></div>';
    if (imp.stage === 'done') return '<div class="callout callout-ok"><p><b>Đã thêm ' + b.problems.length + ' bài vào ngân hàng</b> (chủ đề ' + U.esc(A.TP[b.problems[0].topic].name) + ').</p></div><div class="row"><button type="button" class="btn btn-primary" data-act="imp-show">Xem các bài mới</button></div>';
    var needs = b.problems.filter(needsPick);
    var rows = imp.only ? needs : b.problems;
    var sk = A.skills.filter(function (k) { return k.topic === b.problems[0].topic; });
    return '<p><b>' + U.esc(b.file) + '</b>: ' + b.problems.length + ' bài · ' + (b.problems.length - needs.length) + ' bài đã có kỹ năng và mức · <b>' + needs.length + ' bài cần thầy/cô chọn</b>.</p>' +
      '<div class="seg" role="group" aria-label="Lọc bài"><button type="button" class="seg-btn" data-act="imp-only" data-v="1" aria-pressed="' + imp.only + '">Cần chọn (' + needs.length + ')</button><button type="button" class="seg-btn" data-act="imp-only" data-v="0" aria-pressed="' + !imp.only + '">Tất cả (' + b.problems.length + ')</button></div>' +
      '<div class="stack" style="gap:8px">' + rows.map(function (p) {
        var need = needsPick(p), pk = pickOf(p), done = pk.skill && (pk.level || pk.touched);
        var miss = [!p.skills.length ? 'kỹ năng' : '', !p.level ? 'mức' : ''].filter(Boolean).join(' và ');
        return '<div class="imp-row' + (need && !pk.skill ? ' needs' : '') + '"><div class="row"><span class="ref">' + p.ref + '</span>' + (need ? (done ? '<span class="chip chip-ok">đã chọn</span>' : '<span class="chip chip-warn">thiếu ' + miss + '</span>') : U.diffChip(p.level)) + '</div>' +
          (p.unknownLabel ? '<p class="small m-check">Nhãn kỹ năng ghi trong file không có trong danh mục — chọn lại kỹ năng.</p>' : '') + U.texHtml(p.statement) +
          (need ? '<div class="row"><label class="field grow"><span>Kỹ năng</span><select data-imp-skill="' + p.id + '"><option value="">— chọn kỹ năng —</option>' + sk.map(function (k) { return '<option value="' + k.id + '"' + (pk.skill === k.id ? ' selected' : '') + '>' + U.esc(k.name) + '</option>'; }).join('') + '</select></label>' +
            '<div class="field"><span>Mức</span><div class="seg" role="group" aria-label="Mức bài ' + p.ref + '">' + [['de', 'dễ'], ['vua', 'vừa'], ['kho', 'khó'], ['', 'để trống']].map(function (l) {
              return '<button type="button" class="seg-btn" data-act="imp-level" data-pid="' + p.id + '" data-v="' + l[0] + '" aria-pressed="' + ((pk.level || '') === l[0]) + '">' + l[1] + '</button>'; }).join('') + '</div></div></div>'
            : '<div class="row">' + p.skills.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(U.skillName(k)) + '</span>'; }).join('') + '</div>') + '</div>';
      }).join('') + '</div><p class="small muted">Bỏ trống mức thì tính như mức vừa. Bài mới chưa có cách chấm — trợ lý soạn bản nháp khi chấm lần đầu.</p>';
  }
  function impFoot() {
    if (imp.stage !== 'preview') return '<button type="button" class="btn" data-act="modal-close">Đóng</button>';
    var left = A.bankInbox[imp.file].problems.filter(function (p) { return needsPick(p) && !pickOf(p).skill; }).length;
    return '<button type="button" class="btn" data-act="modal-close">Thôi</button><span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="imp-save"' + (left ? ' disabled' : '') + '>Lưu vào ngân hàng</button>' +
      (left ? '<span class="reason">Còn ' + left + ' bài chưa chọn kỹ năng.</span>' : '') + '</span>';
  }
  function showImp() {
    var body = document.getElementById('modal-body');
    if (body && imp.shown) { body.innerHTML = impBody(); document.getElementById('modal-foot').innerHTML = impFoot(); U.typeset(body); return; }
    imp.shown = true;
    U.modal({ title: 'Nạp bài mới', wide: true, body: impBody(), foot: impFoot() });
    var m = document.getElementById('modal-body');
    m.addEventListener('change', function (ev) {
      var id = ev.target.dataset.impSkill; if (!id) return;
      (imp.pick[id] = imp.pick[id] || {}).skill = +ev.target.value || null; showImp();
      var s = document.querySelector('[data-imp-skill="' + id + '"]'); if (s) s.focus();
    });
  }
  ACT['imp-open'] = function () { imp = { stage: 'files', file: null, pick: {}, only: true, shown: false }; showImp(); };
  ACT['imp-back'] = function () { imp.stage = 'files'; showImp(); };
  ACT['imp-read'] = function (el) {
    imp.file = +el.dataset.i; imp.stage = 'reading'; showImp();
    setTimeout(function () { imp.stage = A.bankInbox[imp.file].error ? 'error' : 'preview'; showImp(); }, 500);
  };
  ACT['imp-only'] = function (el) { imp.only = el.dataset.v === '1'; showImp(); };
  ACT['imp-level'] = function (el) { var pk = pickOf(A.bankInbox[imp.file].problems.find(function (p) { return p.id === +el.dataset.pid; })); pk.level = el.dataset.v; pk.touched = true; showImp(); };
  ACT['imp-save'] = function () {
    var b = A.bankInbox[imp.file];
    b.problems.forEach(function (p) {
      if (needsPick(p)) { var pk = pickOf(p); p.skills = p.skills.length ? p.skills : [pk.skill]; p.level = pk.level || null; }
      A.problems.push(p); A.P[p.id] = p; A.REF[p.ref] = p; S.problemsNew[p.id] = true;
    });
    b.imported = U.today; imp.stage = 'done'; showImp(); draw();
    U.toast('Đã thêm ' + b.problems.length + ' bài vào ngân hàng.');
  };
  ACT['imp-show'] = function () { var b = A.bankInbox[imp.file]; U.closeModal(); f = { q: '', topic: b.problems[0].topic, grade: 0, level: '', skill: 0 }; shown = 12; U.tab('ngan-hang'); draw(); };

  ACT['b-level'] = function (el) { f.level = el.dataset.v; shown = 12; draw(); };
  ACT['b-clear'] = function () { f = { q: '', topic: 0, grade: 0, level: '', skill: 0 }; shown = 12; draw(); };
  ACT['b-more'] = function () { shown += 12; draw(); };

  TABS['ngan-hang'] = {
    render: function (p) {
      panel = p; draw();
      p.addEventListener('change', function (ev) {
        var id = ev.target.id;
        if (id === 'b-topic') { f.topic = +ev.target.value; f.skill = 0; }
        else if (id === 'b-grade') { f.grade = +ev.target.value; f.skill = 0; }
        else if (id === 'b-skill') f.skill = +ev.target.value;
        else return;
        shown = 12; draw();
      });
      var t; p.addEventListener('input', function (ev) {
        if (ev.target.id !== 'b-q') return;
        f.q = ev.target.value; clearTimeout(t);
        t = setTimeout(function () { var pos = ev.target.selectionStart; shown = 12; draw(); var n = panel.querySelector('#b-q'); n.focus(); n.setSelectionRange(pos, pos); }, 250);
      });
    },
    onShow: function () { draw(); }
  };
  return C;
})();
