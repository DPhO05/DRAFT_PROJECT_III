/* Tab Báo cáo (api-v3 §5, IA-app §3): pick a student and a period, read the draft (G5), fix sentences, Duyệt báo cáo, Tải PDF.
   The draft is polled through CHAT.poll; each sentence change PUTs the whole list, and only Duyệt báo cáo and Thử lại resume.
   Server text goes through U.nesc (HS-xx to names, escaped); fact ids are sent back as they came and never shown. */
(function () {
  var C = window.CHAT, btn = U.btn, esc = U.nesc;
  var KIND = { day: 'Ngày', week: 'Tuần', month: 'Tháng' };
  var OPEN_BOX = 'Lưu hoặc bỏ câu đang sửa trước nhé.';
  var ERR = { already_committed: 'Báo cáo này đã duyệt rồi.', undecided_items: 'Báo cáo cần ít nhất một câu.' };
  var MAKE = '[data-act="rep-make"]';
  var BUSY = 'Báo cáo đang được xử lý. Thử lại sau giây lát.';
  var STALE = 'Có buổi mới được duyệt trong kỳ này. Bỏ bản nháp rồi tạo lại.';  // the one 409 text the server writes for the tutor (report.py check)
  var EMPTY = '<div class="empty"><p>Chọn một báo cáo bên trái, hoặc tạo báo cáo mới.</p>' +
    '<p class="small">Báo cáo viết cho phụ huynh: chỉ dùng lời, không có phần trăm hay con số khó hiểu.</p></div>';

  var ready = false, students = [], list = { drafts: [], approved: [] };
  var days = {}, form = { student: 0, kind: 'week', start: '' }, filt = 0, msg = '', busy = false, want = '', pick = 0;
  var cur = null;  // the report on the right: { tid?, id?, holder, card, eff, json, edit, busy, go, retrying, waits, paused, rep }

  function $(id) { return document.getElementById(id); }
  function noop() { /* the next poll or click tries again */ }
  function pad(x) { return String(x).padStart(2, '0'); }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addDays(s, n) { var d = U.parse(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); }
  function monday(s) { return addDays(s, -((U.parse(s).getUTCDay() + 6) % 7)); }
  function local(ts) { var d = new Date(ts); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }  // approved_at is UTC, the tutor reads local days
  function label(kind, start) {
    if (kind === 'day') return 'ngày ' + U.d(start);
    if (kind === 'week') return 'tuần ' + U.dm(start) + '–' + U.d(addDays(start, 6));
    return 'tháng ' + (+start.slice(5, 7)) + '/' + start.slice(0, 4);
  }
  function lab(kind, start) { return U.esc(label(kind, start)); }
  function active() { return students.filter(function (s) { return !s.archived_at; }); }
  function grade(id) { var s = students.find(function (x) { return x.id === id; }); return s && s.grade ? ' · lớp ' + s.grade : ''; }
  function keyOf(el) { return el.id || [el.tagName, el.dataset.act, el.dataset.kind, el.dataset.tid, el.dataset.id, el.dataset.i].join('|'); }
  function wire(text) {  // C-40: a name typed in a box goes back as its HS-xx code (grading.js wire)
    return Object.keys(U.people).filter(function (c) { return U.people[c].trim().split(/\s+/).length >= 2; })
      .sort(function (a, b) { return U.people[b].length - U.people[a].length; })
      .reduce(function (t, c) {
        return t.replace(new RegExp('(?<![\\p{L}\\p{N}])' + U.people[c].replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}\\p{N}])', 'gu'), c);
      }, String(text));
  }
  var IDS = 'F\\d\\d(?:\\s*,\\s*F\\d\\d)*', WORD = '[\\p{L}\\p{N}_]';
  var ID_MARK = new RegExp('\\s*(?:\\[' + IDS + '\\]|\\(' + IDS + '\\)|(?<!' + WORD + ')' + IDS + '(?!' + WORD + '))', 'gu');  // reporter.py _ID_MARK: [F01], (F01, F03), a bare F01
  function clean(t) { return t.replace(ID_MARK, '').replace(/\s+/g, ' ').trim(); }  // the server drops typed fact ids the same way (C-44)

  // ---- lists ----
  function loadStudents() {
    return U.api.get('/students?archived=true').then(function (rows) {
      students = rows;
      rows.forEach(function (s) { U.people[s.code] = s.name; });
    });
  }
  function fetchList() {
    return U.api.get('/reports').then(function (r) { list = r; }, function () { U.toast('Chưa tải được danh sách báo cáo. Thử lại sau.', 'warn'); });
  }
  function load() {
    return Promise.all([loadStudents().catch(noop), fetchList()]).then(function () {
      ready = true;
      if (pick) { form.student = pick; pick = 0; }  // prefill's student may be newer than the roster the tab held
      drawLeft();
    });
  }
  function refresh(sel) { return fetchList().then(function () { drawLeft(sel); }); }
  function loadDays(sid) {
    if (days[sid] !== undefined) return;
    days[sid] = null;  // asked, not here yet
    U.api.get('/sessions?student=' + sid + '&status=committed&view=teacher').then(function (rows) {
      days[sid] = rows.map(function (r) { return r.held_on; }).filter(function (d, i, a) { return a.indexOf(d) === i; }).sort().reverse();
    }, function () { days[sid] = false; }).then(function () { drawLeft(); });
  }

  // ---- left: the form and the two lists ----
  function periodOptions() {
    var o = [], t = U.today;
    if (form.kind === 'day') (days[form.student] || []).forEach(function (d) { o.push([d, U.wd(d) + ' ' + U.d(d)]); });
    else if (form.kind === 'week') {
      for (var i = 0; i < 8; i++) {
        var s = addDays(monday(t), -7 * i);
        o.push([s, U.dm(s) + '–' + U.dm(addDays(s, 6)) + (i === 0 ? ' (tuần này)' : i === 1 ? ' (tuần trước)' : '')]);
      }
    } else {
      for (var j = 0; j < 3; j++) {
        var m = iso(new Date(Date.UTC(+t.slice(0, 4), +t.slice(5, 7) - 1 - j, 1)));
        o.push([m, 'Tháng ' + (+m.slice(5, 7)) + '/' + m.slice(0, 4) + (j === 0 ? ' (tháng này)' : '')]);
      }
    }
    if (!o.some(function (x) { return x[0] === form.start; })) form.start = o.length ? o[0][0] : '';
    return o;
  }
  function itemHTML(r, draft) {
    var on = cur && (draft ? cur.tid === r.thread_id : cur.id === r.id);
    return '<button type="button" class="rep-item" data-act="rep-sel" ' + (draft ? 'data-tid="' + U.esc(r.thread_id) + '"' : 'data-id="' + U.esc(r.id) + '"') + ' aria-current="' + !!on + '">' +
      '<span><b>' + U.esc(U.who(r.student_id)) + '</b> · ' + lab(r.period_kind, r.period_start) + '</span>' +
      (draft ? '<span class="chip chip-warn">' + (r.status === 'failed' ? 'chưa làm xong' : r.n_flagged ? U.esc(r.n_flagged) + ' câu cần xem lại' : 'nháp') + '</span>' : '<span class="small muted">' + U.esc(U.dm(local(r.approved_at))) + '</span>') + '</button>';
  }
  function leftHTML() {
    var act = active(), opts = periodOptions(), d = days[form.student];
    var none = form.kind !== 'day' ? '' : d === false ? 'Chưa tải được các buổi học' : Array.isArray(d) ? 'Chưa có buổi nào đã duyệt' : 'Đang tải…';
    var appr = list.approved.filter(function (r) { return !filt || r.student_id === filt; });
    return '<section class="section"><h2>Tạo báo cáo mới</h2>' +
      '<label class="field"><span>Học sinh</span><select id="rep-student"' + (act.length ? '' : ' disabled') + '>' + (act.length ? act.map(function (s) {
        return '<option value="' + U.esc(s.id) + '"' + (s.id === form.student ? ' selected' : '') + '>' + U.esc(s.name) + '</option>'; }).join('') : '<option value="">Chưa có học sinh</option>') + '</select></label>' +
      '<div class="field"><span>Kỳ báo cáo</span><div class="seg" role="group" aria-label="Kỳ báo cáo">' + ['day', 'week', 'month'].map(function (k) {
        return '<button type="button" class="seg-btn" data-act="rep-kind" data-kind="' + k + '" aria-pressed="' + (form.kind === k) + '">' + KIND[k] + '</button>'; }).join('') + '</div></div>' +
      '<label class="field"><span>' + (form.kind === 'day' ? 'Buổi học' : form.kind === 'week' ? 'Tuần (thứ Hai–Chủ nhật)' : 'Tháng') + '</span><select id="rep-start"' + (opts.length ? '' : ' disabled') + '>' +
      (opts.length ? opts.map(function (o) { return '<option value="' + U.esc(o[0]) + '"' + (o[0] === form.start ? ' selected' : '') + '>' + U.esc(o[1]) + '</option>'; }).join('') : '<option value="">' + none + '</option>') + '</select></label>' +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="rep-make"' + (act.length && form.student && form.start && !busy ? '' : ' disabled') + '>Tạo báo cáo</button></div>' +
      (msg ? '<div class="callout callout-warn" role="status"><p>' + msg + '</p></div>' : '') + '</section>' +
      '<section class="section"><h2>Bản nháp chờ duyệt (' + list.drafts.length + ')</h2><div class="rep-list">' +
      (list.drafts.length ? list.drafts.map(function (r) { return itemHTML(r, true); }).join('') : '<p class="small muted">Không có bản nháp nào.</p>') + '</div></section>' +
      '<section class="section"><div class="section-head"><h2>Đã duyệt (' + appr.length + ')</h2><select id="rep-filter" aria-label="Lọc theo học sinh"><option value="0">Tất cả học sinh</option>' +
      students.map(function (s) { return '<option value="' + U.esc(s.id) + '"' + (filt === s.id ? ' selected' : '') + '>' + U.esc(s.name) + '</option>'; }).join('') + '</select></div><div class="rep-list">' +
      (appr.length ? appr.map(function (r) { return itemHTML(r, false); }).join('') : '<p class="small muted">Chưa có báo cáo nào được duyệt.</p>') + '</div></section>';
  }
  function drawLeft(sel) {
    var left = $('rep-left');
    if (!left) return;
    var act = active(), a = document.activeElement, k = left.contains(a) && keyOf(a);
    if (ready && !act.some(function (s) { return s.id === form.student; })) form.student = act.length ? act[0].id : 0;  // before the list is in, prefill's student stays
    if (form.kind === 'day' && form.student) loadDays(form.student);
    left.innerHTML = leftHTML();
    sel = sel || want;
    var n = sel ? ready && left.querySelector(sel) : k && [].find.call(left.querySelectorAll('button, select'), function (x) { return keyOf(x) === k; });
    if (n) { n.focus(); if (sel === want) want = ''; }
  }

  // ---- right: the report ----
  function head(r, chip) {
    return '<div class="spread"><div><div class="eyebrow">Báo cáo ' + lab(r.period_kind, r.period_start) + '</div><h2 id="rep-title" tabindex="-1">' + U.esc(U.who(r.student_id)) + grade(r.student_id) + '</h2></div>' + chip + '</div>';
  }
  function flags(s) { return s.card.sentences.filter(function (x) { return x.flag; }).length; }
  function sentRow(x, i) {
    return '<div class="sent"><p class="rep-text">' + (x.flag ? '<span class="uncheck">' + esc(x.text) + '</span>' : esc(x.text)) + '</p><div class="acts">' +
      '<button type="button" class="btn btn-sm" data-act="sent-edit" data-i="' + i + '" aria-label="Sửa câu ' + (i + 1) + '">Sửa</button>' +
      '<button type="button" class="btn btn-sm" data-act="sent-del" data-i="' + i + '" aria-label="Bỏ câu ' + (i + 1) + '">Bỏ</button></div>' +
      (x.flag ? '<p class="uncheck-note">Cần xem lại: ' + esc(x.why) + '</p>' : '') + '</div>';
  }
  function editRow(i, text) {
    return '<div class="sent sent-edit"><label class="field"><span>Câu ' + (i + 1) + '</span><textarea rows="3" id="sent-' + i + '" autocomplete="off">' + U.esc(text) + '</textarea></label>' +
      '<div class="row"><button type="button" class="btn btn-primary btn-sm" data-act="sent-save" data-i="' + i + '">Lưu câu</button>' +
      '<button type="button" class="btn btn-sm" data-act="sent-cancel" data-i="' + i + '">Thôi</button></div></div>';
  }
  function draftHTML(s) {
    var rows = s.card.sentences, n = flags(s), e = s.edit, none = !rows.length;
    return (n ? '<div class="callout callout-warn"><p>Có <b>' + n + ' câu cần xem lại</b> (gạch chân vàng). Sửa hoặc bỏ câu đó; vẫn duyệt được nếu thầy/cô thấy ổn.</p></div>'
      : none ? '<div class="callout callout-warn"><p>Bản nháp chưa có câu nào. Thêm câu, hoặc bỏ bản nháp rồi tạo lại.</p></div>'
      : '<div class="callout callout-ok"><p>Mọi câu đã khớp với dữ liệu đã duyệt.</p></div>') +
      '<div>' + rows.map(function (x, i) { return e && e.i === i ? editRow(i, e.text) : sentRow(x, i); }).join('') + (e && e.i === rows.length ? editRow(e.i, e.text) : '') + '</div>' +
      '<div class="row">' + btn('sent-add', '+ Thêm câu') + '</div>' +
      '<div class="spread">' + btn('rep-discard', 'Bỏ bản nháp', '', 'btn-ghost') + '<span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="rep-approve"' +
      (none ? ' disabled aria-describedby="rep-why"' : '') + '>Duyệt báo cáo</button>' + (none ? '<span class="reason" id="rep-why">Cần ít nhất một câu.</span>' : '') + '</span></div>' +
      '<p class="small muted">Chưa lưu vào hồ sơ cho tới khi bấm “Duyệt báo cáo”. Mỗi kỳ của một em chỉ duyệt một lần.</p>';
  }
  function approvedHTML(r) {
    return '<article class="rep-doc is-approved" aria-label="Báo cáo">' + head(r, '<span class="chip chip-ok">Đã duyệt ' + U.esc(U.d(local(r.approved_at))) + '</span>') +
      '<p class="rep-text">' + r.sentences.map(function (t) { return '<span class="rep-s">' + esc(t) + '</span>'; }).join(' ') + '</p>' +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="rep-pdf">Tải PDF</button></div></article>';
  }
  function docHTML(s) {
    var c = s.card, st = s.eff;
    if (s.rep) return approvedHTML(s.rep);
    if (!c) return '<p class="tool-line" role="status">Đang mở báo cáo…</p>';
    if (st === 'draft') return '<article class="rep-doc is-draft" aria-label="Báo cáo" data-thread="' + U.esc(s.tid) + '">' + head(c, '<span class="chip chip-warn">Bản nháp — chưa duyệt</span>') + draftHTML(s) + '</article>';
    return '<article class="rep-doc is-draft" aria-label="Báo cáo">' + head(c, '') + (st === 'writing' ? '<p class="tool-line" role="status">Đang viết bản nháp…</p>'
      : st === 'saving' ? '<p class="tool-line" role="status">Đang lưu…</p>'
      : st === 'saved' ? '<p class="tool-line" role="status">Đã duyệt. Báo cáo nằm trong danh sách “Đã duyệt” bên trái.</p>'
      : '<div class="callout callout-crit" role="alert"><p id="rep-failed" tabindex="-1"><b>Chưa làm xong bản nháp.</b> Chưa có gì được lưu. Thầy/cô bấm Thử lại, hoặc bỏ bản nháp rồi tạo lại.</p><div class="row">' +
        btn('rep-retry', 'Thử lại', s.retrying ? 'disabled' : '', 'btn-primary') + btn('rep-discard', 'Bỏ bản nháp') + '</div></div>') + '</article>';
  }
  function drawDoc(s, focusSel) {
    var h = s.holder, a = document.activeElement, k = h.contains(a) && keyOf(a), pos = k && a.selectionStart;
    h.innerHTML = docHTML(s);
    if (s.land && !focusSel && h.querySelector('#rep-title')) { s.land = false; focusSel = '#rep-title'; }  // opened from another tab: the clicked button is in a hidden panel
    var n = focusSel ? h.querySelector(focusSel) : k && [].find.call(h.querySelectorAll('button, textarea, [tabindex="-1"]'), function (x) { return keyOf(x) === k; });
    if (!n) return;
    n.focus({ preventScroll: !focusSel });
    if (!focusSel && typeof pos === 'number') try { n.setSelectionRange(pos, pos); } catch (e) { /* not a text box */ }
  }

  // ---- opening: a thread (draft, polled) or a report id (approved) ----
  function openDoc(id, land) {
    var box = $('rep-doc'), h = document.createElement('div');
    var s = { holder: h, card: null, eff: '', json: '', edit: null, busy: false, go: false, retrying: false, waits: 0, rep: null, land: !!land };
    if (cur && cur.holder.isConnected && (cur.tid === id || cur.id === id)) {
      box.scrollIntoView({ block: 'start' });
      if (land) { cur.land = true; drawDoc(cur); }
      return;
    }
    box.innerHTML = ''; box.appendChild(h);  // the old holder leaves the page, so its poll stops
    cur = s; msg = '';
    if (typeof id === 'number') {
      s.id = id;
      U.api.get('/reports/' + id).then(function (r) { if (cur === s) { s.rep = r; drawDoc(s); } }, function () {
        if (cur === s) h.innerHTML = '<div class="empty"><p>Chưa mở được báo cáo này. Thử lại sau.</p></div>';
      });
    } else {
      s.tid = id;
      poll(s);
    }
    drawDoc(s); drawLeft();
    if (matchMedia('(max-width: 900px)').matches) box.scrollIntoView({ block: 'start' });
  }
  function path(s, tail) { return '/threads/' + encodeURIComponent(s.tid) + tail; }
  function poll(s) {  // C.poll writes its "Việc này đã xong" card into the holder on a 404; this holder drops the report instead, so chat.js stays as it is
    C.poll(s.tid, function (row) { return onRow(s, row); }, {
      get isConnected() { return s.holder.isConnected; },
      set innerHTML(v) { gone(s); }
    });
  }
  function gone(s) {  // the thread is not there any more: dropped or cleaned up elsewhere
    if (cur !== s) return;
    cur = null; $('rep-doc').innerHTML = EMPTY;
    C.refreshPending(); refresh(MAKE);
    U.toast('Bản nháp này không còn nữa.', 'info');
  }
  function onRow(s, row) {
    var c = row.card, was = s.eff, redraw = false;
    if (c.stage === 'saved') { s.card = c; s.eff = 'saved'; settle(s); return false; }
    if ($('panel-bao-cao').hidden) { s.paused = true; return false; }  // a hidden tab does not poll; onShow starts it again
    // 09's draft is in the state a moment before the gate, so `saving` counts only after this screen saw a draft or asked to resume
    var eff = c.stage === 'saving' && !(s.go || was === 'draft' || was === 'saving') ? 'writing' : c.stage;
    if (s.retrying && (c.stage !== 'failed' || ++s.waits >= 2)) { s.retrying = false; redraw = true; }  // Thử lại failed again before a poll saw it run
    var j = JSON.stringify([eff, c]);
    if (j !== s.json || redraw) {
      s.json = j; s.card = c; s.eff = eff;
      drawDoc(s);
      if (eff !== was && /^(draft|failed)$/.test(eff)) refresh();
    }
    return true;
  }
  function settle(s) {  // saved here or somewhere else: show the approved report and stop polling
    var mine = s.go, id = s.card.report_id;
    C.refreshPending(); refresh();
    if (id == null) { drawDoc(s); return; }
    s.id = id;
    U.api.get('/reports/' + id).then(function (r) {
      if (cur !== s) return;
      s.rep = r; drawDoc(s, mine ? '[data-act="rep-pdf"]' : '');
      if (mine) U.toast('Đã duyệt báo cáo ' + label(r.period_kind, r.period_start) + ' của ' + U.who(r.student_id) + '.');
      drawLeft();
    }, function () { if (cur === s) drawDoc(s); });
  }

  // ---- writes: PUT the whole list; resume only from Duyệt báo cáo and Thử lại ----
  function plain(s) { return s.card.sentences.map(function (x) { return { text: x.text, facts: x.facts }; }); }
  function save(s, rows) {
    return U.api.send('PUT', path(s, '/decisions'), { sentences: rows }).then(function (r) {
      s.card = Object.assign({}, s.card, { sentences: rows.map(function (x, i) {
        var a = r.audit[i] || {};
        return { text: clean(x.text), facts: x.facts, flag: a.flag || null, why: a.why || null };
      }) });
      return r;
    });
  }
  function fail(s, e) {  // a 409 means the draft moved on (approved elsewhere, busy, stale): the poll that goes on shows how
    if (e.status === 404) { gone(s); return; }
    if (e.status === 409) s.edit = null;
    var said = e.status === 422 || e.status === 409 && e.message === STALE;  // other server texts can be a raw thread id
    U.toast(said ? U.names(e.message) : e.status === 409 ? ERR[e.code] || BUSY : 'Chưa làm được. Thử lại sau.', 'warn');
    var id = e.detail && e.detail.report_id;
    if (cur === s && e.status === 409 && e.code === 'already_committed' && id != null) openDoc(id, true);  // approved elsewhere: show that report (like rep-make)
    else drawDoc(s);
  }
  function change(s, rows, focusSel, after) {
    s.busy = true;
    save(s, rows).then(function () { s.busy = false; if (after) after(); drawDoc(s, focusSel); }, function (e) { s.busy = false; fail(s, e); });
  }
  function nextSel(n, i) { return i < n ? '[data-act="sent-edit"][data-i="' + i + '"]' : '[data-act="sent-add"]'; }

  ACT['sent-edit'] = function (el) {
    var s = cur, i = +el.dataset.i;
    if (!s || s.busy) return;
    if (s.edit) { U.toast(OPEN_BOX, 'warn'); return; }  // a second box would drop the typed text
    s.edit = { i: i, text: U.names(s.card.sentences[i].text) };
    drawDoc(s, '#sent-' + i);
  };
  ACT['sent-add'] = function () {
    var s = cur;
    if (!s || s.busy) return;
    if (s.edit) { U.toast(OPEN_BOX, 'warn'); return; }
    s.edit = { i: s.card.sentences.length, text: '' };
    drawDoc(s, '#sent-' + s.edit.i);
  };
  ACT['sent-cancel'] = function (el) {
    var s = cur;
    s.edit = null;
    drawDoc(s, nextSel(s.card.sentences.length, +el.dataset.i));
  };
  ACT['sent-save'] = function (el) {
    var s = cur, i = +el.dataset.i, box = $('sent-' + i);
    if (!s || s.busy || !box) return;
    var rows = plain(s), t = wire(box.value.trim()), added = i >= rows.length;
    if (!t && added || !added && t === rows[i].text) { ACT['sent-cancel'](el); return; }  // an empty new box, or nothing changed
    if (!t) rows.splice(i, 1);
    else if (added) rows.push({ text: t, facts: [] });
    else rows[i] = { text: t, facts: rows[i].facts };
    change(s, rows, nextSel(rows.length, i), function () { s.edit = null; });
  };
  ACT['sent-del'] = function (el) {
    var s = cur, i = +el.dataset.i, rows = s && plain(s), e = s && s.edit;
    if (!s || s.busy) return;
    rows.splice(i, 1);
    change(s, rows, nextSel(rows.length, i), function () {  // an open box moves with its sentence, or goes with it
      if (e && e === s.edit) { if (e.i === i) s.edit = null; else if (e.i > i) e.i--; }
    });
  };
  ACT['rep-approve'] = function () {
    var s = cur, n = s && flags(s);
    if (!s || s.busy) return;
    if (s.edit) { U.toast(OPEN_BOX, 'warn'); return; }
    if (!n) { approve(s); return; }
    U.confirm('Vẫn duyệt?', 'Còn ' + n + ' câu cần xem lại (gạch chân vàng). Chúng có thể chưa đúng với dữ liệu đã duyệt. Vẫn duyệt báo cáo?', 'Vẫn duyệt', function () { approve(s); });
  };
  function approve(s) {
    if (cur !== s || s.busy || s.edit) return;
    s.busy = s.go = true;
    save(s, plain(s)).then(function () { return U.api.send('POST', path(s, '/resume')); }).then(function () {
      s.busy = false; s.eff = 'saving'; C.refreshPending(); drawDoc(s);
    }, function (e) { s.busy = s.go = false; fail(s, e); });
  }
  ACT['rep-retry'] = function () {
    var s = cur;
    if (!s || s.retrying) return;
    s.retrying = s.go = true; s.waits = 0; drawDoc(s, '#rep-failed');  // the button disables itself
    U.api.send('POST', path(s, '/resume')).then(function () { C.refreshPending(); }, function (e) { s.retrying = s.go = false; fail(s, e); });
  };
  ACT['rep-discard'] = function () {
    var s = cur;
    if (!s || !s.tid) return;
    U.confirm('Bỏ bản nháp này?', 'Bản nháp sẽ mất; tạo lại lúc nào cũng được.', 'Bỏ bản nháp', function () {
      U.api.send('POST', path(s, '/cancel')).then(null, function (e) { if (e.status !== 404) throw e; }).then(function () {
        C.refreshPending(); refresh(MAKE);  // the Bỏ button is gone, so the focus goes to the form
        if (cur === s) { cur = null; $('rep-doc').innerHTML = EMPTY; }
      }, function () { U.toast('Chưa bỏ được bản nháp. Thử lại sau.', 'warn'); });
    }, true);
  };
  ACT['rep-pdf'] = function () {
    var r = cur && cur.rep;
    if (!r) return;
    U.print('<h1>Báo cáo ' + lab(r.period_kind, r.period_start) + ' · ' + U.esc(U.who(r.student_id)) + '</h1>' +
      '<p class="p-meta">Gia sư Toán · duyệt ngày ' + U.esc(U.d(local(r.approved_at))) + '</p>' + r.sentences.map(function (t) { return '<p>' + esc(t) + '</p>'; }).join(''), 'báo cáo');
  };

  // ---- the form ----
  function notReady(e, kind, start, sid) {
    var d = (e.detail && e.detail.pending) || [], dates = d.map(function (p) { return U.esc(U.dm(p.held_on)); }).filter(function (x, i, a) { return a.indexOf(x) === i; });
    return 'Chưa làm được báo cáo ' + lab(kind, start) + ' cho <b>' + U.esc(U.who(sid)) + '</b>: kỳ này chưa có buổi nào đã duyệt' + (dates.length ? ' (bài ' + dates.join(', ') + ' còn chờ duyệt)' : '') + '.';
  }
  ACT['rep-kind'] = function (el) { form.kind = el.dataset.kind; form.start = ''; msg = ''; drawLeft('[data-act="rep-kind"][data-kind="' + form.kind + '"]'); };
  ACT['rep-sel'] = function (el) { openDoc(el.dataset.tid || +el.dataset.id); };
  ACT['rep-make'] = function () {
    var sid = form.student, kind = form.kind, start = form.start;
    if (busy) return;
    busy = true; msg = ''; drawLeft();
    U.api.send('POST', '/reports', { student_id: sid, period_kind: kind, period_start: start }).then(function (r) {
      busy = false; C.refreshPending(); refresh(); openDoc(r.thread_id);
    }, function (e) {
      busy = false;
      var d = e.detail || {};
      if (e.status === 409 && e.code === 'already_committed' && d.report_id != null) {
        openDoc(d.report_id);  // clears the message, so it is set after
        msg = 'Báo cáo ' + lab(kind, start) + ' của ' + U.esc(U.who(sid)) + ' đã duyệt ngày ' + U.esc(U.d(local(d.approved_at))) + '. Mỗi kỳ chỉ duyệt một lần.';
      } else if (e.status === 409 && e.code === 'not_ready') msg = notReady(e, kind, start, sid);
      else msg = e.status === 422 ? esc(e.message) : 'Chưa tạo được báo cáo. Thử lại sau.';
      drawLeft(MAKE);
    });
  };

  // ---- API for the other tabs: open(thread id | report id), prefill(student id), the period words and local day ----
  window.REPORTS = {
    label: label, local: local,
    open: function (id) { U.tab('bao-cao'); openDoc(id, true); },
    prefill: function (sid) { U.tab('bao-cao'); pick = sid; msg = ''; want = '[data-act="rep-kind"][aria-pressed="true"]'; drawLeft(); }
  };

  TABS['bao-cao'] = {
    render: function (p) {
      p.innerHTML = '<div class="page"><div class="page-head"><div><h1>Báo cáo</h1><p>Báo cáo cho phụ huynh theo ngày, tuần hoặc tháng, chỉ từ các buổi đã duyệt.</p></div></div>' +
        '<div class="rep-layout"><div class="stack" id="rep-left"></div><div id="rep-doc">' + EMPTY + '</div></div></div>';
      p.addEventListener('change', function (ev) {
        var id = ev.target.id;
        if (id === 'rep-student') { form.student = +ev.target.value; msg = ''; drawLeft('#rep-student'); }
        else if (id === 'rep-start') { form.start = ev.target.value; msg = ''; drawLeft('#rep-start'); }
        else if (id === 'rep-filter') { filt = +ev.target.value; drawLeft('#rep-filter'); }
      });
      p.addEventListener('input', function (ev) {
        if (cur && cur.edit && ev.target.matches('.sent-edit textarea')) cur.edit.text = ev.target.value;
      });
      drawLeft(); load();
    },
    onShow: function () {
      days = {}; load();
      if (cur && cur.paused && cur.tid) { cur.paused = false; poll(cur); }  // the poll stopped while the tab was hidden
    }
  };
})();
