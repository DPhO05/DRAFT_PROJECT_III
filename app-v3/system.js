/* ⚙ menu: SYS[name]() opens each item's modal. Items without a real version yet keep their "Sắp có" placeholder in MENU. */
(function () {
  var NEXT = '<span class="chip chip-info">Sắp có</span>';
  var CLOSE = '<button type="button" class="btn" data-act="modal-close">Đóng</button>';
  var MENU = {
    settings: ['Cài đặt', 'Chỉnh số bài mỗi phiếu, số ngày không lặp lại bài và ngân sách mỗi tháng.'],
    cost: ['Chi phí tháng', 'Xem chi phí trợ lý trong tháng, chia theo từng việc.']
  };
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

  ACT.sys = function (el) {
    var k = el.dataset.sys, m = MENU[k];
    U.closeGear();
    document.getElementById('gear-btn').focus();
    if (SYS[k]) SYS[k](); else show({ title: m[0], body: NEXT + '<p>' + m[1] + '</p>', foot: CLOSE });
  };
})();
