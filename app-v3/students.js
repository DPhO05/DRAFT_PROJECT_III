/* Tab Học sinh (api-v3 §4, IA-app §2): the list with add / edit / archive, and one student's profile.
   Levels show as words only; ids, codes and numbers go to the API and never on screen. Server text goes through U.nesc. */
(function () {
  var C = window.CHAT, btn = U.btn, esc = U.nesc;
  var LEVELS = ['vững', 'đang hình thành', 'chưa vững'], CLS = { 'vững': 'vung', 'đang hình thành': 'dang', 'chưa vững': 'chua' };
  var TREND = { 'tiến bộ': ['↑ tiến bộ', 'chip-ok'], 'giữ': ['→ giữ', ''], 'cần ôn': ['↓ cần ôn', 'chip-warn'] };
  var SHOWN = 8, LOADING = '<p class="tool-line" role="status">Đang tải…</p>', FAIL = '<p class="muted">Chưa tải được. Thử lại sau.</p>';

  var panel = null, ready = false, failed = false, rows = [], q = '', seq = 0, want = '';
  var view = 0, prof = null, chartKc = 'all', asTable = false, more = {};  // view = the student whose profile is open, 0 = the list

  function $(id) { return document.getElementById(id); }
  function norm(s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase(); }
  function num(n) { return String(n).replace('.', ','); }
  function live(s) { return !s.archived_at; }
  function find(id) { return rows.find(function (s) { return s.id === id; }); }
  function key(el) { return el.id || [el.tagName, el.dataset.act, el.dataset.sid, el.dataset.g, el.dataset.id, el.dataset.i].join('|'); }
  function sec(title, n, inner, extra) {
    return '<section class="section"><div class="section-head"><h2>' + title + (n == null ? '' : ' (' + n + ')') + '</h2>' + (extra || '') + '</div>' + inner + '</section>';
  }

  // ---- loading ----
  function loadList() {
    return U.api.get('/students?view=teacher&archived=true').then(function (r) {
      rows = r; failed = false;
      r.forEach(function (s) { U.people[s.code] = s.name; });
    }, function () { failed = true; });
  }
  function loadProfile(sid) {
    var get = function (p) { return U.api.get(p).catch(function () { return null; }); };  // null: that section says it did not load
    return Promise.all([get('/students/' + sid + '/profile'), get('/students/' + sid + '/progress'),
      get('/sessions?student=' + sid + '&status=committed&view=teacher'), get('/worksheets?student=' + sid), get('/reports?student=' + sid)]).then(function (r) {
      return r[0] ? { profile: r[0], progress: r[1], sessions: r[2], sheets: r[3], reports: r[4] && r[4].approved } : { gone: true };
    });
  }
  function load() {
    var my = ++seq;  // an answer that is not for the latest load is dropped
    return Promise.all([loadList(), view ? loadProfile(view) : null]).then(function (r) {
      if (my !== seq) return;
      ready = true; prof = r[1]; draw(); want = '';
    });
  }
  function saved() { C.refreshPending(); return load(); }  // the @ list and badge of the Trợ lý tab follow the names

  // ---- list ----
  function cardHTML(s) {
    var ls = s.last_session, n = {}, meta = [s.grade ? 'Lớp ' + s.grade : '', esc(s.note)].filter(Boolean).join(' · ');
    s.level_counts.forEach(function (x) { n[x.level] = x.n; });
    return '<article class="card st-card" data-act="st-open" data-sid="' + s.id + '">' +
      '<div class="spread"><h3><button type="button" class="st-name" data-act="st-open" data-sid="' + s.id + '">' + esc(s.name) + '</button></h3>' +
      (s.pending_grading ? '<span class="chip chip-warn">' + s.pending_grading + ' bài chờ duyệt</span>' : '') + '</div>' +
      (meta ? '<p class="small muted">' + meta + '</p>' : '') +
      '<p class="small">' + (ls ? 'Buổi gần nhất: <b>' + U.dm(ls.held_on) + '</b> · ' + U.score(ls.score, ls.max_score) : 'Chưa có buổi nào đã chấm') + '</p>' +
      '<div class="row">' + LEVELS.map(function (l) { return '<span class="chip lv-' + CLS[l] + '">' + (n[l] || 0) + ' ' + l + '</span>'; }).join('') + '</div>' +
      '<div class="row">' + btn('st-edit', 'Sửa', 'data-sid="' + s.id + '"') + btn('st-archive', 'Lưu trữ', 'data-sid="' + s.id + '"') + '</div></article>';
  }
  function cardsHTML() {
    var list = rows.filter(function (s) { return live(s) && (!q.trim() || norm(s.name).indexOf(norm(q.trim())) >= 0); });
    return list.length ? '<div class="grid">' + list.map(cardHTML).join('') + '</div>'
      : '<div class="empty">Không có học sinh nào' + (q.trim() ? ' tên “' + U.esc(q.trim()) + '”' : '') + '.</div>';
  }
  function archHTML() {
    var arch = rows.filter(function (s) { return !live(s); });
    return '<div class="section-head"><h2>Đã lưu trữ (' + arch.length + ')</h2></div>' + (arch.length ? arch.map(function (s) {
      return '<div class="spread"><span>' + esc(s.name) + (s.grade ? ' <span class="muted small">lớp ' + s.grade + '</span>' : '') + '</span>' +
        btn('st-unarchive', 'Bỏ lưu trữ', 'data-sid="' + s.id + '"') + '</div>';
    }).join('') : '<p class="small muted">Em nào nghỉ học thì lưu trữ: dữ liệu vẫn giữ, em không hiện trong danh sách và khi gõ @.</p>');
  }
  function listHTML() {
    if (failed && !rows.length) return '<div class="empty"><p>Chưa tải được danh sách học sinh.</p>' + btn('st-reload', 'Tải lại') + '</div>';
    return '<div class="page-head"><div><h1 id="st-h1" tabindex="-1">Học sinh</h1><p>' + rows.filter(live).length + ' em đang học</p></div>' +
      '<div class="row"><input type="search" id="st-q" placeholder="Tìm theo tên" aria-label="Tìm học sinh theo tên" autocomplete="off" value="' + U.esc(q) + '">' +
      '<button type="button" class="btn btn-primary" data-act="st-add">+ Thêm học sinh</button></div></div>' +
      '<div id="st-cards">' + cardsHTML() + '</div><section class="section" id="st-arch">' + archHTML() + '</section>';
  }

  // ---- profile ----
  function pendingHTML(list) {
    if (!list.length) return '';
    var days = list.map(function (x) { return x.held_on ? U.dm(x.held_on) : ''; }).filter(Boolean).join(', ');
    return '<div class="callout callout-warn"><div class="spread"><p>Có <b>' + list.length + ' bài</b> chờ thầy/cô duyệt' + (days ? ' (' + days + ')' : '') +
      '. Kết quả các bài này chưa tính vào tiến bộ.</p>' + btn('st-job', 'Duyệt trong Trợ lý', 'data-tid="' + U.esc(list[0].thread_id) + '"') + '</div></div>';
  }
  function chartSec(g, skills) {
    if (!g) return sec('Tiến bộ theo thời gian', null, FAIL);
    if (!g.dates.length) return sec('Tiến bộ theo thời gian', null, '<div class="empty">Chưa có buổi nào đã chấm, chưa vẽ được tiến bộ.</div>');
    var opts = '<option value="all">Mức chung (mọi kỹ năng)</option>' + skills.filter(function (s) { return g.skills[s.kc_id]; })
      .sort(function (a, b) { return a.kc.localeCompare(b.kc, 'vi'); }).map(function (s) {
        return '<option value="' + s.kc_id + '"' + (String(s.kc_id) === chartKc ? ' selected' : '') + '>' + esc(s.kc) + '</option>';
      }).join('');
    return sec('Tiến bộ theo thời gian', null, '<label class="field"><span>Xem theo</span><select id="st-chart-skill">' + opts + '</select></label>' +
      '<div class="chart-box" id="st-chart"></div><p class="chart-tip" id="st-tip" aria-live="polite">Rê chuột hoặc Tab vào một điểm để xem mức ở buổi đó.</p>',
      '<button type="button" class="btn btn-ghost btn-sm" data-act="st-table" aria-pressed="' + asTable + '">' + (asTable ? 'Xem biểu đồ' : 'Xem dạng bảng') + '</button>');
  }
  function skillsSec(skills) {
    return sec('Kỹ năng', null, '<div class="lv-groups">' + LEVELS.map(function (l) {
      var list = skills.filter(function (s) { return s.level === l; }), all = more[CLS[l]];  // the server sends the newest first
      return '<div class="lv-group g-' + CLS[l] + '"><h3>' + l.charAt(0).toUpperCase() + l.slice(1) + ' <span class="muted">(' + list.length + ')</span></h3>' +
        (list.length ? '<ul>' + list.slice(0, all ? list.length : SHOWN).map(function (s) {
          var t = TREND[s.trend] || TREND['giữ'];
          return '<li><span>' + esc(s.kc) + '</span><span class="chip ' + t[1] + '">' + t[0] + '</span></li>';
        }).join('') + '</ul>' : '<p class="small muted">Chưa có.</p>') +
        (list.length > SHOWN ? btn('st-more', all ? 'Thu gọn' : 'Xem tất cả ' + list.length, 'data-g="' + CLS[l] + '"', 'btn-ghost') : '') + '</div>';
    }).join('') + '</div>', '<span class="small muted">mũi tên: thay đổi ở buổi gần nhất có kỹ năng đó</span>');
  }
  function recurSec(rec) {
    var open = rec.filter(function (r) { return !r.resolved_at; }), done = rec.filter(function (r) { return r.resolved_at; });
    return sec('Lỗi hay lặp lại', null, (open.length ? '<ul class="st-list">' + open.map(function (r) {
      return '<li><b>' + esc(r.kind) + '</b> ở phần “' + esc(r.kc) + '” — ' + r.count + ' lần' + (r.count > 1 ? ', từ ' + U.dm(r.first_seen) : '') + ', lần cuối ' + U.dm(r.last_seen) + '</li>';
    }).join('') + '</ul>' : '<p class="muted">' + (done.length ? 'Không còn lỗi nào lặp lại.' : 'Chưa có lỗi nào lặp lại.') + '</p>') +
      (done.length ? '<details><summary class="small">Đã sửa được (' + done.length + ')</summary><ul class="st-list small muted">' + done.map(function (r) {
        return '<li>' + esc(r.kind) + ' ở “' + esc(r.kc) + '” — hết từ ' + U.dm(r.resolved_at) + '</li>';
      }).join('') + '</ul></details>' : '') +
      (rec.length ? '<p class="small muted">Một lỗi được tính là đã sửa khi em làm đúng hai lần liên tiếp sau lần sai cuối.</p>' : ''));
  }
  function sessionsSec(ss) {
    if (!ss) return sec('Các buổi đã chấm', null, FAIL);
    return sec('Các buổi đã chấm', ss.length, ss.length ? '<div class="table-wrap"><table class="tbl"><thead><tr><th>Buổi</th><th class="al-right">Số bài</th><th class="al-right">Điểm</th><th class="al-right">Lỗi</th><th></th></tr></thead><tbody>' +
      ss.map(function (x) {
        return '<tr><td>' + U.wd(x.held_on) + ' ' + U.d(x.held_on) + '</td><td class="al-right">' + x.n_attempts + '</td><td class="al-right"><b>' + U.score(x.score, x.max_score) + '</b></td>' +
          '<td class="al-right">' + x.n_mistakes + '</td><td class="al-right">' + btn('st-session', 'Xem bài', 'data-id="' + x.id + '"') + '</td></tr>';
      }).join('') + '</tbody></table></div>' : '<p class="muted">Chưa có buổi nào đã chấm.</p>');
  }
  function sheetsSec(ws) {
    if (!ws) return sec('Phiếu đã giao', null, FAIL);
    return sec('Phiếu đã giao', ws.length, ws.length ? ws.map(function (w, i) {
      return '<div class="spread st-sheet"><span>Buổi ' + U.d(w.for_date) + ' · ' + w.n_problems + ' bài</span>' + btn('st-ws-view', 'Xem phiếu', 'data-i="' + i + '"') + '</div>';
    }).join('') : '<p class="muted">Chưa có phiếu nào được giao.</p>');
  }
  function repsSec(rs) {
    if (!rs) return sec('Báo cáo đã duyệt', null, FAIL);
    return sec('Báo cáo đã duyệt', rs.length, rs.length ? rs.map(function (r) {
      return '<div class="spread st-report"><span>Báo cáo ' + U.esc(REPORTS.label(r.period_kind, r.period_start)) + ' · duyệt ' + U.esc(U.d(REPORTS.local(r.approved_at))) + '</span>' +
        btn('st-rep-open', 'Xem', 'data-id="' + r.id + '"') + '</div>';
    }).join('') : '<p class="muted">Chưa có báo cáo nào được duyệt.</p>');
  }
  function profileHTML() {
    var back = '<div><button type="button" class="btn btn-ghost btn-sm" data-act="st-back">← Danh sách</button></div>';
    if (!prof) return back + LOADING;
    if (prof.gone) return back + '<div class="empty"><p>Chưa mở được hồ sơ này. Thử lại sau.</p></div>';
    var p = prof.profile, s = p.student, id = 'data-sid="' + s.id + '"';
    return back + '<div class="page-head"><div><h1 id="st-h1" tabindex="-1">' + esc(s.name) + (s.archived_at ? ' <span class="chip chip-dim">đã lưu trữ</span>' : '') + '</h1>' +
      '<p>' + [s.grade ? 'Lớp ' + s.grade : '', esc(s.note), 'Học từ ' + U.d(s.since)].filter(Boolean).join(' · ') + '</p></div><div class="row">' +
      (s.archived_at ? '' : '<button type="button" class="btn btn-primary" data-act="st-ws" ' + id + '>Soạn phiếu với Trợ lý</button><button type="button" class="btn" data-act="st-rep" ' + id + '>Làm báo cáo</button>') +
      '<button type="button" class="btn" data-act="st-edit" ' + id + '>Sửa</button></div></div>' + pendingHTML(p.pending) +
      '<div class="profile-grid">' + chartSec(prof.progress, p.skills) + skillsSec(p.skills) + recurSec(p.recurring) + sessionsSec(prof.sessions) + sheetsSec(prof.sheets) + repsSec(prof.reports) + '</div>';
  }

  // ---- drawing: the whole page, keeping focus on the same button; the search box and the chart redraw alone ----
  function draw(sel) {
    if (!panel) return;
    var a = document.activeElement, k = panel.contains(a) && key(a);
    panel.innerHTML = '<div class="page">' + (!ready ? LOADING : view ? profileHTML() : listHTML()) + '</div>';
    if (prof && prof.profile) drawChart();
    sel = sel || want;
    var n = sel ? panel.querySelector(sel) : k && [].find.call(panel.querySelectorAll('button, select, input'), function (x) { return key(x) === k; });
    if (n) { n.focus({ preventScroll: !sel }); if (sel === want) want = ''; }
  }
  function drawChart() {
    var box = $('st-chart'), g = prof && prof.progress;
    if (!box || !g) return;
    if (chartKc !== 'all' && !g.skills[chartKc]) chartKc = 'all';
    var vals = chartKc === 'all' ? g.all : g.skills[chartKc], dates = g.dates;
    var label = chartKc === 'all' ? 'Mức chung' : esc(prof.profile.skills.find(function (s) { return String(s.kc_id) === chartKc; }).kc);
    if (asTable) {
      box.innerHTML = '<div class="table-wrap"><table class="tbl" aria-label="' + label + ' theo buổi"><thead><tr><th>Buổi</th><th>' + label + '</th></tr></thead><tbody>' +
        dates.map(function (d, i) { return '<tr><td>' + U.d(d) + '</td><td>' + (vals[i] ? vals[i].level : '<span class="muted">chưa làm</span>') + '</td></tr>'; }).join('') + '</tbody></table></div>';
      return;
    }
    var w = Math.max(280, box.clientWidth), h = 210, L = 104, R = 14, T = 8, B = 26;
    var X = function (i) { return dates.length === 1 ? (L + w - R) / 2 : L + i * (w - L - R) / (dates.length - 1); };
    var Y = function (v) { return T + (100 - v) / 100 * (h - T - B); };  // v = pos, 0-100: a place on the chart, not a score
    var s = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" role="group" aria-label="' + label + ' qua ' + dates.length + ' buổi">';
    [[100, 66.7, 'var(--band-3)', 'vững'], [66.7, 33.3, 'var(--band-2)', 'đang hình thành'], [33.3, 0, 'var(--band-1)', 'chưa vững']].forEach(function (b) {
      s += '<rect x="' + L + '" y="' + Y(b[0]) + '" width="' + (w - L - R) + '" height="' + (Y(b[1]) - Y(b[0])) + '" fill="' + b[2] + '"/>' +
        '<text class="band-label" x="' + (L - 8) + '" y="' + ((Y(b[0]) + Y(b[1])) / 2 + 4) + '" text-anchor="end">' + b[3] + '</text>';
    });
    var path = '', pen = false, step = Math.ceil(dates.length / Math.max(2, Math.floor((w - L - R) / 48)));
    dates.forEach(function (d, i) {
      if (i % step === 0 || i === dates.length - 1) s += '<text class="tick" x="' + X(i) + '" y="' + (h - 8) + '" text-anchor="middle">' + U.dm(d) + '</text>';
      if (!vals[i]) { pen = false; return; }
      path += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(vals[i].pos).toFixed(1); pen = true;
    });
    s += '<path class="cline" d="' + path + '"/>';
    dates.forEach(function (d, i) {
      if (!vals[i]) return;
      var tip = U.dm(d) + ': ' + vals[i].level;
      s += '<circle class="chit" cx="' + X(i) + '" cy="' + Y(vals[i].pos) + '" r="12" tabindex="0" role="img" data-tip="' + tip + '"><title>' + tip + '</title></circle>' +
        '<circle class="cdot" cx="' + X(i) + '" cy="' + Y(vals[i].pos) + '" r="4.5" pointer-events="none"/>';
    });
    box.innerHTML = s + '</svg>';
  }

  // ---- modals ----
  function sessionModal(x) {
    var body = '<p><b>' + U.score(x.score, x.max_score) + '</b> <span class="muted">(' + num(x.score) + '/' + num(x.max_score) + ' ý đúng) · ' + x.attempts.length + ' bài · ' + x.n_mistakes + ' lỗi</span></p>' +
      x.attempts.map(function (a) {
        var hit = a.mistakes.map(function (m) { return m.step_idx; });
        return '<div class="gprob"><div class="gprob-head"><div class="row"><b>Bài ' + a.seq + '</b><span class="ref">' + U.esc(a.ref) + '</span><span class="chip">' + num(a.score) + '/' + num(a.max_score) + ' ý</span></div></div><div class="gprob-body">' +
          '<details><summary class="small">Đề bài</summary>' + U.texHtml(a.statement_latex) + '</details>' +
          '<div class="work"><div class="small muted">Bài làm của em</div>' + a.steps.map(function (st) {
            return '<div class="wstep' + (hit.indexOf(st.idx) >= 0 ? ' hit' : '') + '"><span class="small muted">Bước ' + st.idx + '</span>' + U.texHtml(st.latex) + '</div>';
          }).join('') + '</div>' +
          (a.mistakes.length ? a.mistakes.map(function (m) {
            var where = [m.step_idx != null ? 'Bước ' + m.step_idx : '', m.kc ? 'phần “' + esc(m.kc.name) + '”' : ''].filter(Boolean).join(' · ');
            return '<div class="mistake d-accept"><div class="m-title">' + esc(m.kind) + '</div>' + (where ? '<div class="small muted">' + where + '</div>' : '') +
              (m.description ? '<div class="tex">' + esc(m.description) + '</div>' : '') + (m.evidence_latex ? U.texHtml(m.evidence_latex) : '') +
              (m.teacher_note ? '<p class="small">Ghi chú của thầy/cô: ' + esc(m.teacher_note) + '</p>' : '') + '</div>';
          }).join('') : '<p class="muted">Không có lỗi.</p>') + '</div></div>';
      }).join('');
    U.modal({ title: esc(U.who(x.student_id)) + ' · buổi ' + U.d(x.held_on), wide: true, body: body, foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  }
  function studentForm(s) {
    var g = s ? s.grade : 9;
    U.modal({ title: s ? 'Sửa thông tin học sinh' : 'Thêm học sinh', body:
      '<label class="field"><span>Họ và tên</span><input type="text" id="sf-name" value="' + U.esc(s ? s.name : '') + '" autocomplete="off" required autofocus></label>' +
      '<label class="field"><span>Lớp</span><select id="sf-grade">' + (g ? '' : '<option value="" selected>Chưa ghi</option>') + [6, 7, 8, 9, 10, 11, 12].map(function (x) {
        return '<option' + (g === x ? ' selected' : '') + '>' + x + '</option>';
      }).join('') + '</select></label>' +
      '<label class="field"><span>Ghi chú (không bắt buộc)</span><textarea id="sf-note" rows="2">' + U.esc(s ? s.note : '') + '</textarea></label>' +
      '<p class="small muted">Tên chỉ lưu trên máy này. Khi hỏi trợ lý, tên được thay bằng mã trước khi gửi đi.</p><p class="small" id="sf-err" role="alert" style="color:var(--crit)" hidden></p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="st-save" data-sid="' + (s ? s.id : '') + '">' + (s ? 'Lưu thay đổi' : 'Thêm học sinh') + '</button>' });
  }

  // ---- buttons ----
  function go(id) { view = id; prof = null; chartKc = 'all'; asTable = false; more = {}; want = '#st-h1'; draw(); }
  ACT['st-open'] = function (el) { go(+el.dataset.sid); load(); };
  ACT['st-back'] = function () { want = view ? '.st-card[data-sid="' + view + '"] .st-name' : ''; view = 0; prof = null; seq++; draw(); };
  ACT['st-reload'] = function () { load(); };
  ACT['st-add'] = function () { studentForm(null); };
  ACT['st-edit'] = function (el) {
    var id = +el.dataset.sid;
    studentForm(view === id && prof && prof.profile ? prof.profile.student : find(id));
  };
  ACT['st-save'] = function (el) {
    var id = el.dataset.sid, g = $('sf-grade').value, err = $('sf-err');
    var body = { name: $('sf-name').value.trim().replace(/\s+/g, ' '), note: $('sf-note').value.trim() };
    if (g) body.grade = +g;
    el.disabled = true;
    U.api.send(id ? 'PATCH' : 'POST', '/students' + (id ? '/' + id : ''), body).then(function (r) {
      U.closeModal(); U.toast(id ? 'Đã lưu thông tin ' + r.name + '.' : 'Đã thêm ' + r.name + '.'); saved();
    }, function (e) {
      el.disabled = false; err.hidden = false;
      err.textContent = e.status === 422 ? U.names(e.message) : 'Chưa lưu được. Thử lại sau.';  // the server words the 422 (a one-word name)
      $('sf-name').focus();
    });
  };
  ACT['st-archive'] = function (el) {
    var s = find(+el.dataset.sid);
    U.confirm('Lưu trữ ' + esc(s.name) + '?', 'Dữ liệu của em vẫn giữ nguyên. Em sẽ không hiện trong danh sách và khi gõ @ ở Trợ lý. Bỏ lưu trữ được bất cứ lúc nào.', 'Lưu trữ', function () {
      U.api.send('POST', '/students/' + s.id + '/archive').then(function () { U.toast('Đã lưu trữ ' + s.name + '.'); saved(); },
        function () { U.toast('Chưa lưu trữ được. Thử lại sau.', 'warn'); });
    });
  };
  ACT['st-unarchive'] = function (el) {
    var s = find(+el.dataset.sid);
    U.api.send('POST', '/students/' + s.id + '/unarchive').then(function () { U.toast('Đã đưa ' + s.name + ' về danh sách.'); saved(); },
      function () { U.toast('Chưa bỏ lưu trữ được. Thử lại sau.', 'warn'); });
  };
  ACT['st-ws'] = function (el) { var id = +el.dataset.sid; U.tab('tro-ly'); C.send('Gợi ý bài cho @' + U.code(id), { mentions: [id] }); };
  ACT['st-rep'] = function (el) { REPORTS.prefill(+el.dataset.sid); };
  ACT['st-job'] = function (el) { U.tab('tro-ly'); C.openThread(el.dataset.tid, 'grading'); };  // shortcut: the oldest waiting day only, the next shows once it is saved
  ACT['st-rep-open'] = function (el) { REPORTS.open(+el.dataset.id); };
  ACT['st-table'] = function () { asTable = !asTable; draw(); };
  ACT['st-more'] = function (el) { more[el.dataset.g] = !more[el.dataset.g]; draw(); };
  ACT['st-session'] = function (el) {
    U.api.get('/sessions/' + encodeURIComponent(el.dataset.id) + '?view=teacher').then(sessionModal, function () { U.toast('Chưa mở được buổi này. Thử lại sau.', 'warn'); });
  };
  ACT['st-ws-view'] = function (el) {
    var w = prof.sheets[+el.dataset.i];
    U.modal({ title: 'Phiếu buổi ' + U.d(w.for_date) + ' · ' + esc(U.who(w.student_id)), wide: true, body: '<ol class="stack st-list">' + w.items.map(function (it) {
      return '<li><div class="row"><span class="ref">' + U.esc(it.ref) + '</span><span class="chip">' + U.esc(it.level || 'chưa có mức') + '</span>' +
        it.kcs.map(function (k) { return '<span class="chip chip-wrap">' + esc(k) + '</span>'; }).join('') + '</div>' +
        (it.reason ? '<p class="small muted">' + esc(it.reason) + '</p>' : '') + U.texHtml(it.statement_latex) + '</li>';
    }).join('') + '</ol>', foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  };

  window.STUDENTS = { open: function (id) { go(id); U.tab('hoc-sinh'); } };

  TABS['hoc-sinh'] = {
    render: function (p) {
      panel = p;
      p.addEventListener('input', function (ev) {
        if (ev.target.id === 'st-q') { q = ev.target.value; $('st-cards').innerHTML = cardsHTML(); }
      });
      p.addEventListener('change', function (ev) {
        if (ev.target.id === 'st-chart-skill') { chartKc = ev.target.value; drawChart(); }
      });
      var tip = function (ev) { var t = $('st-tip'); if (t && ev.target.classList && ev.target.classList.contains('chit')) t.textContent = ev.target.dataset.tip; };
      p.addEventListener('mouseover', tip); p.addEventListener('focusin', tip);
      var rt;
      window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (!p.hidden) drawChart(); }, 120); });
      draw(); load();
    },
    onShow: function () { load(); }
  };
})();
