/* Tab Học sinh: list (add / edit / archive) + per-student progress page. */
var STU = (function () {
  var C = {}, panel = null, view = 'list', q = '', chartSkill = 'all', showTable = false, showAll = {};

  function draw() {
    if (!panel) return;
    panel.innerHTML = '<div class="page">' + (view === 'list' ? listHTML() : profileHTML(view)) + '</div>';
    U.typeset(panel);
    if (view !== 'list') drawChart();
  }
  function lvCount(sid) {
    var lv = S.levels[sid] || {}, c = { vung: 0, dang: 0, chua: 0 };
    Object.keys(lv).forEach(function (k) { c[lv[k].lv] += 1; }); return c;
  }
  function cardHTML(s) {
    var ses = U.studentSessions(s.id)[0], c = lvCount(s.id), pend = U.pendingJobs(s.id).length;
    return '<article class="card st-card" data-act="st-open" data-sid="' + s.id + '">' +
      '<div class="spread"><h3><button type="button" class="btn-ghost" style="border:0;background:none;padding:0;font:inherit;color:var(--ink);cursor:pointer;text-align:left" data-act="st-open" data-sid="' + s.id + '">' + U.esc(s.name) + '</button></h3>' +
      (pend ? '<span class="chip chip-warn">' + pend + ' bài chờ duyệt</span>' : '') + '</div>' +
      '<p class="small muted">Lớp ' + s.grade + (s.note ? ' · ' + U.esc(s.note) : '') + '</p>' +
      '<p class="small">' + (ses ? 'Buổi gần nhất: <b>' + U.dm(ses.date) + '</b> · ' + U.sessionScore(ses).ten + '/10' : 'Chưa có buổi nào đã chấm') + '</p>' +
      '<div class="row"><span class="chip lv-vung">' + c.vung + ' vững</span><span class="chip lv-dang">' + c.dang + ' đang hình thành</span><span class="chip lv-chua">' + c.chua + ' chưa vững</span></div>' +
      '<div class="row">' + '<button type="button" class="btn btn-sm" data-act="st-edit" data-sid="' + s.id + '">Sửa</button>' +
      '<button type="button" class="btn btn-sm" data-act="st-archive" data-sid="' + s.id + '">Lưu trữ</button></div></article>';
  }
  function listHTML() {
    var act = S.students.filter(function (s) { return !s.archived && (!q || U.norm(s.name).indexOf(U.norm(q)) >= 0); });
    var arch = S.students.filter(function (s) { return s.archived; });
    return '<div class="page-head"><div><h1>Học sinh</h1><p>' + S.students.filter(function (s) { return !s.archived; }).length + ' em đang học</p></div>' +
      '<div class="row"><input type="search" id="st-q" placeholder="Tìm theo tên" aria-label="Tìm học sinh theo tên" value="' + U.esc(q) + '">' +
      '<button type="button" class="btn btn-primary" data-act="st-add">+ Thêm học sinh</button></div></div>' +
      (act.length ? '<div class="grid">' + act.map(cardHTML).join('') + '</div>' : '<div class="empty">Không có học sinh nào' + (q ? ' tên “' + U.esc(q) + '”' : '') + '.</div>') +
      '<section class="section"><div class="section-head"><h2>Đã lưu trữ (' + arch.length + ')</h2></div>' +
      (arch.length ? arch.map(function (s) { return '<div class="spread"><span>' + U.esc(s.name) + ' <span class="muted small">lớp ' + s.grade + '</span></span><button type="button" class="btn btn-sm" data-act="st-unarchive" data-sid="' + s.id + '">Bỏ lưu trữ</button></div>'; }).join('')
        : '<p class="small muted">Em nào nghỉ học thì lưu trữ: dữ liệu vẫn giữ, em không hiện trong danh sách và khi gõ @.</p>') + '</section>';
  }

  function profileHTML(sid) {
    var s = U.student(sid), lv = S.levels[sid] || {}, ses = U.studentSessions(sid), pend = U.pendingJobs(sid);
    var h = '<div><button type="button" class="btn btn-ghost btn-sm" data-act="st-back">← Tất cả học sinh</button></div>' +
      '<div class="page-head"><div><h1>' + U.esc(s.name) + (s.archived ? ' <span class="chip chip-dim">đã lưu trữ</span>' : '') + '</h1><p>Lớp ' + s.grade + (s.note ? ' · ' + U.esc(s.note) : '') + ' · học từ ' + U.d(s.since) + '</p></div>' +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="st-ws" data-sid="' + sid + '">Soạn phiếu với Trợ lý</button>' +
      '<button type="button" class="btn" data-act="st-rep" data-sid="' + sid + '">Làm báo cáo</button>' +
      '<button type="button" class="btn" data-act="st-edit" data-sid="' + sid + '">Sửa</button></div></div>';
    if (pend.length) h += '<div class="callout callout-warn"><div class="spread"><p>Có <b>' + pend.length + ' bài</b> chờ thầy/cô duyệt (' + pend.map(function (j) { return U.dm(A.JOB[j.id].date); }).join(', ') + '). Kết quả các bài này chưa tính vào tiến bộ.</p>' +
      '<button type="button" class="btn btn-sm" data-act="st-job" data-job="' + pend[0].id + '">Duyệt trong Trợ lý</button></div></div>';
    h += '<div class="profile-grid">';
    // progress over time
    var ser = A.series[sid], opts = '<option value="all">Mức chung (mọi kỹ năng)</option>';
    if (ser) Object.keys(ser.skills).sort(function (a, b) { return U.skillName(+a).localeCompare(U.skillName(+b), 'vi'); }).forEach(function (k) {
      opts += '<option value="' + k + '"' + (String(chartSkill) === k ? ' selected' : '') + '>' + U.esc(U.skillName(+k)) + '</option>';
    });
    h += '<section class="section"><div class="section-head"><h2>Tiến bộ theo thời gian</h2>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-act="st-table" aria-pressed="' + showTable + '">' + (showTable ? 'Xem biểu đồ' : 'Xem dạng bảng') + '</button></div>' +
      (ser && ser.dates.length ? '<label class="field"><span>Xem theo</span><select id="st-chart-skill">' + opts + '</select></label><div class="chart-box" id="st-chart"></div><p class="chart-tip" id="st-tip" aria-live="polite">Rê chuột hoặc Tab vào một điểm để xem mức ở buổi đó.</p>'
        : '<div class="empty">Chưa có buổi nào đã chấm, chưa vẽ được tiến bộ.</div>') + '</section>';
    // skills
    var groups = { vung: [], dang: [], chua: [] };
    Object.keys(lv).forEach(function (k) { groups[lv[k].lv].push(+k); });
    h += '<section class="section"><div class="section-head"><h2>Kỹ năng</h2><span class="small muted">mũi tên: thay đổi ở buổi gần nhất có kỹ năng đó</span></div><div class="lv-groups">' +
      ['vung', 'dang', 'chua'].map(function (g) {
        var list = groups[g].sort(function (a, b) { return (lv[b].last || '').localeCompare(lv[a].last || ''); });
        var lim = showAll[g] ? list.length : 8;
        return '<div class="lv-group g-' + g + '"><h3>' + U.LV[g].charAt(0).toUpperCase() + U.LV[g].slice(1) + ' <span class="muted">(' + list.length + ')</span></h3>' +
          (list.length ? '<ul>' + list.slice(0, lim).map(function (k) { return '<li><span>' + U.esc(U.skillName(k)) + '</span>' + U.chTag(lv[k].ch) + '</li>'; }).join('') + '</ul>' : '<p class="small muted">Chưa có.</p>') +
          (list.length > 8 ? '<button type="button" class="btn btn-ghost btn-sm" data-act="st-more" data-g="' + g + '">' + (showAll[g] ? 'Thu gọn' : 'Xem tất cả ' + list.length) + '</button>' : '') + '</div>';
      }).join('') + '</div></section>';
    // recurring mistakes
    var rec = (A.recurring[sid] || []).slice().sort(function (a, b) { return b.count - a.count || b.last.localeCompare(a.last); });
    var open = rec.filter(function (r) { return !r.resolved; }), done = rec.filter(function (r) { return r.resolved; });
    h += '<section class="section"><div class="section-head"><h2>Lỗi hay lặp lại</h2></div>' +
      (open.length ? '<ul class="stack" style="gap:8px;margin:0;padding-left:18px">' + open.map(function (r) {
        return '<li><b>' + U.esc(U.kindLabel(r.kind)) + '</b> ở phần “' + U.esc(U.skillName(r.skill)) + '” — ' + r.count + ' lần' + (r.count > 1 ? ', từ ' + U.dm(r.first) : '') + ', lần cuối ' + U.dm(r.last) + '</li>';
      }).join('') + '</ul>' : '<p class="muted">Không còn lỗi nào lặp lại.</p>') +
      (done.length ? '<details><summary class="small">Đã sửa được (' + done.length + ')</summary><ul class="small muted">' + done.map(function (r) {
        return '<li>' + U.esc(U.kindLabel(r.kind)) + ' ở “' + U.esc(U.skillName(r.skill)) + '” — hết từ ' + U.dm(r.resolved) + '</li>';
      }).join('') + '</ul></details>' : '') + '<p class="small muted">Một lỗi được tính là đã sửa khi em làm đúng hai lần liên tiếp sau lần sai cuối.</p></section>';
    // sessions
    h += '<section class="section"><div class="section-head"><h2>Các buổi đã chấm (' + ses.length + ')</h2></div>' +
      (ses.length ? '<div class="table-wrap"><table class="tbl"><thead><tr><th>Buổi</th><th class="al-right">Số bài</th><th class="al-right">Điểm</th><th class="al-right">Lỗi</th><th></th></tr></thead><tbody>' +
        ses.map(function (x) { var sc = U.sessionScore(x); return '<tr><td>' + U.wd(x.date) + ' ' + U.d(x.date) + '</td><td class="al-right">' + x.problems.length + '</td><td class="al-right"><b>' + sc.ten + '/10</b></td><td class="al-right">' + U.sessionMistakes(x) + '</td>' +
          '<td class="al-right"><button type="button" class="btn btn-sm" data-act="st-session" data-id="' + x.id + '">Xem bài</button></td></tr>'; }).join('') + '</tbody></table></div>'
        : '<div class="empty">Chưa có buổi nào đã chấm.</div>') + '</section>';
    // worksheets
    var ws = S.worksheets.filter(function (w) { return w.student === sid; }).sort(function (a, b) { return b.date.localeCompare(a.date); });
    h += '<section class="section"><div class="section-head"><h2>Phiếu đã giao (' + ws.length + ')</h2></div>' +
      (ws.length ? ws.map(function (w, i) { return '<div class="spread"><span>Buổi ' + U.d(w.date) + ' · ' + w.items.length + ' bài</span><button type="button" class="btn btn-sm" data-act="st-ws-view" data-sid="' + sid + '" data-date="' + w.date + '" data-i="' + i + '">Xem phiếu</button></div>'; }).join('')
        : '<p class="muted">Chưa giao phiếu nào.</p>') + '</section>';
    // reports
    var reps = S.reports.filter(function (r) { return r.student === sid; });
    h += '<section class="section"><div class="section-head"><h2>Báo cáo đã duyệt (' + reps.length + ')</h2></div>' +
      (reps.length ? reps.map(function (r) { return '<div class="spread"><span>Báo cáo ' + REP.label(r.kind, r.start) + ' · duyệt ' + U.d(r.approved) + '</span><button type="button" class="btn btn-sm" data-act="rep-open" data-id="' + r.id + '">Xem</button></div>'; }).join('')
        : '<p class="muted">Chưa có báo cáo nào được duyệt.</p>') + '</section>';
    return h + '</div>';
  }

  // ---- progress chart: one series, three word bands, no numbers ----
  function drawChart() {
    var box = panel.querySelector('#st-chart'), ser = A.series[view];
    if (!box || !ser) return;
    var vals = chartSkill === 'all' ? ser.all : ser.skills[chartSkill], dates = ser.dates;
    var label = chartSkill === 'all' ? 'Mức chung' : U.skillName(+chartSkill);
    var lvOf = function (v) { return v > 66.7 ? 'vững' : v < 33.3 ? 'chưa vững' : 'đang hình thành'; };
    if (showTable) {
      box.innerHTML = '<div class="table-wrap"><table class="tbl"><caption class="sr-only">' + U.esc(label) + ' theo buổi</caption><thead><tr><th>Buổi</th><th>' + U.esc(label) + '</th></tr></thead><tbody>' +
        dates.map(function (d, i) { return '<tr><td>' + U.d(d) + '</td><td>' + (vals[i] == null ? '<span class="muted">chưa làm</span>' : lvOf(vals[i])) + '</td></tr>'; }).join('') + '</tbody></table></div>';
      return;
    }
    var w = Math.max(280, box.clientWidth), h = 210, L = 104, R = 14, T = 8, B = 26;
    var X = function (i) { return dates.length === 1 ? (L + w - R) / 2 : L + i * (w - L - R) / (dates.length - 1); };
    var Y = function (v) { return T + (100 - v) / 100 * (h - T - B); };
    var s = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="' + U.esc(label) + ' qua ' + dates.length + ' buổi">';
    [[100, 66.7, 'var(--band-3)', 'vững'], [66.7, 33.3, 'var(--band-2)', 'đang hình thành'], [33.3, 0, 'var(--band-1)', 'chưa vững']].forEach(function (b) {
      s += '<rect x="' + L + '" y="' + Y(b[0]) + '" width="' + (w - L - R) + '" height="' + (Y(b[1]) - Y(b[0])) + '" fill="' + b[2] + '"/>' +
        '<text class="band-label" x="' + (L - 8) + '" y="' + ((Y(b[0]) + Y(b[1])) / 2 + 4) + '" text-anchor="end">' + b[3] + '</text>';
    });
    var path = '', pen = false, step = Math.ceil(dates.length / Math.max(2, Math.floor((w - L - R) / 48)));
    dates.forEach(function (d, i) {
      if (i % step === 0 || i === dates.length - 1) s += '<text class="tick" x="' + X(i) + '" y="' + (h - 8) + '" text-anchor="middle">' + U.dm(d) + '</text>';
      if (vals[i] == null) { pen = false; return; }
      path += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(vals[i]).toFixed(1); pen = true;
    });
    s += '<path class="cline" d="' + path + '"/>';
    dates.forEach(function (d, i) {
      if (vals[i] == null) return;
      var tip = U.d(d) + ': ' + lvOf(vals[i]);
      s += '<circle class="chit" cx="' + X(i) + '" cy="' + Y(vals[i]) + '" r="12" tabindex="0" data-tip="' + U.esc(tip) + '"><title>' + U.esc(tip) + '</title></circle>' +
        '<circle class="cdot" cx="' + X(i) + '" cy="' + Y(vals[i]) + '" r="4.5" pointer-events="none"/>';
    });
    box.innerHTML = s + '</svg>';
  }
  C.redrawChart = function () { if (panel && view !== 'list') drawChart(); };

  // ---- modals ----
  function sessionModal(id) {
    var x = S.sessions.find(function (s) { return String(s.id) === String(id); }), st = U.student(x.student), sc = U.sessionScore(x);
    var body = '<p><b>' + sc.ten + '/10</b> <span class="muted">(' + sc.score + '/' + sc.max + ' ý đúng) · ' + x.problems.length + ' bài · ' + U.sessionMistakes(x) + ' lỗi</span></p>' +
      x.problems.map(function (p, i) {
        var q = A.P[p.pid] || {}, hit = p.mistakes.map(function (m) { return m.step; });
        return '<div class="gprob"><div class="gprob-head"><div class="row"><b>Bài ' + (i + 1) + '</b><span class="ref">' + (q.ref || '') + '</span><span class="chip">' + p.score + '/' + p.max + ' ý</span></div></div><div class="gprob-body">' +
          '<details><summary class="small">Đề bài</summary>' + U.texHtml(q.statement || '') + '</details>' +
          '<div class="work"><div class="small muted">Bài làm của em</div>' + p.steps.map(function (s, k) { return '<div class="wstep' + (hit.indexOf(k + 1) >= 0 ? ' hit' : '') + '"><span class="small muted">Bước ' + (k + 1) + '</span>' + U.texHtml(s) + '</div>'; }).join('') + '</div>' +
          (p.mistakes.length ? p.mistakes.map(function (m) {
            return '<div class="mistake d-ok"><div class="m-title">' + U.esc(U.kindLabel(m.kind)) + '</div><div class="small muted">Bước ' + m.step + ' · phần “' + U.esc(U.skillName(m.skill)) + '”</div>' +
              (m.desc ? '<div class="tex">' + U.esc(m.desc) + '</div>' : '') + (m.evidence ? U.texHtml(m.evidence) : '') + (m.note ? '<p class="small">Ghi chú của thầy/cô: ' + U.esc(m.note) + '</p>' : '') + '</div>';
          }).join('') : '<p class="muted">Không có lỗi.</p>') + '</div></div>';
      }).join('');
    U.modal({ title: st.short + ' · buổi ' + U.d(x.date), wide: true, body: body, foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  }
  function studentForm(s) {
    U.modal({ title: s ? 'Sửa thông tin học sinh' : 'Thêm học sinh', body:
      '<label class="field"><span>Họ và tên</span><input type="text" id="sf-name" value="' + U.esc(s ? s.name : '') + '" autocomplete="off" required autofocus></label>' +
      '<label class="field"><span>Lớp</span><select id="sf-grade">' + [6, 7, 8, 9, 10, 11, 12].map(function (g) { return '<option' + ((s ? s.grade : 9) === g ? ' selected' : '') + '>' + g + '</option>'; }).join('') + '</select></label>' +
      '<label class="field"><span>Ghi chú (không bắt buộc)</span><textarea id="sf-note" rows="2">' + U.esc(s ? s.note : '') + '</textarea></label>' +
      '<p class="small muted">Tên chỉ lưu trên máy này. Khi hỏi trợ lý, tên được thay bằng mã trước khi gửi đi.</p><p class="small" id="sf-err" style="color:var(--crit)" hidden></p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="st-save" data-sid="' + (s ? s.id : '') + '">' + (s ? 'Lưu thay đổi' : 'Thêm học sinh') + '</button>' });
  }

  ACT['st-open'] = function (el) { view = +el.dataset.sid; chartSkill = 'all'; showTable = false; showAll = {}; draw(); window.scrollTo(0, 0); };
  ACT['st-back'] = function () { view = 'list'; draw(); };
  ACT['st-add'] = function () { studentForm(null); };
  ACT['st-edit'] = function (el) { studentForm(U.student(+el.dataset.sid)); };
  ACT['st-save'] = function (el) {
    var nm = document.getElementById('sf-name').value.trim().replace(/\s+/g, ' '), err = document.getElementById('sf-err');
    if (nm.split(' ').length < 2) { err.hidden = false; err.textContent = 'Nhập đủ họ và tên (ít nhất 2 chữ).'; document.getElementById('sf-name').focus(); return; }
    var g = +document.getElementById('sf-grade').value, note = document.getElementById('sf-note').value.trim();
    if (el.dataset.sid) { var s = U.student(+el.dataset.sid); s.name = nm; s.short = nm.split(' ').pop(); s.grade = g; s.note = note; U.toast('Đã lưu thông tin ' + U.esc(s.short) + '.'); }
    else { S.students.push({ id: S.nextStudentId++, name: nm, short: nm.split(' ').pop(), grade: g, note: note, since: U.today, archived: false }); U.toast('Đã thêm ' + U.esc(nm) + '.'); }
    U.closeModal(); draw();
  };
  ACT['st-archive'] = function (el) {
    var s = U.student(+el.dataset.sid);
    U.confirm('Lưu trữ ' + U.esc(s.name) + '?', 'Dữ liệu của em vẫn giữ nguyên. Em sẽ không hiện trong danh sách và khi gõ @ ở Trợ lý. Bỏ lưu trữ được bất cứ lúc nào.', 'Lưu trữ', function () { s.archived = true; if (view === s.id) view = 'list'; draw(); U.toast('Đã lưu trữ ' + U.esc(s.short) + '.'); });
  };
  ACT['st-unarchive'] = function (el) { var s = U.student(+el.dataset.sid); s.archived = false; draw(); U.toast('Đã đưa ' + U.esc(s.short) + ' về danh sách.'); };
  ACT['st-ws'] = function (el) { var s = U.student(+el.dataset.sid); U.tab('tro-ly'); ACT.ask({ dataset: { q: 'Gợi ý ' + A.settings.n + ' bài cho @' + s.short, sid: String(s.id) } }); };
  ACT['st-rep'] = function (el) { REP.prefill(+el.dataset.sid); };
  ACT['st-job'] = function (el) { CHAT.openJob(el.dataset.job); };
  ACT['st-session'] = function (el) { sessionModal(el.dataset.id); };
  ACT['st-table'] = function () { showTable = !showTable; draw(); };
  ACT['st-more'] = function (el) { showAll[el.dataset.g] = !showAll[el.dataset.g]; draw(); };
  ACT['st-ws-view'] = function (el) {
    var sid = +el.dataset.sid, w = S.worksheets.filter(function (x) { return x.student === sid && x.date === el.dataset.date; }).pop();
    U.modal({ title: 'Phiếu buổi ' + U.d(w.date) + ' · ' + U.esc(U.student(sid).short), wide: true, body: '<ol class="stack" style="padding-left:20px;margin:0">' + w.items.map(function (it) {
      var p = A.P[it.pid]; return '<li><div class="row"><span class="ref">' + p.ref + '</span>' + U.diffChip(p.level) + '<span class="small muted">' + U.esc(it.why) + '</span></div>' + U.texHtml(p.statement) + '</li>';
    }).join('') + '</ol>', foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  };
  C.open = function (sid) { view = sid; chartSkill = 'all'; showTable = false; showAll = {}; U.tab('hoc-sinh'); draw(); };

  TABS['hoc-sinh'] = {
    render: function (p) {
      panel = p; draw();
      p.addEventListener('input', function (ev) {
        if (ev.target.id === 'st-q') { q = ev.target.value; var pos = ev.target.selectionStart; draw(); var n = panel.querySelector('#st-q'); n.focus(); n.setSelectionRange(pos, pos); }
      });
      p.addEventListener('change', function (ev) { if (ev.target.id === 'st-chart-skill') { chartSkill = ev.target.value; drawChart(); } });
      var tip = function (ev) { if (ev.target.classList && ev.target.classList.contains('chit')) { var t = panel.querySelector('#st-tip'); if (t) t.textContent = ev.target.dataset.tip; } };
      p.addEventListener('mouseover', tip); p.addEventListener('focusin', tip);
      var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(C.redrawChart, 120); });
    },
    onShow: function () { draw(); },
    redrawChart: function () { C.redrawChart(); }
  };
  return C;
})();
