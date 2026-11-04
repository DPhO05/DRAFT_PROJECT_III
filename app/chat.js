/* Tab Trợ lý: reminders, conversations, the box (@, 📎), the assistant stream and the simple cards.
   Grading and worksheet cards register in CHAT.cards from grading.js / worksheet.js. Every server string goes through U.names / U.md / U.esc. */
(function () {
  var C = window.CHAT = { cards: {} };
  var dm = U.dm, code = U.code, btn = U.btn, norm = U.norm;
  var panel = null, students = [], pending = null, convs = [], cur = { id: null }, busy = false, remindOpen = true;
  var inbox = [], attached = null, mentionMap = {}, pop = { open: false, items: [], i: -1, start: 0 };
  var retries = {}, turnSeq = 0;
  var GROUPS = [['grading', 'Bài chờ duyệt'], ['report', 'Báo cáo nháp'], ['worksheet', 'Phiếu nháp'], ['bank_import', 'Bài mới chờ nạp']];
  var ERR = {
    not_ready: 'Trợ lý đang trả lời tin trước. Chờ một lát rồi bấm Gửi lại.',
    validation_error: 'Tin này chưa gửi được. Kiểm tra lại học sinh đã chọn rồi bấm Gửi lại.',
    not_found: 'Hội thoại này không còn nữa. Bấm Mới để bắt đầu lại.'
  };
  var UNAVAILABLE = 'Chưa trả lời được, thử lại';

  function $(sel) { return panel && panel.querySelector(sel); }
  function noop() { /* a failed refresh keeps what is on screen; the next one tries again */ }
  function nameOf(id) { return U.people[code(id)] || code(id); }
  function active() { return students.filter(function (s) { return !s.archived_at; }); }
  function scrollEnd(force) {
    var s = $('.chat-scroll');
    if (s && (force || s.scrollHeight - s.scrollTop - s.clientHeight < 120)) s.scrollTop = s.scrollHeight;
  }

  // ---- people, reminders, badge ----
  function loadPeople() {
    return U.api.get('/students?archived=true').then(function (rows) {
      students = rows; U.people = {};
      rows.forEach(function (s) { U.people[s.code] = s.name; });
    });
  }
  function remindRow(it) {
    var when = it.kind === 'report' ? REPORTS.label(it.period_kind, it.period_start) : it.date ? (it.kind === 'worksheet' ? 'buổi ' : '') + dm(it.date) : '';
    var rest = [when, it.words].filter(Boolean).join(' · ');
    return '<div class="remind-item"><span><b>' + U.esc(it.kind === 'bank_import' ? it.file : nameOf(it.student_id)) + '</b> · ' + U.esc(rest) + '</span>' +
      btn('c-open', 'Mở', 'data-tid="' + U.esc(it.thread_id) + '" data-kind="' + U.esc(it.kind) + '"') + '</div>';
  }
  function remindHTML() {
    if (!pending) return '';
    var items = pending.items;
    if (!items.length) return '<p class="small muted">Không có việc nào đang chờ thầy/cô.</p>';
    var h = '<div class="spread"><h2 class="eyebrow">Việc đang chờ thầy/cô (' + items.length + ')</h2><button type="button" class="btn btn-ghost btn-sm" data-act="c-remind" aria-expanded="' + remindOpen + '" aria-controls="remind-cards">' + (remindOpen ? 'Ẩn' : 'Xem') + '</button></div>';
    if (!remindOpen) return h;
    return h + '<div class="remind-cards" id="remind-cards">' + GROUPS.map(function (g) {
      var rows = items.filter(function (i) { return i.kind === g[0]; });
      return rows.length ? '<div class="remind-card"><h3>' + g[1] + ' <span class="n">' + rows.length + '</span></h3>' + rows.map(remindRow).join('') + '</div>' : '';
    }).join('') + '</div>';
  }
  function drawRemind() { var r = $('#remind'); if (r) r.innerHTML = remindHTML(); }
  C.refreshPending = function () {
    return Promise.all([loadPeople().catch(noop), U.api.get('/assistant/pending')]).then(function (r) {
      pending = r[1];
      var n = pending.counts.assistant, b = document.getElementById('badge-tro-ly'), nr = pending.counts.reports, br = document.getElementById('badge-bao-cao');
      b.textContent = n; b.hidden = !n;
      br.textContent = nr; br.hidden = !nr;
      drawRemind(); drawConvs();  // names are known now
      var w = $('.welcome .suggest');
      if (w) w.outerHTML = suggestHTML();
    }, noop);
  };
  ACT['c-remind'] = function () { remindOpen = !remindOpen; drawRemind(); };
  ACT['c-open'] = function (el) {
    var k = el.dataset.kind;
    if (k === 'grading' || k === 'worksheet') C.openThread(el.dataset.tid, k);
    else if (k === 'report') REPORTS.open(el.dataset.tid);
    else if (k === 'bank_import') U.tab('ngan-hang');
  };
  ACT['c-tab'] = function (el) { U.tab(el.dataset.tab); };

  // ---- polling a thread card (grading.js, worksheet.js) ----
  C.poll = function (tid, onRow, holder, onGone) {  // onGone: what to do when the thread is not there any more (404); default is the "Việc này đã xong" card
    (function tick() {
      if (!holder.isConnected) return;
      U.api.get('/threads/' + encodeURIComponent(tid) + '?view=teacher').then(function (row) {
        if (!holder.isConnected) return;
        var more = true;
        try { more = onRow(row) !== false; } catch (e) { console.error(e); }  // a card bug shows, the card keeps polling
        if (more) setTimeout(tick, 1000);
      }, function (e) {
        if (!holder.isConnected) return;
        if (e.status !== 404) setTimeout(tick, 1000);
        else if (onGone) onGone();
        else holder.innerHTML = '<div class="empty"><p>Việc này đã xong.</p>' + btn('c-tab', 'Sang tab Học sinh', 'data-tab="hoc-sinh"') + '</div>';
      });
    })();
  };
  C.openThread = function (tid, kind) {
    var hit = [].find.call(panel.querySelectorAll('[data-thread]'), function (h) { return h.dataset.thread === tid; });
    if (hit) { hit.scrollIntoView({ block: 'center' }); return; }
    addCard(botMsg(), { kind: kind, thread_id: tid });
    scrollEnd(true);
  };

  // ---- messages ----
  function userHTML(t) {
    var html = U.esc(t.text || '').replace(/(@?)\b(HS-\d{2,})\b/gi, function (x, at, c) {  // a name is escaped on its own: U.names runs after U.esc
      var name = U.nesc(c);
      return at ? '<span class="mention">' + name + '</span>' : name;
    });
    return (t.attachment ? '<span class="file-chip"><span>📄 ' + U.esc(t.attachment.path) + '</span></span>' : '') + (html ? '<p>' + html + '</p>' : '');
  }
  function addUser(t) {
    var el = document.createElement('div');
    el.className = 'msg msg-me'; el.innerHTML = '<div class="bubble">' + userHTML(t) + '</div>';
    $('#chat-msgs').appendChild(el);
    return el;
  }
  function botMsg() {
    var el = document.createElement('div');
    el.className = 'msg msg-bot';
    el.innerHTML = '<span class="avatar" aria-hidden="true">GS</span><div class="bubble"><div class="b-tools"></div><div class="b-text"></div><div class="b-cards"></div><div class="b-end"></div></div>';
    $('#chat-msgs').appendChild(el);
    return { el: el, bubble: el.querySelector('.bubble'), text: '', warnings: [], busy: {}, source: null, stopped: null, done: false, error: null, retry: null };
  }
  function drawText(m) {
    var live = !m.done && !m.error, t = m.text, lost = [];
    if (!m.done || m.error) t = t.replace(/\bH(?:S(?:-\d?)?)?$/i, '');  // a code still arriving, or cut by a lost stream, never shows half
    m.warnings.forEach(function (w, i) {
      var at = t.indexOf(w.sentence), skip = (w.sentence.match(/^\s*(?:[-*]|\d+[.)])\s+/) || [''])[0].length;  // keep a list marker outside the mark
      if (at < 0) lost.push(w);
      else t = t.slice(0, at + skip) + '' + w.sentence.slice(skip) + '' + i + '' + t.slice(at + w.sentence.length);
    });
    var note = function (w) { return '<span class="uncheck-note">Số chưa kiểm: ' + U.esc(w.numbers.join(', ')) + '. Thầy/cô đừng dựa vào câu này.</span>'; };
    var html = U.md(U.names(t)).replace(//g, '<span class="uncheck">').replace(/(\d+)/g, function (x, i) { return '</span>' + note(m.warnings[i]); });
    var el = m.bubble.querySelector('.b-text');
    el.innerHTML = (live && !m.text ? '<span class="typing">Trợ lý đang trả lời</span>' : html) + lost.map(function (w) { return '<p>' + note(w) + '</p>'; }).join('');
    if (!live) U.typeset(el);
  }
  function drawTools(m) {
    m.bubble.querySelector('.b-tools').innerHTML = Object.keys(m.busy).map(function (k) { return '<p class="tool-line">Đang ' + U.esc(m.busy[k]) + '…</p>'; }).join('');
  }
  function drawEnd(m) {
    var h = '';
    if (m.source) {
      h += m.source.items ? '<p class="src"><b>Nguồn:</b> ' + m.source.items.map(function (x) { return U.esc(U.names(x)); }).join(' · ') + '</p>'
        : '<p class="src">Câu trả lời này không lấy từ dữ liệu học sinh.</p>';
    }
    if (m.stopped === 'max_tool_turns') h += '<p class="small">Mình dừng sau 8 lượt tra cứu, thầy/cô hỏi hẹp hơn giúp mình nhé.</p>';
    if (m.error) {
      h += '<p class="err">' + U.esc(ERR[m.error.code] || UNAVAILABLE) + '</p>' + (m.retry ? btn('c-retry', 'Gửi lại', 'data-turn="' + m.retry.id + '"') : '');
    }
    m.bubble.querySelector('.b-end').innerHTML = h;
  }
  function addCard(m, card) {
    var host = document.createElement('div');
    host.className = 'card-host';
    if (card.thread_id) host.dataset.thread = card.thread_id;
    m.bubble.querySelector('.b-cards').appendChild(host);
    (C.cards[card.kind] || function (h) { h.innerHTML = '<p class="small muted">Thẻ này chưa mở được ở bản này.</p>'; })(host, card, m);
    U.typeset(host);
  }
  function apply(m, ev) {
    if (ev.type === 'text') { m.text += ev.delta; drawText(m); }
    else if (ev.type === 'tool') { if (ev.state === 'start') m.busy[ev.name] = ev.label; else delete m.busy[ev.name]; drawTools(m); }
    else if (ev.type === 'card') addCard(m, ev.card);
    else if (ev.type === 'warning') { m.warnings.push(ev); drawText(m); }
    else if (ev.type === 'source') { m.source = ev; drawEnd(m); }
    else if (ev.type === 'done') { m.done = true; m.stopped = ev.stopped; m.busy = {}; drawText(m); drawTools(m); drawEnd(m); }
    else if (ev.type === 'error') { m.error = ev; m.bubble.classList.add('bubble-err'); drawText(m); drawEnd(m); }
  }
  function replay(row) {
    var m = botMsg();
    m.text = row.text || ''; m.done = true;
    (row.events || []).forEach(function (ev) { apply(m, ev); });
    m.busy = {}; drawTools(m); drawText(m); drawEnd(m);
  }

  // ---- sending ----
  function setBusy(on) {
    busy = on;
    $('.asst').classList.toggle('is-busy', on);
    canSend();
  }
  function lose(turn, m, why) {
    m.error = { code: why || '' }; m.bubble.classList.add('bubble-err');
    drawText(m); drawEnd(m);
    var ta = $('#chat-input');
    if (turn.conv === cur && ta && !ta.value && !attached) {  // the typed text comes back unless the teacher already typed something else
      ta.value = turn.shown; mentionMap = turn.map; attached = turn.chip; renderAttach(); autosize(ta);
    }
  }
  function go(turn) {
    if (busy) { U.toast('Trợ lý đang trả lời, chờ một lát.', 'info'); return false; }
    setBusy(true);
    var ta = $('#chat-input'), w = $('.welcome');
    if (w) w.remove();
    if (ta.value.trim() === turn.shown.trim()) { ta.value = ''; mentionMap = {}; autosize(ta); }
    if (attached && attached === turn.chip) { attached = null; renderAttach(); }
    if (turn.m) turn.m.el.remove();  // Gửi lại: the red bubble goes, the tutor's own bubble stays
    else addUser(turn);
    turn.id = turn.id || ++turnSeq; retries[turn.id] = turn;
    turn.conv = cur;
    var m = turn.m = botMsg();
    m.retry = turn; drawText(m); scrollEnd(true);
    var body = { conversation_id: cur.id, text: turn.text, mentions: turn.mentions, attachment: turn.attachment, held_on: turn.held_on,
      context: { worksheet_thread_id: C.worksheetThread ? C.worksheetThread() : null } };
    U.ndjson('/assistant/messages', body, function (ev) {
      try {
        var s = $('.chat-scroll'), stick = s && s.scrollHeight - s.scrollTop - s.clientHeight < 120;
        if (ev.type === 'start') turn.conv.id = ev.conversation_id;
        else if (ev.type === 'error') lose(turn, m, ev.code);
        else apply(m, ev);
        if (stick) scrollEnd(true);
      } catch (e) { console.error(e); }
    }).then(function () {
      if (!m.done && !m.error) lose(turn, m, '');  // the stream closed before `done`
    }, function (e) { lose(turn, m, e.code); }).then(function () {
      setBusy(false);
      C.refreshPending(); loadConvs();
    });
    return true;
  }
  C.send = function (text, opts) {
    opts = opts || {};
    var map = {};
    (opts.mentions || []).forEach(function (id) { map['@' + nameOf(id)] = id; });
    return go({ text: text, mentions: opts.mentions || [], attachment: opts.attachment || null, held_on: opts.held_on || null, shown: U.names(text), map: map, chip: null });
  };
  function sendBox() {
    var ta = $('#chat-input'), text = ta.value.trim(), wire = text, ids = [];
    if (busy || !(text || attached)) return;
    Object.keys(mentionMap).sort(function (a, b) { return b.length - a.length; }).forEach(function (tag) {
      var re = new RegExp(tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}\\p{N}])', 'gu'), next = wire.replace(re, '@' + code(mentionMap[tag]));
      if (next !== wire) { wire = next; ids.push(mentionMap[tag]); }
    });
    go({ text: wire, mentions: ids, attachment: attached ? { path: attached.path } : null, held_on: attached && attached.guess ? attached.guess.held_on : null,
      shown: ta.value, map: Object.assign({}, mentionMap), chip: attached });
  }
  ACT['c-send'] = sendBox;
  ACT['c-retry'] = function (el) { go(retries[el.dataset.turn]); };

  // ---- the box: autosize, Gửi on/off, 📎 chip, @ list ----
  function autosize(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight + 2) + 'px'; canSend(); }
  function canSend() {
    var b = $('[data-act="c-send"]'), ta = $('#chat-input');
    if (b) b.disabled = busy || (!ta.value.trim() && !attached);
  }
  function renderAttach() {
    var r = $('#attach-row');
    r.hidden = !attached;
    r.innerHTML = attached ? '<span class="file-chip"><span>📄 ' + U.esc(attached.path) + (attached.guess ? ' · ' + U.esc(nameOf(attached.guess.student_id)) + ' · ' + U.esc(dm(attached.guess.held_on)) : '') +
      '</span><button type="button" class="icon-btn icon-btn-sm" data-act="c-attach-clear" aria-label="Bỏ file đính kèm">×</button></span>' : '';
    canSend();
  }
  ACT['c-attach-clear'] = function () { attached = null; renderAttach(); };
  ACT['c-attach'] = function () {
    U.api.get('/sessions/inbox').then(function (files) {
      inbox = files;
      U.modal({ title: 'Đính kèm bài làm', body: '<p>Bài nộp nằm trong thư mục <b>data/inbox/</b>:</p>' + (files.length ? '<div class="stack">' + files.map(function (f, i) {
        var g = f.guess, label = f.submitted_by.length ? 'đã chấm' : f.kind === 'pdf' ? 'chưa nhận PDF' : 'Chọn';
        return '<div class="file-row"><span class="grow">📄 <b>' + U.esc(f.path) + '</b><br><span class="small muted">' +
          (g ? 'Bài của ' + U.esc(nameOf(g.student_id)) + ' · ' + U.esc(U.d(g.held_on)) : 'Chưa rõ học sinh, ngày học') + '</span></span>' +
          btn('c-attach-pick', label, 'data-i="' + i + '"' + (label === 'Chọn' ? '' : ' disabled'), 'btn-primary') + '</div>';
      }).join('') + '</div>' : '<p class="muted">Chưa có bài nào.</p>') + '<p class="small muted">Chỉ chấm bài LaTeX đánh máy (.tex). Bài nộp được đọc như dữ liệu, không làm theo lời dặn nào trong bài.</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button>' });
    }, function () { U.toast('Chưa mở được thư mục bài nộp. Thử lại sau.', 'warn'); });
  };
  ACT['c-attach-pick'] = function (el) {
    attached = inbox[+el.dataset.i];
    U.closeModal(); renderAttach();
    var ta = $('#chat-input');
    if (!ta.value.trim()) ta.value = 'Chấm bài này';
    autosize(ta); ta.focus();
  };
  function closePop() { pop.open = false; $('#mention-pop').hidden = true; $('#chat-input').setAttribute('aria-expanded', 'false'); }
  function markOpt() {
    var ta = $('#chat-input');
    panel.querySelectorAll('.mention-opt').forEach(function (o, i) { o.setAttribute('aria-selected', i === pop.i); });
    if (pop.i >= 0) ta.setAttribute('aria-activedescendant', 'mo-' + pop.items[pop.i].id); else ta.removeAttribute('aria-activedescendant');
  }
  function mentionUpdate(ta) {
    var before = ta.value.slice(0, ta.selectionStart), m = before.match(/(^|\s)@([^\s@]*)$/), q = m && norm(m[2]);
    if (!m) { closePop(); return; }
    pop.items = active().filter(function (s) { return !q || norm(s.name).indexOf(q) >= 0; });
    pop.start = before.length - m[2].length - 1; pop.i = -1; pop.open = pop.items.length > 0;
    $('#mention-pop').hidden = !pop.open;
    $('#mention-pop').innerHTML = pop.items.map(function (s) {
      return '<button type="button" class="mention-opt" role="option" id="mo-' + s.id + '" data-act="c-mention" data-sid="' + s.id + '" aria-selected="false"><b>' + U.esc(s.name) + '</b><span class="small muted">lớp ' + (s.grade || '?') + '</span></button>';
    }).join('');
    ta.setAttribute('aria-expanded', pop.open); markOpt();
  }
  function mentionPick(sid) {
    var ta = $('#chat-input'), tag = '@' + nameOf(sid), end = ta.selectionStart;
    ta.value = ta.value.slice(0, pop.start) + tag + ' ' + ta.value.slice(end);
    mentionMap[tag] = sid;
    var caret = pop.start + tag.length + 1; ta.setSelectionRange(caret, caret);
    closePop(); autosize(ta); ta.focus();
  }
  ACT['c-mention'] = function (el) { mentionPick(+el.dataset.sid); };

  // ---- conversations ----
  function loadConvs() {
    return U.api.get('/assistant/conversations').then(function (rows) { convs = rows; drawConvs(); }, noop);
  }
  function drawConvs() {
    var el = $('#conv-list');
    if (!el) return;
    el.innerHTML = convs.map(function (c) {
      var t = U.names(c.title || 'Cuộc trò chuyện');
      return '<button type="button" class="conv-item" data-act="c-conv" data-id="' + U.esc(c.id) + '" aria-current="' + (c.id === cur.id) + '"><span class="t">' + U.esc(t.length > 40 ? t.slice(0, 39) + '…' : t) +
        '</span><span class="d">' + (c.date === U.today ? 'Hôm nay' : U.esc(U.d(c.date))) + '</span></button>';
    }).join('');
  }
  function closeDrawer() { if ($('.convs.open')) ACT['c-conv-toggle'](); }
  ACT['c-conv-toggle'] = function () {
    var cv = $('.convs'), open = !cv.classList.contains('open');
    cv.classList.toggle('open', open); $('#sheet-back').classList.toggle('open', open);
    $('#conv-toggle').setAttribute('aria-expanded', open);
    if (open) cv.querySelector('button').focus(); else $('#conv-toggle').focus();
  };
  ACT['c-back'] = closeDrawer;
  ACT['c-conv'] = function (el) {
    var id = el.dataset.id;
    U.api.get('/assistant/conversations/' + encodeURIComponent(id)).then(function (r) {
      cur = { id: id };
      $('#chat-msgs').innerHTML = '';
      r.messages.forEach(function (row) { if (row.role === 'user') addUser(row); else replay(row); });
      drawConvs(); closeDrawer(); scrollEnd(true); $('#chat-input').focus();
    }, function () { U.toast('Chưa mở được hội thoại này. Thử lại sau.', 'warn'); });
  };
  ACT['c-new'] = function () {
    cur = { id: null };
    $('#chat-msgs').innerHTML = '';
    welcome(); drawConvs(); closeDrawer(); $('#chat-input').focus();
  };

  // ---- welcome + suggestions ----
  function suggestHTML() {
    var s = active(), a = s[0], b = s[1] || s[0];
    var Q = [
      a && ['Chấm bài của ' + a.name, 'Chấm bài này cho @' + a.name, a.id, 1],
      a && ['Gợi ý 6 bài cho ' + a.name + ' buổi thứ Bảy', 'Gợi ý 6 bài cho @' + a.name + ' buổi thứ Bảy', a.id],
      a && ['Tháng này ' + a.name + ' yếu gì?', 'Tháng này @' + a.name + ' yếu gì?', a.id],
      ['Ai còn nhầm dấu khi chuyển vế?', 'Ai còn nhầm dấu khi chuyển vế?'],
      b && ['Làm báo cáo tuần cho ' + b.name, 'Làm báo cáo tuần cho @' + b.name, b.id],
      ['Tìm 3 bài Viète mức vừa', 'Tìm 3 bài Viète mức vừa']
    ].filter(Boolean);
    return '<div class="suggest">' + Q.map(function (q) {
      return '<button type="button" class="btn btn-sm" data-act="c-suggest" data-q="' + U.esc(q[1]) + '"' + (q[2] ? ' data-sid="' + q[2] + '"' : '') + (q[3] ? ' data-attach="1"' : '') + '>' + U.esc(q[0]) + '</button>';
    }).join('') + '</div>';
  }
  ACT['c-suggest'] = function (el) {
    var ta = $('#chat-input');
    if (el.dataset.sid) mentionMap['@' + nameOf(+el.dataset.sid)] = +el.dataset.sid;
    ta.value = el.dataset.q; autosize(ta); ta.focus();
    if (el.dataset.attach) ACT['c-attach'](); else sendBox();
  };
  function welcome() {
    var el = document.createElement('div');
    el.className = 'msg msg-bot welcome';
    el.innerHTML = '<span class="avatar" aria-hidden="true">GS</span><div class="bubble"><p>Chào thầy/cô! Mình giúp chấm bài, soạn phiếu, trả lời về học sinh và tìm bài. Gõ <b>@</b> để chọn học sinh, ' +
      'gõ mã bài (ví dụ <span class="ref">9DS-PT2-003</span>) để xem bài hoặc thêm vào phiếu, bấm 📎 để đính kèm bài làm.</p>' + suggestHTML() + '</div>';
    $('#chat-msgs').appendChild(el);
  }

  // ---- cards ----
  function pcard(p) {
    return '<div class="pcard"><div class="pcard-head"><span class="ref">' + U.esc(p.ref) + '</span>' +
      (p.level ? '<span class="chip">' + U.esc(p.level) + '</span>' : '<span class="chip chip-warn">chưa có mức</span>') + (p.grade ? '<span class="chip">lớp ' + p.grade + '</span>' : '') +
      p.kcs.map(function (k) { return '<span class="chip chip-wrap">' + U.esc(k.name) + '</span>'; }).join('') + '</div>' + U.texHtml(p.statement_latex) +
      '<div class="row">' + btn('c-sol', 'Xem lời giải', 'aria-expanded="false"') + btn('c-bank', 'Mở trong Ngân hàng', 'data-pid="' + p.id + '"', 'btn-ghost') + '</div>' +
      '<div class="sol" hidden>' + p.solution_steps.map(function (s) { return U.texHtml(s); }).join('') + '</div></div>';
  }
  C.cards.problem = function (host, card) {
    host.innerHTML = (card.problems.length ? '<div class="pcards">' + card.problems.map(pcard).join('') + '</div>' : '') +
      (card.missing.length ? '<p>Không tìm thấy bài <b>' + card.missing.map(function (r) { return U.esc(r); }).join(', ') + '</b> trong ngân hàng.</p>'
        : !card.problems.length ? '<p>Không thấy bài nào khớp. Thầy/cô xem thêm ở tab <b>Ngân hàng bài</b>.</p>' : '');
  };
  ACT['c-sol'] = function (el) {
    var sol = el.closest('.pcard').querySelector('.sol'), open = sol.hidden;
    sol.hidden = !open; el.setAttribute('aria-expanded', open); el.textContent = open ? 'Ẩn lời giải' : 'Xem lời giải'; U.typeset(sol);
  };
  ACT['c-bank'] = function (el) { BANK.open(+el.dataset.pid); };
  C.cards.ask_grading = function (host, card) {
    var g = card.guess;
    host.innerHTML = '<div class="ask-grade"><p>' + (g ? 'Mình đoán từ tên file. Thầy/cô xem lại em và ngày học rồi bấm Chấm bài này.' : 'File này chưa ghi tên em và ngày học. Thầy/cô chọn rồi bấm Chấm bài này.') + '</p><div class="row">' +
      '<select aria-label="Học sinh">' + (g ? '' : '<option value="">Chọn học sinh</option>') + active().map(function (s) {
        return '<option value="' + s.id + '"' + (g && g.student_id === s.id ? ' selected' : '') + '>' + U.esc(s.name) + '</option>';
      }).join('') + '</select><input type="date" aria-label="Ngày học" value="' + (g ? U.esc(g.held_on) : U.today) + '">' +
      btn('c-grade', 'Chấm bài này', 'data-path="' + U.esc(card.attachment) + '"' + (g ? '' : ' disabled'), 'btn-primary') + '</div></div>';
  };
  ACT['c-grade'] = function (el) {
    var box = el.closest('.ask-grade'), sid = +box.querySelector('select').value;
    el.disabled = C.send('Chấm bài này cho @' + code(sid), { mentions: [sid], attachment: { path: el.dataset.path }, held_on: box.querySelector('input').value });
  };
  C.cards.pick_student = function (host, card) {
    host.innerHTML = '<div class="row">' + active().map(function (s) { return btn('c-pick', U.esc(s.name), 'data-sid="' + s.id + '" data-text="' + U.esc(card.text) + '"'); }).join('') + '</div>';
  };
  ACT['c-pick'] = function (el) {
    var sid = +el.dataset.sid;
    if (!C.send(el.dataset.text + ' @' + code(sid), { mentions: [sid] })) return;
    el.closest('.row').querySelectorAll('button').forEach(function (b) { b.disabled = true; });
  };
  C.cards.actions = function (host, card) {
    host.innerHTML = '<div class="row">' + card.items.map(function (it) { return btn('c-action', U.esc(U.names(it.label)), 'data-item="' + U.esc(JSON.stringify(it)) + '"'); }).join('') + '</div>';
  };
  ACT['c-action'] = function (el) {
    var it = JSON.parse(el.dataset.item);
    if (it.ask) C.send(it.ask, { mentions: it.mentions || [] });
    else if (it.open && it.open.tab) U.tab(it.open.tab);
  };

  // G5 report card (api-v3 §5.3): the draft is read, fixed and approved in the Báo cáo tab; this card follows it
  function reportHTML(c, st, tid) {
    var when = U.esc(REPORTS.label(c.period_kind, c.period_start));
    var body = st === 'writing' ? '<p class="tool-line">Đang viết bản nháp báo cáo…</p>'
      : st === 'saving' ? '<p class="tool-line">Đang lưu…</p>'
      : st === 'saved' ? '<div class="callout callout-ok"><p><b>Đã duyệt</b> báo cáo ' + when + '.</p></div>'
      : st === 'failed' ? '<div class="callout callout-crit"><p><b>Chưa làm xong bản nháp.</b> Mở tab Báo cáo để thử lại.</p></div>'
      : '<div class="callout callout-warn"><p><b>Bản nháp báo cáo ' + when + ' sẵn sàng</b>' + (c.n_flagged ? ' · ' + U.esc(c.n_flagged) + ' câu cần xem lại' : '') + '</p></div>';
    return '<div class="rcard stack"><p class="small muted">' + U.esc(U.who(c.student_id)) + '</p>' + body +
      '<div class="row">' + btn('c-open', 'Mở trong Báo cáo', 'data-kind="report" data-tid="' + U.esc(tid) + '"') + '</div></div>';
  }
  C.cards.report = function (host, card) {
    var tid = card.thread_id, was = '', json = '';
    host.innerHTML = '<p class="tool-line">Đang mở bản nháp báo cáo…</p>';
    C.poll(tid, function (row) {
      var c = row.card, st = c.stage === 'saving' && was !== 'draft' && was !== 'saving' ? 'writing' : c.stage;  // 09's draft is in the state a moment before the gate
      var j = JSON.stringify([st, c.n_flagged]);
      if (j !== json) {
        json = j; host.innerHTML = reportHTML(c, st, tid);
        if (st !== was && /^(draft|failed|saved)$/.test(st)) C.refreshPending();  // the reminder row comes or goes
        was = st;
      }
      return !/^(saved|failed)$/.test(st);
    }, host, function () {  // dropped in the Báo cáo tab, or cleaned up elsewhere
      host.innerHTML = '<div class="empty"><p>Bản nháp này không còn nữa.</p>' + btn('c-tab', 'Sang tab Báo cáo', 'data-tab="bao-cao"') + '</div>';
    });
  };

  // ---- no key (R15): without one the assistant only says "Chưa trả lời được"; say why, and where the key goes ----
  C.keyNotice = function () {
    return Promise.all([U.api.get('/health'), U.api.get('/settings')]).then(function (r) {
      var n = $('#nokey');
      if (n) n.hidden = r[0].fake_llm || !Object.keys(r[1].keys).some(function (p) { return r[1].keys[p] === false; });
    }, noop);
  };
  ACT['c-keys'] = function () { SYS.settings(); };

  // ---- tab ----
  TABS['tro-ly'] = {
    render: function (p) {
      panel = p;
      p.innerHTML = '<div class="asst">' +
        '<nav class="convs" aria-label="Các cuộc trò chuyện"><button type="button" class="btn btn-primary" data-act="c-new">+ Mới</button><div class="eyebrow">Đã trò chuyện</div><div class="conv-list" id="conv-list"></div></nav>' +
        '<div class="chat"><div class="nokey" id="nokey" role="status" hidden><span>Trợ lý chưa có khoá API.</span>' + btn('c-keys', 'Mở Cài đặt') + '</div>' +
        '<div class="chat-head"><button type="button" class="btn btn-sm" id="conv-toggle" data-act="c-conv-toggle" aria-expanded="false">☰ Hội thoại</button></div>' +
        '<div class="chat-scroll"><div class="chat-inner"><div class="remind" id="remind"></div><div class="chat-msgs" id="chat-msgs" aria-live="polite"></div></div></div>' +
        '<div class="composer"><div class="mention-pop" id="mention-pop" role="listbox" aria-label="Chọn học sinh" hidden></div><div class="composer-inner"><div class="row" id="attach-row" hidden></div>' +
        '<div class="composer-row"><button type="button" class="icon-btn" data-act="c-attach" aria-label="Đính kèm bài làm của học sinh" title="Đính kèm bài làm">📎</button>' +
        '<textarea id="chat-input" rows="1" placeholder="Hỏi trợ lý, gõ @ chọn học sinh…" aria-label="Tin nhắn cho trợ lý" aria-controls="mention-pop" aria-autocomplete="list" aria-expanded="false"></textarea>' +
        '<button type="button" class="btn btn-primary" data-act="c-send" disabled>Gửi</button></div>' +
        '<p class="hint">Enter để gửi · Shift+Enter xuống dòng · Gõ “ok” trong chat không lưu gì · Tên học sinh chỉ ở trên máy này</p></div></div></div>' +
        '<div class="sheet-back" id="sheet-back" data-act="c-back"></div></div>';
      if (matchMedia('(max-width: 719px)').matches) remindOpen = false;
      var ta = $('#chat-input');
      ta.addEventListener('input', function () { autosize(ta); mentionUpdate(ta); });
      ta.addEventListener('keydown', function (ev) {
        if (pop.open && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
          ev.preventDefault();
          pop.i = ev.key === 'ArrowDown' ? (pop.i + 1) % pop.items.length : pop.i <= 0 ? pop.items.length - 1 : pop.i - 1;
          markOpt();
        } else if (pop.open && (ev.key === 'Enter' || ev.key === 'Tab')) { ev.preventDefault(); mentionPick(pop.items[Math.max(pop.i, 0)].id); }
        else if (pop.open && ev.key === 'Escape') closePop();
        else if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); sendBox(); }
      });
      p.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeDrawer(); });
      p.addEventListener('change', function (ev) {
        var box = ev.target.closest('.ask-grade');
        if (box) box.querySelector('[data-act="c-grade"]').disabled = !box.querySelector('select').value || !box.querySelector('input').value;
      });
      welcome(); drawRemind(); drawConvs(); loadConvs(); C.keyNotice();
    },
    onShow: function () { C.refreshPending(); loadConvs(); }
  };
  C.refreshPending();  // the badge shows from the first screen, whichever tab opens
})();
