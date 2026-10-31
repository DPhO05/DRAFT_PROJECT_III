/* Lớp fetch chung: mọi lời gọi /api của app đi qua đây (SDD monolith §5). */
(function () {
  'use strict';
  function request(method, path, body) {
    var opts = { method: method, headers: {} };
    if (method !== 'GET') {
      // Server từ chối mọi request ghi thiếu X-Tutor (chặn CSRF, SDD §9.1).
      opts.headers['X-Tutor'] = '1';
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body || {});
    }
    return fetch('/api' + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.ok) return j;
        var err = j.error || {}, e = new Error(err.message || r.statusText);
        e.status = r.status; e.code = err.code; e.detail = err.detail;
        throw e;
      });
    });
  }
  function today() {
    var d = new Date(), p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  window.api = {
    get: function (path) { return request('GET', path); },
    send: function (method, path, body) { return request(method, path, body); }
  };
  // Số mục chờ của 1 thread đang dừng: gate_review = số đề xuất lỗi (+ số 04 bất đồng), gate_confirm_match = số cờ chưa xử lý,
  // gate_confirm_commit = không còn gì để duyệt (0 mục, chỉ chờ Lưu kết quả).
  var SUMMARY_MAX = 20, summaries = {}, queueSeq = 0, queueSig = null;
  function summarize(t) {
    var sig = t.node + '|' + t.updated_at + '|' + t.checkpoints, c = summaries[t.thread_id];
    if (c && c.sig === sig) return Promise.resolve(c.v);
    return api.get('/threads/' + encodeURIComponent(t.thread_id) + '?include=state').then(function (x) {
      var st = x.state || {}, ps = st.proposals || [], fl = (st.ingest || {}).flags || [];
      var v = t.node === 'gate_confirm_match'
        ? { items: fl.filter(function (f) { return !f.resolved; }).length, unit: 'cờ', disagree: null }
        : t.node === 'gate_confirm_commit'
          ? { items: 0, unit: '', label: 'chờ lưu kết quả', disagree: null }
          : { items: ps.length, unit: 'đề xuất', disagree: ps.filter(function (p) { return (p.verifier || {}).verdict !== 'agree'; }).length };
      summaries[t.thread_id] = { sig: sig, v: v };
      return v;
    }, function () { return null; });
  }
  window.TutorApi = {
    // Sau mỗi lần ghi: cập nhật đồng hồ tutor.db trên thanh trên.
    refreshCounts: function () {
      return api.get('/backup').then(function (b) { window.TUTOR_DATA.meta.db_rows = b.total; App.refresh(); });
    },
    // Hàng chờ duyệt cho badge, đồng hồ, Hộp duyệt, Hôm nay: mọi thread + t.summary của mục đang chờ.
    refreshQueue: function () {
      var seq = ++queueSeq;
      return api.get('/threads').then(function (rows) {
        // shortcut: state chỉ tải cho 20 mục chờ đầu (mục sau hiện "—"); nâng lên khi /api/threads trả sẵn số mục.
        var aw = rows.filter(function (t) { return t.status === 'awaiting_review'; }).slice(0, SUMMARY_MAX);
        return Promise.all(aw.map(summarize)).then(function (vs) {
          if (seq !== queueSeq) return rows;  // một lần tải mới hơn đã chạy
          aw.forEach(function (t, i) { t.summary = vs[i]; });
          var sig = JSON.stringify(rows);
          if (sig === queueSig) return rows;  // không đổi: không vẽ lại tab
          queueSig = sig;
          window.TUTOR_DATA.checkpoints.threads = rows;
          if (window.App && App.started) App.refresh();
          return rows;
        });
      });
    },
    // Nạp dữ liệu shell cần trước App.start(); tab tự gọi api khi render.
    boot: function () {
      // Đồng hồ chi phí không được chặn app khởi động.
      var cost = api.get('/logs/cost?month=' + today().slice(0, 7)).catch(function () { return null; });
      return Promise.all([api.get('/health'), api.get('/backup'), cost]).then(function (r) {
        window.TUTOR_DATA = { meta: { today: today(), db_rows: r[1].total, health: r[0], cost: r[2] }, db: {}, checkpoints: { threads: [] }, settings: {} };
        return TutorApi.refreshQueue().catch(function () { /* Hộp duyệt tự báo lỗi tải */ });
      });
    }
  };
})();
