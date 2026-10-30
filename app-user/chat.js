/* Tab Trợ lý: chat with the Orchestrator (scripted), grading cards, worksheet draft panel, reminders, old conversations. */
var CHAT = (function () {
  var C = {};
  var convs = [], cur = null, cards = {}, cardSeq = 0, msgSeq = 0;
  var mentionMap = {}, attached = null, pop = { open: false, items: [], i: 0, start: 0 };
  var drafts = {}, draftSid = null, instant = false, panel = null, remindOpen = true;
  var CODE_RE = /\b\d[A-Z]{2}-[A-Z0-9]+-\d{3}\b/g;
  var INBOX = A.inbox.concat([{ file: 'bai-lam-moi.tex', student: null, date: null, job: 'j-bao' }]);
  var SWAP_KIND = A.kinds.find(function (k) { return /^Nhầm phép toán/.test(k.label); }).id;
  S.wsDraftPending = true;

  function name(sid) { var s = U.student(sid); return s ? s.short : '?'; }
  function full(sid) { var s = U.student(sid); return s ? s.name : '?'; }
  function active() { return S.students.filter(function (s) { return !s.archived; }); }
  function src(text) { return '<p class="src"><b>Nguồn:</b> ' + text + '</p>'; }
  function btn(act, label, attrs, cls) { return '<button type="button" class="btn btn-sm ' + (cls || '') + '" data-act="' + act + '" ' + (attrs || '') + '>' + label + '</button>'; }

  // ---------------- conversations ----------------
  function newConv(title, date) {
    var c = { id: 'v' + (convs.length + 1), title: title || 'Cuộc trò chuyện mới', date: date || U.today, msgs: [], fresh: !title };
    convs.unshift(c); return c;
  }
  function push(m) {
    m.id = 'm' + (++msgSeq); cur.msgs.push(m);
    var list = panel && panel.querySelector('#chat-msgs');
    if (list) { list.insertAdjacentHTML('beforeend', msgHTML(m)); hydrate(list.lastElementChild); scrollEnd(); }
    return m;
  }
  function msgHTML(m) {
    if (m.who === 'me') return '<div class="msg msg-me" data-msg="' + m.id + '"><div class="bubble">' + m.html + '</div></div>';
    return '<div class="msg msg-bot" data-msg="' + m.id + '"><span class="avatar" aria-hidden="true">GS</span><div class="bubble">' + m.html + '</div></div>';
  }
  function hydrate(el) {
    el.querySelectorAll('[data-card]').forEach(function (h) { renderCard(h.dataset.card); });
    U.typeset(el);
  }
  function scrollEnd() { var s = panel && panel.querySelector('.chat-scroll'); if (s) s.scrollTop = s.scrollHeight; }
  function me(text, sids) {
    var html = U.esc(text);
    Object.keys(mentionMap).concat(sids.map(function (s) { return '@' + name(s); })).forEach(function (k) {
      html = html.split(U.esc(k)).join('<span class="mention">' + U.esc(k.slice(1)) + '</span>');
    });
    sids.forEach(function (s) { html = html.split(U.esc(full(s))).join('<span class="mention">' + U.esc(full(s)) + '</span>'); });
    if (attached) html = '<span class="file-chip"><span>📄 ' + U.esc(attached.file) + '</span></span>' + (text ? '<p>' + html + '</p>' : '');
    push({ who: 'me', html: html });
    if (cur.fresh && text) { cur.title = text.length > 42 ? text.slice(0, 40) + '…' : text; cur.fresh = false; renderConvs(); }
  }
  function bot(html) { return push({ who: 'bot', html: html }); }
  function think(fn) {
    if (instant) { fn(); return; }
    var list = panel.querySelector('#chat-msgs');
    list.insertAdjacentHTML('beforeend', '<div class="msg msg-bot" id="typing"><span class="avatar" aria-hidden="true">GS</span><div class="bubble"><span class="typing">Trợ lý đang trả lời</span></div></div>');
    scrollEnd();
    setTimeout(function () { var t = document.getElementById('typing'); if (t) t.remove(); fn(); }, 450);
  }
  function later(ms, fn) { if (instant) fn(); else setTimeout(fn, ms); }

  // ---------------- intent routing (mock Orchestrator) ----------------
  function handle(text, sids, file) {
    var n = U.norm(text), sid = sids[0] || null;
    var codes = text.match(CODE_RE) || [];
    if (file) return grade(file, sid);
    if (codes.length && (!text.replace(CODE_RE, '').replace(/[\s,;.+]+/g, '') || /them|vao phieu/.test(n))) return byCodes(codes);
    if (n.length < 24 && /^(ok|oke|okay|duoc|dong y|luu|duyet|chot)\b/.test(n)) {
      return bot('<p>Mình chưa lưu gì cả. Muốn lưu, thầy/cô bấm nút trên thẻ: <b>Lưu kết quả</b>, <b>Tạo phiếu</b>, <b>Duyệt báo cáo</b> hoặc <b>Lưu vào ngân hàng</b>.</p>');
    }
    if (/\bcham\b/.test(n)) return sid ? grade(null, sid) : askStudent(text, 'Chấm bài của học sinh nào?');
    if (/phieu|goi y|de xuat|soan .*bai/.test(n)) return sid ? worksheet(sid, text) : askStudent(text, 'Soạn phiếu cho học sinh nào?');
    if (/bao cao/.test(n)) return sid ? report(sid, n) : askStudent(text, 'Làm báo cáo cho học sinh nào?');
    if (!sid && (/\bai\b.*(nham|sai|quen)/.test(n) || /chuyen ve|nham dau/.test(n))) return compare();
    if (/\btim\b|\bbai\b.*\bmuc\b/.test(n)) return search(text);
    if (sid) return profile(sid);
    if (/meo|cach day|giai thich|lam sao|tai sao/.test(n)) return general(text);
    if (/(yeu|tien bo|the nao|ra sao|kem)/.test(n)) return askStudent(text, 'Thầy/cô hỏi về học sinh nào? Gõ <b>@</b> rồi chọn tên, hoặc bấm một tên dưới đây.');
    bot('<p>Mình chưa rõ ý thầy/cô. Mình làm được những việc này:</p>' + suggestHTML());
  }
  function askStudent(text, q) {
    bot('<p>' + q + '</p><div class="row">' + active().map(function (s) {
      return btn('pick-student', U.esc(s.short), 'data-sid="' + s.id + '" data-q="' + U.esc(text) + '"');
    }).join('') + '</div><p class="small muted">Tên gọi ngắn không có <b>@</b> thì trợ lý không nhận ra, để khỏi nhầm chữ “Minh” trong “chứng minh”.</p>');
  }
  ACT['pick-student'] = function (el) {
    var sid = +el.dataset.sid, q = el.dataset.q;
    el.closest('.row').querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    push({ who: 'me', html: '<span class="mention">' + U.esc(name(sid)) + '</span>' });
    think(function () { handle(q, [sid], null); });
  };

  function suggestHTML() {
    var Q = [
      ['Chấm bài của An hôm nay', 'Chấm bài này cho @An', 1, 'hs01-2026-10-21.tex'],
      ['Gợi ý 6 bài cho An buổi thứ Bảy', 'Gợi ý 6 bài cho @An buổi thứ Bảy', 1],
      ['Tháng này An yếu gì?', 'Tháng này @An yếu gì?', 1],
      ['Ai còn nhầm dấu khi chuyển vế?', 'Ai còn nhầm dấu khi chuyển vế?'],
      ['Làm báo cáo tuần cho Bảo', 'Làm báo cáo tuần cho @Bảo', 2],
      ['Tìm 3 bài Viète mức vừa', 'Tìm 3 bài Viète mức vừa']
    ];
    return '<div class="suggest">' + Q.map(function (q) {
      return '<button type="button" class="btn btn-sm" data-act="suggest" data-q="' + U.esc(q[1]) + '"' + (q[2] ? ' data-sid="' + q[2] + '"' : '') + (q[3] ? ' data-file="' + q[3] + '"' : '') + '>' + q[0] + '</button>';
    }).join('') + '</div>';
  }
  ACT.suggest = function (el) {
    var sid = el.dataset.sid ? +el.dataset.sid : null;
    if (sid) mentionMap['@' + name(sid)] = sid;
    if (el.dataset.file) attached = INBOX.find(function (f) { return f.file === el.dataset.file; });
    send(el.dataset.q);
  };

  // ---------------- answers ----------------
  function byCodes(codes) {
    var found = codes.filter(function (c) { return A.REF[c]; }), missing = codes.filter(function (c) { return !A.REF[c]; });
    var d = draftSid != null && drafts[draftSid] && drafts[draftSid].status === 'draft' ? drafts[draftSid] : null;
    var html = '';
    if (d) {
      var added = [], dup = [];
      found.forEach(function (c) {
        var p = A.REF[c];
        if (d.items.some(function (it) { return it.pid === p.id; })) dup.push(c);
        else { d.items.push({ pid: p.id, why: 'Thầy/cô tự thêm', b: null, isNew: true }); added.push(c); }
      });
      if (added.length) html += '<p>Đã thêm <b>' + added.join(', ') + '</b> vào phiếu nháp của <b>' + U.esc(name(d.student)) + '</b>.</p>';
      if (dup.length) html += '<p>' + dup.join(', ') + ' đã có trong phiếu.</p>';
      renderDraft(); openDraft();
    } else if (found.length) {
      html += '<p>' + (found.length > 1 ? 'Các bài' : 'Bài') + ' thầy/cô gõ mã:</p><div class="pcards">' + found.map(function (c) { return pcard(A.REF[c]); }).join('') + '</div>';
    }
    if (missing.length) html += '<p>Không tìm thấy bài <b>' + missing.join(', ') + '</b> trong ngân hàng.</p>';
    bot(html + '<p class="src">Nhận mã bài trực tiếp, không cần hỏi trợ lý.</p>');
  }
  function pcard(p, withAdd) {
    var sk = p.skills.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(U.skillName(k)) + '</span>'; }).join(' ');
    var d = draftSid != null && drafts[draftSid] && drafts[draftSid].status === 'draft';
    return '<div class="pcard"><div class="pcard-head"><span class="ref">' + p.ref + '</span>' + U.diffChip(p.level) + ' <span class="chip">lớp ' + p.grade + '</span> ' + sk + '</div>' +
      U.texHtml(p.statement) +
      '<div class="row">' + btn('pc-sol', 'Xem lời giải', 'data-pid="' + p.id + '" aria-expanded="false"') +
      (d || withAdd ? btn('pc-add', 'Thêm vào phiếu', 'data-pid="' + p.id + '"') : '') +
      btn('pc-bank', 'Mở trong Ngân hàng', 'data-pid="' + p.id + '"', 'btn-ghost') + '</div>' +
      '<div class="sol" hidden>' + p.solution.map(function (s) { return U.texHtml(s); }).join('') + '</div></div>';
  }
  ACT['pc-sol'] = function (el) {
    var sol = el.closest('.pcard').querySelector('.sol'), open = sol.hidden;
    sol.hidden = !open; el.setAttribute('aria-expanded', open); el.textContent = open ? 'Ẩn lời giải' : 'Xem lời giải'; U.typeset(sol);
  };
  ACT['pc-add'] = function (el) {
    var p = A.P[+el.dataset.pid], d = drafts[draftSid];
    if (!d || d.status !== 'draft') { U.toast('Chưa có phiếu nháp nào đang mở. Hãy nhờ trợ lý “gợi ý bài cho @…” trước.', 'warn'); return; }
    if (d.items.some(function (it) { return it.pid === p.id; })) { U.toast(p.ref + ' đã có trong phiếu.', 'info'); return; }
    d.items.push({ pid: p.id, why: 'Thầy/cô tự thêm', b: null, isNew: true });
    el.disabled = true; el.textContent = 'Đã thêm'; renderDraft(); openDraft();
  };
  ACT['pc-bank'] = function (el) { BANK.openProblem(+el.dataset.pid); };

  function monthSessions(sid) {
    var m = U.today.slice(0, 7);
    return U.studentSessions(sid).filter(function (s) { return s.date.slice(0, 7) === m; }).reverse();
  }
  function profile(sid) {
    var nm = name(sid), lv = S.levels[sid] || {}, m1 = U.today.slice(0, 8) + '01';
    var ses = monthSessions(sid);
    var chua = Object.keys(lv).filter(function (k) { return lv[k].lv === 'chua'; });
    var down = Object.keys(lv).filter(function (k) { return lv[k].ch === 'down' && lv[k].last >= m1; });
    var rec = (A.recurring[sid] || []).filter(function (r) { return !r.resolved; }).sort(function (a, b) { return b.count - a.count; });
    var h = '<p>Tháng ' + (+U.today.slice(5, 7)) + ' (đến ' + U.dm(U.today) + '), <b>' + nm + '</b> có ' + ses.length + ' buổi đã chấm' +
      (ses.length ? ': ' + ses.map(function (s) { return U.dm(s.date) + ' được ' + U.sessionScore(s).ten + '/10'; }).join(', ') : '') + '.</p>';
    h += chua.length ? '<p>Chưa vững: ' + chua.map(function (k) { return '“' + U.esc(U.skillName(+k)) + '”'; }).join(', ') + '.</p>'
      : '<p>Không có kỹ năng nào ở mức <b>chưa vững</b>.</p>';
    if (down.length) h += '<p>Cần ôn (kết quả đi xuống ở buổi gần nhất): ' + down.slice(0, 4).map(function (k) { return '“' + U.esc(U.skillName(+k)) + '”'; }).join(', ') + '.</p>';
    if (rec.length) {
      h += '<p>Lỗi còn lặp lại:</p><ul>' + rec.slice(0, 4).map(function (r) {
        return '<li>“' + U.esc(U.kindLabel(r.kind).toLowerCase()) + '” ở “' + U.esc(U.skillName(r.skill)) + '” — ' + r.count + ' lần, lần cuối ' + U.dm(r.last) + '</li>';
      }).join('') + '</ul>';
    } else h += '<p>Không còn lỗi nào lặp lại.</p>';
    if (ses.length) h += '<p><span class="uncheck">Khoảng 3/4 số bài tháng này em làm đúng gần hết.</span><br><span class="uncheck-note">Số chưa kiểm: con số này không có trong dữ liệu vừa lấy — thầy/cô đừng dựa vào câu này.</span></p>';
    h += '<div class="row">' + btn('ask', 'Soạn phiếu ôn cho ' + U.esc(nm), 'data-q="Gợi ý 6 bài cho @' + U.esc(nm) + '" data-sid="' + sid + '"') + btn('open-student', 'Mở hồ sơ ' + U.esc(nm), 'data-sid="' + sid + '"', 'btn-ghost') + '</div>';
    bot(h + src('hồ sơ của ' + U.esc(nm) + ' · lỗi đã duyệt từ ' + U.d(m1)));
  }
  ACT.ask = function (el) { var sid = el.dataset.sid ? +el.dataset.sid : null; if (sid) mentionMap['@' + name(sid)] = sid; send(el.dataset.q); };
  ACT['open-student'] = function (el) { STU.open(+el.dataset.sid); };

  function compare() {
    var rows = [];
    S.students.forEach(function (s) {
      (A.recurring[s.id] || []).forEach(function (r) { if (r.kind === SWAP_KIND && !r.resolved) rows.push({ s: s, r: r }); });
    });
    var by = {};
    rows.forEach(function (x) { (by[x.s.id] = by[x.s.id] || { s: x.s, n: 0, last: '', skills: [] }); var b = by[x.s.id]; b.n += x.r.count; if (x.r.last > b.last) b.last = x.r.last; b.skills.push(U.skillName(x.r.skill)); });
    var list = Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.n - a.n; });
    var h = '<p>Còn <b>' + list.length + ' em</b> chưa hết lỗi “nhầm phép toán hoặc dấu (+/−)”:</p>' +
      '<div class="table-wrap"><table class="tbl"><thead><tr><th>Học sinh</th><th class="al-right">Số lần</th><th>Lần cuối</th><th>Ở phần</th></tr></thead><tbody>' +
      list.map(function (b) { return '<tr><td><b>' + U.esc(b.s.short) + '</b></td><td class="al-right">' + b.n + '</td><td>' + U.dm(b.last) + '</td><td>' + b.skills.map(U.esc).join('; ') + '</td></tr>'; }).join('') +
      '</tbody></table></div><p class="small muted">Dữ liệu ghi theo loại lỗi “nhầm dấu”, không tách riêng lúc chuyển vế.</p>' +
      '<div class="row">' + list.slice(0, 2).map(function (b) { return btn('ask', 'Soạn phiếu ôn cho ' + U.esc(b.s.short), 'data-q="Gợi ý 6 bài cho @' + U.esc(b.s.short) + '" data-sid="' + b.s.id + '"'); }).join('') + '</div>';
    bot(h + src('so sánh lỗi đã duyệt của ' + active().length + ' học sinh'));
  }

  var STOP = ['tim', 'cho', 'toi', 'minh', 'muc', 'cac', 'nhung', 've', 'co', 'la', 'giup', 'mot', 'vai', 'bai', 'de', 'vua', 'kho', 'o'];
  function search(text) {
    var n = U.norm(text);
    var lvm = n.match(/muc (de|vua|kho)\b/), lv = lvm ? lvm[1] : null;
    var cnt = n.match(/(\d+)\s*bai/), k = cnt ? Math.min(10, +cnt[1]) : 3;
    var toks = n.replace(/\d+/g, ' ').split(/[^a-z0-9]+/).filter(function (t) { return t.length > 1 && STOP.indexOf(t) < 0; });
    var res = A.problems.map(function (p) {
      var hay = U.norm(p.statement + ' ' + p.skills.map(U.skillName).join(' ') + ' ' + (A.TP[p.topic] ? A.TP[p.topic].name : ''));
      return { p: p, s: toks.filter(function (t) { return hay.indexOf(t) >= 0; }).length };
    }).filter(function (x) { return toks.length && x.s === toks.length && (!lv || x.p.level === lv); }).slice(0, k);
    var h = res.length ? '<p>Mình tìm được ' + res.length + ' bài' + (lv ? ' mức ' + U.DIFF[lv] : '') + ':</p><div class="pcards">' + res.map(function (x) { return pcard(x.p); }).join('') + '</div>'
      : '<p>Không thấy bài nào khớp “' + U.esc(text) + '”. Thử bỏ bớt từ, hoặc xem tab <b>Ngân hàng bài</b>.</p>';
    bot(h + src('tìm trong ngân hàng bài (' + A.problems.length + ' bài)'));
  }
  function general() {
    bot('<p>Một cách hay: cho em viết riêng dòng “a = …, b = …, c = …” (giữ cả dấu) trước khi thay vào công thức, rồi đọc lại dấu của từng số. Với Viète, nhắc em kiểm tra phương trình có nghiệm trước khi dùng tổng và tích.</p>' +
      '<p class="src">Câu trả lời này không lấy từ dữ liệu học sinh.</p>');
  }

  // ---------------- reports (hand-off to tab Báo cáo) ----------------
  function report(sid, n) {
    var kind = /\bngay\b|\bbuoi\b/.test(n) ? 'day' : /\btuan\b/.test(n) ? 'week' : 'month', start;
    if (kind === 'week') start = U.addDays(U.monday(U.today), /tuan truoc/.test(n) ? -7 : 0);
    else if (kind === 'month') {
      var mm = n.match(/thang (\d{1,2})\b/), m = mm ? +mm[1] : +U.today.slice(5, 7) - (/thang truoc/.test(n) ? 1 : 0);
      start = U.today.slice(0, 4) + '-' + String(m).padStart(2, '0') + '-01';
    } else {
      var dm = n.match(/(\d{1,2})\/(\d{1,2})/), last = U.studentSessions(sid)[0];
      start = dm ? U.today.slice(0, 4) + '-' + dm[2].padStart(2, '0') + '-' + dm[1].padStart(2, '0') : (last ? last.date : U.today);
    }
    startReport(sid, kind, start);
  }
  function startReport(sid, kind, start) {
    var nm = name(sid), label = REP.label(kind, start), ex = REP.find(sid, kind, start);
    if (ex && ex.approved) {
      return bot('<p>Báo cáo ' + label + ' của <b>' + nm + '</b> đã duyệt ngày ' + U.d(ex.approved) + '. Mỗi kỳ chỉ duyệt một lần.</p><div class="row">' + btn('rep-open', 'Xem báo cáo', 'data-id="' + ex.id + '"', 'btn-primary') + '</div>' + src('danh sách báo cáo đã duyệt'));
    }
    if (ex) return bot('<p>Đã có bản nháp báo cáo ' + label + ' của <b>' + nm + '</b>, chưa duyệt.</p><div class="row">' + btn('rep-open', 'Mở trong Báo cáo', 'data-id="' + ex.id + '"', 'btn-primary') + '</div>');
    var r = REP.make(sid, kind, start);
    if (!r.ok) {
      var acts = '';
      U.pendingJobs(sid).forEach(function (j) { var J = A.JOB[j.id]; if (REP.inPeriod(J.date, kind, start)) acts += btn('open-job', 'Duyệt bài ' + U.dm(J.date) + ' trước', 'data-job="' + j.id + '"', 'btn-primary'); });
      var prev = kind === 'week' ? U.addDays(start, -7) : kind === 'month' ? U.iso(new Date(Date.UTC(+start.slice(0, 4), +start.slice(5, 7) - 2, 1))) : null;
      if (prev) acts += btn('rep-start', 'Làm báo cáo ' + REP.label(kind, prev), 'data-sid="' + sid + '" data-kind="' + kind + '" data-start="' + prev + '"');
      return bot('<p>' + r.reason + '</p>' + (acts ? '<div class="row">' + acts + '</div>' : '') + src('các buổi đã duyệt của ' + nm));
    }
    var id = 'c' + (++cardSeq);
    cards[id] = { type: 'rep', draft: r.draft.id, stage: instant ? 3 : 0 };
    bot('<p>Mình làm bản nháp báo cáo ' + label + ' cho <b>' + nm + '</b>.</p><div class="card-host" data-card="' + id + '"></div>' + src('số liệu các buổi đã duyệt trong kỳ'));
    [1, 2, 3].forEach(function (st, i) { later(500 * (i + 1), function () { cards[id].stage = st; renderCard(id); }); });
  }
  ACT['rep-start'] = function (el) { el.disabled = true; think(function () { startReport(+el.dataset.sid, el.dataset.kind, el.dataset.start); }); };
  ACT['rep-open'] = function (el) { var id = el.dataset.id; REP.open(isNaN(+id) ? id : +id); };

  // ---------------- grading (G1) ----------------
  function grade(file, sid) {
    if (!file) {
      var f = INBOX.find(function (x) { return x.student === sid && !jobSaved(x.job); });
      if (!f) {
        var pend = U.pendingJobs(sid)[0];
        if (pend) return openJob(pend.id);
        return bot('<p>Chưa thấy bài mới nào của <b>' + name(sid) + '</b> trong thư mục bài nộp. Thầy/cô bấm 📎 để đính kèm file .tex.</p>');
      }
      file = f;
    }
    if (jobSaved(file.job) && file.student) return bot('<p>Bài ' + U.esc(file.file) + ' đã chấm và lưu rồi.</p>');
    var who = sid || file.student;
    if (!who || !file.date) {
      return bot('<p>File <b>' + U.esc(file.file) + '</b> không ghi tên học sinh và ngày học. Bài này của ai, học buổi nào?</p>' +
        '<div class="row"><label class="field"><span>Học sinh</span><select class="ask-sid">' + active().map(function (s) { return '<option value="' + s.id + '"' + (s.id === who ? ' selected' : '') + '>' + U.esc(s.name) + '</option>'; }).join('') + '</select></label>' +
        '<label class="field"><span>Ngày học</span><input type="date" class="ask-date" value="' + U.today + '"></label></div>' +
        '<div class="row">' + btn('g-ask-go', 'Chấm bài này', 'data-file="' + U.esc(file.file) + '"', 'btn-primary') + '</div>');
    }
    startJob(file.job, who, file.date);
  }
  ACT['g-ask-go'] = function (el) {
    var b = el.closest('.bubble'), sid = +b.querySelector('.ask-sid').value, date = b.querySelector('.ask-date').value;
    if (!date) { U.toast('Chọn ngày học trước nhé.', 'warn'); return; }
    el.disabled = true;
    var f = INBOX.find(function (x) { return x.file === el.dataset.file; });
    push({ who: 'me', html: 'Bài của <span class="mention">' + U.esc(name(sid)) + '</span>, buổi ' + U.d(date) });
    think(function () { startJob(f.job, sid, date); });
  };
  function jobSaved(jid) { var j = S.jobs.find(function (x) { return x.id === jid; }); return j && j.status === 'saved'; }
  function startJob(jid, sid, date) {
    var J = A.JOB[jid], id = 'c' + (++cardSeq);
    cards[id] = { type: 'grade', job: jid, student: sid, date: date, stage: 'reading', dec: {}, edit: {}, added: [], match: {}, work: {}, addForm: null };
    bot('<p>Mình chấm bài của <b>' + name(sid) + '</b>, buổi ' + U.wd(date) + ' ' + U.d(date) + ' (' + J.problems.length + ' bài).</p><div class="card-host" data-card="' + id + '"></div>');
    later(900, function () {
      var c = cards[id];
      if (J.problems.some(function (p) { return p.confirm; })) { c.stage = 'confirm'; renderCard(id); }
      else runGrading(id);
    });
  }
  function runGrading(id) {
    var c = cards[id]; c.stage = 'grading'; c.prog = 1; renderCard(id);
    var J = A.JOB[c.job], k = 1;
    (function tick() {
      if (k >= J.problems.length) { later(500, function () { c.stage = 'review'; setJob(c.job, 'review'); renderCard(id); }); return; }
      later(450, function () { k += 1; c.prog = k; renderCard(id); tick(); });
    })();
  }
  function setJob(jid, st) { var j = S.jobs.find(function (x) { return x.id === jid; }); if (j && j.status !== 'saved') j.status = st; C.refreshRemind(); }
  function openJob(jid) {
    for (var k in cards) if (cards[k].type === 'grade' && cards[k].job === jid && cur.msgs.some(function (m) { return m.html.indexOf('data-card="' + k + '"') >= 0; })) {
      var h = panel.querySelector('[data-card="' + k + '"]'); if (h) h.scrollIntoView({ block: 'start', behavior: 'smooth' }); return;
    }
    var J = A.JOB[jid], st = S.jobs.find(function (x) { return x.id === jid; }).status, id = 'c' + (++cardSeq);
    cards[id] = { type: 'grade', job: jid, student: J.student, date: J.date, stage: st === 'match' ? 'confirm' : st === 'failed' ? 'failed' : 'review', dec: {}, edit: {}, added: [], match: {}, work: {}, addForm: null };
    var why = st === 'match' ? 'cần thầy/cô xác nhận một bài trước khi chấm' : st === 'failed' ? 'chấm chưa xong' : 'đã chấm xong, chờ thầy/cô duyệt từng lỗi';
    bot('<p>Bài của <b>' + name(J.student) + '</b>, buổi ' + U.d(J.date) + ' — ' + why + '.</p><div class="card-host" data-card="' + id + '"></div>');
  }
  C.openJob = function (jid) { U.tab('tro-ly'); openJob(jid); };
  ACT['open-job'] = function (el) { el.disabled = true; openJob(el.dataset.job); };

  function probOf(c, p) { return A.P[c.match[p.seq] && c.match[p.seq] !== 'skip' ? c.match[p.seq] : p.pid] || A.P[p.pid]; }
  function mistakesOf(c, seq) {
    var J = A.JOB[c.job];
    return J.mistakes.filter(function (m) { return m.seq === seq; });
  }
  function allMistakes(c) {
    var J = A.JOB[c.job];
    return J.mistakes.filter(function (m) { return c.match[m.seq] !== 'skip'; });
  }
  function undecided(c) { return allMistakes(c).filter(function (m) { return !c.dec[m.id]; }).length; }
  function kept(c) {
    var out = [];
    allMistakes(c).forEach(function (m) { if (c.dec[m.id] === 'ok' || c.dec[m.id] === 'edit') out.push(Object.assign({}, m, c.edit[m.id] || {})); });
    return out.concat(c.added);
  }
  function totals(c) {
    var sc = 0, mx = 0;
    A.JOB[c.job].problems.forEach(function (p) { if (c.match[p.seq] !== 'skip') { sc += p.score; mx += p.max; } });
    return { sc: sc, mx: mx };
  }
  function preview(c) {
    var sk = {}, lv = S.levels[c.student] || {};
    A.JOB[c.job].problems.forEach(function (p) { if (c.match[p.seq] !== 'skip') probOf(c, p).skills.forEach(function (k) { sk[k] = sk[k] || 0; }); });
    kept(c).forEach(function (m) { if (m.skill) sk[m.skill] = (sk[m.skill] || 0) + 1; });
    return Object.keys(sk).map(function (k) {
      var cur = lv[k] ? lv[k].lv : 'dang';
      // Elo: a clean problem on an already strong skill barely moves it.
      return { k: +k, n: sk[k], ch: sk[k] ? 'down' : cur === 'vung' ? 'keep' : 'up', lv: cur };
    });
  }
  function kindOptions(sel) { return A.kinds.map(function (k) { return '<option value="' + k.id + '"' + (k.id === sel ? ' selected' : '') + '>' + U.esc(k.label) + '</option>'; }).join(''); }
  function skillOptions(sel, first) {
    var pri = (first || []).map(function (k) { return '<option value="' + k + '"' + (k === sel ? ' selected' : '') + '>' + U.esc(U.skillName(k)) + '</option>'; }).join('');
    var rest = A.skills.filter(function (k) { return (first || []).indexOf(k.id) < 0; }).map(function (k) { return '<option value="' + k.id + '"' + (k.id === sel ? ' selected' : '') + '>' + U.esc(k.name) + '</option>'; }).join('');
    return '<option value="">Không gắn kỹ năng</option>' + (pri ? '<optgroup label="Kỹ năng của bài">' + pri + '</optgroup>' : '') + '<optgroup label="Kỹ năng khác">' + rest + '</optgroup>';
  }
  function stepsHTML(stage) {
    var S3 = [['reading', 'Đang đọc bài…', 'Đã đọc bài'], ['grading', 'Đang chấm…', 'Đã chấm'], ['done', 'Xong', 'Xong']];
    var at = { reading: 0, confirm: 0, grading: 1, failed: 1, review: 2, saved: 2 }[stage];
    return '<ol class="steps" aria-label="Tiến độ">' + S3.map(function (s, i) {
      var cls = i < at || stage === 'saved' ? 'done' : i === at ? (stage === 'confirm' || stage === 'failed' ? 'wait' : 'on') : '';
      var txt = i < at ? s[2] : i === at && stage === 'confirm' ? 'Chờ thầy/cô xác nhận bài' : i === at && stage === 'failed' ? 'Chấm chưa xong' : s[1];
      return '<li class="' + cls + '"' + (i === at ? ' aria-current="step"' : '') + '>' + txt + '</li>';
    }).join('') + '</ol>';
  }
  function mistakeHTML(c, m, added) {
    var d = added ? 'ok' : c.dec[m.id], e = Object.assign({}, m, (c.edit[m.id] || {}));
    var cls = 'mistake' + (d ? ' d-' + d : '') + (added ? ' is-added' : '');
    var h = '<div class="' + cls + '" data-mid="' + m.id + '"><div class="m-text stack" style="gap:4px">' +
      '<div class="row"><span class="m-title">' + U.esc(U.kindLabel(e.kind)) + '</span>' + (m.unsure && !added ? '<span class="chip chip-warn">Trợ lý chưa chắc</span>' : '') + (added ? '<span class="chip chip-info">Thầy/cô thêm</span>' : '') + (d === 'edit' ? '<span class="chip chip-info">Đã sửa</span>' : '') + '</div>' +
      '<div class="small muted">Bước ' + e.step + ' · phần “' + U.esc(U.skillName(e.skill)) + '”</div>' +
      (e.desc ? '<div class="tex">' + U.esc(e.desc) + '</div>' : '') + (e.evidence ? U.texHtml(e.evidence) : '') + '</div>' +
      (m.check && !added ? '<p class="m-check">' + U.esc(m.check) + '</p>' : '');
    if (c.stage === 'saved') return h + '</div>';
    if (added) return h + '<div class="m-acts">' + btn('g-added-del', 'Bỏ lỗi này', 'data-mid="' + m.id + '"') + '</div></div>';
    h += '<div class="m-acts" role="group" aria-label="Quyết định cho lỗi này">' +
      '<button type="button" class="btn btn-sm btn-ok" data-act="g-dec" data-v="ok" data-mid="' + m.id + '" aria-pressed="' + (d === 'ok') + '">Đúng</button>' +
      '<button type="button" class="btn btn-sm btn-edit" data-act="g-dec" data-v="edit" data-mid="' + m.id + '" aria-pressed="' + (d === 'edit') + '">Sửa</button>' +
      '<button type="button" class="btn btn-sm btn-drop" data-act="g-dec" data-v="drop" data-mid="' + m.id + '" aria-pressed="' + (d === 'drop') + '">Bỏ</button></div>';
    if (c.editing === m.id) {
      var p = A.JOB[c.job].problems.find(function (x) { return x.seq === m.seq; });
      h += '<div class="edit-form"><label class="field"><span>Loại lỗi</span><select data-f="kind">' + kindOptions(e.kind) + '</select></label>' +
        '<label class="field"><span>Kỹ năng</span><select data-f="skill">' + skillOptions(e.skill, probOf(c, p).skills) + '</select></label>' +
        '<label class="field full"><span>Mô tả (thầy/cô viết lại nếu cần)</span><textarea rows="2" data-f="desc">' + U.esc(e.desc) + '</textarea></label>' +
        '<div class="row full">' + btn('g-edit-done', 'Xong', 'data-mid="' + m.id + '"', 'btn-primary') + '</div></div>';
    }
    return h + '</div>';
  }
  function gradeHTML(id) {
    var c = cards[id], J = A.JOB[c.job], nm = name(c.student);
    var head = '<div class="gcard-head"><div class="row"><b>Bài của ' + U.esc(nm) + '</b><span class="muted small">buổi ' + U.d(c.date) + ' · ' + J.problems.length + ' bài · ' + U.esc(J.file) + '</span></div>' +
      (c.stage === 'saved' ? '<span class="chip chip-ok">Đã lưu</span>' : c.stage === 'review' ? '<span class="chip chip-warn">Chờ duyệt</span>' : c.stage === 'failed' ? '<span class="chip chip-crit">Chấm chưa xong</span>' : '<span class="chip chip-info">Đang làm</span>') + '</div>';
    var body = stepsHTML(c.stage);
    if (c.stage === 'reading') body += '<p class="typing">Đang đọc bài, tách từng bài và từng bước</p>';
    if (c.stage === 'grading') body += '<p class="typing">Đang chấm bài ' + c.prog + '/' + J.problems.length + '</p>';
    if (c.stage === 'failed') {
      body += '<div class="callout callout-crit"><p><b>Chấm chưa xong:</b> mất kết nối khi đang chấm bài 3. Bài làm vẫn còn nguyên, chưa có gì được lưu.</p><div class="row">' + btn('g-retry', 'Chấm lại', 'data-card="' + id + '"', 'btn-primary') + '</div></div>';
    }
    if (c.stage === 'confirm') {
      J.problems.filter(function (p) { return p.confirm && !c.match[p.seq]; }).slice(0, 1).forEach(function (p) {
        body += '<div class="callout callout-warn"><p><b>Bài ' + p.seq + ' không ghi mã bài.</b> Trợ lý thấy giống bài <b>' + A.P[p.confirm[0]].ref + '</b> nhất, nhưng chưa chắc. Thầy/cô chọn đúng bài:</p>' +
          '<div class="work"><div class="small muted">Đầu bài làm của em:</div>' + U.texHtml(p.steps[0]) + '</div>' +
          '<div class="stack" style="gap:6px" role="radiogroup" aria-label="Chọn bài khớp">' + p.confirm.map(function (pid, i) {
            var q = A.P[pid];
            return '<label class="match-opt"><input type="radio" name="match-' + id + '" value="' + pid + '"' + (i === 0 ? ' checked' : '') + '><span class="stack" style="gap:4px"><span><span class="ref">' + q.ref + '</span> ' + (i === 0 ? '<span class="chip chip-info">giống nhất</span>' : '') + '</span>' + U.texHtml(q.statement) + '</span></label>';
          }).join('') + '</div>' +
          '<label class="field"><span>Hoặc gõ mã bài khác</span><input type="text" class="match-code" placeholder="ví dụ 9DS-CAN-010" autocomplete="off"></label>' +
          '<div class="row">' + btn('g-match-ok', 'Đúng bài này', 'data-card="' + id + '" data-seq="' + p.seq + '"', 'btn-primary') + btn('g-match-skip', 'Bỏ bài này, không chấm', 'data-card="' + id + '" data-seq="' + p.seq + '"') + '</div></div>';
      });
    }
    if (c.stage === 'review' || c.stage === 'saved') {
      var t = totals(c);
      body += '<div class="spread"><p><b>Điểm: ' + U.score10(t.sc, t.mx) + '/10</b> <span class="muted small">(' + t.sc + '/' + t.mx + ' ý đúng)</span></p>' +
        '<p class="small muted">' + allMistakes(c).length + ' lỗi trợ lý tìm thấy' + (c.added.length ? ', ' + c.added.length + ' lỗi thầy/cô thêm' : '') + '</p></div>';
      J.problems.forEach(function (p) {
        var q = probOf(c, p), ms = mistakesOf(c, p.seq), ad = c.added.filter(function (m) { return m.seq === p.seq; });
        var hitSteps = ms.map(function (m) { return m.step; });
        body += '<div class="gprob"><div class="gprob-head"><div class="row"><b>Bài ' + p.seq + '</b><span class="ref">' + q.ref + '</span>' +
          (c.match[p.seq] === 'skip' ? '<span class="chip chip-dim">không chấm</span>' : '<span class="chip">' + p.score + '/' + p.max + ' ý</span>') +
          (p.rubricDraft ? '<span class="chip chip-warn">cách chấm nháp</span>' : '') + '</div>' +
          (c.match[p.seq] === 'skip' ? '' : btn('g-work', c.work[p.seq] ? 'Ẩn đề & bài làm' : 'Xem đề & bài làm', 'data-card="' + id + '" data-seq="' + p.seq + '" aria-expanded="' + !!c.work[p.seq] + '"', 'btn-ghost')) + '</div>';
        if (c.match[p.seq] === 'skip') { body += '<div class="gprob-body"><p class="muted">Thầy/cô đã bỏ bài này, không chấm.</p></div></div>'; return; }
        body += '<div class="gprob-body">';
        if (c.work[p.seq]) {
          body += '<div class="stack" style="gap:6px"><div class="small muted">Đề bài</div>' + U.texHtml(q.statement) + '<div class="work"><div class="small muted">Bài làm của em</div>' +
            p.steps.map(function (s, i) { return '<div class="wstep' + (hitSteps.indexOf(i + 1) >= 0 ? ' hit' : '') + '"><span class="small muted">Bước ' + (i + 1) + '</span>' + U.texHtml(s) + '</div>'; }).join('') + '</div></div>';
        }
        if (!ms.length && !ad.length) body += '<p class="muted">Không thấy lỗi nào trong bài này.</p>';
        ms.forEach(function (m) { body += mistakeHTML(c, m, false); });
        ad.forEach(function (m) { body += mistakeHTML(c, m, true); });
        if (c.stage === 'review') {
          if (c.addForm === p.seq) {
            body += '<div class="edit-form"><label class="field"><span>Loại lỗi</span><select data-f="kind">' + kindOptions(1) + '</select></label>' +
              '<label class="field"><span>Kỹ năng</span><select data-f="skill">' + skillOptions(q.skills[0], q.skills) + '</select></label>' +
              '<label class="field"><span>Ở bước</span><select data-f="step">' + p.steps.map(function (s, i) { return '<option value="' + (i + 1) + '">Bước ' + (i + 1) + '</option>'; }).join('') + '</select></label>' +
              '<label class="field full"><span>Mô tả lỗi</span><textarea rows="2" data-f="desc" placeholder="Ví dụ: quên đổi dấu khi chuyển vế"></textarea></label>' +
              '<div class="row full">' + btn('g-add-ok', 'Thêm lỗi', 'data-card="' + id + '" data-seq="' + p.seq + '"', 'btn-primary') + btn('g-add-cancel', 'Thôi', 'data-card="' + id + '"') + '</div></div>';
          } else body += '<div class="row">' + btn('g-add', '+ Thêm lỗi', 'data-card="' + id + '" data-seq="' + p.seq + '"') + '</div>';
        }
        body += '</div></div>';
      });
      var left = undecided(c);
      if (!left) {
        var pv = preview(c);
        body += '<div class="stack" style="gap:6px"><h3>Xem trước tiến bộ</h3><div class="table-wrap"><table class="tbl preview-tbl"><thead><tr><th>Kỹ năng</th><th>Sau buổi này</th><th>Mức</th></tr></thead><tbody>' +
          pv.map(function (r) { return '<tr><td>' + U.esc(U.skillName(r.k)) + (r.n ? ' <span class="small muted">(' + r.n + ' lỗi)</span>' : '') + '</td><td>' + U.chTag(r.ch) + '</td><td>' + U.lvChip(r.lv) + '</td></tr>'; }).join('') +
          '</tbody></table></div></div>';
      }
      if (c.stage === 'saved') {
        body += '<div class="callout callout-ok"><p><b>Đã lưu kết quả.</b> Dữ liệu đã được sao lưu trước khi lưu.</p></div>';
      }
    }
    var foot = '';
    if (c.stage === 'review') {
      var n = allMistakes(c).length, l = undecided(c);
      foot = '<div class="gfoot"><span class="progress-words">' + (n ? 'Đã xem ' + (n - l) + '/' + n + ' lỗi' : 'Không có lỗi nào cần xem') + '</span>' +
        '<span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="g-save" data-card="' + id + '"' + (l ? ' disabled aria-describedby="why-' + id + '"' : '') + '>Lưu kết quả</button>' +
        (l ? '<span class="reason" id="why-' + id + '">Còn ' + l + ' lỗi chưa chọn Đúng / Sửa / Bỏ.</span>' : '') + '</span></div>';
    }
    return '<div class="gcard' + (c.stage === 'saved' ? ' is-saved' : '') + '">' + head + '<div class="gcard-body">' + body + '</div>' + foot + '</div>';
  }
  function repCardHTML(id) {
    var c = cards[id], d = REP.get(c.draft);
    var steps = ['Đang lấy số liệu…', 'Đang viết…', 'Đang kiểm từng câu…', 'Xong'];
    var h = '<div class="gcard"><div class="gcard-body"><ol class="steps">' + steps.map(function (s, i) { return '<li class="' + (i < c.stage || c.stage === 3 ? 'done' : i === c.stage ? 'on' : '') + '">' + s + '</li>'; }).join('') + '</ol>';
    if (c.stage === 3 && d) {
      var fl = d.sentences.filter(function (s) { return s.flag; }).length;
      h += '<p>Bản nháp báo cáo ' + REP.label(d.kind, d.start) + ' cho <b>' + U.esc(name(d.student)) + '</b>: ' + d.sentences.length + ' câu' + (fl ? ', <b>' + fl + ' câu cần xem lại</b>' : '') + '. Chưa lưu gì — thầy/cô sửa rồi bấm “Duyệt báo cáo”.</p>' +
        '<div class="row">' + btn('rep-open', 'Mở trong Báo cáo', 'data-id="' + d.id + '"', 'btn-primary') + '</div>';
    } else if (c.stage === 3) h += '<p class="muted">Bản nháp này đã được duyệt hoặc bỏ.</p>';
    return h + '</div></div>';
  }
  function renderCard(id) {
    var host = panel && panel.querySelector('[data-card="' + id + '"]'), c = cards[id];
    if (!host || !c) return;
    host.innerHTML = c.type === 'grade' ? gradeHTML(id) : repCardHTML(id);
    U.typeset(host);
  }
  function cardOf(el) { var h = el.closest('[data-card]'); return h ? h.dataset.card : el.dataset.card; }
  ACT['g-retry'] = function (el) { runGrading(el.dataset.card); };
  ACT['g-match-ok'] = function (el) {
    var id = el.dataset.card, c = cards[id], box = el.closest('.callout'), seq = +el.dataset.seq;
    var code = box.querySelector('.match-code').value.trim().toUpperCase();
    if (code) {
      if (!A.REF[code]) { U.toast('Không có bài ' + U.esc(code) + ' trong ngân hàng.', 'warn'); return; }
      c.match[seq] = A.REF[code].id;
    } else c.match[seq] = +box.querySelector('input[type=radio]:checked').value;
    afterMatch(id);
  };
  ACT['g-match-skip'] = function (el) { var id = el.dataset.card; cards[id].match[+el.dataset.seq] = 'skip'; afterMatch(id); };
  function afterMatch(id) {
    var c = cards[id], J = A.JOB[c.job];
    if (J.problems.some(function (p) { return p.confirm && !c.match[p.seq]; })) { renderCard(id); return; }
    runGrading(id);
  }
  ACT['g-dec'] = function (el) {
    var id = cardOf(el), c = cards[id], mid = el.dataset.mid, v = el.dataset.v;
    c.dec[mid] = v;
    if (v === 'edit') {
      c.editing = mid;
      var m = A.JOB[c.job].mistakes.find(function (x) { return x.id === mid; });
      if (!c.edit[mid] && m.suggest) c.edit[mid] = { kind: m.suggest };
    } else if (c.editing === mid) c.editing = null;
    renderCard(id);
    var f = panel.querySelector('[data-mid="' + mid + '"] select'); if (f) f.focus();
  };
  ACT['g-edit-done'] = function (el) {
    var id = cardOf(el), c = cards[id], box = el.closest('.edit-form'), mid = el.dataset.mid;
    c.edit[mid] = { kind: +box.querySelector('[data-f=kind]').value, skill: +box.querySelector('[data-f=skill]').value || null, desc: box.querySelector('[data-f=desc]').value.trim() };
    c.editing = null; renderCard(id);
  };
  ACT['g-work'] = function (el) { var id = el.dataset.card, c = cards[id], s = +el.dataset.seq; c.work[s] = !c.work[s]; renderCard(id); };
  ACT['g-add'] = function (el) { var id = el.dataset.card; cards[id].addForm = +el.dataset.seq; renderCard(id); var t = panel.querySelector('[data-card="' + id + '"] .edit-form select'); if (t) t.focus(); };
  ACT['g-add-cancel'] = function (el) { var id = el.dataset.card; cards[id].addForm = null; renderCard(id); };
  ACT['g-add-ok'] = function (el) {
    var id = el.dataset.card, c = cards[id], box = el.closest('.edit-form');
    var desc = box.querySelector('[data-f=desc]').value.trim();
    if (!desc) { box.querySelector('[data-f=desc]').focus(); U.toast('Viết vài chữ mô tả lỗi trước nhé.', 'warn'); return; }
    c.added.push({ id: id + '-a' + (c.added.length + 1), seq: +el.dataset.seq, step: +box.querySelector('[data-f=step]').value, kind: +box.querySelector('[data-f=kind]').value,
      skill: +box.querySelector('[data-f=skill]').value || null, desc: desc, evidence: '' });
    c.addForm = null; renderCard(id);
  };
  ACT['g-added-del'] = function (el) { var id = cardOf(el), c = cards[id]; c.added = c.added.filter(function (m) { return m.id !== el.dataset.mid; }); renderCard(id); };
  ACT['g-save'] = function (el) {
    var id = el.dataset.card, c = cards[id], J = A.JOB[c.job];
    if (undecided(c)) return;
    var pv = preview(c), keep = kept(c), t = totals(c);
    S.sessions.push({ id: 'new-' + c.job, student: c.student, date: c.date, problems: J.problems.filter(function (p) { return c.match[p.seq] !== 'skip'; }).map(function (p) {
      return { pid: probOf(c, p).id, score: p.score, max: p.max, steps: p.steps, mistakes: keep.filter(function (m) { return m.seq === p.seq; }) };
    }) });
    S.levels[c.student] = S.levels[c.student] || {};
    pv.forEach(function (r) { var L = S.levels[c.student][r.k] || { lv: 'dang', n: 0 }; L.ch = r.ch; L.n += 1; L.last = c.date; S.levels[c.student][r.k] = L; });
    var j = S.jobs.find(function (x) { return x.id === c.job; }); j.status = 'saved';
    c.stage = 'saved'; renderCard(id); C.refreshRemind();
    var nm = name(c.student);
    bot('<p>Đã lưu kết quả buổi ' + U.dm(c.date) + ' của <b>' + nm + '</b>: ' + U.score10(t.sc, t.mx) + '/10, ' + keep.length + ' lỗi. Đã sao lưu dữ liệu trước khi lưu.</p>' +
      '<div class="row">' + btn('open-student', 'Xem hồ sơ ' + U.esc(nm), 'data-sid="' + c.student + '"') + btn('ask', 'Soạn phiếu buổi sau', 'data-q="Gợi ý 6 bài cho @' + U.esc(nm) + '" data-sid="' + c.student + '"', 'btn-primary') + '</div>');
  };

  // ---------------- worksheet draft (G4) ----------------
  function nextLesson(sid, n) {
    var m = n.match(/(\d{1,2})\/(\d{1,2})/);
    if (m) return U.today.slice(0, 4) + '-' + m[2].padStart(2, '0') + '-' + m[1].padStart(2, '0');
    var W = ['chu nhat', 'thu hai', 'thu ba', 'thu tu', 'thu nam', 'thu sau', 'thu bay'];
    for (var i = 0; i < 7; i++) if (new RegExp('\\b' + W[i] + '\\b').test(n)) { var d = U.addDays(U.today, 1); while (U.parse(d).getUTCDay() !== i) d = U.addDays(d, 1); return d; }
    var last = U.studentSessions(sid)[0], dt = last ? last.date : U.today;
    while (dt <= U.today) dt = U.addDays(dt, 7);
    return dt;
  }
  function worksheet(sid, text) {
    var n = U.norm(text), nm = name(sid);
    if (S.wsDraftPending && A.wsDraft.student === sid && !drafts[sid]) C.openWsDraft();
    var d = drafts[sid];
    if (d && d.status === 'draft') {
      draftSid = sid; renderDraft(); openDraft();
      return bot('<p>Phiếu nháp cho <b>' + nm + '</b> (buổi ' + U.d(d.date) + ') đang mở — thầy/cô sửa tiếp ở khung phiếu.</p>');
    }
    var cnt = n.match(/(\d+)\s*bai/), k = cnt ? Math.min(12, +cnt[1]) : A.settings.n;
    var sug = A.suggest[sid] || [];
    if (!sug.length) {  // new student, no history yet: "vừa" problems of the student's grade
      var g = U.student(sid).grade;
      sug = A.problems.filter(function (p) { return p.rubric && p.level === 'vua' && p.grade <= g; }).slice(-k).map(function (p) { return { pid: p.id, b: 'vua', why: 'Vừa sức: “' + U.skillName(p.skills[0]) + '” (em mới, chưa có dữ liệu)' }; });
    }
    var items = sug.slice(0, k).map(function (x) { return { pid: x.pid, why: x.why, b: x.b }; });
    drafts[sid] = { student: sid, date: nextLesson(sid, n), items: items, status: 'draft' };
    draftSid = sid; renderDraft(); openDraft();
    var c = { on: 0, vua: 0, thu: 0 }; items.forEach(function (x) { c[x.b] += 1; });
    bot('<p>Mình chọn <b>' + items.length + ' bài</b> cho <b>' + nm + '</b> (buổi ' + U.wd(drafts[sid].date) + ' ' + U.d(drafts[sid].date) + '): ' + c.on + ' bài ôn lại, ' + c.vua + ' bài vừa sức, ' + c.thu + ' bài thử thách.' +
      (items.length < k ? ' Chỉ tìm được ' + items.length + ' bài hợp — thầy/cô thêm bài theo mã nếu cần.' : '') + '</p>' +
      '<p>Phiếu nháp ở khung bên cạnh: bỏ, đổi thứ tự, thêm bài theo mã (gõ mã ngay trong ô chat cũng được), rồi bấm <b>Tạo phiếu</b>.</p>' +
      '<div class="row">' + btn('draft-open', 'Mở phiếu nháp', '', 'draft-toggle') + '</div>' +
      src('hồ sơ của ' + U.esc(nm) + ' · ngân hàng bài (bỏ bài em đã làm trong ' + A.settings.noRepeat + ' ngày, chỉ lấy bài có cách chấm)'));
  }
  C.openWsDraft = function () {
    var w = A.wsDraft;
    if (!drafts[w.student]) drafts[w.student] = { student: w.student, date: w.date, items: w.items.map(function (x) { return { pid: x.pid, why: x.why, b: x.b }; }), status: 'draft', pending: true };
    draftSid = w.student; renderDraft(); openDraft();
  };
  function draftHTML() {
    var d = drafts[draftSid];
    if (!d) return '';
    var nm = name(d.student);
    var head = '<div class="draft-head"><div><div class="eyebrow">' + (d.status === 'saved' ? 'Phiếu đã tạo' : 'Phiếu nháp') + '</div><h2>' + U.esc(nm) + ' · ' + d.items.length + ' bài</h2></div>' +
      '<button type="button" class="icon-btn" data-act="draft-close" aria-label="Đóng khung phiếu">×</button></div>';
    if (d.status === 'saved') {
      return head + '<div class="draft-body"><div class="callout callout-ok"><p><b>Đã tạo phiếu</b> cho ' + U.esc(nm) + ', buổi ' + U.wd(d.date) + ' ' + U.d(d.date) + ' · ' + d.items.length + ' bài.</p></div>' +
        '<ol class="draft-list">' + d.items.map(function (it, i) { var p = A.P[it.pid]; return '<li class="draft-item"><span class="pos">' + (i + 1) + '</span><div><span class="ref">' + p.ref + '</span> ' + U.diffChip(p.level) + '<div class="why">' + U.esc(it.why) + '</div></div><span></span></li>'; }).join('') + '</ol></div>' +
        '<div class="draft-foot"><div class="row">' + btn('ws-tex', 'Tải .tex', '', 'btn-primary') + btn('ws-pdf', 'In PDF') + '</div>' + btn('draft-close', 'Đóng', '', 'btn-ghost') + '</div>';
    }
    var c = { on: 0, vua: 0, thu: 0 }; d.items.forEach(function (x) { if (x.b) c[x.b] += 1; });
    var own = d.items.filter(function (x) { return !x.b; }).length;
    return head + '<div class="draft-body" data-draft-panel>' +
      '<label class="field"><span>Buổi học</span><input type="date" id="ws-date" value="' + d.date + '"></label>' +
      '<p class="small muted">' + c.on + ' ôn lại · ' + c.vua + ' vừa sức · ' + c.thu + ' thử thách' + (own ? ' · ' + own + ' thầy/cô thêm' : '') + '</p>' +
      (d.items.length ? '<ol class="draft-list">' + d.items.map(function (it, i) {
        var p = A.P[it.pid];
        return '<li class="draft-item' + (it.isNew ? ' is-new' : '') + '"><span class="pos">' + (i + 1) + '</span><div class="stack" style="gap:4px"><div class="row"><span class="ref">' + p.ref + '</span>' + U.diffChip(p.level) + '</div>' +
          '<div class="small">' + U.esc(p.skills.map(U.skillName).join(' · ')) + '</div><div class="why">' + U.esc(it.why) + '</div><div class="clamp small">' + U.texHtml(p.statement) + '</div></div>' +
          '<div class="acts">' + '<button type="button" class="icon-btn icon-btn-sm" data-act="ws-move" data-i="' + i + '" data-d="-1" aria-label="Đưa bài ' + (i + 1) + ' lên"' + (i === 0 ? ' disabled' : '') + '>↑</button>' +
          '<button type="button" class="icon-btn icon-btn-sm" data-act="ws-move" data-i="' + i + '" data-d="1" aria-label="Đưa bài ' + (i + 1) + ' xuống"' + (i === d.items.length - 1 ? ' disabled' : '') + '>↓</button>' +
          '<button type="button" class="icon-btn icon-btn-sm" data-act="ws-del" data-i="' + i + '" aria-label="Bỏ bài ' + (i + 1) + '">×</button></div></li>';
      }).join('') + '</ol>' : '<div class="empty">Phiếu chưa có bài nào. Thêm bài theo mã ở dưới.</div>') +
      '<div class="row"><input type="text" id="ws-code" class="grow" placeholder="Thêm theo mã, ví dụ 9DS-PT2-012" aria-label="Thêm bài theo mã" autocomplete="off">' + btn('ws-add', 'Thêm') + '</div></div>' +
      '<div class="draft-foot"><span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="ws-create"' + (d.items.length ? '' : ' disabled') + '>Tạo phiếu</button>' +
      (d.items.length ? '' : '<span class="reason">Phiếu cần ít nhất 1 bài.</span>') + '</span><p class="small muted">Chưa lưu gì cho tới khi bấm “Tạo phiếu”.</p></div>';
  }
  function renderDraft() {
    if (!panel) return;
    var el = panel.querySelector('#draft'), asst = panel.querySelector('.asst');
    var d = drafts[draftSid];
    asst.classList.toggle('has-draft', !!d && !el.dataset.closed);
    el.hidden = !d || !!el.dataset.closed;
    el.innerHTML = draftHTML();
    U.typeset(el);
    var t = panel.querySelector('#draft-toggle');
    t.hidden = !d; if (d) t.textContent = (d.status === 'saved' ? 'Phiếu đã tạo' : 'Phiếu nháp') + ' (' + d.items.length + ')';
  }
  function openDraft() {
    var el = panel.querySelector('#draft'); delete el.dataset.closed; el.classList.add('open');
    renderDraft();
    if (matchMedia('(max-width: 860px)').matches) panel.querySelector('#sheet-back').classList.add('open');
  }
  ACT['draft-open'] = function () { openDraft(); };
  ACT['draft-close'] = function () {
    var el = panel.querySelector('#draft'); el.dataset.closed = '1'; el.classList.remove('open');
    panel.querySelector('#sheet-back').classList.remove('open'); renderDraft();
  };
  ACT['ws-move'] = function (el) {
    var d = drafts[draftSid], i = +el.dataset.i, j = i + (+el.dataset.d), it = d.items[i];
    d.items[i] = d.items[j]; d.items[j] = it; renderDraft();
    var b = panel.querySelector('[data-act="ws-move"][data-i="' + j + '"][data-d="' + el.dataset.d + '"]') || panel.querySelector('[data-act="ws-del"][data-i="' + j + '"]'); if (b) b.focus();
  };
  ACT['ws-del'] = function (el) { drafts[draftSid].items.splice(+el.dataset.i, 1); renderDraft(); };
  ACT['ws-add'] = function () {
    var inp = panel.querySelector('#ws-code'), codes = inp.value.toUpperCase().match(CODE_RE) || [], d = drafts[draftSid];
    if (!codes.length) { U.toast('Gõ mã bài, ví dụ 9DS-PT2-012.', 'warn'); inp.focus(); return; }
    var bad = [];
    codes.forEach(function (c) {
      var p = A.REF[c];
      if (!p) bad.push(c); else if (!d.items.some(function (x) { return x.pid === p.id; })) d.items.push({ pid: p.id, why: 'Thầy/cô tự thêm', b: null, isNew: true });
    });
    renderDraft();
    if (bad.length) U.toast('Không có bài ' + bad.join(', ') + ' trong ngân hàng.', 'warn');
    var n = panel.querySelector('#ws-code'); if (n) n.focus();
  };
  ACT['ws-create'] = function () {
    var d = drafts[draftSid], dt = panel.querySelector('#ws-date').value;
    if (!dt) { U.toast('Chọn ngày buổi học trước nhé.', 'warn'); return; }
    d.date = dt;
    var go = function () {
      d.status = 'saved';
      S.worksheets.push({ student: d.student, date: d.date, items: d.items.map(function (x) { return { pid: x.pid, why: x.why }; }) });
      if (d.pending) S.wsDraftPending = false;
      renderDraft(); C.refreshRemind();
      bot('<p>Đã tạo phiếu cho <b>' + name(d.student) + '</b>, buổi ' + U.wd(d.date) + ' ' + U.d(d.date) + ' · ' + d.items.length + ' bài.</p><div class="row">' + btn('ws-tex', 'Tải .tex', '', 'btn-primary') + btn('ws-pdf', 'In PDF') + '</div>');
      U.toast('Đã tạo phiếu bài tập.');
    };
    if (S.worksheets.some(function (w) { return w.student === d.student && w.date === d.date; })) {
      U.confirm('Đã có phiếu cho buổi này', 'Buổi ' + U.d(d.date) + ' của ' + U.esc(name(d.student)) + ' đã có phiếu. Tạo phiếu mới thay thế? Phiếu cũ vẫn được giữ, đánh dấu “đã thay”.', 'Tạo phiếu mới', go);
    } else go();
  };
  function wsDone() { for (var k in drafts) if (drafts[k].status === 'saved' && +k === draftSid) return drafts[k]; var all = Object.keys(drafts).map(function (k) { return drafts[k]; }).filter(function (d) { return d.status === 'saved'; }); return all[all.length - 1]; }
  ACT['ws-tex'] = function () {
    var d = wsDone(); if (!d) return;
    var s = U.student(d.student), code = 'HS-' + String(d.student).padStart(2, '0');
    var tex = '% Phiếu bài tập — ' + s.name + ' — buổi ' + U.d(d.date) + '\n\\documentclass[12pt,a4paper]{article}\n\\usepackage[utf8]{vietnam}\n\\usepackage{amsmath,amssymb}\n' +
      '\\newenvironment{problem}[1][]{\\par\\medskip\\noindent\\textbf{Bài.}\\ }{\\par}\n\\begin{document}\n\\section*{Phiếu bài tập — buổi ' + U.d(d.date) + '}\n\n' +
      d.items.map(function (it) { var p = A.P[it.pid]; return '\\begin{problem}[' + p.ref + ']\n' + p.statement + '\n\\end{problem}\n'; }).join('\n') + '\n\\end{document}\n';
    U.download('phieu-' + code + '-' + d.date + '.tex', tex);
    U.toast('Đã tải phiếu của ' + U.esc(s.short) + ' (file .tex).');
  };
  ACT['ws-pdf'] = function () {
    var d = wsDone(); if (!d) return; var s = U.student(d.student);
    U.print('<h1>Phiếu bài tập</h1><p class="p-meta">' + U.esc(s.name) + ' · buổi ' + U.wd(d.date) + ' ' + U.d(d.date) + '</p><ol>' +
      d.items.map(function (it) { var p = A.P[it.pid]; return '<li>' + U.texHtml(p.statement) + '</li>'; }).join('') + '</ol>', 'phiếu');
  };

  // ---------------- reminders ----------------
  function remindHTML() {
    var jobs = U.pendingJobs(), reps = S.reportDrafts, ws = S.wsDraftPending ? [A.wsDraft] : [];
    if (!jobs.length && !reps.length && !ws.length) return '<p class="small muted">Không có việc nào đang chờ thầy/cô.</p>';
    var total = jobs.length + reps.length + ws.length;
    var h = '<div class="spread"><h2 class="eyebrow">Việc đang chờ thầy/cô (' + total + ')</h2><button type="button" class="btn btn-ghost btn-sm" data-act="remind-toggle" aria-expanded="' + remindOpen + '" aria-controls="remind-cards">' + (remindOpen ? 'Ẩn' : 'Xem') + '</button></div>';
    if (!remindOpen) return h;
    h += '<div class="remind-cards" id="remind-cards">';
    if (jobs.length) h += '<div class="remind-card"><h3>Bài chờ duyệt <span class="n">' + jobs.length + '</span></h3>' + jobs.map(function (j) {
      var J = A.JOB[j.id], what = j.status === 'match' ? 'cần xác nhận 1 bài' : j.status === 'failed' ? 'chấm chưa xong' : J.mistakes.length + ' lỗi cần xem';
      return '<div class="remind-item"><span><b>' + U.esc(name(J.student)) + '</b> · ' + U.dm(J.date) + ' · ' + what + '</span>' + btn('open-job', 'Mở', 'data-job="' + j.id + '"') + '</div>';
    }).join('') + '</div>';
    if (reps.length) h += '<div class="remind-card"><h3>Báo cáo nháp <span class="n">' + reps.length + '</span></h3>' + reps.map(function (r) {
      return '<div class="remind-item"><span><b>' + U.esc(name(r.student)) + '</b> · ' + REP.label(r.kind, r.start) + '</span>' + btn('rep-open', 'Mở', 'data-id="' + r.id + '"') + '</div>';
    }).join('') + '</div>';
    if (ws.length) h += '<div class="remind-card"><h3>Phiếu nháp <span class="n">1</span></h3><div class="remind-item"><span><b>' + U.esc(name(A.wsDraft.student)) + '</b> · buổi ' + U.dm(A.wsDraft.date) + ' · ' + A.wsDraft.items.length + ' bài</span>' + btn('ws-pending', 'Mở') + '</div></div>';
    return h + '</div>';
  }
  C.refreshRemind = function () {
    U.badges();
    var r = panel && panel.querySelector('#remind'); if (r) r.innerHTML = remindHTML();
  };
  ACT['remind-toggle'] = function () { remindOpen = !remindOpen; C.refreshRemind(); };
  ACT['ws-pending'] = function () { C.openWsDraft(); };

  // ---------------- composer ----------------
  function send(text) {
    text = (text || '').trim();
    if (!text && !attached) return;
    var sids = [];
    Object.keys(mentionMap).forEach(function (k) { if (text.indexOf(k) >= 0 && sids.indexOf(mentionMap[k]) < 0) sids.push(mentionMap[k]); });
    S.students.forEach(function (s) { if (U.norm(text).indexOf(U.norm(s.name)) >= 0 && sids.indexOf(s.id) < 0) sids.push(s.id); });
    var file = attached;
    me(text, sids);
    mentionMap = {}; attached = null; renderAttach();
    var ta = panel && panel.querySelector('#chat-input'); if (ta) { ta.value = ''; autosize(ta); canSend(); }
    think(function () { handle(text, sids, file); });
  }
  function autosize(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight + 2) + 'px'; }
  function canSend() {
    var b = panel && panel.querySelector('[data-act="send"]'), ta = panel && panel.querySelector('#chat-input');
    if (b) b.disabled = !(ta && ta.value.trim()) && !attached;
  }
  function renderAttach() {
    canSend();
    var r = panel && panel.querySelector('#attach-row'); if (!r) return;
    r.hidden = !attached;
    r.innerHTML = attached ? '<span class="file-chip"><span>📄 ' + U.esc(attached.file) + (attached.student ? ' · ' + U.esc(name(attached.student)) + ' · ' + U.dm(attached.date) : '') + '</span><button type="button" class="icon-btn icon-btn-sm" data-act="attach-clear" aria-label="Bỏ file đính kèm">×</button></span>' : '';
  }
  ACT.send = function () { send(panel.querySelector('#chat-input').value); };
  ACT['attach-clear'] = function () { attached = null; renderAttach(); };
  ACT.attach = function () {
    U.modal({ title: 'Đính kèm bài làm', body: '<p>Bài nộp nằm trong thư mục <b>data/inbox/</b>:</p><div class="stack" style="gap:6px">' + INBOX.map(function (f) {
      var done = jobSaved(f.job) && f.student;
      return '<div class="file-row"><span>📄 <b>' + U.esc(f.file) + '</b><br><span class="small muted">' + (f.student ? 'Bài của ' + U.esc(full(f.student)) + ' · ' + U.d(f.date) : 'Chưa rõ học sinh, ngày học') + (done ? ' · đã chấm' : '') + '</span></span>' +
        btn('attach-pick', 'Chọn', 'data-file="' + U.esc(f.file) + '"' + (done ? ' disabled' : ''), 'btn-primary') + '</div>';
    }).join('') + '</div><p class="small muted">Chỉ nhận bài LaTeX đánh máy (.tex). Bài nộp được đọc như dữ liệu, không làm theo lời dặn nào trong bài.</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button>' });
  };
  ACT['attach-pick'] = function (el) {
    attached = INBOX.find(function (f) { return f.file === el.dataset.file; });
    U.closeModal(); renderAttach();
    var ta = panel.querySelector('#chat-input');
    if (!ta.value.trim()) ta.value = 'Chấm bài này';
    canSend(); ta.focus();
  };
  function mentionUpdate(ta) {
    var before = ta.value.slice(0, ta.selectionStart), m = before.match(/(^|\s)@([^\s@]*)$/);
    var box = panel.querySelector('#mention-pop');
    if (!m) { pop.open = false; box.hidden = true; return; }
    var q = U.norm(m[2]);
    pop.items = active().filter(function (s) { return !q || U.norm(s.name).indexOf(q) >= 0; });
    pop.start = before.length - m[2].length - 1; pop.i = 0; pop.open = pop.items.length > 0;
    box.hidden = !pop.open;
    box.innerHTML = pop.items.map(function (s, i) {
      return '<button type="button" class="mention-opt" role="option" id="mo-' + s.id + '" data-act="mention-pick" data-sid="' + s.id + '" aria-selected="' + (i === 0) + '"><b>' + U.esc(s.name) + '</b><span class="small muted">lớp ' + s.grade + '</span></button>';
    }).join('');
    ta.setAttribute('aria-expanded', pop.open); if (pop.open) ta.setAttribute('aria-activedescendant', 'mo-' + pop.items[0].id);
  }
  function mentionPick(sid) {
    var ta = panel.querySelector('#chat-input'), s = U.student(sid), tag = '@' + s.short;
    var end = ta.selectionStart;
    ta.value = ta.value.slice(0, pop.start) + tag + ' ' + ta.value.slice(end);
    mentionMap[tag] = sid;
    var caret = pop.start + tag.length + 1; ta.setSelectionRange(caret, caret);
    pop.open = false; panel.querySelector('#mention-pop').hidden = true; ta.setAttribute('aria-expanded', 'false'); ta.focus();
  }
  ACT['mention-pick'] = function (el) { mentionPick(+el.dataset.sid); };
  C.escape = function () {
    if (pop.open) { pop.open = false; panel.querySelector('#mention-pop').hidden = true; return true; }
    var cv = panel && panel.querySelector('.convs.open'); if (cv) { ACT['conv-toggle'](); return true; }
    var dr = panel && panel.querySelector('#draft.open'); if (dr && matchMedia('(max-width: 860px)').matches) { ACT['draft-close'](); return true; }
    return false;
  };

  // ---------------- conversation list ----------------
  function renderConvs() {
    var el = panel && panel.querySelector('#conv-list'); if (!el) return;
    el.innerHTML = convs.map(function (c) {
      return '<button type="button" class="conv-item" data-act="conv-open" data-id="' + c.id + '" aria-current="' + (c === cur) + '"><span class="t">' + U.esc(c.title) + '</span><span class="d">' + (c.date === U.today ? 'Hôm nay' : U.d(c.date)) + '</span></button>';
    }).join('');
  }
  function renderConv() {
    var list = panel.querySelector('#chat-msgs');
    list.innerHTML = cur.msgs.map(msgHTML).join('');
    hydrate(list); renderConvs(); scrollEnd();
  }
  ACT['conv-open'] = function (el) {
    cur = convs.find(function (c) { return c.id === el.dataset.id; }); renderConv();
    if (panel.querySelector('.convs.open')) ACT['conv-toggle']();
    panel.querySelector('#chat-input').focus();
  };
  ACT['conv-new'] = function () {
    cur = newConv(); welcome(); renderConv();
    if (panel.querySelector('.convs.open')) ACT['conv-toggle']();
    panel.querySelector('#chat-input').focus();
  };
  ACT['conv-toggle'] = function () {
    var cv = panel.querySelector('.convs'), open = !cv.classList.contains('open');
    cv.classList.toggle('open', open); panel.querySelector('#sheet-back').classList.toggle('open', open);
    panel.querySelector('#conv-toggle').setAttribute('aria-expanded', open);
    if (open) cv.querySelector('button').focus();
  };
  ACT['sheet-back'] = function () {
    if (panel.querySelector('.convs.open')) ACT['conv-toggle']();
    else ACT['draft-close']();
  };
  function welcome() {
    cur.msgs.push({ id: 'm' + (++msgSeq), who: 'bot', html: '<p>Chào thầy/cô! Mình giúp chấm bài, soạn phiếu, trả lời về học sinh và làm báo cáo. Gõ <b>@</b> để chọn học sinh; gõ mã bài (ví dụ <span class="ref">9DS-PT2-003</span>) để thêm thẳng vào phiếu; bấm 📎 để đính kèm bài làm.</p>' + suggestHTML() });
  }

  // ---------------- tab render ----------------
  TABS['tro-ly'] = {
    render: function (p) {
      panel = p;
      p.innerHTML = '<div class="asst">' +
        '<nav class="convs" aria-label="Các cuộc trò chuyện"><button type="button" class="btn btn-primary" data-act="conv-new">+ Cuộc trò chuyện mới</button><div class="eyebrow">Đã trò chuyện</div><div class="conv-list" id="conv-list"></div></nav>' +
        '<div class="chat"><div class="chat-head"><button type="button" class="btn btn-sm" id="conv-toggle" data-act="conv-toggle" aria-expanded="false">☰ Hội thoại</button><span class="grow"></span><button type="button" class="btn btn-sm draft-toggle" id="draft-toggle" data-act="draft-open" hidden>Phiếu nháp</button></div>' +
        '<div class="chat-scroll"><div class="chat-inner"><div class="remind" id="remind"></div><div class="stack" id="chat-msgs" aria-live="polite" style="gap:14px"></div></div></div>' +
        '<div class="composer"><div class="mention-pop" id="mention-pop" role="listbox" aria-label="Chọn học sinh" hidden></div><div class="composer-inner"><div class="row" id="attach-row" hidden></div>' +
        '<div class="composer-row"><button type="button" class="icon-btn" data-act="attach" aria-label="Đính kèm bài làm của học sinh" title="Đính kèm bài làm">📎</button>' +
        '<textarea id="chat-input" rows="1" placeholder="Hỏi trợ lý, gõ @ để chọn học sinh, hoặc gõ mã bài…" aria-label="Tin nhắn cho trợ lý" aria-controls="mention-pop" aria-autocomplete="list" aria-expanded="false"></textarea>' +
        '<button type="button" class="btn btn-primary" data-act="send">Gửi</button></div>' +
        '<p class="hint">Enter để gửi · Shift+Enter xuống dòng · Gõ “ok” trong chat không lưu gì · Tên học sinh chỉ ở trên máy này</p></div></div></div>' +
        '<aside class="draft" id="draft" aria-label="Phiếu bài tập nháp" hidden></aside><div class="sheet-back" id="sheet-back" data-act="sheet-back"></div></div>';
      if (matchMedia('(max-width: 719px)').matches) remindOpen = false;
      var ta = p.querySelector('#chat-input');
      ta.addEventListener('input', function () { autosize(ta); mentionUpdate(ta); canSend(); });
      ta.addEventListener('keydown', function (ev) {
        if (pop.open && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
          ev.preventDefault(); pop.i = (pop.i + (ev.key === 'ArrowDown' ? 1 : pop.items.length - 1)) % pop.items.length;
          p.querySelectorAll('.mention-opt').forEach(function (o, i) { o.setAttribute('aria-selected', i === pop.i); });
          ta.setAttribute('aria-activedescendant', 'mo-' + pop.items[pop.i].id); return;
        }
        if (pop.open && (ev.key === 'Enter' || ev.key === 'Tab')) { ev.preventDefault(); mentionPick(pop.items[pop.i].id); return; }
        if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); send(ta.value); }
      });
      // §6.4: Enter presses "Tạo phiếu" only while focus is inside the draft panel (the add-code box adds instead).
      p.querySelector('#draft').addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter' || ev.target.tagName === 'BUTTON') return;
        ev.preventDefault();
        if (ev.target.id === 'ws-code') ACT['ws-add'](); else { var b = p.querySelector('[data-act="ws-create"]'); if (b && !b.disabled) ACT['ws-create'](); }
      });
      p.querySelector('#draft').addEventListener('change', function (ev) { if (ev.target.id === 'ws-date' && drafts[draftSid]) drafts[draftSid].date = ev.target.value; });
      renderConv(); C.refreshRemind(); renderAttach(); renderDraft();
    }
  };

  // ---------------- seed: old conversations replayed through the same handlers ----------------
  C.init = function seed() {
    instant = true;
    [['Báo cáo tháng 9 cho An', '2026-10-03', 'Làm báo cáo tháng 9 cho @An', 1],
      ['Tìm 3 bài Viète mức vừa', '2026-10-16', 'Tìm 3 bài Viète mức vừa'],
      ['Ai còn nhầm dấu khi chuyển vế?', '2026-10-19', 'Ai còn nhầm dấu khi chuyển vế?'],
      ['Tháng này An yếu gì?', '2026-10-20', 'Tháng này @An yếu gì?', 1]].forEach(function (x) {
      cur = newConv(x[0], x[1]);
      if (x[3]) mentionMap['@' + name(x[3])] = x[3];
      var sids = x[3] ? [x[3]] : [];
      me(x[2], sids); mentionMap = {};
      handle(x[2], sids, null);
    });
    cur = newConv(); welcome();
    instant = false;
  };
  return C;
})();
