/* Thẻ chấm bài G1 in the Trợ lý tab (api-v3 §3.4): polls its thread through CHAT.poll, PUTs every choice (500 ms debounce)
   and resumes only from the last confirm answer, Lưu kết quả (two resumes, R7) and Chấm lại. Server text goes through U.names / U.esc. */
(function () {
  var C = window.CHAT, codes = null, codeReq = null;
  var CHANGED = 'Kết quả xem trước vừa thay đổi, xem lại rồi bấm Lưu kết quả';
  var NO_CODES = 'Chưa tải được danh sách loại lỗi. Thử lại sau.';
  var NO_TEXT = 'Viết vài chữ mô tả lỗi trước nhé.';
  var ERR = {
    not_ready: 'Bài đang được xử lý, chờ một lát rồi bấm lại.',
    undecided_items: 'Còn lỗi chưa chọn Đúng / Sửa / Bỏ.',
    date_order_locked: 'Cần duyệt buổi trước của em này trước.',
    already_committed: 'Bài này đã lưu rồi.'
  };
  var DECIDE = [['accept', 'Đúng', 'btn-ok'], ['edit', 'Sửa', 'btn-edit'], ['reject', 'Bỏ', 'btn-drop']];
  var CHIP = { saved: ['chip-ok', 'Đã lưu'], review: ['chip-warn', 'Chờ duyệt'], preview: ['chip-warn', 'Chờ lưu'], confirm: ['chip-warn', 'Chờ xác nhận'],
    locked: ['chip-warn', 'Chờ buổi trước'], failed: ['chip-crit', 'Chấm chưa xong'] };
  var TREND = { 'tiến bộ': 'chip-ok', 'cần ôn': 'chip-warn' };

  function noop() { /* the next poll or click tries again */ }
  function esc(s) { return U.esc(U.names(s == null ? '' : s)); }
  function num(x) { return String(x).replace('.', ','); }
  function dm(iso) { return iso.slice(8, 10) + '/' + iso.slice(5, 7); }
  function code(id) { return 'HS-' + String(id).padStart(2, '0'); }
  function who(id) { return U.people[code(id)] || 'học sinh'; }
  function btn(act, label, attrs, cls) { return '<button type="button" class="btn btn-sm ' + (cls || '') + '" data-act="' + act + '" ' + (attrs || '') + '>' + label + '</button>'; }
  function path(s, tail) { return '/threads/' + encodeURIComponent(s.tid) + tail; }
  function stateOf(el) { var h = el.closest('.card-host'); return h && h.gstate; }
  function props(s) { return [].concat.apply([], s.card.attempts.map(function (a) { return a.mistakes; })); }
  function isAdd(d) { return !!d && d.action === 'add'; }
  function addsOf(s, seq) { return Object.keys(s.dec).filter(function (k) { return isAdd(s.dec[k]) && s.dec[k].attempt_seq === seq; }); }
  function words(c, fallback) { var x = (codes || []).find(function (y) { return y.code === c; }); return x ? x.description : fallback || ''; }
  function kcName(a, id) { var k = a.kcs.find(function (x) { return x.id === id; }); return k ? k.name : 'không gắn kỹ năng'; }
  function wire(text) {  // C-40: a name shown or typed in a box goes back as its HS-xx code (chat.js sendBox does it for @)
    return Object.keys(U.people).filter(function (c) { return U.people[c].trim().split(/\s+/).length >= 2; })  // one-word names stay (S24)
      .sort(function (a, b) { return U.people[b].length - U.people[a].length; })
      .reduce(function (t, c) {
        return t.replace(new RegExp('(?<![\\p{L}\\p{N}])' + U.people[c].replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}\\p{N}])', 'gu'), c);
      }, String(text));
  }
  function flagOf(s, seq) { return s.card.confirm.find(function (f) { return f.seq === seq; }); }
  function loadCodes() {
    codeReq = codeReq || U.api.get('/catalog/error-codes').then(function (rows) {
      codes = rows.filter(function (c) { return c.active === 1; });
    }, function (e) { codeReq = null; throw e; });
    return codeReq;
  }

  // ---- card state: the server card + this screen's choices; redrawn whole, focus kept ----
  C.cards.grading = function (host, card) {
    var s = host.gstate = { host: host, tid: card.thread_id, card: null, json: '', dec: {}, seeded: false, answers: {}, pick: {}, typed: {}, rubric: null,
      editing: null, add: null, work: {}, left: null, dirty: false, putErr: false, putSeq: 0, timer: 0, chain: null, busy: false, secs: 0, mark: 0 };
    host.innerHTML = '<div class="gcard"><div class="gcard-body"><p class="tool-line">Đang mở bài chấm…</p></div></div>';
    loadCodes().then(function () { if (s.card) draw(s); }, noop);
    C.poll(s.tid, function (row) { return onRow(s, row); }, host);
  };
  function onRow(s, row) {
    var c = row.card, j = JSON.stringify(Object.assign({}, c, { saved: null })), back = bounced(s, row);  // `saved` only echoes this screen's PUTs
    tick(s);
    if (back) { s.chain = null; U.toast(CHANGED, 'info'); }
    if (j !== s.json || back) {
      if (!s.card || s.card.stage !== c.stage) s.busy = false;
      s.json = j; s.card = c;
      if (!s.seeded && /^(review|preview|saved)$/.test(c.stage)) seed(s, c.saved);
      if (s.chain) chainStep(s);
      draw(s);
    }
    if (c.stage !== 'saved') return true;
    C.refreshPending();
    return false;
  }
  function seed(s, sv) {  // P2: `saved` is the stored decisions; only its cards and review_seconds come back on screen
    s.seeded = true;
    if (sv && sv.cards && typeof sv.cards === 'object' && !Array.isArray(sv.cards)) s.dec = JSON.parse(JSON.stringify(sv.cards));
    if (sv && typeof sv.review_seconds === 'number') s.secs = sv.review_seconds;
  }
  function tick(s) {  // R6: seconds the review card is on screen, summed over every opening
    var now = Date.now();
    if (s.mark && s.card && s.card.stage === 'review' && s.host.offsetParent && !document.hidden) s.secs += (now - s.mark) / 1000;
    s.mark = now;
  }
  function key(el) {
    var form = el.closest('[data-key]');
    return [el.tagName, el.dataset.act, el.dataset.pid, el.dataset.seq, el.dataset.v, el.dataset.f, el.dataset.i, form && form.dataset.key].join('|');
  }
  function draw(s, focusSel) {
    var h = s.host, a = document.activeElement, k = h.contains(a) && key(a), pos = k && a.selectionStart;
    if (!h.querySelector('.gcard')) return;  // CHAT.poll put "Việc này đã xong" here
    h.innerHTML = cardHTML(s);
    U.typeset(h);
    var n = focusSel ? h.querySelector(focusSel) : k && [].find.call(h.querySelectorAll('button, input, select, textarea'), function (x) { return key(x) === k; });
    if (!n) return;
    n.focus({ preventScroll: !focusSel });
    if (!focusSel && typeof pos === 'number') try { n.setSelectionRange(pos, pos); } catch (e) { /* not a text box */ }
  }
  function drawFoot(s) { var f = s.host.querySelector('.gfoot'); if (f) f.outerHTML = footHTML(s); }

  // ---- HTML per stage ----
  function stepsHTML(st) {
    var S3 = [['Đang đọc bài…', 'Đã đọc bài'], ['Đang chấm…', 'Đã chấm'], ['Xong', 'Xong']];
    var at = { reading: 0, confirm: 0, grading: 1, failed: 1 }[st];
    if (at == null) at = 2;
    return '<ol class="steps" aria-label="Tiến độ">' + S3.map(function (x, i) {
      var done = i < at || st === 'saved', wait = i === at && /^(confirm|failed|locked)$/.test(st);
      var txt = done ? x[1] : i === at && st === 'confirm' ? 'Chờ thầy/cô xác nhận bài' : i === at && st === 'failed' ? 'Chấm chưa xong' : x[0];
      return '<li class="' + (done ? 'done' : wait ? 'wait' : i === at ? 'on' : '') + '"' + (i === at ? ' aria-current="step"' : '') + '>' + txt + '</li>';
    }).join('') + '</ol>';
  }
  function cardHTML(s) {
    var c = s.card, st = c.stage, body = stepsHTML(st), p = c.progress, chip = CHIP[st] || ['chip-info', 'Đang làm'], n = c.attempts.length;
    if (st === 'reading') body += '<p class="tool-line">Đang đọc bài…</p>';
    else if (st === 'grading') body += '<p class="tool-line">' + (p && p.total ? 'Đang chấm bài ' + Math.min(p.done + 1, p.total) + '/' + p.total : 'Đang chấm…') + '</p>';
    else if (st === 'saving') body += '<p class="tool-line">Đang lưu…</p>';
    else if (st === 'confirm') body += confirmHTML(s);
    else if (st === 'review' || st === 'preview') body += reviewHTML(s);
    else if (st === 'saved') body += savedHTML(c);
    else if (st === 'failed') {
      body += '<div class="callout callout-crit"><p><b>Chấm chưa xong:</b> ' + esc(c.error_words) + '</p><div class="row">' + btn('g-retry', 'Chấm lại', s.busy ? 'disabled' : '', 'btn-primary') + '</div></div>';
    } else if (st === 'locked') {
      var d = dm(c.lock.blocked_by.held_on);
      body += '<div class="callout callout-warn"><p>Duyệt buổi ' + d + ' của ' + U.esc(who(c.student_id)) + ' trước (tiến bộ tính theo thứ tự ngày).</p><div class="row">' +
        btn('g-open', 'Mở buổi ' + d, 'data-tid="' + U.esc(c.lock.blocked_by.thread_id) + '"') + '</div></div>';
    }
    return '<div class="gcard' + (st === 'saved' ? ' is-saved' : '') + '"><div class="gcard-head"><div class="row"><b>Bài của ' + U.esc(who(c.student_id)) + '</b><span class="muted small">buổi ' +
      dm(c.held_on) + (n ? ' · ' + n + ' bài' : '') + (c.file ? ' · ' + esc(c.file) : '') + '</span></div><span class="chip ' + chip[0] + '">' + chip[1] + '</span></div>' +
      '<div class="gcard-body">' + body + '</div>' + footHTML(s) + '</div>';
  }
  function flag(s) {  // one flag at a time; once all are answered the last one stays, so a refused resume can be sent again
    var open = s.card.confirm.filter(function (f) { return !s.answers[f.seq]; });
    return open[0] || s.card.confirm[s.card.confirm.length - 1];
  }
  function confirmHTML(s) {
    var f = flag(s), off = s.busy ? ' disabled' : '';
    if (!f) return '';
    var sq = 'data-seq="' + f.seq + '"';
    if (f.type === 'low_match') {
      var best = f.candidates[0], pick = s.pick[f.seq] || (best && best.ref);
      return '<div class="callout callout-warn"><p><b>Bài ' + f.seq + ' không ghi mã bài.</b>' + (best ? ' Trợ lý thấy giống bài <span class="ref">' + U.esc(best.ref) + '</span> nhất, nhưng chưa chắc.' : '') +
        ' Thầy/cô chọn đúng bài:</p><div class="work"><div class="small muted">Đầu bài làm của em:</div>' + U.texHtml(U.names(f.first_step_latex)) + '</div>' +
        '<div class="stack match-list" role="radiogroup" aria-label="Chọn bài khớp">' + f.candidates.map(function (c) {
          return '<label class="match-opt"><input type="radio" name="match-' + U.esc(s.tid) + '-' + f.seq + '" data-f="pick" ' + sq + ' value="' + U.esc(c.ref) + '"' + (c.ref === pick ? ' checked' : '') + '>' +
            '<span class="stack"><span><span class="ref">' + U.esc(c.ref) + '</span>' + (c.best ? ' <span class="chip chip-info">giống nhất</span>' : '') + '</span>' + U.texHtml(c.statement_latex) + '</span></label>';
        }).join('') + '</div><label class="field"><span>Hoặc gõ mã bài khác</span><input type="text" data-f="typed" ' + sq + ' value="' + U.esc(s.typed[f.seq] || '') + '" placeholder="ví dụ 9DS-CAN-010" autocomplete="off"></label>' +
        '<div class="row">' + btn('g-match', 'Đúng bài này', sq + off, 'btn-primary') + btn('g-skip', 'Bỏ bài này, không chấm', sq + off) + '</div></div>';
    }
    var r = s.rubric && s.rubric.seq === f.seq ? s.rubric.items : null;
    return '<div class="callout callout-warn"><p><b>Bài ' + f.seq + (f.ref ? ' (<span class="ref">' + U.esc(f.ref) + '</span>)' : '') + ' chưa có cách chấm.</b> Trợ lý soạn nháp, thầy/cô xem lại rồi bấm Dùng cách chấm này:</p>' +
      (r ? '<div class="rub">' + r.map(function (it, i) {  // the bank's rubric list and form (bank.js rubricHTML, editHTML)
        return '<div class="rub-row"><span class="muted small">Ý ' + (i + 1) + '</span><textarea rows="2" data-f="rtext" data-i="' + i + '" aria-label="Nội dung ý ' + (i + 1) + '">' + esc(it.text) + '</textarea>' +
          '<input type="number" min="0.5" step="0.5" data-f="rpts" data-i="' + i + '" value="' + U.esc(it.points) + '" aria-label="Điểm ý ' + (i + 1) + '">' +
          '<button type="button" class="icon-btn icon-btn-sm" data-act="g-rub-del" data-i="' + i + '" aria-label="Bỏ ý ' + (i + 1) + '">×</button></div>';
      }).join('') + '</div>'
        : '<ul class="rub-list">' + f.rubric_draft.map(function (it, i) {
          return '<li><span class="rub-n muted small">Ý ' + (i + 1) + '</span><span class="tex">' + esc(it.text) + '</span><span class="chip">' + num(it.points) + ' điểm</span></li>';
        }).join('') + '</ul>') +
      '<div class="row">' + btn('g-rubric', 'Dùng cách chấm này', sq + off, 'btn-primary') + (r ? btn('g-rub-add', '+ Thêm ý', off) : btn('g-rub-edit', 'Sửa', sq + off)) + '</div></div>';
  }
  function reviewHTML(s) {
    var c = s.card, ro = c.stage !== 'review' || !!s.chain, added = Object.keys(s.dec).filter(function (k) { return isAdd(s.dec[k]); }).length;
    return '<div class="spread">' + (c.max_score ? '<p><b>Điểm: ' + U.score(c.score, c.max_score) + '</b> <span class="muted small">(' + num(c.score) + '/' + num(c.max_score) + ' ý)</span></p>' : '') +
      '<p class="small muted">' + props(s).length + ' lỗi trợ lý tìm thấy' + (added ? ', ' + added + ' lỗi thầy/cô thêm' : '') + '</p></div>' +
      c.attempts.map(function (a) { return attemptHTML(s, a, ro); }).join('') + (c.preview ? previewHTML(c.preview) : '');
  }
  function attemptHTML(s, a, ro) {
    var open = !!s.work[a.seq], adds = addsOf(s, a.seq), sq = 'data-seq="' + a.seq + '"';
    var h = '<div class="gprob"><div class="gprob-head"><div class="row"><b>Bài ' + a.seq + '</b>' + (a.ref ? '<span class="ref">' + U.esc(a.ref) + '</span>' : '') +
      (a.skipped ? '<span class="chip chip-dim">không chấm</span>' : a.max_score ? '<span class="chip">' + num(a.score) + '/' + num(a.max_score) + ' ý</span>' : '') +
      (a.rubric_draft ? '<span class="chip chip-warn">cách chấm nháp</span>' : '') + '</div>' +
      (a.skipped ? '' : btn('g-work', open ? 'Ẩn đề & bài làm' : 'Xem đề & bài làm', sq + ' aria-expanded="' + open + '"', 'btn-ghost')) + '</div><div class="gprob-body">';
    if (a.skipped) return h + '<p class="muted">Thầy/cô đã bỏ bài này, không chấm.</p></div></div>';
    if (open) h += workHTML(s, a, adds);
    if (!a.mistakes.length && !adds.length) h += '<p class="muted">Không thấy lỗi nào trong bài này.</p>';
    h += a.mistakes.map(function (m) { return mistakeHTML(s, a, m, ro); }).join('') + adds.map(function (k) { return addedHTML(s, a, k, ro); }).join('');
    if (!ro) h += s.add && s.add.seq === a.seq ? formHTML(a, s.add, 'add') : '<div class="row">' + btn('g-add', '+ Thêm lỗi', sq) + '</div>';
    return h + '</div></div>';
  }
  function workHTML(s, a, adds) {  // steps with a kept or added mistake are red
    var hit = a.mistakes.filter(function (m) { var d = s.dec[m.pid]; return !(d && d.action === 'reject'); }).map(function (m) { return m.step_idx; })
      .concat(adds.map(function (k) { return s.dec[k].step_idx; }));
    return '<div class="stack"><div class="small muted">Đề bài</div>' + (a.statement_latex ? U.texHtml(a.statement_latex) : '<p class="muted">Bài này chưa có trong ngân hàng.</p>') +
      '<div class="work"><div class="small muted">Bài làm của em</div>' + a.steps.map(function (st) {
        return '<div class="wstep' + (hit.indexOf(st.idx) >= 0 ? ' hit' : '') + '"><span class="small muted">Bước ' + st.idx + '</span>' + U.texHtml(U.names(st.latex)) + '</div>';
      }).join('') + '</div></div>';
  }
  function mistakeHTML(s, a, m, ro) {
    var d = s.dec[m.pid], act = d && d.action, e = act === 'edit' ? d : null;
    var h = '<div class="mistake' + (act ? ' d-' + U.esc(act) : '') + '" data-pid="' + U.esc(m.pid) + '"><div class="m-text"><div class="row"><span class="m-title">' + esc(e ? words(e.code, m.kind) : m.kind) + '</span>' +
      (m.unsure ? '<span class="chip chip-warn">Trợ lý chưa chắc</span>' : '') + (e ? '<span class="chip chip-info">Đã sửa</span>' : '') + '</div>' +
      '<div class="small muted">Bước ' + m.step_idx + ' · ' + U.esc(e ? kcName(a, e.kc_id) : m.kc ? m.kc.name : 'không gắn kỹ năng') + '</div>' +
      '<div class="tex">' + esc(e ? e.description : m.description) + '</div>' + (m.evidence_latex ? U.texHtml(U.names(m.evidence_latex)) : '') + '</div>' +
      (m.check ? '<p class="m-check">' + esc(m.check) + '</p>' : '');
    if (!ro) {
      h += '<div class="m-acts" role="group" aria-label="Quyết định cho lỗi ở bước ' + m.step_idx + '">' + DECIDE.map(function (b) {
        return btn('g-dec', b[1], 'data-pid="' + U.esc(m.pid) + '" data-v="' + b[0] + '" aria-pressed="' + (act === b[0]) + '"', b[2]);
      }).join('') + '</div>';
      if (e && s.editing === m.pid) h += formHTML(a, e, m.pid);
    }
    return h + '</div>';
  }
  function addedHTML(s, a, k, ro) {
    var d = s.dec[k];
    return '<div class="mistake is-added" data-pid="' + U.esc(k) + '"><div class="m-text"><div class="row"><span class="m-title">' + U.esc(words(d.code)) + '</span><span class="chip chip-info">Thầy/cô thêm</span></div>' +
      '<div class="small muted">Bước ' + U.esc(d.step_idx) + ' · ' + U.esc(kcName(a, d.kc_id)) + '</div><div class="tex">' + esc(d.description) + '</div></div>' +
      (ro ? '' : '<div class="m-acts">' + btn('g-add-del', 'Bỏ lỗi này', 'data-pid="' + U.esc(k) + '"') + '</div>') + '</div>';
  }
  function formHTML(a, d, k) {  // Sửa (k = pid) or + Thêm lỗi (k = "add"); skills are the problem's own, the only ones the server takes
    var add = k === 'add', opt = function (v, label, on) { return '<option value="' + U.esc(v) + '"' + (on ? ' selected' : '') + '>' + U.esc(label) + '</option>'; };
    return '<div class="edit-form' + (add ? ' add-form' : '') + '" data-key="' + U.esc(k) + '">' +
      '<label class="field"><span>Loại lỗi</span><select data-f="code">' + codes.map(function (c) { return opt(c.code, c.description, c.code === d.code); }).join('') + '</select></label>' +
      '<label class="field"><span>Kỹ năng</span><select data-f="kc_id">' + opt('', 'Không gắn kỹ năng', d.kc_id == null) + a.kcs.map(function (x) { return opt(x.id, x.name, x.id === d.kc_id); }).join('') + '</select></label>' +
      (add ? '<label class="field"><span>Ở bước</span><select data-f="step_idx">' + a.steps.map(function (st) { return opt(st.idx, 'Bước ' + st.idx, st.idx === d.step_idx); }).join('') + '</select></label>' : '') +
      '<label class="field full"><span>' + (add ? 'Mô tả lỗi' : 'Mô tả (thầy/cô viết lại nếu cần)') + '</span><textarea rows="2" data-f="description"' + (add ? ' placeholder="Ví dụ: quên đổi dấu khi chuyển vế"' : '') + '>' +
      esc(d.description) + '</textarea></label><div class="row full">' +
      (add ? btn('g-add-ok', 'Thêm lỗi', '', 'btn-primary') + btn('g-add-cancel', 'Thôi') : btn('g-edit-done', 'Xong', 'data-pid="' + U.esc(k) + '"', 'btn-primary')) + '</div></div>';
  }
  function previewHTML(p) {
    var mc = p.miscon || {}, said = [['Lỗi mới', mc.new], ['Lặp lại', mc.again], ['Đã hết', mc.resolved]].filter(function (w) { return w[1] && w[1].length; });
    return '<div class="stack"><h3>Xem trước tiến bộ</h3><div class="table-wrap"><table class="tbl preview-tbl"><thead><tr><th>Kỹ năng</th><th>Sau buổi này</th><th>Mức</th></tr></thead><tbody>' +
      p.kcs.map(function (k) {
        return '<tr><td>' + U.esc(k.kc) + (k.n_mistakes ? ' <span class="small muted">(' + k.n_mistakes + ' lỗi)</span>' : '') + '</td><td><span class="chip ' + (TREND[k.trend] || '') + '">' + U.esc(k.trend) + '</span></td>' +
          '<td>' + U.esc(k.before === k.after ? k.after : k.before + ' → ' + k.after) + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      (said.length ? '<ul class="small">' + said.map(function (w) { return '<li><b>' + w[0] + ':</b> ' + w[1].map(esc).join('; ') + '</li>'; }).join('') + '</ul>' : '') + '</div>';
  }
  function savedHTML(c) {
    var rc = c.receipt;
    return '<div class="callout callout-ok"><p><b>Đã lưu kết quả.</b> Đã sao lưu trước khi lưu.</p>' +
      (rc && rc.max_score ? '<p>Điểm ' + U.score(rc.score, rc.max_score) + ' (' + num(rc.score) + '/' + num(rc.max_score) + ' ý) · ' + rc.n_mistakes + ' lỗi.</p>' : '') + '</div>' +
      '<div class="row">' + btn('g-profile', 'Xem hồ sơ') + btn('g-next', 'Soạn phiếu buổi sau', '', 'btn-primary') + '</div>';
  }
  function footHTML(s) {
    var c = s.card, st = c && c.stage;
    if (st !== 'review' && st !== 'preview') return '';
    var ps = props(s), left = st === 'preview' ? 0 : s.left != null ? s.left : c.decided ? c.decided.total - c.decided.done : 0;  // P1
    var why = s.chain ? '' : left ? 'Còn ' + left + ' lỗi chưa chọn Đúng / Sửa / Bỏ.' : s.dirty ? 'Đang lưu lựa chọn…'
      : s.putErr ? 'Chưa lưu được lựa chọn, thầy/cô chọn lại giúp mình.' : c.preview ? '' : 'Đang tính xem trước…';
    var seen = ps.filter(function (m) { var d = s.dec[m.pid]; return d && /^(accept|edit|reject)$/.test(d.action); }).length, id = 'why-' + U.esc(s.tid);
    return '<div class="gfoot"><span class="progress-words">' + (st === 'preview' ? 'Xem lại tiến bộ rồi bấm Lưu kết quả' : ps.length ? 'Đã xem ' + seen + '/' + ps.length + ' lỗi' : 'Không có lỗi nào cần xem') + '</span>' +
      '<span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="g-save"' + (s.chain || why ? ' disabled' : '') + (why ? ' aria-describedby="' + id + '"' : '') + '>' +
      (s.chain ? 'Đang lưu…' : 'Lưu kết quả') + '</button>' + (why ? '<span class="reason" id="' + id + '">' + why + '</span>' : '') + '</span></div>';
  }

  // ---- writes: PUT (debounced at review), resume ----
  function put(s) {  // every review choice: one PUT 500 ms after the last change (bank.js impPut)
    var my = ++s.putSeq;
    s.dirty = true; clearTimeout(s.timer); drawFoot(s);
    s.timer = setTimeout(function () { send(s, my).catch(noop); }, 500);
  }
  function send(s, my) {
    my = my || ++s.putSeq;
    tick(s);
    return U.api.send('PUT', path(s, '/decisions'), { cards: s.dec, review_seconds: Math.round(s.secs) }).then(function (r) {
      if (my === s.putSeq) { s.dirty = false; s.putErr = false; s.left = r.pending; drawFoot(s); }
      return r;
    }, function (e) {
      if (my === s.putSeq) { s.dirty = false; s.putErr = true; drawFoot(s); }
      throw e;
    });
  }
  function resume(s) {
    return U.api.send('POST', path(s, '/resume')).then(function () { C.refreshPending(); }, function (e) {
      U.toast(ERR[e.code] || 'Chưa làm được, thử lại sau.', 'warn');
      throw e;
    });
  }
  function free(s) { s.busy = false; draw(s); }
  function answer(s, seq, d, bad) {  // confirm: PUT every answer so far; resume once the server has none left
    s.answers[seq] = d; s.busy = true; draw(s);
    U.api.send('PUT', path(s, '/decisions'), s.answers).then(function (r) {
      if (r.pending > s.card.confirm.filter(function (f) { return !s.answers[f.seq]; }).length) { delete s.answers[seq]; U.toast(bad, 'warn'); }
      return r.pending ? free(s) : resume(s).catch(function () { free(s); });  // after a resume, busy lasts until the stage moves
    }, function () { delete s.answers[seq]; U.toast('Chưa lưu được lựa chọn. Thử lại sau.', 'warn'); free(s); });
  }
  function chainStep(s) {  // R7: the second resume goes only if the preview on screen still holds
    var c = s.card, ch = s.chain;
    if (c.stage === 'preview' && c.preview_sig !== ch.sig) { s.chain = null; U.toast(CHANGED, 'info'); }
    else if (c.stage === 'preview' && ch.step === 1) commit(s);
    else if (/^(saved|failed|locked)$/.test(c.stage)) s.chain = null;
  }
  function commit(s) {  // resume 2 (commit ②); `after` starts once the server has taken it
    var ch = s.chain;
    ch.step = 2;
    resume(s).then(function () { ch.after = 0; }, function () { if (s.chain === ch) { s.chain = null; draw(s); } });
  }
  function bounced(s, row) {  // commit ② refused (StaleProfile, session.py:548): back at the gate, maybe with the same preview
    var ch = s.chain;
    if (!ch || ch.after == null) return false;
    if (row.status === 'running' || row.card.stage !== 'preview') { ch.moved = true; return false; }
    return ch.moved || ++ch.after >= 2;  // polls go one at a time, so the 2nd one after the 202 was asked after the resume ran
  }

  // ---- buttons + fields ----
  ACT['g-save'] = function (el) {
    var s = stateOf(el), c = s.card;
    if (s.chain) return;  // one chain per click, however fast the second click comes
    s.chain = { sig: c.preview_sig, step: 1 };
    s.editing = null; s.add = null; clearTimeout(s.timer);
    draw(s);
    if (c.stage === 'preview') commit(s);
    else send(s).then(function (r) { if (r.pending) throw r; return resume(s); }).catch(function () { s.chain = null; draw(s); });
  };
  ACT['g-retry'] = function (el) {
    var s = stateOf(el);
    s.busy = true; draw(s);
    resume(s).catch(function () { free(s); });
  };
  ACT['g-open'] = function (el) { C.openThread(el.dataset.tid, 'grading'); };
  ACT['g-profile'] = function () { U.tab('hoc-sinh'); };
  ACT['g-next'] = function (el) { var id = stateOf(el).card.student_id; C.send('Gợi ý 6 bài cho @' + code(id), { mentions: [id] }); };
  ACT['g-match'] = function (el) {
    var s = stateOf(el), seq = +el.dataset.seq, typed = (s.typed[seq] || '').trim().toUpperCase();
    var ref = typed || s.pick[seq] || (flagOf(s, seq).candidates[0] || {}).ref;
    if (!ref) { U.toast('Chọn một bài hoặc gõ mã bài trước nhé.', 'warn'); return; }
    answer(s, seq, { problem_ref: ref }, 'Không có bài ' + ref + ' trong ngân hàng.');
  };
  ACT['g-skip'] = function (el) { answer(stateOf(el), +el.dataset.seq, { skip: true }, ''); };
  function newItem(items) { var n = items.length + 1; while (items.some(function (i) { return i.item_id === 'i' + n; })) n++; return { item_id: 'i' + n, text: '', points: 1 }; }
  ACT['g-rub-edit'] = function (el) {
    var s = stateOf(el), seq = +el.dataset.seq;
    s.rubric = { seq: seq, items: flagOf(s, seq).rubric_draft.map(function (i) { return { item_id: i.item_id, text: i.text, points: i.points }; }) };
    if (!s.rubric.items.length) s.rubric.items.push(newItem([]));
    draw(s, '.rub-row textarea');
  };
  ACT['g-rub-add'] = function (el) { var s = stateOf(el); s.rubric.items.push(newItem(s.rubric.items)); draw(s, '.rub-row:last-child textarea'); };
  ACT['g-rub-del'] = function (el) { var s = stateOf(el); s.rubric.items.splice(+el.dataset.i, 1); draw(s); };
  ACT['g-rubric'] = function (el) {
    var s = stateOf(el), seq = +el.dataset.seq, items = s.rubric && s.rubric.seq === seq ? s.rubric.items : flagOf(s, seq).rubric_draft;
    if (!items.length || items.some(function (i) { return !String(i.text).trim() || !(i.points > 0); })) { U.toast('Mỗi ý cần có chữ và số điểm lớn hơn 0.', 'warn'); return; }
    answer(s, seq, { rubric_items: items.map(function (i) { return { item_id: i.item_id, text: String(i.text).trim(), points: i.points }; }) },
      'Cách chấm này chưa dùng được, thầy/cô sửa lại từng ý.');
  };
  ACT['g-work'] = function (el) { var s = stateOf(el), q = +el.dataset.seq; s.work[q] = !s.work[q]; draw(s); };
  ACT['g-dec'] = function (el) {
    var s = stateOf(el), pid = el.dataset.pid, v = el.dataset.v, d = s.dec[pid];
    if (v === 'edit' && !(codes && codes.length)) { loadCodes().catch(noop); U.toast(NO_CODES, 'warn'); return; }
    if (v === 'edit') {
      var m = props(s).find(function (x) { return x.pid === pid; }), a = s.card.attempts.find(function (x) { return x.mistakes.indexOf(m) >= 0; });
      var ok = function (c) { return codes.some(function (x) { return x.code === c; }); };  // Sửa starts from the proposal, the checked code first
      if (!d || d.action !== 'edit') {
        s.dec[pid] = { action: 'edit', code: ok(m.suggested_code) ? m.suggested_code : ok(m.code) ? m.code : codes[0].code,
          kc_id: m.kc && a.kcs.some(function (k) { return k.id === m.kc.id; }) ? m.kc.id : null, description: m.description };
      }
      s.editing = pid;
    } else {
      s.dec[pid] = { action: v };
      if (s.editing === pid) s.editing = null;
    }
    put(s);
    draw(s, v === 'edit' ? '[data-key="' + pid + '"] select' : null);
  };
  ACT['g-edit-done'] = function (el) {
    var s = stateOf(el), pid = el.dataset.pid;
    if (!String(s.dec[pid].description).trim()) { U.toast(NO_TEXT, 'warn'); return; }
    s.editing = null;
    draw(s, '[data-act="g-dec"][data-pid="' + pid + '"][data-v="edit"]');
  };
  ACT['g-add'] = function (el) {
    var s = stateOf(el), a = s.card.attempts.find(function (x) { return x.seq === +el.dataset.seq; });
    if (!(codes && codes.length)) { loadCodes().catch(noop); U.toast(NO_CODES, 'warn'); return; }
    s.add = { seq: a.seq, code: codes[0].code, kc_id: a.kcs.length ? a.kcs[0].id : null, step_idx: a.steps.length ? a.steps[0].idx : 1, description: '' };
    draw(s, '.add-form select');
  };
  ACT['g-add-cancel'] = function (el) { var s = stateOf(el), q = s.add.seq; s.add = null; draw(s, '[data-act="g-add"][data-seq="' + q + '"]'); };
  ACT['g-add-ok'] = function (el) {
    var s = stateOf(el), d = s.add, n = 1;
    if (!d.description.trim()) { U.toast(NO_TEXT, 'warn'); s.host.querySelector('.add-form textarea').focus(); return; }
    while (s.dec['a' + n]) n++;  // add keys never meet a proposal pid (p1, p2, …)
    s.dec['a' + n] = { action: 'add', attempt_seq: d.seq, step_idx: d.step_idx, code: d.code, kc_id: d.kc_id, description: d.description.trim(), evidence_latex: '' };
    s.add = null; put(s);
    draw(s, '[data-act="g-add"][data-seq="' + d.seq + '"]');
  };
  ACT['g-add-del'] = function (el) { var s = stateOf(el); delete s.dec[el.dataset.pid]; put(s); draw(s); };
  function onField(ev) {
    var t = ev.target, f = t.dataset && t.dataset.f, s = f && stateOf(t);
    if (!s) return;
    if (f === 'pick' || f === 'typed') { s[f][t.dataset.seq] = t.value; return; }
    if (f === 'rtext' || f === 'rpts') { s.rubric.items[+t.dataset.i][f === 'rtext' ? 'text' : 'points'] = f === 'rtext' ? wire(t.value) : +t.value; return; }
    var k = t.closest('[data-key]').dataset.key, d = k === 'add' ? s.add : s.dec[k];
    d[f] = f === 'kc_id' ? (t.value ? +t.value : null) : f === 'step_idx' ? +t.value : f === 'description' ? wire(t.value) : t.value;
    if (k === 'add') return;
    put(s);
    if (t.tagName === 'SELECT' && ev.type === 'change') draw(s);  // the mistake line shows the new kind / skill
  }
  document.addEventListener('input', onField);
  document.addEventListener('change', onField);
})();
