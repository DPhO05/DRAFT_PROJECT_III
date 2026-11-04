/* ⚙ menu: SYS[name]() opens each item's modal. */
(function () {
  var CLOSE = '<button type="button" class="btn" data-act="modal-close">Đóng</button>';
  var SYS = window.SYS = {};

  // the modal returns focus to whatever had it when it opened: always the ⚙ button, even after a slow fetch
  function show(o) { document.getElementById('gear-btn').focus(); U.modal(o); }

  SYS.catalog = function () {
    Promise.all([U.api.get('/catalog/kc'), U.api.get('/catalog/error-codes')]).then(function (r) {
      var kc = r[0], kinds = r[1].filter(function (c) { return c.active; });
      var topics = kc.filter(function (k) { return k.parent_id == null; }).map(function (t) {
        var sk = kc.filter(function (k) { return k.parent_id === t.id; });
        return '<details><summary><b>' + U.esc(t.name) + '</b> <span class="muted small">' + (t.lop ? '· lớp ' + t.lop + ' ' : '') + '· ' + sk.length + ' kỹ năng</span></summary>' +
          '<ul class="cat-list">' + sk.map(function (k) { return '<li>' + U.esc(k.name) + '</li>'; }).join('') + '</ul></details>';
      }).join('');
      show({ title: 'Danh mục kỹ năng &amp; loại lỗi', wide: true, body:
        '<div class="grid"><div class="stack cat-topics"><h3>Kỹ năng theo chủ đề</h3>' + (topics || '<p class="muted">Chưa có kỹ năng nào trong danh mục.</p>') + '</div>' +
        '<div class="stack"><h3>Loại lỗi (' + kinds.length + ')</h3><ul class="cat-kinds">' +
        kinds.map(function (c) { return '<li>' + U.esc(c.description) + '</li>'; }).join('') + '</ul>' +
        '<p class="small muted">Danh mục chỉ xem ở đây; người cài đổi được bằng file.</p></div></div>',
        foot: CLOSE });
    }).catch(function () { U.toast('Chưa mở được danh mục. Thử lại sau.', 'warn'); });
  };

  // ---- Sao lưu: list, back up now, restore (tutor restore does the same from the terminal) ----
  var BK_NAME = /^tutor-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})/;
  var KINDS = [['G1', 'bài chấm'], ['G4', 'phiếu nháp'], ['G2', 'lần nạp bài'], ['G5', 'báo cáo nháp']];
  var asked = null;  // the restore the teacher confirmed: { name, when }

  function when(name) {
    var m = BK_NAME.exec(name);
    return m ? m[3] + '/' + m[2] + '/' + m[1] + ' ' + m[4] + ':' + m[5] : name;
  }

  SYS.backup = function () {
    U.api.get('/backup').then(function (b) {
      var rows = b.backups.map(function (x) {
        return '<tr><td>' + when(x.name) + '</td><td class="al-right">' + (x.bytes / 1048576).toFixed(1).replace('.', ',') + ' MB</td>' +
          '<td class="al-right">' + U.btn('backup-restore', 'Khôi phục', 'data-name="' + U.esc(x.name) + '"') + '</td></tr>';
      }).join('');
      show({ title: 'Sao lưu', body:
        '<p>Dữ liệu tự sao lưu trước mỗi lần lưu kết quả chấm bài. Bản sao nằm trên máy này.</p>' +
        '<p class="small muted bk-dir">Thư mục dữ liệu: ' + U.esc(b.data_dir) + '</p>' +
        (rows ? '<div class="table-wrap"><table class="tbl"><thead><tr><th>Lúc</th><th class="al-right">Dung lượng</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>'
          : '<p class="muted">Chưa có bản sao lưu.</p>'),
        foot: CLOSE + '<button type="button" class="btn btn-primary" data-act="backup-now">Sao lưu ngay</button>' });
    }).catch(function () { U.toast('Chưa mở được danh sách sao lưu. Thử lại sau.', 'warn'); });
  };

  ACT['backup-now'] = function () {
    U.api.send('POST', '/backup').then(function () {
      U.toast('Đã sao lưu dữ liệu.');
      SYS.backup();
    }).catch(function () { U.toast('Chưa sao lưu được. Thử lại sau.', 'warn'); });
  };

  ACT['backup-restore'] = function (el) {
    var name = el.dataset.name, at = when(name);
    U.confirm('Khôi phục bản sao lưu?', 'Dữ liệu sẽ quay về lúc <b>' + at + '</b>. Mọi thay đổi sau lúc đó sẽ mất (bản hiện tại được sao lưu trước).',
      'Khôi phục', function () { asked = { name: name, when: at }; restore(); }, true);
  };

  function restore() {
    U.api.send('POST', '/backup/restore', { name: asked.name }).then(function () {
      U.toast('Đã khôi phục bản ' + asked.when + '.');
      setTimeout(function () { location.reload(); }, 1000);  // let the toast be read; the page then shows the restored data
    }).catch(function (e) {
      var d = e.detail || {};
      if (e.status === 409 && d.reason === 'unfinished') return unfinished(d.threads || []);
      if (e.status === 404) { U.toast('Bản sao lưu này không còn nữa.', 'warn'); return SYS.backup(); }
      if (e.status === 422 || e.code === 'restore_failed') return U.toast(e.message, 'warn');  // the server's own words
      U.toast('Chưa khôi phục được. Thử lại sau.', 'warn');
    });
  }

  function unfinished(threads) {
    var busy = threads.some(function (t) { return t.running || t.status === 'running'; });
    var parts = KINDS.map(function (k) {
      return threads.filter(function (t) { return t.graph === k[0]; }).length + ' ' + k[1];
    });
    asked.threads = threads.map(function (t) { return t.thread_id; });
    show({ title: 'Còn việc chưa xong', body:
      '<p>Còn ' + threads.length + ' việc chưa xong (' + parts.join(', ') + ').</p>' +
      '<p class="small muted">Bỏ các việc này thì phần đã làm dở trong đó sẽ mất.</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button>' +
        '<button type="button" class="btn btn-danger" data-act="backup-drop"' + (busy ? ' disabled' : '') + '>' +
        (busy ? 'Chờ việc đang chạy xong' : 'Bỏ các việc này rồi khôi phục') + '</button>' });
  }

  ACT['backup-drop'] = function () {
    U.closeModal();
    asked.threads.reduce(function (p, id) {  // one at a time: each cancel writes tutor.db
      return p.then(function () {
        return U.api.send('POST', '/threads/' + encodeURIComponent(id) + '/cancel').catch(function (e) { if (e.status !== 404) throw e; });
      });
    }, Promise.resolve()).then(restore).catch(function () { U.toast('Chưa bỏ được các việc này. Thử lại sau.', 'warn'); });
  };

  // ---- Cài đặt: three numbers and one box per provider in use. A key goes to the server and no further: no answer holds it ----
  var PROVIDER = { anthropic: 'Anthropic', openai: 'OpenAI' };
  var FIELDS = [
    { id: 'set-n', label: 'Số bài mỗi phiếu (mặc định)', min: 3, max: 12, whole: true,
      hint: 'Trợ lý chia phiếu thành bài ôn lại, bài vừa sức và một bài thử thách.',
      read: function (s) { return s.reco.n_problems; }, put: function (c, v) { (c.reco = c.reco || {}).n_problems = v; } },
    { id: 'set-norep', label: 'Không lặp lại bài em đã làm trong (ngày)', min: 0, max: 120, whole: true,
      read: function (s) { return s.reco.no_repeat_days; }, put: function (c, v) { (c.reco = c.reco || {}).no_repeat_days = v; } },
    { id: 'set-budget', label: 'Ngân sách mỗi tháng (USD) — chỉ nhắc, không chặn', min: 0,
      read: function (s) { return s.budget_usd_month; }, put: function (c, v) { c.budget_usd_month = v; } }
  ];
  var BROKEN = 'File cài đặt bị hỏng, nhờ người cài sửa.';
  var cfg = null;  // the last GET / PATCH answer; keys in it are true / false only

  function settingsModal() {
    var nums = FIELDS.map(function (f) {
      return '<label class="field"><span>' + f.label + '</span><input type="number" id="' + f.id + '" min="' + f.min + '"' + (f.max != null ? ' max="' + f.max + '"' : '') +
        ' value="' + U.esc(f.read(cfg)) + '"><span class="small err" id="' + f.id + '-err" role="alert"></span></label>' + (f.hint ? '<p class="small muted">' + f.hint + '</p>' : '');
    }).join('');
    var keys = Object.keys(cfg.keys).map(function (p) {
      var id = 'set-key-' + p;
      return '<label class="field"><span>Khoá ' + U.esc(PROVIDER[p] || p) + '</span><input type="password" autocomplete="off" spellcheck="false" id="' + id + '">' +
        '<span class="small muted">' + (cfg.keys[p] ? 'Đã có khoá. Để trống nếu không đổi.' : 'Chưa có khoá: dán khoá người cài gửi.') + '</span>' +
        '<span class="small err" id="' + id + '-err" role="alert"></span></label>';
    }).join('');
    show({ title: 'Cài đặt', body: nums + keys,
      foot: '<button type="button" class="btn" data-act="modal-close">Thôi</button><button type="button" class="btn btn-primary" data-act="settings-save">Lưu cài đặt</button>' });
  }

  SYS.settings = function () {
    U.api.get('/settings').then(function (s) { cfg = s; settingsModal(); })
      .catch(function () { U.toast('Chưa mở được cài đặt. Thử lại sau.', 'warn'); });
  };

  function fault(id, text) { document.getElementById(id + '-err').textContent = text; }

  ACT['settings-save'] = function (el) {
    var changes = {}, bad = false, keys = [];
    FIELDS.forEach(function (f) {
      var raw = document.getElementById(f.id).value.trim(), v = Number(raw);
      fault(f.id, '');
      if (raw === '' || !isFinite(v) || v < f.min || (f.max != null && v > f.max) || (f.whole && Math.floor(v) !== v)) {
        fault(f.id, 'Nhập số từ ' + f.min + (f.max != null ? ' đến ' + f.max : ' trở lên') + '.');
        bad = true;
      } else if (v !== f.read(cfg)) f.put(changes, v);  // only what changed reaches settings.json
    });
    Object.keys(cfg.keys).forEach(function (p) {
      var v = document.getElementById('set-key-' + p).value.trim();
      fault('set-key-' + p, '');
      if (v) keys.push([p, v]);
    });
    if (bad) return;
    el.disabled = true;
    var broken = false;  // settings.json is corrupt: the numbers are refused, but a key lives in .env and still saves
    (Object.keys(changes).length ? U.api.send('PATCH', '/settings', changes).then(function (s) { cfg = s; }, function (e) {
      if (e.status !== 409) throw e;
      broken = true;
    }) : Promise.resolve()).then(function () {
      return keys.reduce(function (done, k) {
        return done.then(function () {
          return U.api.send('PUT', '/settings/key', { provider: k[0], key: k[1] }).then(function (r) { cfg.keys = r.keys; }, function (e) {
            e.box = 'set-key-' + k[0];
            throw e;
          });
        });
      }, Promise.resolve());
    }).then(function () {
      if (broken) U.toast(BROKEN, 'warn');
      if (broken && !keys.length) { el.disabled = false; return; }
      U.toast(broken ? 'Đã lưu khoá.' : 'Đã lưu cài đặt.');
      settingsModal();  // the key boxes come back empty
      if (window.CHAT) CHAT.keyNotice();
    }).catch(function (e) {
      el.disabled = false;
      if (broken) U.toast(BROKEN, 'warn');
      if (e.status === 422 && e.box) fault(e.box, 'Khoá không đúng dạng');
      else U.toast('Chưa lưu được. Thử lại sau.', 'warn');
    });
  };

  // ---- Chi phí tháng: total on budget, a bar, four tasks. The server groups the agents; no call, session or code reaches the page ----
  var WARN = { near: 'Đã dùng hơn 80 % ngân sách tháng.', over: 'Đã vượt ngân sách tháng. App vẫn chạy bình thường.' };

  function usd(n) { return n.toFixed(n && n < 1 ? 2 : 1).replace('.', ','); }

  SYS.cost = function () {
    U.api.get('/logs/cost').then(function (c) {
      var m = c.month.split('-'), pct = Math.min(100, Math.round((c.pct || 0) * 100));
      show({ title: 'Chi phí tháng ' + m[1] + '/' + m[0], body:
        '<p>Khoảng <b>' + usd(c.total_usd) + ' USD</b>' + (c.budget_usd ? ' trên ' + U.esc(String(c.budget_usd).replace('.', ',')) + ' USD (giả định).' : ' (giả định). Chưa đặt ngân sách tháng.') + '</p>' +
        (c.budget_usd ? '<div class="cost-bar" role="progressbar" aria-label="Đã dùng của ngân sách tháng" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '"><div style="width:' + pct + '%"></div></div>' : '') +
        (WARN[c.warning] ? '<p class="cost-warn" role="status">' + WARN[c.warning] + '</p>' : '') +
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>Việc</th><th class="al-right">Khoảng</th></tr></thead><tbody>' +
        c.parts.map(function (p) { return '<tr><td>' + U.esc(p.label) + '</td><td class="al-right">' + usd(p.usd) + ' USD</td></tr>'; }).join('') + '</tbody></table></div>',
        foot: CLOSE });
    }).catch(function () { U.toast('Chưa mở được chi phí. Thử lại sau.', 'warn'); });
  };

  // R14: one reminder when the app opens; a failed read says nothing
  U.api.get('/logs/cost').then(function (c) { if (WARN[c.warning]) U.toast(WARN[c.warning], 'warn'); }, function () {});

  ACT.sys = function (el) {
    var k = el.dataset.sys;
    U.closeGear();
    document.getElementById('gear-btn').focus();
    if (SYS[k]) SYS[k]();
  };
})();
