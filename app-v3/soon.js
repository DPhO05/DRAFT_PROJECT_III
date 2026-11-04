/* "Sắp có" placeholders: each ⚙ item says what it will do until its real version replaces it. */
(function () {
  var NEXT = '<span class="chip chip-info">Sắp có</span>';
  var MENU = {
    backup: ['Sao lưu', 'Xem các bản sao lưu, sao lưu ngay và khôi phục khi cần.'],
    catalog: ['Danh mục kỹ năng &amp; loại lỗi', 'Xem kỹ năng theo chủ đề và các loại lỗi học sinh hay gặp.'],
    settings: ['Cài đặt', 'Chỉnh số bài mỗi phiếu, số ngày không lặp lại bài và ngân sách mỗi tháng.'],
    cost: ['Chi phí tháng', 'Xem chi phí trợ lý trong tháng, chia theo từng việc.']
  };

  ACT.sys = function (el) {
    var m = MENU[el.dataset.sys];
    U.closeGear();
    document.getElementById('gear-btn').focus();  // the modal returns focus here on close
    U.modal({ title: m[0], body: NEXT + '<p>' + m[1] + '</p>',
      foot: '<button type="button" class="btn" data-act="modal-close">Đóng</button>' });
  };
})();
