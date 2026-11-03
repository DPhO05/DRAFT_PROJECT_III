/* "Sắp có" placeholders: each tab and ⚙ item says what it will do until its real version replaces it. */
(function () {
  var NEXT = '<span class="chip chip-info">Sắp có</span>';
  var PAGES = {
    'hoc-sinh': ['Học sinh', 'Xem từng em tiến bộ ra sao và quản lý danh sách học sinh.'],
    'bao-cao': ['Báo cáo', 'Làm báo cáo cho phụ huynh theo ngày, tuần hoặc tháng, chỉ từ các buổi đã duyệt.']
  };
  var MENU = {
    backup: ['Sao lưu', 'Xem các bản sao lưu, sao lưu ngay và khôi phục khi cần.'],
    catalog: ['Danh mục kỹ năng &amp; loại lỗi', 'Xem kỹ năng theo chủ đề và các loại lỗi học sinh hay gặp.'],
    settings: ['Cài đặt', 'Chỉnh số bài mỗi phiếu, số ngày không lặp lại bài và ngân sách mỗi tháng.'],
    cost: ['Chi phí tháng', 'Xem chi phí trợ lý trong tháng, chia theo từng việc.']
  };

  Object.keys(PAGES).forEach(function (id) {
    TABS[id] = { render: function (panel) {
      panel.innerHTML = '<div class="page"><div class="page-head"><h1>' + PAGES[id][0] + '</h1></div>' +
        '<div class="empty">' + NEXT + '<p>' + PAGES[id][1] + '</p></div></div>';
    } };
  });

  ACT.sys = function (el) {
    var m = MENU[el.dataset.sys];
    U.closeGear();
    document.getElementById('gear-btn').focus();  // the modal returns focus here on close
    U.modal({ title: m[0], body: NEXT + '<p>' + m[1] + '</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  };
})();
