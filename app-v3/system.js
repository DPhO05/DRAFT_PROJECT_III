/* ⚙ menu: SYS[name]() opens each item's modal. Items without a real version yet keep their "Sắp có" placeholder in MENU. */
(function () {
  var NEXT = '<span class="chip chip-info">Sắp có</span>';
  var CLOSE = '<button type="button" class="btn" data-act="modal-close">Đóng</button>';
  var MENU = {
    backup: ['Sao lưu', 'Xem các bản sao lưu, sao lưu ngay và khôi phục khi cần.'],
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
    }, function () { U.toast('Chưa mở được danh mục. Thử lại sau.', 'warn'); });
  };

  ACT.sys = function (el) {
    var k = el.dataset.sys, m = MENU[k];
    U.closeGear();
    document.getElementById('gear-btn').focus();
    if (SYS[k]) SYS[k](); else show({ title: m[0], body: NEXT + '<p>' + m[1] + '</p>', foot: CLOSE });
  };
})();
