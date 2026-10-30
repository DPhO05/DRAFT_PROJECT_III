/* Core: data indexes, mutable state, helpers, tabs, modal, toast, MathJax, print, ⚙ menu. */
var A = window.APP;
var ACT = {};          // data-act="name" -> handler(el, event)
var TABS = {};         // tab id -> { render(panel), shown }
var U = {};
var S = {};

(function () {
  // ---- indexes ----
  A.P = {}; A.problems.forEach(function (p) { A.P[p.id] = p; });
  A.REF = {}; A.problems.forEach(function (p) { A.REF[p.ref] = p; });
  A.SK = {}; A.skills.forEach(function (k) { A.SK[k.id] = k; });
  A.TP = {}; A.topics.forEach(function (t) { A.TP[t.id] = t; });
  A.K = {}; A.kinds.forEach(function (k) { A.K[k.id] = k; });
  A.JOB = {}; A.jobs.forEach(function (j) { A.JOB[j.id] = j; });

  // ---- mutable state (nothing here is "saved" until a save button runs) ----
  S.students = A.students.map(function (s) { return Object.assign({}, s); });
  S.sessions = A.sessions.slice();
  S.levels = JSON.parse(JSON.stringify(A.levels));
  S.reports = A.reports.slice();
  S.reportDrafts = A.reportDrafts.slice();
  S.worksheets = A.worksheets.slice();
  S.jobs = A.jobs.map(function (j) { return { id: j.id, status: j.status }; });
  S.problemsNew = {};    // pid -> true for problems added through "Nạp bài mới"
  S.nextStudentId = 7;

  // ---- text + dates ----
  U.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  U.norm = function (s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd'); };
  U.d = function (iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; };
  U.dm = function (iso) { var p = iso.split('-'); return p[2] + '/' + p[1]; };
  U.parse = function (iso) { var p = iso.split('-').map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2])); };
  U.iso = function (dt) { return dt.toISOString().slice(0, 10); };
  U.addDays = function (iso, n) { var t = U.parse(iso); t.setUTCDate(t.getUTCDate() + n); return U.iso(t); };
  U.WD = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  U.wd = function (iso) { return U.WD[U.parse(iso).getUTCDay()]; };
  U.monday = function (iso) { var day = U.parse(iso).getUTCDay(); return U.addDays(iso, -((day + 6) % 7)); };
  U.today = A.today;
  U.LV = { vung: 'vững', dang: 'đang hình thành', chua: 'chưa vững' };
  U.CH = { up: 'tiến bộ', keep: 'giữ', down: 'cần ôn' };
  U.DIFF = { de: 'dễ', vua: 'vừa', kho: 'khó' };
  U.lvChip = function (lv) { return '<span class="chip lv-' + lv + '">' + U.LV[lv] + '</span>'; };
  U.chTag = function (ch) { return '<span class="ch ch-' + ch + ' small">' + U.CH[ch] + '</span>'; };
  U.diffChip = function (lv) { return lv ? '<span class="chip">' + U.DIFF[lv] + '</span>' : '<span class="chip chip-warn">chưa có mức</span>'; };
  U.skillName = function (id) { return id && A.SK[id] ? A.SK[id].name : 'không gắn kỹ năng'; };
  U.kindLabel = function (id) { return A.K[id] ? A.K[id].label : 'Lỗi khác'; };
  U.student = function (id) { return S.students.find(function (s) { return s.id === id; }); };
  U.score10 = function (score, max) { if (!max) return '—'; var v = Math.round(score / max * 20) / 2; return String(v).replace('.', ','); };
  U.plural = function (n, w) { return n + ' ' + w; };
  U.sessionScore = function (sess) {
    var sc = 0, mx = 0; sess.problems.forEach(function (p) { sc += p.score || 0; mx += p.max || 0; });
    return { score: sc, max: mx, ten: U.score10(sc, mx) };
  };
  U.sessionMistakes = function (sess) { return sess.problems.reduce(function (n, p) { return n + p.mistakes.length; }, 0); };
  U.studentSessions = function (sid) { return S.sessions.filter(function (s) { return s.student === sid; }).sort(function (a, b) { return a.date < b.date ? 1 : -1; }); };
  U.pendingJobs = function (sid) { return S.jobs.filter(function (j) { var J = A.JOB[j.id]; return (sid == null || J.student === sid) && ['review', 'match', 'failed'].indexOf(j.status) >= 0; }); };
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
    t.className = 'toast toast-' + (kind || 'ok'); t.innerHTML = msg;
    root.appendChild(t);
    setTimeout(function () { t.remove(); }, 4200);
  };

  // ---- modal ----
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
  U.download = function (name, text) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
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
  U.badges = function () {
    var nJobs = U.pendingJobs().length + (S.wsDraftPending ? 1 : 0);
    var b = document.getElementById('badge-tro-ly'); b.hidden = !nJobs; b.textContent = nJobs; b.title = nJobs + ' việc đang chờ';
    var r = document.getElementById('badge-bao-cao'); r.hidden = !S.reportDrafts.length; r.textContent = S.reportDrafts.length; r.title = S.reportDrafts.length + ' báo cáo nháp';
  };

  // ---- ⚙ menu + system panels ----
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
    if (TABS['hoc-sinh'] && TABS['hoc-sinh'].redrawChart) TABS['hoc-sinh'].redrawChart();
  };
  S.backups = A.backups.slice();
  var SYS = {
    backup: function () {
      var rows = S.backups.map(function (b, i) {
        var p = b.at.split(' ');
        return '<tr><td>' + U.d(p[0]) + ' ' + p[1] + '</td><td class="al-right">' + (b.kb / 1024).toFixed(1).replace('.', ',') + ' MB</td>' +
          '<td class="al-right"><button type="button" class="btn btn-sm" data-act="restore" data-i="' + i + '">Khôi phục</button></td></tr>';
      }).join('');
      U.modal({ title: 'Sao lưu', body:
        '<p>Dữ liệu tự sao lưu trước mỗi lần lưu kết quả chấm bài. Bản sao nằm trên máy này.</p>' +
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>Lúc</th><th class="al-right">Dung lượng</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>',
        foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button><button type="button" class="btn btn-primary" data-act="backup-now">Sao lưu ngay</button>' });
    },
    catalog: function () {
      var topics = A.topics.map(function (t) {
        var sk = A.skills.filter(function (k) { return k.topic === t.id; });
        return '<details><summary><b>' + U.esc(t.name) + '</b> <span class="muted small">lớp ' + t.grade + ' · ' + sk.length + ' kỹ năng</span></summary><ul>' +
          sk.map(function (k) { return '<li>' + U.esc(k.name) + '</li>'; }).join('') + '</ul></details>';
      }).join('');
      var kinds = A.kinds.map(function (k) { return '<li>' + U.esc(k.label) + '</li>'; }).join('');
      U.modal({ title: 'Danh mục kỹ năng & loại lỗi', wide: true, body:
        '<div class="grid"><div class="stack"><h3>Kỹ năng theo chủ đề</h3>' + topics + '</div>' +
        '<div class="stack"><h3>Loại lỗi (' + A.kinds.length + ')</h3><ul class="stack" style="gap:4px;padding-left:18px;margin:0">' + kinds + '</ul>' +
        '<p class="small muted">Danh mục đổi bằng file trong thư mục dữ liệu; trợ lý chỉ dùng các mục ở đây.</p></div></div>',
        foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
    },
    settings: function () {
      var st = A.settings;
      U.modal({ title: 'Cài đặt', body:
        '<label class="field"><span>Số bài mỗi phiếu (mặc định)</span><input type="number" id="set-n" min="3" max="12" value="' + st.n + '"></label>' +
        '<p class="small muted">Trợ lý chia phiếu thành bài ôn lại, bài vừa sức và một bài thử thách.</p>' +
        '<label class="field"><span>Không lặp lại bài em đã làm trong (ngày)</span><input type="number" id="set-norep" min="0" max="120" value="' + st.noRepeat + '"></label>' +
        '<label class="field"><span>Ngân sách mỗi tháng (USD) — chỉ nhắc, không chặn</span><input type="number" id="set-budget" min="0" value="' + st.budget + '"></label>' +
        '<div class="field"><span>Giao diện</span><div class="seg" role="group" aria-label="Giao diện">' +
        ['system', 'light', 'dark'].map(function (v, i) { var cur = document.documentElement.getAttribute('data-theme') || 'system'; return '<button type="button" class="seg-btn" data-act="theme" data-theme-opt="' + v + '" aria-pressed="' + (cur === v) + '">' + ['Theo máy', 'Sáng', 'Tối'][i] + '</button>'; }).join('') + '</div></div>',
        foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="settings-save">Lưu cài đặt</button>' });
    },
    cost: function () {
      var c = A.cost, b = A.settings.budget, pct = Math.min(100, c.total / b * 100);
      U.modal({ title: 'Chi phí tháng ' + c.month, body:
        '<p class="rep-text"><b>Khoảng ' + c.total.toFixed(1).replace('.', ',') + ' USD</b> trên ngân sách ' + b + ' USD.</p>' +
        '<div style="height:10px;background:var(--dim-soft);border-radius:3px;overflow:hidden"><div style="height:100%;width:' + pct + '%;background:var(--accent)"></div></div>' +
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>Việc</th><th class="al-right">Khoảng</th></tr></thead><tbody>' +
        c.parts.map(function (p) { return '<tr><td>' + p[0] + '</td><td class="al-right">' + p[1].toFixed(1).replace('.', ',') + ' USD</td></tr>'; }).join('') + '</tbody></table></div>' +
        '<p class="small muted">Còn xa ngân sách. Vượt ngân sách chỉ có lời nhắc, app vẫn chạy.</p>',
        foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
    }
  };
  ACT.sys = function (el) { U.closeGear(); SYS[el.dataset.sys](); };
  ACT['backup-now'] = function () {
    S.backups.unshift({ at: U.today + ' ' + new Date().toTimeString().slice(0, 5), kb: 1652 });
    SYS.backup(); U.toast('Đã sao lưu dữ liệu.');
  };
  ACT.restore = function (el) {
    var b = S.backups[+el.dataset.i], p = b.at.split(' ');
    U.confirm('Khôi phục bản sao lưu?', 'Dữ liệu sẽ quay về lúc <b>' + U.d(p[0]) + ' ' + p[1] + '</b>. Mọi thay đổi sau lúc đó sẽ mất (bản hiện tại được sao lưu trước).',
      'Khôi phục', function () { U.toast('Đã khôi phục bản ' + U.d(p[0]) + ' ' + p[1] + '. (Bản thử: dữ liệu mẫu không đổi.)', 'info'); }, true);
  };
  ACT['settings-save'] = function () {
    A.settings.n = +document.getElementById('set-n').value || A.settings.n;
    A.settings.noRepeat = +document.getElementById('set-norep').value;
    A.settings.budget = +document.getElementById('set-budget').value || A.settings.budget;
    U.closeModal(); U.toast('Đã lưu cài đặt.');
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
      if (window.CHAT && CHAT.escape()) return;
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
