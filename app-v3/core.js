/* Core: helpers, tabs, modal, toast, MathJax, print, ⚙ menu. Tabs register in TABS and fetch through U.api. */
var ACT = {};          // data-act="name" -> handler(el, event)
var TABS = {};         // tab id -> { render(panel), onShow(panel)? }
var U = {};

(function () {
  U.api = window.api;

  // ---- text + dates ----
  U.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  U.norm = function (s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd'); };
  U.d = function (iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; };
  U.parse = function (iso) { var p = iso.split('-').map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2])); };
  U.WD = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  U.wd = function (iso) { return U.WD[U.parse(iso).getUTCDay()]; };
  (function () {
    var n = new Date(), p = function (x) { return String(x).padStart(2, '0'); };
    U.today = n.getFullYear() + '-' + p(n.getMonth() + 1) + '-' + p(n.getDate());
  })();
  U.texHtml = function (latex) {
    // Bank LaTeX uses blank lines between paragraphs; keep them as <p>.
    return '<div class="tex tex-block">' + String(latex).split(/\n\s*\n/).map(function (p) { return '<p>' + U.esc(p) + '</p>'; }).join('') + '</div>';
  };
  U.texInline = function (latex) { return '<span class="tex">' + U.esc(latex) + '</span>'; };

  // ---- MathJax: typeset on demand, queue until the CDN script is ready ----
  var texQueue = [], texReady = false;
  window.__texReady = function () { texReady = true; var q = texQueue; texQueue = []; q.forEach(U.typeset); };
  U.typeset = function (el) {
    if (!el) return;
    if (!texReady || !window.MathJax || !MathJax.typesetPromise) { texQueue.push(el); return; }
    var els = el.classList && el.classList.contains('tex') ? [el] : Array.prototype.slice.call(el.querySelectorAll('.tex'));
    els = els.filter(function (x) { return x.isConnected && !x.dataset.typeset; });
    if (!els.length) return;
    els.forEach(function (x) { x.dataset.typeset = '1'; });
    MathJax.typesetPromise(els).catch(function (e) { console.warn('MathJax', e); });
  };

  // ---- toast ----
  U.toast = function (msg, kind) {
    var root = document.getElementById('toasts');
    var t = document.createElement('div');
    t.className = 'toast toast-' + (kind || 'ok'); t.textContent = msg;
    root.appendChild(t);
    setTimeout(function () { t.remove(); }, 4200);
  };

  // ---- modal: o.title, o.body and o.foot are HTML, callers escape with U.esc ----
  var lastFocus = null;
  U.modal = function (o) {
    U.closeModal();
    lastFocus = document.activeElement;
    var root = document.getElementById('modal-root');
    root.innerHTML = '<div class="modal-back" data-modal-back><div class="modal' + (o.wide ? ' modal-wide' : '') + '" role="dialog" aria-modal="true" aria-labelledby="modal-title">' +
      '<div class="modal-head"><h2 id="modal-title">' + o.title + '</h2><button type="button" class="icon-btn" data-act="modal-close" aria-label="Đóng">×</button></div>' +
      '<div class="modal-body" id="modal-body">' + o.body + '</div>' +
      (o.foot ? '<div class="modal-foot" id="modal-foot">' + o.foot + '</div>' : '') + '</div></div>';
    var m = root.querySelector('.modal');
    U.typeset(m);
    var f = m.querySelector('[autofocus]') || m.querySelector('input, select, textarea, button:not([data-act="modal-close"])') || m.querySelector('button');
    if (f) f.focus();
    return m;
  };
  U.closeModal = function () {
    var root = document.getElementById('modal-root');
    if (!root.firstChild) return;
    root.innerHTML = '';
    if (lastFocus && lastFocus.isConnected) lastFocus.focus();
  };
  U.confirm = function (title, text, okLabel, onOk, danger) {
    U.modal({ title: title, body: '<p>' + text + '</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn ' + (danger ? 'btn-danger' : 'btn-primary') + '" data-act="confirm-ok">' + okLabel + '</button>' });
    ACT['confirm-ok'] = function () { U.closeModal(); onOk(); };
  };
  ACT['modal-close'] = function () { U.closeModal(); };

  // ---- print view (PDF via the browser's print dialog) ----
  U.print = function (html, what) {
    var root = document.getElementById('print-root');
    root.innerHTML = '<div class="print-sheet tex">' + html + '</div>';
    root.querySelector('.print-sheet').classList.remove('tex');
    root.classList.remove('tex-ignore');
    U.toast('Đang mở hộp thoại in — chọn “Lưu thành PDF” để có file ' + what + '.', 'info');
    var go = function () { root.classList.add('tex-ignore'); try { window.print(); } catch (e) { /* print unsupported */ } };
    if (texReady && window.MathJax && MathJax.typesetPromise) {
      MathJax.typesetPromise(Array.prototype.slice.call(root.querySelectorAll('.tex'))).then(go, go);
    } else { setTimeout(go, 50); }
  };

  // ---- tabs ----
  var ORDER = ['tro-ly', 'hoc-sinh', 'bao-cao', 'ngan-hang'];
  U.tab = function (id, focusTab) {
    if (ORDER.indexOf(id) < 0) id = 'tro-ly';
    ORDER.forEach(function (t) {
      var b = document.getElementById('tab-' + t), p = document.getElementById('panel-' + t), on = t === id;
      b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; p.hidden = !on;
    });
    var T = TABS[id], panel = document.getElementById('panel-' + id);
    if (T && !T.shown) { T.shown = true; T.render(panel); }
    else if (T && T.onShow) T.onShow(panel);
    if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
    if (focusTab) document.getElementById('tab-' + id).focus();
    U.closeGear();
    window.scrollTo(0, 0);
  };
  ACT.tab = function (el, ev) { if (ev) ev.preventDefault(); U.tab(el.dataset.tab); };

  // ---- ⚙ menu: items run ACT.sys (soon.js); theme is real ----
  U.closeGear = function () { var m = document.getElementById('gear-menu'); if (!m.hidden) { m.hidden = true; document.getElementById('gear-btn').setAttribute('aria-expanded', 'false'); } };
  ACT.gear = function () {
    var m = document.getElementById('gear-menu'), open = m.hidden;
    m.hidden = !open; document.getElementById('gear-btn').setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) m.querySelector('[role=menuitem]').focus();
  };
  ACT.theme = function (el) {
    var v = el.dataset.themeOpt;
    if (v === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', v);
    document.querySelectorAll('[data-theme-opt]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.themeOpt === v ? 'true' : 'false'); });
    try { localStorage.setItem('gs-theme', v); } catch (e) { /* storage blocked */ }
  };

  // ---- global events ----
  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-act]');
    if (ev.target.matches('[data-modal-back]')) { U.closeModal(); return; }
    if (!ev.target.closest('.gear-wrap')) U.closeGear();
    if (!el || el.disabled) return;
    var fn = ACT[el.dataset.act];
    if (fn) fn(el, ev);
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') {
      if (document.getElementById('modal-root').firstChild) { U.closeModal(); return; }
      var g = document.getElementById('gear-menu');
      if (!g.hidden) { U.closeGear(); document.getElementById('gear-btn').focus(); return; }
    }
    var tab = ev.target.closest && ev.target.closest('[role=tab]');
    if (tab && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft' || ev.key === 'Home' || ev.key === 'End')) {
      var i = ORDER.indexOf(tab.dataset.tab);
      i = ev.key === 'Home' ? 0 : ev.key === 'End' ? ORDER.length - 1 : (i + (ev.key === 'ArrowRight' ? 1 : ORDER.length - 1)) % ORDER.length;
      ev.preventDefault(); U.tab(ORDER[i], true);
    }
    var menu = ev.target.closest && ev.target.closest('#gear-menu');
    if (menu && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
      var items = Array.prototype.slice.call(menu.querySelectorAll('[role=menuitem]')), k = items.indexOf(ev.target);
      ev.preventDefault(); items[(k + (ev.key === 'ArrowDown' ? 1 : items.length - 1) + items.length) % items.length].focus();
    }
  });
  document.querySelector('.tabs').addEventListener('click', function (ev) {
    var t = ev.target.closest('[role=tab]'); if (t) U.tab(t.dataset.tab);
  });
})();
