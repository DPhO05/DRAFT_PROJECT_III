/* Khung phiếu nháp G4 beside the chat (api-v3 §3.5, IA-app §1.5): one draft on screen (R9), polled through CHAT.poll.
   Every change PUTs the whole sheet (500 ms debounce) and redraws from the server card; only Tạo phiếu and Thử lại resume. */
(function () {
  var C = window.CHAT, W = null, esc = U.nesc, who = U.who, btn = U.btn;  // W: the draft on screen
  var NEED_ONE = 'Phiếu cần ít nhất 1 bài.', BAD = 'Bỏ mã không hợp lệ trước khi tạo phiếu.';
  var GROUPS = [['review', 'ôn lại'], ['zpd', 'vừa sức'], ['challenge', 'thử thách'], [null, 'thầy/cô thêm']];
  var REF = /\d[A-Z]{2}-[A-Z0-9]+-\d{3}/g;
  var CODES_ONLY = /^\s*\d[A-Z]{2}-[A-Z0-9]+-\d{3}(\s*,\s*\d[A-Z]{2}-[A-Z0-9]+-\d{3})*\s*$/i;  // orchestrator _REFS_ONLY: answered by add_refs
  var ERR = { not_ready: 'Phiếu đang được lưu, chờ một lát.', undecided_items: NEED_ONE, already_committed: 'Phiếu này đã tạo rồi.' };

  function noop() { /* the next poll or click tries again */ }
  function day(iso) { return U.wd(iso) + ' ' + U.d(iso); }
  function ref(r) { return '<span class="ref">' + U.esc(r) + '</span>'; }
  function icon(act, label, i, d, off, aria) {
    return '<button type="button" class="icon-btn icon-btn-sm" data-act="' + act + '" data-i="' + i + '"' + (d ? ' data-d="' + d + '"' : '') + ' aria-label="' + U.esc(aria) + '"' + (off ? ' disabled' : '') + '>' + label + '</button>';
  }
  function path(s, tail) { return '/threads/' + encodeURIComponent(s.tid) + tail; }
  function refsOf(s) { return s.card.items.map(function (i) { return i.ref; }).concat(s.card.invalid.map(function (x) { return x.ref; }), s.extra); }
  function dirty(s) { return !!s.timer || s.saving > 0; }
  function live(s) { return !!s && s.el.isConnected && !!s.el.querySelector('.ws'); }  // not replaced by another draft, and no 404 ("Việc này đã xong")

  // ---- the panel: an aside in the Trợ lý grid + "Phiếu nháp (n)" in the chat head (a sheet at ≤ 860 px) ----
  function aside() {
    var asst = document.querySelector('#panel-tro-ly .asst'), a = asst.querySelector('#draft');
    if (a) return a;
    a = document.createElement('aside');
    a.className = 'draft'; a.id = 'draft'; a.hidden = true; a.setAttribute('aria-label', 'Phiếu bài tập nháp');
    a.innerHTML = '<div class="draft-head"><div><div class="eyebrow"></div><h2 tabindex="-1"></h2></div><button type="button" class="icon-btn" data-act="ws-close" aria-label="Đóng khung phiếu">×</button></div><div class="draft-main"></div>';
    asst.appendChild(a);
    asst.querySelector('.chat-head').insertAdjacentHTML('beforeend', '<button type="button" class="btn btn-sm draft-toggle" id="draft-toggle" data-act="ws-show" hidden></button>');
    a.addEventListener('keydown', onKey);
    a.addEventListener('change', onDate);
    return a;
  }
  function show(on) {
    var a = aside(), toggle = document.getElementById('draft-toggle'), flip = a.hidden === on;
    a.hidden = !on;
    a.parentNode.classList.toggle('has-draft', on);
    toggle.hidden = !W;
    if (flip && matchMedia('(max-width: 860px)').matches) (on ? a.querySelector('h2') : toggle).focus();  // the sheet is a layer over the chat
  }
  function open(tid, how) {  // how: null = only show, true = a new proposal, [refs] = codes the chat just added
    var a = aside();
    if (!W || W.tid !== tid || !live(W) || how === true) {
      if (W && W.tid === tid) clearTimeout(W.timer);  // propose re-made this thread: the old sheet must not land on it
      var el = document.createElement('div');
      el.className = 'draft-main';
      el.innerHTML = '<div class="ws draft-body"><p class="tool-line">Đang mở phiếu nháp…</p></div>';
      a.replaceChild(el, a.querySelector('.draft-main'));  // the old draft's poll stops with it
      var s = W = { tid: tid, el: el, card: null, json: '', extra: [], pending: null, timer: 0, putSeq: 0, saving: 0, fresh: 0, busy: false, waits: 0 };
      a.querySelector('h2').textContent = ''; a.querySelector('.eyebrow').textContent = 'Phiếu nháp';
      C.poll(tid, function (row) { return onRow(s, row); }, el, function () { gone(s); });
    } else if (how && W.card) {  // add_refs saved them before the card came, but a panel PUT may still carry the old list
      var have = refsOf(W), more = how.filter(function (r) { return have.indexOf(r) < 0; });
      if (more.length) { W.extra = W.extra.concat(more); put(W); draw(W); }
    }
    show(true);
  }

  // ---- server card in: adopt it unless this screen has a change the server has not seen ----
  function gone(s) {  // 404: dropped on this panel (`dropped`), or finished or dropped somewhere else
    s.el.innerHTML = '<div class="empty"><p>' + (s.dropped ? 'Đã bỏ phiếu nháp.' : 'Việc này đã xong.') + '</p>' + btn('c-tab', 'Sang tab Học sinh', 'data-tab="hoc-sinh"') + '</div>';
  }
  function onRow(s, row) {
    if (s.dropped) return false;  // a poll already in the air when Bỏ phiếu nháp went through
    s.fresh++;
    if (s.busy && row.card.stage === 'failed' && ++s.waits >= 2) { s.busy = false; draw(s); }  // Thử lại failed again before a poll saw it run
    apply(s, row, false);
    return row.card.stage !== 'saved';
  }
  function refresh(s) {  // polls go one at a time: the 2nd after now was asked after now, so `fresh` counts from 0
    s.fresh = 0;
    U.api.get(path(s, '?view=teacher')).then(function (row) { apply(s, row, true); }, noop);
  }
  function apply(s, row, force) {
    var c = row.card, was = s.card, j = JSON.stringify(c), moved = !was || was.stage !== c.stage;
    if (!moved && (dirty(s) || !(force || s.fresh >= 2) || (j === s.json && !force))) return;
    if (moved) s.busy = false;
    s.card = c; s.json = j; s.extra = [];
    draw(s);
    if (moved && c.stage === 'saved') C.refreshPending();
  }

  // ---- HTML ----
  function draw(s, focus) {
    var el = s.el, a = document.activeElement, k = el.contains(a) && keyOf(a), box = el.querySelector('.ws-code'), v = box ? box.value : '';
    if (!live(s)) return;
    el.innerHTML = bodyHTML(s) + footHTML(s);
    if ((box = el.querySelector('.ws-code'))) box.value = v;  // a code being typed survives a poll
    head(s);
    U.typeset(el);
    var sel = focus || k, n = sel && el.querySelector(sel);
    if (n) n.focus();
  }
  function keyOf(a) {
    if (a.classList.contains('ws-code')) return '.ws-code';
    if (a.classList.contains('ws-date')) return '.ws-date';
    return a.dataset.act ? '[data-act="' + a.dataset.act + '"]' + (a.dataset.i ? '[data-i="' + a.dataset.i + '"]' : '') + (a.dataset.d ? '[data-d="' + a.dataset.d + '"]' : '') : null;
  }
  function head(s) {
    var c = s.card, done = c.stage === 'saved', a = aside(), t = document.getElementById('draft-toggle');
    a.querySelector('.eyebrow').textContent = done ? 'Phiếu đã tạo' : 'Phiếu nháp';
    a.querySelector('h2').textContent = who(c.student_id) + ' · ' + c.items.length + ' bài';
    t.textContent = (done ? 'Phiếu đã tạo' : 'Phiếu nháp') + ' (' + c.items.length + ')';
  }
  function itemHTML(it, i, n, ro) {
    return '<li class="draft-item' + (it.bucket ? '' : ' is-new') + '"><span class="pos">' + (i + 1) + '</span><div class="stack"><div class="row">' + ref(it.ref) +
      (it.level ? '<span class="chip">' + U.esc(it.level) + '</span>' : '<span class="chip chip-warn">chưa có mức</span>') + '</div>' +
      '<div class="small">' + esc(it.kcs.join(' · ')) + '</div><div class="why">' + esc(it.reason) + '</div><div class="clamp small">' + U.texHtml(it.statement_latex) + '</div></div>' +
      (ro ? '<span></span>' : '<div class="acts">' + icon('ws-move', '↑', i, -1, i === 0, 'Đưa bài ' + (i + 1) + ' lên') + icon('ws-move', '↓', i, 1, i === n - 1, 'Đưa bài ' + (i + 1) + ' xuống') +
        icon('ws-del', '×', i, 0, false, 'Bỏ bài ' + (i + 1)) + '</div>') + '</li>';
  }
  function bodyHTML(s) {
    var c = s.card, st = c.stage, ro = st !== 'draft', items = c.items, h = '';
    if (st === 'saving') h += '<p class="tool-line">Đang tạo phiếu…</p>';
    else if (st === 'saved') h += '<div class="callout callout-ok"><p><b>Đã tạo phiếu</b> cho ' + U.esc(who(c.student_id)) + ', buổi ' + day(c.for_date) + ' · ' + items.length + ' bài.</p></div>';
    else if (st === 'failed') h += '<div class="callout callout-crit"><p><b>Chưa tạo được phiếu.</b> Chưa có gì được lưu.</p><div class="row">' + btn('ws-retry', 'Thử lại', s.busy ? 'disabled' : '', 'btn-primary') +
      btn('ws-drop', 'Bỏ phiếu nháp', s.busy ? 'disabled' : '', 'btn-ghost') + '</div></div>';
    if (!ro) h += '<label class="field"><span>Buổi học</span><input type="date" class="ws-date" value="' + U.esc(c.for_date) + '"></label>';
    h += '<p class="small muted ws-counts">' + GROUPS.map(function (g) { return items.filter(function (i) { return (i.bucket || null) === g[0]; }).length + ' ' + g[1]; }).join(' · ') + '</p>';
    if (c.warnings.length) h += '<div class="callout callout-warn">' + c.warnings.map(function (w) { return '<p>' + esc(w) + '</p>'; }).join('') + '</div>';
    h += c.invalid.map(function (x, i) {
      return '<div class="row"><span class="grow small">' + ref(x.ref) + ': ' + U.esc(x.why) + '</span>' + (ro ? '' : icon('ws-bad-del', '×', i, 0, false, 'Bỏ mã ' + x.ref)) + '</div>';
    }).join('');
    h += items.length ? '<ol class="draft-list">' + items.map(function (it, i) { return itemHTML(it, i, items.length, ro); }).join('') + '</ol>'
      : '<div class="empty">Phiếu chưa có bài nào. Thêm bài theo mã ở dưới.</div>';
    h += s.extra.map(function (r) { return '<p class="tool-line">Đang thêm ' + U.esc(r) + '…</p>'; }).join('');
    if (!ro) h += '<div class="row"><input type="text" class="grow ws-code" placeholder="Thêm theo mã, ví dụ 9DS-PT2-012" aria-label="Thêm bài theo mã" autocomplete="off">' + btn('ws-add', 'Thêm') + '</div>';
    return '<div class="ws draft-body">' + h + '</div>';
  }
  function footHTML(s) {
    var c = s.card;
    if (c.stage === 'saved') {
      return '<div class="draft-foot"><div class="row">' + (c.saved ? '<a class="btn btn-primary ws-tex" href="' + U.esc(c.saved.tex) + '" download>Tải .tex</a>' : '') + btn('ws-pdf', 'In PDF') + '</div></div>';
    }
    if (c.stage !== 'draft') return '';
    var off = !c.items.length || s.pending > 0 || c.invalid.length > 0;  // P3, P8
    return '<div class="draft-foot"><span class="btn-wrap"><button type="button" class="btn btn-primary" data-act="ws-create"' + (off || s.busy ? ' disabled' : '') + (off ? ' aria-describedby="ws-why"' : '') + '>' +
      (s.busy ? 'Đang tạo phiếu…' : 'Tạo phiếu') + '</button>' + (off ? '<span class="reason" id="ws-why">' + (c.invalid.length ? BAD : NEED_ONE) + '</span>' : '') + '</span>' +
      '<p class="small muted">Chưa lưu gì cho tới khi bấm “Tạo phiếu”.</p><div class="row">' + btn('ws-drop', 'Bỏ phiếu nháp', s.busy ? 'disabled' : '', 'btn-ghost') + '</div></div>';
  }

  // ---- writes: PUT the whole sheet (debounced), resume only from Tạo phiếu / Thử lại ----
  function put(s) {
    var my = ++s.putSeq;
    clearTimeout(s.timer);
    s.timer = setTimeout(function () { save(s, false, my).then(function () { if (my === s.putSeq) refresh(s); }, noop); }, 500);
  }
  function save(s, replace, my) {
    my = my || ++s.putSeq;
    clearTimeout(s.timer); s.timer = 0; s.saving++;
    return U.api.send('PUT', path(s, '/decisions'), { for_date: s.card.for_date, refs: refsOf(s), replace: replace }).then(function (r) {
      s.saving--;
      if (my === s.putSeq) { s.pending = r.pending; draw(s); }
      return r;
    }, function (e) {
      s.saving--;
      if (!s.dropped) U.toast('Chưa lưu được phiếu nháp. Thử lại sau.', 'warn');  // a PUT in the air when Bỏ phiếu nháp went through gets a 404
      throw e;
    });
  }
  function resume(s) {
    return U.api.send('POST', path(s, '/resume')).then(function () { C.refreshPending(); });  // busy lasts until the stage moves
  }
  function ask(n, go) {
    U.confirm('Tạo phiếu mới thay thế?', 'Ngày này đã có phiếu ' + n + ' bài. Phiếu cũ vẫn giữ để tra cứu.', 'Tạo phiếu mới', function () { go(true); });
  }
  function create(s) {
    var c = s && s.card, box = s && s.el.querySelector('.ws-date');
    if (!c || c.stage !== 'draft' || s.busy || !c.items.length || s.pending > 0 || c.invalid.length) return;
    if (s.saving) { U.toast(ERR.not_ready, 'info'); return; }  // the sheet in the air must land before this one is sent
    if (!box.value) { U.toast('Chọn ngày buổi học trước nhé.', 'warn'); box.focus(); return; }
    c.for_date = box.value;
    var go = function (replace) {
      s.busy = true; draw(s);
      save(s, replace).then(function (r) {
        if (r.pending) { s.busy = false; draw(s); return; }
        return resume(s).catch(function (e) {
          s.busy = false; draw(s);
          if (e.code === 'worksheet_exists') ask((e.detail || {}).n_problems, go);
          else U.toast(ERR[e.code] || 'Chưa tạo được phiếu, thử lại sau.', 'warn');
        });
      }, function () { s.busy = false; draw(s); });
    };
    if (c.existing_for_date) ask(c.existing_for_date.n_problems, go);
    else go(false);
  }

  // ---- buttons, Enter, date ----
  function editing() { return W && W.card && W.card.stage === 'draft' && !W.busy ? W : null; }
  ACT['ws-move'] = function (el) {
    var s = editing(), i = +el.dataset.i, d = +el.dataset.d, j = i + d;
    if (!s) return;
    var it = s.card.items[i];
    s.card.items[i] = s.card.items[j]; s.card.items[j] = it;
    put(s);
    draw(s, '[data-act="ws-move"][data-i="' + j + '"][data-d="' + d + '"]:not(:disabled), [data-act="ws-del"][data-i="' + j + '"]');  // focus follows the problem
  };
  ACT['ws-del'] = function (el) {
    var s = editing(), i = +el.dataset.i;
    if (!s) return;
    s.card.items.splice(i, 1);
    put(s);
    draw(s, '[data-act="ws-del"][data-i="' + Math.min(i, s.card.items.length - 1) + '"], .ws-code');
  };
  ACT['ws-bad-del'] = function (el) {
    var s = editing();
    if (!s) return;
    s.card.invalid.splice(+el.dataset.i, 1);
    s.pending = null;  // that `pending` counted the code just dropped; the PUT below gives the new one
    put(s); draw(s, '.ws-code');
  };
  ACT['ws-add'] = function () {
    var s = editing();
    if (!s) return;
    var box = s.el.querySelector('.ws-code'), refs = box.value.toUpperCase().match(REF) || [], have = refsOf(s);
    if (!refs.length) { U.toast('Gõ mã bài, ví dụ 9DS-PT2-012.', 'warn'); box.focus(); return; }
    var dup = refs.filter(function (r) { return have.indexOf(r) >= 0; });
    if (dup.length) U.toast(dup.join(', ') + ' đã có trong phiếu.', 'info');
    s.extra = s.extra.concat(refs.filter(function (r, k) { return have.indexOf(r) < 0 && refs.indexOf(r) === k; }));
    box.value = '';
    put(s); draw(s, '.ws-code');
  };
  ACT['ws-create'] = function () { create(W); };
  ACT['ws-retry'] = function () {
    var s = W;
    s.busy = true; s.waits = 0; draw(s);
    resume(s).catch(function (e) { s.busy = false; draw(s); U.toast(ERR[e.code] || 'Chưa tạo được phiếu, thử lại sau.', 'warn'); });
  };
  ACT['ws-drop'] = function () {
    var s = W;
    if (!s || s.busy) return;
    U.confirm('Bỏ phiếu nháp này?', 'Phiếu nháp sẽ mất, chưa lưu gì. Gợi ý lại lúc nào cũng được.', 'Bỏ phiếu nháp', function () {
      var had = !!s.timer;  // a change still waiting for its PUT must not go out after the cancel
      clearTimeout(s.timer); s.timer = 0;
      U.api.send('POST', path(s, '/cancel')).then(function () {
        s.dropped = true; gone(s); C.refreshPending();
        if (W === s) W = null;
        var h = aside().querySelector('h2');  // the button is gone: the focus goes to the heading
        h.textContent = who(s.card.student_id); show(true); h.focus();
      }, function (e) {
        if (had) put(s);  // not cancelled: the change goes out as it would have
        U.toast(e.code === 'not_ready' ? 'Đang chạy, chờ xong rồi huỷ.' : ERR[e.code] || 'Chưa bỏ được phiếu nháp, thử lại sau.', 'warn');
      });
    }, true);
  };
  ACT['ws-pdf'] = function () {
    var c = W.card;
    U.print('<h1>Phiếu bài tập</h1><p class="p-meta">' + U.esc(who(c.student_id)) + ' · buổi ' + day(c.for_date) + '</p><ol>' +
      c.items.map(function (it) { return '<li>' + U.texHtml(it.statement_latex) + '</li>'; }).join('') + '</ol>', 'phiếu');
  };
  ACT['ws-close'] = function () { show(false); };
  ACT['ws-show'] = function () { show(true); };
  ACT['ws-open'] = function (el) { open(el.dataset.tid, false); };
  function onKey(ev) {  // IA-app §6: Enter in the panel = Tạo phiếu, in Thêm theo mã = Thêm; buttons and links keep their own Enter
    if (ev.key === 'Escape' && matchMedia('(max-width: 860px)').matches) { show(false); return; }
    if (ev.key !== 'Enter' || ev.isComposing || /^(BUTTON|A)$/.test(ev.target.tagName)) return;
    ev.preventDefault();
    if (ev.target.classList.contains('ws-code')) ACT['ws-add']();
    else create(W);
  }
  function onDate(ev) {
    var s = editing();
    if (s && ev.target.classList.contains('ws-date') && ev.target.value) { s.card.for_date = ev.target.value; put(s); }
  }

  // ---- the chat side ----
  C.cards.worksheet = function (host, card, m) {
    var add = card.added || [];
    host.innerHTML = (add.length ? '<p>Đã thêm ' + add.length + ' bài vào phiếu nháp: ' + add.map(ref).join(', ') + '.</p>' : '') +
      (card.invalid || []).map(function (x) { return '<p class="small">Không thêm được ' + ref(x.ref) + ': ' + U.esc(x.why) + '.</p>'; }).join('') +
      '<div class="row">' + btn('ws-open', 'Mở phiếu nháp', 'data-tid="' + U.esc(card.thread_id) + '"') + '</div>';
    var said = m && m.retry ? m.retry.text : null;  // the message this card answers (chat.js go); none from Mở
    if (!(m && m.done)) open(card.thread_id, said == null ? null : CODES_ONLY.test(said) ? card.added || [] : true);  // a reopened conversation does not open its old cards
  };
  C.worksheetThread = function () {  // R9: the draft on screen, while it can still take codes
    var s = W;
    if (!live(s) || (s.card && s.card.stage !== 'draft')) return null;
    if (s.timer) save(s, false).catch(noop);  // the last change lands before the code typed in the chat
    return s.tid;
  };
})();
