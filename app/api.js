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
  window.api = {
    get: function (path) { return request('GET', path); },
    send: function (method, path, body) { return request(method, path, body); }
  };
})();
