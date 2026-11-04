/* Core: helpers, tabs, modal, toast, MathJax, print, ⚙ menu. Tabs register in TABS and fetch through U.api. */
var ACT = {};          // data-act="name" -> handler(el, event)
var TABS = {};         // tab id -> { render(panel), onShow(panel)? }
var U = {};

(function () {
  U.api = window.api;

  // ---- text + dates ----
  U.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
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

  // ---- chat text: HS-xx -> name (C-40), sub-Markdown (api-v3 §3.1), score on a 10 scale ----
  U.people = {};  // "HS-01" -> full name; the Trợ lý tab fills it from /students?archived=true
  U.names = function (text) {
    return String(text).replace(/\bHS-(\d{2,})\b/gi, function (m, n) { return U.people['HS-' + n.padStart(2, '0')] || m; });
  };
  U.nesc = function (s) { return U.esc(U.names(s == null ? '' : s)); };  // server text: codes to names, then escaped
  U.wire = function (text) {  // C-40: a name shown or typed in a box goes back as its HS-xx code (chat.js sendBox does it for @)
    return Object.keys(U.people).filter(function (c) { return U.people[c].trim().split(/\s+/).length >= 2; })  // one-word names stay (S24)
      .sort(function (a, b) { return U.people[b].length - U.people[a].length; })
      .reduce(function (t, c) {
        return t.replace(new RegExp('(?<![\\p{L}\\p{N}])' + U.people[c].replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}\\p{N}])', 'gu'), c);
      }, String(text));
  };
  U.norm = function (s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/đ/g, 'd'); };  // lower first: Đ has no decomposition
  U.code = function (id) { return 'HS-' + String(id).padStart(2, '0'); };
  U.who = function (id) { return U.people[U.code(id)] || 'học sinh'; };
  U.dm = function (iso) { return iso.slice(8, 10) + '/' + iso.slice(5, 7); };
  U.btn = function (act, label, attrs, cls) { return '<button type="button" class="btn btn-sm ' + (cls || '') + '" data-act="' + act + '" ' + (attrs || '') + '>' + label + '</button>'; };
  U.score = function (score, max) { return String(Math.round(max ? score / max * 20 : 0) / 2).replace('.', ',') + '/10'; };
  U.md = function (text) {
    var inline = function (s) {
      return U.esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\$([^$\n]+)\$/g, '<span class="tex">$$$1$$</span>');
    };
    var cell = function (tag) { return function (c) { return '<' + tag + '>' + inline(c.trim()) + '</' + tag + '>'; }; };
    var out = [], kind = '', buf = [];
    var flush = function () {
      if (!buf.length) return;
      if (kind === 'ul' || kind === 'ol') {
        out.push('<' + kind + '>' + buf.map(function (l) { return '<li>' + inline(l.replace(/^\s*(?:[-*]|\d+\.)\s+/, '')) + '</li>'; }).join('') + '</' + kind + '>');
      } else if (kind === 'table') {
        var rows = buf.filter(function (l) { return !/^[\s|:-]+$/.test(l); }).map(function (l) { return l.trim().replace(/^\||\|$/g, '').split('|'); });
        out.push('<div class="table-wrap"><table class="tbl"><thead><tr>' + (rows.shift() || []).map(cell('th')).join('') + '</tr></thead><tbody>' +
          rows.map(function (r) { return '<tr>' + r.map(cell('td')).join('') + '</tr>'; }).join('') + '</tbody></table></div>');
      } else out.push('<p>' + buf.map(inline).join('<br>') + '</p>');
      buf = []; kind = '';
    };
    String(text).split('\n').forEach(function (l) {
      var k = !l.trim() ? '' : /^\s*[-*]\s/.test(l) ? 'ul' : /^\s*\d+\.\s/.test(l) ? 'ol' : /^\s*\|/.test(l) ? 'table' : 'p';
      if (k !== kind) flush();
      kind = k;
      if (k) buf.push(l);
    });
    flush();
    return out.join('');
  };

  // ---- NDJSON POST (the assistant stream): onEvent gets every complete line; a non-2xx answer rejects like app/api.js ----
  U.ndjson = function (path, body, onEvent) {
    return fetch('/api' + path, { method: 'POST', headers: { 'X-Tutor': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          var err = j.error || {}, e = new Error(err.message || r.statusText);
          e.status = r.status; e.code = err.code; e.detail = err.detail;
          throw e;
        });
      }
      var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
      var pump = function () {
        return rd.read().then(function (x) {
          buf += dec.decode(x.value, { stream: !x.done });
          var lines = buf.split('\n');
          buf = lines.pop();  // a line cut short stays unread: the caller sees a stream that ended before `done`
          lines.forEach(function (l) { if (l.trim()) onEvent(JSON.parse(l)); });
          return x.done ? undefined : pump();
        });
      };
      return pump();
    });
  };

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

  // ---- ⚙ menu: items run ACT.sys (system.js); theme is real ----
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
