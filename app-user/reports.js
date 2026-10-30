/* Tab Báo cáo: pick student + period (ngày / tuần / tháng) → draft → edit sentences → Duyệt → Tải PDF. Words only. */
var REP = (function () {
  var C = {}, panel = null, sel = null, form = { student: 1, kind: 'week', start: null }, msg = '', busy = 0, filt = 0, seq = 0;
  var KIND = { day: 'Ngày', week: 'Tuần', month: 'Tháng' };

  C.label = function (kind, start) {
    if (kind === 'day') return 'ngày ' + U.d(start);
    if (kind === 'week') return 'tuần ' + U.dm(start) + '–' + U.d(U.addDays(start, 6));
    return 'tháng ' + (+start.slice(5, 7)) + '/' + start.slice(0, 4);
  };
  C.inPeriod = function (date, kind, start) {
    if (kind === 'day') return date === start;
    if (kind === 'week') return date >= start && date <= U.addDays(start, 6);
    return date.slice(0, 7) === start.slice(0, 7);
  };
  C.find = function (sid, kind, start) {
    var m = function (r) { return r.student === sid && r.kind === kind && r.start === start; };
    return S.reports.find(m) || S.reportDrafts.find(m);
  };
  C.get = function (id) { return S.reportDrafts.find(function (r) { return r.id === id; }) || S.reports.find(function (r) { return r.id === id; }); };
  function prevStart(kind, start) {
    if (kind === 'day') return null;
    if (kind === 'week') return U.addDays(start, -7);
    return U.iso(new Date(Date.UTC(+start.slice(0, 4), +start.slice(5, 7) - 2, 1)));
  }
  function rate(list) { var s = 0, m = 0; list.forEach(function (x) { var t = U.sessionScore(x); s += t.score; m += t.max; }); return m ? s / m : 0; }
  function numsIn(t) { return (t.replace(/\d{1,2}\/\d{1,2}(\/\d{4})?/g, ' ').match(/\d+/g) || []); }

  C.make = function (sid, kind, start) {
    var st = U.student(sid), ses = S.sessions.filter(function (x) { return x.student === sid && C.inPeriod(x.date, kind, start); });
    if (!ses.length) {
      var pend = U.pendingJobs(sid).filter(function (j) { return C.inPeriod(A.JOB[j.id].date, kind, start); });
      return { ok: false, reason: 'Chưa làm được báo cáo ' + C.label(kind, start) + ' cho <b>' + U.esc(st.short) + '</b>: kỳ này chưa có buổi nào đã duyệt' +
        (pend.length ? ' (bài ' + pend.map(function (j) { return U.dm(A.JOB[j.id].date); }).join(', ') + ' còn chờ duyệt)' : '') + '.' };
    }
    var nP = 0, mist = [], byKind = {}, bySkill = {}, clean = [];
    ses.forEach(function (x) { x.problems.forEach(function (p) {
      nP += 1; mist = mist.concat(p.mistakes);
      if (p.score === p.max && A.P[p.pid]) clean = clean.concat(A.P[p.pid].skills);
    }); });
    mist.forEach(function (m) { byKind[m.kind] = (byKind[m.kind] || 0) + 1; if (m.skill) bySkill[m.skill] = (bySkill[m.skill] || 0) + 1; });
    var top = function (o) { return Object.keys(o).sort(function (a, b) { return o[b] - o[a]; })[0]; };
    var r = rate(ses), out = [], nums = [String(ses.length), String(nP)];
    out.push({ t: kind === 'day' ? 'Buổi ' + U.wd(start) + ' ' + U.d(start) + ', em làm ' + nP + ' bài.' :
      'Trong ' + C.label(kind, start) + ', em học ' + ses.length + ' buổi và làm ' + nP + ' bài.' });
    out.push({ t: r >= 0.8 ? 'Em làm đúng phần lớn các bước giải.' : r >= 0.6 ? 'Em làm đúng khá nhiều bước, còn vài chỗ cần cẩn thận hơn.' : 'Em còn sai ở khá nhiều bước, cần luyện thêm.' });
    var ps = prevStart(kind, start);
    if (ps) {
      var prev = S.sessions.filter(function (x) { return x.student === sid && C.inPeriod(x.date, kind, ps); });
      var word = kind === 'week' ? 'tuần trước' : 'tháng trước';
      if (prev.length) { var d = r - rate(prev); out.push({ t: d > 0.05 ? 'So với ' + word + ', em làm chắc tay hơn.' : d < -0.05 ? 'So với ' + word + ', kết quả chưa bằng, cần xem lại cách trình bày.' : 'Kết quả tương đương ' + word + '.' }); }
    }
    var tk = top(byKind);
    if (tk) { out.push({ t: 'Lỗi em hay gặp nhất là “' + U.kindLabel(+tk).toLowerCase() + '” (' + byKind[tk] + ' lần).' }); nums.push(String(byKind[tk])); }
    else out.push({ t: 'Em không mắc lỗi nào trong kỳ này.' });
    var ts = top(bySkill);
    if (ts) out.push({ t: 'Cần ôn thêm phần “' + U.skillName(+ts) + '”.' });
    var good = clean.filter(function (k) { return String(k) !== ts; })[0];
    if (good) out.push({ t: 'Em làm tốt phần “' + U.skillName(good) + '”.' });
    out.push({ t: 'Em dành khoảng 45 phút cho mỗi bài khó.', flag: 'num', why: 'Số “45” không có trong dữ liệu đã duyệt.' });
    var draft = { id: 'n' + (++seq), student: sid, kind: kind, start: start, created: U.today, nums: nums, sentences: out };
    S.reportDrafts.push(draft); U.badges(); if (window.CHAT) CHAT.refreshRemind();
    return { ok: true, draft: draft };
  };
  C.open = function (id) { sel = id; msg = ''; U.tab('bao-cao'); draw(); var d = panel.querySelector('#rep-doc'); if (d && matchMedia('(max-width: 900px)').matches) d.scrollIntoView({ block: 'start' }); };
  C.prefill = function (sid) { form.student = sid; msg = ''; U.tab('bao-cao'); draw(); var k = panel.querySelector('[data-act="rep-kind"][aria-pressed="true"]'); if (k) k.focus(); };

  function periodOptions() {
    var o = [], sid = form.student;
    if (form.kind === 'day') {
      U.studentSessions(sid).forEach(function (x) { o.push([x.date, U.wd(x.date) + ' ' + U.d(x.date)]); });
    } else if (form.kind === 'week') {
      var m = U.monday(U.today);
      for (var i = 0; i < 8; i++) { var s = U.addDays(m, -7 * i); o.push([s, U.dm(s) + '–' + U.dm(U.addDays(s, 6)) + (i === 0 ? ' (tuần này)' : i === 1 ? ' (tuần trước)' : '')]); }
    } else {
      ['2026-10-01', '2026-09-01', '2026-08-01'].forEach(function (s, i) { o.push([s, 'Tháng ' + (+s.slice(5, 7)) + '/2026' + (i === 0 ? ' (tháng này)' : '')]); });
    }
    if (!o.some(function (x) { return x[0] === form.start; })) form.start = o.length ? o[0][0] : null;
    return o;
  }
  function itemHTML(r, draft) {
    return '<button type="button" class="rep-item" data-act="rep-sel" data-id="' + r.id + '" aria-current="' + (sel === r.id) + '"><span><b>' + U.esc(U.student(r.student).short) + '</b> · ' + C.label(r.kind, r.start) + '</span>' +
      (draft ? '<span class="chip chip-warn">nháp</span>' : '<span class="small muted">' + U.dm(r.approved) + '</span>') + '</button>';
  }
  function docHTML() {
    var r = sel && C.get(sel);
    if (!r) return '<div class="empty" id="rep-doc"><p>Chọn một báo cáo bên trái, hoặc tạo báo cáo mới.</p><p class="small">Báo cáo viết cho phụ huynh: chỉ dùng lời, không có phần trăm hay con số khó hiểu.</p></div>';
    var st = U.student(r.student), draft = !r.approved, flagged = r.sentences.filter(function (s) { return s.flag; }).length;
    var h = '<article class="rep-doc ' + (draft ? 'is-draft' : 'is-approved') + '" id="rep-doc" aria-label="Báo cáo"><div class="spread"><div><div class="eyebrow">Báo cáo ' + C.label(r.kind, r.start) + '</div><h2>' + U.esc(st.name) + ' · lớp ' + st.grade + '</h2></div>' +
      (draft ? '<span class="chip chip-warn">Bản nháp — chưa duyệt</span>' : '<span class="chip chip-ok">Đã duyệt ' + U.d(r.approved) + '</span>') + '</div>';
    if (draft) {
      h += flagged ? '<div class="callout callout-warn"><p>Có <b>' + flagged + ' câu cần xem lại</b> (gạch chân vàng). Sửa hoặc bỏ câu đó; vẫn duyệt được nếu thầy/cô thấy ổn.</p></div>'
        : '<div class="callout callout-ok"><p>Mọi câu đã khớp với dữ liệu đã duyệt.</p></div>';
      h += '<div>' + r.sentences.map(function (s, i) {
        if (s.editing) return '<div class="sent"><label class="field" style="grid-column:1/-1"><span>Câu ' + (i + 1) + '</span><textarea rows="2" id="sent-' + i + '">' + U.esc(s.t) + '</textarea></label>' +
          '<div class="row" style="grid-column:1/-1"><button type="button" class="btn btn-primary btn-sm" data-act="sent-save" data-i="' + i + '">Lưu câu</button><button type="button" class="btn btn-sm" data-act="sent-cancel" data-i="' + i + '">Thôi</button></div></div>';
        return '<div class="sent"><p class="rep-text' + (s.flag ? ' uncheck' : '') + '">' + U.esc(s.t) + '</p><div class="acts"><button type="button" class="btn btn-sm" data-act="sent-edit" data-i="' + i + '">Sửa</button><button type="button" class="btn btn-sm" data-act="sent-del" data-i="' + i + '" aria-label="Bỏ câu ' + (i + 1) + '">Bỏ</button></div>' +
          (s.flag ? '<p class="note uncheck-note">Cần xem lại: ' + U.esc(s.why) + '</p>' : '') + '</div>';
      }).join('') + '</div><div class="row"><button type="button" class="btn btn-sm" data-act="sent-add">+ Thêm câu</button></div>' +
        '<div class="spread"><button type="button" class="btn btn-ghost btn-sm" data-act="rep-discard">Bỏ bản nháp</button><button type="button" class="btn btn-primary" data-act="rep-approve">Duyệt báo cáo</button></div>' +
        '<p class="small muted">Chưa lưu gì cho tới khi bấm “Duyệt báo cáo”. Mỗi kỳ của một em chỉ duyệt một lần.</p>';
    } else {
      h += '<p class="rep-text">' + r.sentences.map(function (s) { return U.esc(s.t); }).join(' ') + '</p>' +
        '<div class="row"><button type="button" class="btn btn-primary" data-act="rep-pdf">Tải PDF</button></div>';
    }
    return h + '</article>';
  }
  function draw() {
    if (!panel) return;
    var act = S.students.filter(function (s) { return !s.archived; });
    if (!act.some(function (s) { return s.id === form.student; })) form.student = act[0].id;
    var opts = periodOptions();
    var appr = S.reports.filter(function (r) { return !filt || r.student === filt; }).slice().sort(function (a, b) { return b.approved.localeCompare(a.approved); });
    panel.innerHTML = '<div class="page"><div class="page-head"><div><h1>Báo cáo</h1><p>Báo cáo cho phụ huynh theo ngày, tuần hoặc tháng — chỉ từ các buổi đã duyệt.</p></div></div>' +
      '<div class="rep-layout"><div class="stack">' +
      '<section class="section"><h2>Tạo báo cáo mới</h2>' +
      '<label class="field"><span>Học sinh</span><select id="rep-student">' + act.map(function (s) { return '<option value="' + s.id + '"' + (s.id === form.student ? ' selected' : '') + '>' + U.esc(s.name) + '</option>'; }).join('') + '</select></label>' +
      '<div class="field"><span>Kỳ báo cáo</span><div class="seg" role="group" aria-label="Kỳ báo cáo">' + ['day', 'week', 'month'].map(function (k) {
        return '<button type="button" class="seg-btn" data-act="rep-kind" data-kind="' + k + '" aria-pressed="' + (form.kind === k) + '">' + KIND[k] + '</button>'; }).join('') + '</div></div>' +
      '<label class="field"><span>' + (form.kind === 'day' ? 'Buổi học' : form.kind === 'week' ? 'Tuần (thứ Hai–Chủ nhật)' : 'Tháng') + '</span><select id="rep-start">' +
      (opts.length ? opts.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === form.start ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') : '<option value="">Chưa có buổi nào đã duyệt</option>') + '</select></label>' +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="rep-make"' + (form.start && !busy ? '' : ' disabled') + '>Tạo báo cáo</button></div>' +
      (busy ? '<ol class="steps">' + ['Đang lấy số liệu…', 'Đang viết…', 'Đang kiểm từng câu…'].map(function (s, i) { return '<li class="' + (i < busy - 1 ? 'done' : i === busy - 1 ? 'on' : '') + '">' + s + '</li>'; }).join('') + '</ol>' : '') +
      (msg ? '<div class="callout callout-warn" role="status"><p>' + msg + '</p></div>' : '') + '</section>' +
      '<section class="section"><h2>Bản nháp chờ duyệt (' + S.reportDrafts.length + ')</h2><div class="rep-list">' +
      (S.reportDrafts.length ? S.reportDrafts.map(function (r) { return itemHTML(r, true); }).join('') : '<p class="small muted">Không có bản nháp nào.</p>') + '</div></section>' +
      '<section class="section"><div class="section-head"><h2>Đã duyệt (' + appr.length + ')</h2><select id="rep-filter" aria-label="Lọc theo học sinh"><option value="0">Tất cả học sinh</option>' +
      S.students.map(function (s) { return '<option value="' + s.id + '"' + (filt === s.id ? ' selected' : '') + '>' + U.esc(s.short) + '</option>'; }).join('') + '</select></div><div class="rep-list">' +
      (appr.length ? appr.map(function (r) { return itemHTML(r, false); }).join('') : '<p class="small muted">Chưa có báo cáo nào được duyệt.</p>') + '</div></section>' +
      '</div><div>' + docHTML() + '</div></div></div>';
  }

  ACT['rep-kind'] = function (el) { form.kind = el.dataset.kind; form.start = null; msg = ''; draw(); };
  ACT['rep-sel'] = function (el) { sel = isNaN(+el.dataset.id) ? el.dataset.id : +el.dataset.id; msg = ''; draw(); };
  ACT['rep-make'] = function () {
    var ex = C.find(form.student, form.kind, form.start), st = U.student(form.student);
    if (ex && ex.approved) { msg = 'Báo cáo ' + C.label(form.kind, form.start) + ' của ' + U.esc(st.short) + ' đã duyệt ngày ' + U.d(ex.approved) + '. Mỗi kỳ chỉ duyệt một lần — mở bản đã duyệt bên phải.'; sel = ex.id; draw(); return; }
    if (ex) { sel = ex.id; msg = ''; draw(); return; }
    busy = 1; msg = ''; draw();
    var step = function () {
      if (busy < 3) { busy += 1; draw(); setTimeout(step, 380); return; }
      busy = 0;
      var r = C.make(form.student, form.kind, form.start);
      if (r.ok) sel = r.draft.id; else msg = r.reason;
      draw();
    };
    setTimeout(step, 380);
  };
  function cur() { return C.get(sel); }
  ACT['sent-edit'] = function (el) { cur().sentences[+el.dataset.i].editing = true; draw(); var t = panel.querySelector('#sent-' + el.dataset.i); if (t) t.focus(); };
  ACT['sent-cancel'] = function (el) { var r = cur(), s = r.sentences[+el.dataset.i]; if (!s.t) r.sentences.splice(+el.dataset.i, 1); else s.editing = false; draw(); };
  ACT['sent-save'] = function (el) {
    var r = cur(), i = +el.dataset.i, s = r.sentences[i], t = panel.querySelector('#sent-' + i).value.trim().replace(/\s+/g, ' ');
    if (!t) { r.sentences.splice(i, 1); draw(); return; }
    s.t = t; s.editing = false;
    // Same rule as the backend audit: every number must come from the period's facts (dates are not facts).
    var bad = numsIn(t).filter(function (n) { return r.nums.indexOf(n) < 0; });
    if (bad.length) { s.flag = 'num'; s.why = 'Số “' + bad.join('”, “') + '” không có trong dữ liệu đã duyệt.'; }
    else if (/%/.test(t)) { s.flag = 'num'; s.why = 'Báo cáo cho phụ huynh không dùng phần trăm.'; }
    else { delete s.flag; delete s.why; }
    draw();
  };
  ACT['sent-del'] = function (el) { cur().sentences.splice(+el.dataset.i, 1); draw(); };
  ACT['sent-add'] = function () { cur().sentences.push({ t: '', editing: true }); draw(); var r = cur(); var t = panel.querySelector('#sent-' + (r.sentences.length - 1)); if (t) t.focus(); };
  ACT['rep-discard'] = function () {
    U.confirm('Bỏ bản nháp này?', 'Bản nháp sẽ mất; tạo lại lúc nào cũng được.', 'Bỏ bản nháp', function () {
      S.reportDrafts = S.reportDrafts.filter(function (r) { return r.id !== sel; }); sel = null; U.badges(); CHAT.refreshRemind(); draw();
    }, true);
  };
  ACT['rep-approve'] = function () {
    var r = cur(), editing = r.sentences.some(function (s) { return s.editing; });
    if (editing) { U.toast('Lưu hoặc bỏ câu đang sửa trước nhé.', 'warn'); return; }
    var go = function () {
      S.reportDrafts = S.reportDrafts.filter(function (x) { return x !== r; });
      r.approved = U.today; r.sentences.forEach(function (s) { delete s.flag; delete s.why; });
      S.reports.push(r); U.badges(); CHAT.refreshRemind(); draw();
      U.toast('Đã duyệt báo cáo ' + C.label(r.kind, r.start) + ' của ' + U.esc(U.student(r.student).short) + '.');
      var b = panel.querySelector('[data-act="rep-pdf"]'); if (b) b.focus();
    };
    var fl = r.sentences.filter(function (s) { return s.flag; }).length;
    if (fl) U.confirm('Còn ' + fl + ' câu cần xem lại', 'Câu gạch chân vàng có thể chưa đúng với dữ liệu. Vẫn duyệt báo cáo?', 'Vẫn duyệt', go); else go();
  };
  ACT['rep-pdf'] = function () {
    var r = cur(), st = U.student(r.student);
    U.print('<h1>Báo cáo học tập</h1><p class="p-meta">' + U.esc(st.name) + ' · lớp ' + st.grade + ' · ' + C.label(r.kind, r.start) + '</p>' +
      r.sentences.map(function (s) { return '<p>' + U.esc(s.t) + '</p>'; }).join('') + '<p class="p-meta" style="margin-top:18pt">Gia sư Toán · duyệt ngày ' + U.d(r.approved) + '</p>', 'báo cáo');
  };

  TABS['bao-cao'] = {
    render: function (p) {
      panel = p; draw();
      p.addEventListener('change', function (ev) {
        if (ev.target.id === 'rep-student') { form.student = +ev.target.value; msg = ''; draw(); }
        if (ev.target.id === 'rep-start') { form.start = ev.target.value; msg = ''; draw(); }
        if (ev.target.id === 'rep-filter') { filt = +ev.target.value; draw(); }
      });
    },
    onShow: function () { draw(); }
  };
  return C;
})();
