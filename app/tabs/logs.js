/* Nhật ký & chi phí (P2-T08): chi phí tháng so với ngân sách, theo agent, theo buổi, nhật ký lời gọi LLM + chi tiết.
   Đọc /api/logs (llm.jsonl). Params: agent, graph, student, thread. Chất lượng agent, độ ổn định prompt làm ở P4 (P4-T10). */
(function () {
  'use strict';
  if (!window.App) return;

  // = meta.agents trong bản mẫu (docs/prototype/contract.md §3).
  var AGENTS = [
    ['01', 'Ingest', 'Chép LaTeX, cắt bài, tách bước'], ['02', 'Grader', 'Chấm theo rubric; sinh rubric từ lời giải mẫu'],
    ['03', 'Diagnoser', 'Tìm bước sai, gắn mã lỗi + KC (2 lượt)'], ['04', 'Verifier', 'Phản biện từng lỗi, không thấy lý luận của 03'],
    ['05', 'Profiler', 'Code tính Elo, streak, lỗi lặp; LLM viết knowledge_state'], ['06', 'Tagger', 'Top-5 KC mỗi bước, GV chọn'],
    ['07', 'Difficulty', 'So cặp bài 2 chiều → Bradley-Terry'], ['08', 'Recommender', 'Kiểm tra bài code đã chọn, viết lý do 1 dòng'],
    ['09', 'Reporter', 'Viết report tháng, mỗi câu kèm fact_id']
  ];
  var GRAPHS = ['G1', 'G2', 'G3', 'G4', 'G5'];
  var RESULT_KIND = { ok: 'ok', retry: 'warn', schema_error: 'danger', error: 'danger' };
  var PAGE = 50, PAGE_SES = 6;
  var S = { token: 0 };

  App.registerTab('logs', { title: 'Nhật ký & chi phí', render: render });

  function arr(x) { return Array.isArray(x) ? x : []; }
  function put(el) { el.replaceChildren.apply(el, Array.prototype.slice.call(arguments, 1).flat(Infinity).filter(function (x) { return x != null && x !== false; })); return el; }
  function pad2(x) { return String(x).padStart(2, '0'); }

  function render(root, ctx) {
    var token = ++S.token, h = ctx.ui.h;
    var month = ((ctx.data.meta || {}).today || new Date().toISOString().slice(0, 10)).slice(0, 7);
    root.append(h('p', { class: 'muted' }, 'Đang tải nhật ký…'));
    return api.get('/logs/cost?month=' + month).then(function (c) {
      if (token !== S.token) return;
      if (ctx.data.meta) { ctx.data.meta.cost = c; ctx.refresh(); }
      root.replaceChildren(view(ctx, c, token));
    }, function (e) {
      if (token !== S.token) return;
      root.replaceChildren(ctx.ui.pageHead({}), failBox(ctx, e, 'chi phí LLM'));
    });
  }

  function failBox(ctx, e, what) {
    var U = ctx.ui, h = U.h;
    return h('div', { class: 'callout callout-crit', role: 'alert' }, h('strong', null, 'Không tải được ' + what + '.'),
      h('p', { class: 'mono small' }, (e && e.message) || String(e)), h('div', null, U.button('Thử lại', ctx.rerender, { size: 'sm' })));
  }

  function view(ctx, c, token) {
    var U = ctx.ui, h = U.h, f = U.fmt, P = c.prices || {};
    var mLabel = 'tháng ' + f.month(c.month);
    var agentName = function (id) { var a = AGENTS.find(function (x) { return x[0] === id; }); return a ? a[1] : ''; };
    var agentChip = function (id) { return U.chip((id + ' ' + agentName(id)).trim(), /^0[1-9]$/.test(id) ? 'agent' + id : 'neutral'); };
    var stuParam = ctx.params.student ? String(ctx.params.student) : '';
    var F = {
      agent: ctx.params.agent ? pad2(ctx.params.agent) : '', graph: ctx.params.graph || '', thread: ctx.params.thread || '',
      student: /^\d+$/.test(stuParam) ? 'HS-' + pad2(stuParam) : stuParam.toUpperCase()
    };
    var secs = {};
    var section = function (id, title, annot, lead) {
      var el = h('section', { class: 'section lg-sec', id: 'lg-' + id },
        h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? U.annot(annot) : null)),
        lead ? h('p', { class: 'muted small' }, lead) : null);
      secs[id] = el;
      return el;
    };
    var scrollTo = function (id) {
      var el = secs[id]; if (!el || !el.isConnected) return;
      el.scrollIntoView({ block: 'start', behavior: 'smooth' });
      el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
    };
    var formula = function (x) {
      return '(' + [[x.input_tokens, P.input_per_mtok], [x.output_tokens, P.output_per_mtok], [x.cache_read_tokens, P.cache_read_per_mtok],
        [x.cache_write_tokens, P.cache_write_per_mtok]].map(function (p) { return f.int(p[0] || 0) + ' × ' + p[1]; }).join(' + ') + ') ÷ 1 000 000';
    };
    var page = h('div', { class: 'stack' });

    page.append(U.pageHead({
      lead: 'Mỗi lời gọi LLM được ghi một dòng vào data/logs/llm.jsonl (ngoài tutor.db): agent, prompt_version, token, thời gian, kết quả. Chi phí tính lúc đọc = token × đơn giá giả định.',
      annot: ['file:llm.jsonl', 'NFR10']
    }));

    /* ---------- 1. Chi phí tháng ---------- */
    var kpi = section('kpi', 'Chi phí ' + mLabel, ['file:llm.jsonl']);
    var budget = c.budget_usd, pct = c.pct;
    var g1 = arr(c.by_session).filter(function (s) { return s.graph === 'G1'; });
    var g1Usd = g1.reduce(function (s, x) { return s + x.usd; }, 0), g1N = g1.reduce(function (s, x) { return s + x.calls; }, 0);
    var card = function (label, value, sub, whyEl, extra) {
      return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label, whyEl || null, U.prov('code')),
        h('span', { class: 'kpi-value' }, value), extra || null, h('span', { class: 'kpi-sub' }, sub));
    };
    kpi.append(h('div', { class: 'grid cols-2' },
      card('Chi phí ' + mLabel + ' / ngân sách (giả định)', f.usd(c.total_usd),
        (budget ? 'trên ' + f.usd(budget) + ' · ' + f.pct(pct, 1) + ' · ' : 'chưa đặt ngân sách · ') + f.int(c.calls) + ' lời gọi',
        U.why(function () {
          return h('div', { class: 'stack' },
            h('p', null, 'Cộng chi phí của ' + f.int(c.calls) + ' lời gọi có giờ (UTC) trong ' + f.month(c.month) + ' = ' + f.usd(c.total_usd) + '.'),
            h('p', { class: 'mono small' }, 'mỗi lời gọi = (vào × ' + P.input_per_mtok + ' + ra × ' + P.output_per_mtok + ' + đọc cache × ' + P.cache_read_per_mtok + ' + ghi cache × ' + P.cache_write_per_mtok + ') ÷ 1 000 000'),
            budget ? h('p', null, f.usd(c.total_usd) + ' ÷ ' + f.usd(budget) + ' = ' + f.pct(pct, 1) + '. Ngân sách: budget_usd_month trong data/settings.json.') : h('p', null, 'Chưa đặt ngân sách.'));
        }),
        budget ? U.bar(c.total_usd, budget, { kind: pct >= 1 ? 'danger' : pct >= 0.8 ? 'warn' : 'accent' }) : null),
      card('TB mỗi buổi G1', g1.length ? f.usd(g1Usd / g1.length) : '—',
        g1.length + ' buổi có lời gọi trong ' + mLabel + ' · TB ' + (g1.length ? (g1N / g1.length).toFixed(1) : '—') + ' lời gọi / buổi',
        U.why(function () {
          return h('div', { class: 'stack' }, h('p', null, 'Cộng chi phí theo thread_id của các buổi G1 có lời gọi trong tháng, chia số buổi.'),
            h('p', { class: 'mono small' }, f.usd(g1Usd) + ' ÷ ' + g1.length + ' buổi = ' + (g1.length ? f.usd(g1Usd / g1.length) : '—')));
        }))));
    if (budget && pct >= 1) {
      kpi.append(h('div', { class: 'callout callout-crit', role: 'status' }, h('p', null, h('b', null, 'Đã vượt ngân sách ' + mLabel + ' (' + f.pct(pct, 1) + '). '),
        'App không chặn lời gọi nào; thầy/cô tự quyết có chạy tiếp không.')));
    } else if (budget && pct >= 0.8) {
      kpi.append(h('div', { class: 'callout callout-warn', role: 'status' }, h('p', null, h('b', null, 'Đã dùng ' + f.pct(pct, 1) + ' ngân sách ' + mLabel + ' '),
        '(ngưỡng cảnh báo 80%). App không chặn lời gọi.')));
    }
    kpi.append(h('div', { class: 'callout callout-warn' },
      h('p', null, h('b', null, 'Đơn giá giả định, không phải bảng giá thật. '),
        'Vào $' + P.input_per_mtok + ' / 1M token · ra $' + P.output_per_mtok + ' / 1M · đọc cache $' + P.cache_read_per_mtok + ' / 1M · ghi cache $' + P.cache_write_per_mtok + ' / 1M. ',
        'Đổi đơn giá trong data/settings.json (price_assumption): mọi con số tính lại ngay, nhật ký không đổi.')));
    page.append(kpi);

    /* ---------- 2. Theo agent / theo buổi ---------- */
    var cost = section('cost', 'Chi phí theo agent và theo buổi', ['file:llm.jsonl'], 'Chỉ tính ' + mLabel + '.');
    if (!c.calls) {
      cost.append(U.empty('Chưa có lời gọi LLM nào trong ' + mLabel + '.'));
    } else {
      var by = c.by_agent || {};
      var max = Math.max.apply(null, [0.001].concat(Object.keys(by).map(function (k) { return by[k].usd; })));
      cost.append(h('div', { class: 'stack' },
        h('h3', null, 'Theo agent'),
        h('div', { class: 'lg-bars' }, AGENTS.map(function (a) {
          var x = by[a[0]];
          return h('div', { class: 'lg-bar-row' }, h('div', { class: 'lg-bar-label' }, agentChip(a[0]), h('span', { class: 'small muted' }, a[2])),
            h('div', { class: 'lg-bar-line' }, U.bar(x ? x.usd : 0, max), h('span', { class: 'num small' }, f.usd(x ? x.usd : 0)),
              h('span', { class: 'num small muted lg-n' }, f.int(x ? x.calls : 0) + ' lời gọi')));
        }))));
      var showAll = false, sesBox = h('div', { class: 'stack' });
      var drawSes = function () {
        var rows = arr(c.by_session), view = showAll ? rows : rows.slice(0, PAGE_SES);
        put(sesBox,
          h('h3', null, 'Theo buổi (thread)'),
          h('div', { class: 'lg-nowrap' }, U.table({
            columns: [
              { label: 'HS', render: function (s) { return s.student_code ? h('span', { class: 'mono' }, s.student_code) : h('span', { class: 'muted' }, '—'); } },
              { label: 'Graph', render: function (s) { return s.graph ? U.chip(s.graph, s.graph) : '—'; } },
              { label: 'thread_id', render: function (s) { return h('span', { class: 'mono small' }, s.thread_id); } },
              { label: 'Số lời gọi', align: 'right', render: function (s) { return f.int(s.calls); } },
              { label: 'Chi phí', align: 'right', render: function (s) { return f.usd(s.usd); } },
              { label: '', render: function (s) { return U.button('Lọc nhật ký', function () { setFilter({ thread: s.thread_id }); }, { kind: 'ghost', size: 'sm' }); } }
            ],
            rows: view, empty: 'Không có buổi nào trong ' + mLabel + '.'
          })),
          h('div', { class: 'spread small' },
            h('span', { class: 'muted' }, rows.length + ' thread · tổng ' + f.usd(rows.reduce(function (s, x) { return s + x.usd; }, 0)) + ' · ', U.prov('code'), ' cộng từ llm.jsonl theo thread_id'),
            rows.length > PAGE_SES ? U.button(showAll ? 'Thu gọn' : 'Xem tất cả ' + rows.length + ' thread', function () { showAll = !showAll; drawSes(); }, { kind: 'ghost', size: 'sm' }) : null));
      };
      drawSes();
      cost.append(sesBox);
    }
    page.append(cost);

    /* ---------- 3. Nhật ký lời gọi ---------- */
    var logSec = section('log', 'Nhật ký lời gọi LLM', ['file:llm.jsonl', 'UNTRUSTED INPUT'],
      'Mỗi dòng = 1 dòng JSON trong data/logs/llm.jsonl do tutor/llm.py ghi, kể cả lần gọi lại. Mới nhất ở trên.');
    var logBox = h('div', { class: 'stack' }), q = { token: 0, items: [], total: 0 };
    logSec.append(logBox);
    page.append(logSec);

    function query(offset) {
      var p = new URLSearchParams({ offset: offset, limit: PAGE });
      Object.keys(F).forEach(function (k) { if (F[k]) p.set(k, F[k]); });
      return api.get('/logs/calls?' + p.toString());
    }
    function load() {
      var t = ++q.token;
      put(logBox, filters(), h('p', { class: 'small muted' }, 'Đang tải…'));
      query(0).then(function (r) {
        if (t !== q.token || token !== S.token) return;
        q.items = r.items; q.total = r.total; drawLog();
      }, function (e) { if (t === q.token) put(logBox, filters(), failBox(ctx, e, 'nhật ký lời gọi')); });
    }
    function more(btn) {
      var t = q.token;
      btn.disabled = true; btn.textContent = 'Đang tải…';
      query(q.items.length).then(function (r) {
        if (t !== q.token || token !== S.token) return;
        q.items = q.items.concat(r.items); q.total = r.total; drawLog();
      }, function (e) { if (t === q.token) put(logBox, filters(), failBox(ctx, e, 'nhật ký lời gọi')); });
    }
    function setFilter(next) {
      F = Object.assign({ agent: '', graph: '', student: '', thread: '' }, next || {});
      load(); scrollTo('log');
    }
    function select(label, key, options) {
      if (F[key] && !options.some(function (o) { return o[0] === F[key]; })) options.push([F[key], F[key]]);
      var s = h('select', { 'aria-label': label }, options.map(function (o) { return h('option', { value: o[0], selected: F[key] === o[0] }, o[1]); }));
      s.addEventListener('change', function () { F[key] = s.value; load(); });
      return h('label', { class: 'field' }, h('span', null, label), s);
    }
    function filters() {
      var ses = arr(c.by_session);
      var codes = Array.from(new Set(ses.map(function (s) { return s.student_code; }).filter(Boolean))).sort();
      var active = F.agent || F.graph || F.student || F.thread;
      return [
        h('div', { class: 'lg-filters' },
          select('Agent', 'agent', [['', 'Tất cả agent']].concat(AGENTS.map(function (a) { return [a[0], a[0] + ' ' + a[1]]; }))),
          select('Graph', 'graph', [['', 'Tất cả graph']].concat(GRAPHS.map(function (g) { return [g, g]; }))),
          select('Học sinh (mã)', 'student', [['', 'Tất cả']].concat(codes.map(function (x) { return [x, x]; }))),
          select('Thread', 'thread', [['', 'Tất cả thread']].concat(ses.map(function (s) { return [s.thread_id, s.thread_id]; })))),
        active ? h('div', { class: 'callout callout-info' },
          h('div', { class: 'spread' }, h('span', null, 'Đang lọc: ', [F.agent && 'agent ' + F.agent, F.graph, F.student, F.thread && 'thread ' + F.thread].filter(Boolean).join(' · ')),
            U.button('Bỏ lọc', function () { setFilter({}); }, { kind: 'secondary', size: 'sm' }))) : null
      ];
    }
    function drawLog() {
      var active = F.agent || F.graph || F.student || F.thread;
      if (!q.total && !active) {
        put(logBox, U.empty('Chưa có lời gọi LLM nào: data/logs/llm.jsonl còn trống. Nộp bài ở Buổi học để chạy G1; mỗi lời gọi sẽ hiện ở đây.',
          U.button('Nộp bài', function () { ctx.nav('session', { step: 1 }); }, { kind: 'secondary' })));
        return;
      }
      put(logBox, filters(),
        h('div', { class: 'row small' }, h('b', null, f.int(q.total) + ' lời gọi'), h('span', { class: 'muted' }, active ? 'khớp bộ lọc' : 'trong nhật ký')),
        h('div', { class: 'lg-nowrap' }, U.table({
          columns: [
            { label: 'Giờ (UTC)', render: function (x) { return f.dt(x.ts); } },
            { label: 'Agent', render: function (x) { return agentChip(x.agent); } },
            { label: 'Graph', render: function (x) { return x.graph ? U.chip(x.graph, x.graph) : '—'; } },
            { label: 'Thread', render: function (x) { return h('span', { class: 'mono small' }, x.thread_id || '—'); } },
            { label: 'HS (mã)', render: function (x) { return x.student_code ? h('span', { class: 'mono' }, x.student_code) : h('span', { class: 'muted' }, '—'); } },
            { label: 'prompt_version', render: function (x) { return h('span', { class: 'mono small' }, x.prompt_version); } },
            { label: 'Model', render: function (x) { return h('span', { class: 'mono small' }, x.model); } },
            { label: 'Token vào / ra / cache', align: 'right', render: function (x) { return f.int(x.input_tokens) + ' / ' + f.int(x.output_tokens) + ' / ' + f.int((x.cache_read_tokens || 0) + (x.cache_write_tokens || 0)); } },
            { label: 'Thời gian', align: 'right', render: function (x) { return f.ms(x.ms); } },
            { label: 'Chi phí', align: 'right', render: function (x) { return f.usd(x.cost_usd); } },
            { label: 'Kết quả', render: function (x) { return U.chip(x.result, RESULT_KIND[x.result] || 'neutral'); } },
            { label: '', render: function (x) { return U.button('Xem chi tiết', function () { openCall(x); }, { kind: 'ghost', size: 'sm' }); } }
          ],
          rows: q.items,
          rowClass: function (x) { return x.result !== 'ok' ? 'lg-row-bad' : null; },
          empty: 'Không có lời gọi nào khớp bộ lọc.'
        })),
        q.total > q.items.length ? h('div', { class: 'row' }, U.button('Xem thêm ' + Math.min(PAGE, q.total - q.items.length) + ' dòng', function (ev, b) { more(b); }, { kind: 'secondary', size: 'sm' }),
          h('span', { class: 'small muted' }, 'đang hiện ' + q.items.length + ' / ' + f.int(q.total))) : null);
    }

    /* ---------- 4. Chi tiết lời gọi (drawer) ---------- */
    function pretty(s) { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return String(s); } }
    function openCall(x) {
      ctx.drawer({
        title: 'Lời gọi #' + x.id + ' · ' + x.agent + ' ' + agentName(x.agent) + ' · ' + f.dt(x.ts),
        body: function (el, dr) {
          el.append(
            U.annot(['agent:' + x.agent, x.graph, 'file:llm.jsonl']),
            U.kv([
              ['Agent', agentChip(x.agent)],
              ['Graph · thread', h('span', null, x.graph ? U.chip(x.graph, x.graph) : '—', ' ', h('span', { class: 'mono small' }, x.thread_id || '—'))],
              ['HS (mã gửi API)', x.student_code ? h('span', { class: 'mono' }, x.student_code) : 'không có'],
              ['prompt_version', h('span', { class: 'mono' }, x.prompt_version)], ['Model', h('span', { class: 'mono' }, x.model)],
              ['Token vào / ra', f.int(x.input_tokens) + ' / ' + f.int(x.output_tokens)],
              ['Token cache đọc / ghi', f.int(x.cache_read_tokens) + ' / ' + f.int(x.cache_write_tokens)],
              ['Thời gian', f.ms(x.ms)],
              ['Chi phí', h('span', { class: 'row' }, f.usd(x.cost_usd) + ' (giả định)',
                U.why(function () { return h('p', { class: 'mono small' }, formula(x) + ' = ' + f.usd(x.cost_usd)); }))],
              ['Kết quả', U.chip(x.result, RESULT_KIND[x.result] || 'neutral')],
              ['Che tên', x.name_masked ? 'có: tên học sinh đã thay bằng mã trước khi gửi' : 'không gặp tên nào cần che'],
              x.error ? ['Lỗi', h('span', { class: 'mono small' }, x.error)] : null
            ]),
            x.result === 'retry' ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Lỗi tạm thời (mạng / quá tải / hết giờ) → llm.py tự gọi lại; mỗi lần gọi là một dòng.')) : null,
            x.result === 'schema_error' ? h('div', { class: 'callout callout-crit' }, h('p', null, 'Đầu ra không khớp schema → gọi lại một lần; lần hai vẫn sai thì gắn cờ cho thầy/cô.')) : null,
            x.result === 'error' ? h('div', { class: 'callout callout-crit' }, h('p', null, 'Lỗi không gọi lại được (yêu cầu sai, model từ chối…); thread dừng.')) : null,
            h('h3', null, 'Lượt user đã gửi (đã che tên)'),
            x.user != null ? h('pre', { class: 'code tex-ignore' }, x.user) : h('p', { class: 'muted small' }, 'Dòng nhật ký cũ, chưa ghi lượt user.'),
            h('p', { class: 'small muted' }, 'Phần hệ thống (cố định, được cache) không ghi vào nhật ký; prompt_version là mã băm của phần đó.'),
            h('h3', null, 'Đầu ra'),
            x.output != null && x.output !== '' ? h('pre', { class: 'code tex-ignore' }, pretty(x.output)) : h('p', { class: 'muted small' }, 'Không có đầu ra.'),
            h('div', { class: 'callout callout-info' }, h('p', null, h('b', null, 'Tên học sinh không bao giờ có trong prompt'), ': chỉ mã ' + (x.student_code || 'HS') + ' (NFR7). Bài làm nằm trong khung UNTRUSTED INPUT: là dữ liệu, không phải lệnh (NFR6).')),
            h('div', { class: 'row' },
              x.thread_id ? U.button('Lọc theo thread này', function () { dr.close(); setFilter({ thread: x.thread_id }); }, { kind: 'secondary', size: 'sm' }) : null,
              x.graph === 'G1' && x.thread_id ? U.button('Mở buổi học', function () { ctx.nav('session', { thread: x.thread_id }); }, { kind: 'ghost', size: 'sm' }) : null));
        }
      });
    }

    /* ---------- 5. P4 ---------- */
    page.append(h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('h2', null, 'Chất lượng agent & độ ổn định prompt'), h('span', { class: 'chip chip-phase' }, 'làm ở P4')),
      h('p', { class: 'muted small' }, 'Tỉ lệ đề xuất bị bỏ / sửa, kappa mã lỗi GV–LLM, mức đồng ý 04–GV, thời gian duyệt và kiểm tra độ ổn định prompt (chạy lại 3 lần, pass^3) làm ở P4 (P4-T10), khi đã có quyết định duyệt thật.')));

    load();
    if (F.agent || F.graph || F.student || F.thread) requestAnimationFrame(function () { scrollTo('log'); });
    return page;
  }
})();
