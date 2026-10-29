/* logs — Nhật ký & chi phí (IA §3.10; NFR3, NFR8, NFR10, spec §12). Params: thread, agent, graph, student, section. */
(function () {
  'use strict';
  var arr = function (x) { return Array.isArray(x) ? x : []; };
  var sum = function (a, fn) { return arr(a).reduce(function (s, x) { return s + (+fn(x) || 0); }, 0); };
  var monthOf = function (ts) { return String(ts || '').slice(0, 7); };
  var tokOf = function (c) { return (c.tokens_in || 0) + (c.tokens_out || 0) + (c.cache_read_tokens || 0); };
  var dm = function (d) { var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(d || '')); return m ? m[2] + '/' + m[1] : String(d || ''); };
  // replaceChildren() would print "null" for skipped optional parts.
  var fill = function (el) { el.replaceChildren.apply(el, Array.prototype.slice.call(arguments, 1).filter(function (x) { return x != null && x !== false; })); };
  var PAGE_LOG = 10, PAGE_SES = 6, PAGE_DEC = 8;
  var RESULT_KIND = { ok: 'ok', retry: 'warn', schema_error: 'danger' };
  // api_payload_samples has no 05 / 07 entry; their prompt shape comes from diagrams 05 and 07.
  var FALLBACK_PROMPT = {
    '05': {
      cached_system: 'Bạn là 05 Profiler. Chỉ viết knowledge_state ≤ 150 từ từ số liệu do code tính (θ theo KC, Δθ, mã lỗi lặp / mới / hết). Không tự chấm mức thành thạo.',
      data_title: 'Số liệu buổi (code tính sẵn, chỉ mã HS)',
      untrusted: '<DATA student="{code}">\n[θ trước → sau theo KC · Δθ so với buổi trước · mã lỗi lặp lại / mới / đã hết]\n</DATA>',
      schema: '{"knowledge_state":"str (≤ 150 từ)"}'
    },
    '07': {
      cached_system: 'Bạn là 07 Difficulty. Hai bài cùng KC: bài nào khó hơn với HS lớp 8–9? Trả "a" hoặc "b" kèm lý do. Mỗi cặp hỏi cả (A, B) và (B, A).',
      data_title: 'Đề bài A + đề bài B (ngân hàng, không có bài làm HS)',
      untrusted: null,
      schema: '{"harder":"a|b","reason":"str"}'
    }
  };

  App.registerTab('logs', {
    title: 'Nhật ký & chi phí',
    render: function (root, ctx) {
      var U = ctx.ui, h = U.h, f = U.fmt, M = ctx.data, D = M.db || {}, S = M.settings || {}, L = ctx.lookup;
      var meta = M.meta || {}, agents = arr(meta.agents);
      var today = meta.today || '2026-10-21', curM = today.slice(0, 7);
      var prevM = arr(meta.months).filter(function (m) { return m < curM; }).pop() || '2026-09';
      var price = S.price_assumption || {};
      var log = function () { return arr((M.files || {}).llm_log); };
      var agentName = function (id) { var a = agents.find(function (x) { return x.id === id; }); return a ? a.name : ''; };
      var agentChip = function (id) { return U.chip(id + ' ' + agentName(id), 'agent' + id); };
      var mLabel = function (m) { return 'tháng ' + (+String(m).slice(5, 7)); };
      var pct1 = function (x) { return x == null || isNaN(x) ? '—' : (x * 100).toFixed(1) + '%'; };
      var stuCode = function (p) {
        if (!p) return '';
        if (/^HS-\d+$/i.test(p)) return p.toUpperCase();
        var s = L.student(p); return s ? L.studentCode(s) : '';
      };
      var padAgent = function (a) { return a ? String(a).padStart(2, '0') : ''; };

      var F = { agent: padAgent(ctx.params.agent), graph: ctx.params.graph || '', student: stuCode(ctx.params.student), thread: ctx.params.thread || '' };
      var shownLog = PAGE_LOG;
      var secs = {};
      var section = function (id, title, annot, lead) {
        var el = h('section', { class: 'section lg-sec', id: 'lg-' + id, 'data-sec': id },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? U.annot(annot) : null)),
          lead ? h('p', { class: 'muted small' }, lead) : null);
        secs[id] = el; return el;
      };
      var scrollTo = function (id) {
        var el = secs[id]; if (!el) return;
        el.scrollIntoView({ block: 'start', behavior: 'smooth' });
        el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
      };

      /* ---------- page head ---------- */
      root.append(U.pageHead({
        lead: 'Mỗi lời gọi LLM được ghi vào data/logs/llm.jsonl (ngoài tutor.db, để giữ đúng một nơi ghi): agent, prompt_version, token, thời gian, chi phí. Chất lượng agent đo từ quyết định duyệt của thầy/cô.',
        annot: ['file:llm.jsonl', 'NFR10'],
        actions: [
          U.button('Đổi ngân sách', function () { ctx.nav('ops', { section: 'settings' }); }, { kind: 'secondary', title: 'Cài đặt nằm một chỗ: Vận hành › Cài đặt' }),
          U.button('Xuất CSV chi phí', exportCsv, { kind: 'secondary', noAutoclick: true })
        ]
      }));

      /* ---------- 1. KPI ---------- */
      var kpi = section('kpi', 'Chi phí', ['file:llm.jsonl', 'agent:01', 'agent:09']);
      (function () {
        var c10 = log().filter(function (c) { return monthOf(c.ts) === curM; });
        var c9 = log().filter(function (c) { return monthOf(c.ts) === prevM; });
        var older = log().filter(function (c) { return monthOf(c.ts) < prevM; });
        var s10 = sum(c10, function (c) { return c.cost_usd; }), s9 = sum(c9, function (c) { return c.cost_usd; }), sOld = sum(older, function (c) { return c.cost_usd; });
        var budget = S.budget_usd_month;
        var committed = arr(D.session).filter(function (s) { return s.status === 'committed'; });
        var g1 = committed.map(function (s) { var cs = log().filter(function (c) { return c.thread_id === s.thread_id; }); return { n: cs.length, usd: sum(cs, function (c) { return c.cost_usd; }) }; });
        var g1Usd = sum(g1, function (x) { return x.usd; }), g1N = sum(g1, function (x) { return x.n; });
        var avg = committed.length ? g1Usd / committed.length : null;
        var olderMonths = Array.from(new Set(older.map(function (c) { return monthOf(c.ts); }))).sort();
        var olderFiles = function (g) { return new Set(older.filter(function (c) { return c.graph === g; }).map(function (c) { return c.thread_id; })).size; };
        var byGraph = function (calls) {
          var o = {}; calls.forEach(function (c) { o[c.graph] = (o[c.graph] || 0) + (+c.cost_usd || 0); });
          return h('ul', { class: 'lg-list' }, Object.keys(o).sort().map(function (g) { return h('li', null, U.chip(g, g), ' ', f.usd(o[g])); }));
        };
        var card = function (label, value, sub, whyEl, extra) {
          return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label, whyEl || null, U.prov('code')), h('span', { class: 'kpi-value' }, value), extra || null, h('span', { class: 'kpi-sub' }, sub));
        };
        kpi.append(h('div', { class: 'grid cols-4' },
          card('Chi phí ' + mLabel(curM) + ' / ngân sách', f.usd(s10),
            (budget != null ? 'trên ' + f.usd(budget) + ' · ' + f.pct(s10 / budget) + ' · ' : '') + f.int(c10.length) + ' lời gọi',
            U.why(function () {
              return h('div', { class: 'stack' }, h('p', null, 'Tổng cost_usd của ' + f.int(c10.length) + ' lời gọi có giờ trong ' + f.month(curM) + ' = ' + f.usd(s10) + '.'),
                byGraph(c10),
                budget != null ? h('p', null, f.usd(s10) + ' ÷ ' + f.usd(budget) + ' = ' + f.pct(s10 / budget) + '. Ngân sách lấy từ Vận hành › Cài đặt (chưa chốt).') : h('p', null, 'Chưa đặt ngân sách.'));
            }),
            budget ? U.bar(s10, budget, { kind: s10 > budget * 0.8 ? 'warn' : 'accent' }) : null),
          card('Chi phí ' + mLabel(prevM), f.usd(s9), f.int(c9.length) + ' lời gọi · ' + f.int(sum(c9, tokOf)) + ' token',
            U.why(function () { return h('div', { class: 'stack' }, h('p', null, 'Tổng cost_usd của ' + f.int(c9.length) + ' lời gọi trong ' + f.month(prevM) + '.'), byGraph(c9)); })),
          card('TB mỗi buổi G1', f.usd(avg), committed.length + ' buổi đã ghi · TB ' + (committed.length ? (g1N / committed.length).toFixed(1) : '—') + ' lời gọi / buổi',
            U.why(function () {
              return h('div', { class: 'stack' }, h('p', null, 'Mọi lời gọi có thread_id của một buổi đã ghi (01 ×1, 02 ×số bài, 03 ×2 lượt mỗi bài, 04 ×số lỗi đề xuất, 05 ×1).'),
                h('p', { class: 'mono small' }, f.usd(g1Usd) + ' ÷ ' + committed.length + ' buổi = ' + f.usd(avg)));
            })),
          card('Dựng ngân hàng (' + olderMonths.map(f.month).join(', ') + ')', f.usd(sOld), 'G2 cho ' + olderFiles('G2') + ' file .tex · G3 cho ' + olderFiles('G3') + ' file · ngoài 2 tháng mẫu',
            U.why(function () { return h('div', { class: 'stack' }, h('p', null, f.int(older.length) + ' lời gọi trước ' + f.month(prevM) + ': gắn KC + rubric (06, 02) và so cặp độ khó (07).'), byGraph(older)); }))));
        kpi.append(h('div', { class: 'callout callout-warn' },
          h('p', null, h('b', null, 'Đơn giá giả định — bản nháp. '), 'Vào $' + price.input_per_mtok + ' / 1M token · ra $' + price.output_per_mtok + ' / 1M · đọc cache $' + price.cache_read_per_mtok + ' / 1M. ',
            'Chi phí một lời gọi = (vào × ' + price.input_per_mtok + ' + ra × ' + price.output_per_mtok + ' + cache × ' + price.cache_read_per_mtok + ') ÷ 1 000 000. Không phải bảng giá thật.')));
      })();
      root.append(kpi);

      /* ---------- 2. Chi phí theo agent / theo buổi ---------- */
      var cost = section('cost', 'Chi phí theo agent và theo buổi', ['file:llm.jsonl', 'table:session'],
        'Hai tháng mẫu đặt cạnh nhau. Agent 07 chỉ chạy khi xếp độ khó (G3), nên dồn vào tháng có lô bài mới.');
      (function () {
        var by = function (m) { var o = {}; log().forEach(function (c) { if (monthOf(c.ts) === m) { var x = o[c.agent] || (o[c.agent] = { usd: 0, n: 0 }); x.usd += +c.cost_usd || 0; x.n++; } }); return o; };
        var a9 = by(prevM), a10 = by(curM);
        var max = Math.max.apply(null, [0.01].concat(agents.map(function (a) { return Math.max((a9[a.id] || {}).usd || 0, (a10[a.id] || {}).usd || 0); })));
        var line = function (lab, x, cls) {
          return h('div', { class: 'lg-bar-line ' + cls }, h('span', { class: 'small muted' }, lab), U.bar(x ? x.usd : 0, max, { kind: cls === 'lg-m9' ? 'm9' : 'accent' }),
            h('span', { class: 'num small' }, x ? f.usd(x.usd) : '$0.00'), h('span', { class: 'num small muted lg-n' }, x ? f.int(x.n) + ' lời gọi' : '0'));
        };
        cost.append(h('div', { class: 'stack' },
          h('div', { class: 'row small' }, h('span', { class: 'lg-sw lg-m9' }), mLabel(prevM), h('span', { class: 'lg-sw lg-m10' }), mLabel(curM), h('span', { class: 'muted' }, '· thang chung: ' + f.usd(max) + ' = đầy thanh')),
          h('div', { class: 'lg-bars' }, agents.map(function (a) {
            return h('div', { class: 'lg-bar-row' }, h('div', { class: 'lg-bar-label' }, agentChip(a.id), h('span', { class: 'small muted' }, a.role_vi)),
              h('div', { class: 'lg-bar-pair' }, line('T' + (+prevM.slice(5)), a9[a.id], 'lg-m9'), line('T' + (+curM.slice(5)), a10[a.id], 'lg-m10')));
          }))));

        var sesMonth = curM, showAll = false;
        var sesBox = h('div', { class: 'stack' });
        var drawSes = function () {
          var rows = arr(D.session).filter(function (s) { return monthOf(s.held_on) === sesMonth; }).map(function (s) {
            var cs = log().filter(function (c) { return c.thread_id === s.thread_id; });
            return { s: s, n: cs.length, tok: sum(cs, tokOf), usd: sum(cs, function (c) { return c.cost_usd; }) };
          }).sort(function (a, b) { return a.s.held_on < b.s.held_on ? 1 : a.s.held_on > b.s.held_on ? -1 : b.s.id - a.s.id; });
          var tot = sum(rows, function (r) { return r.usd; });
          var view = showAll ? rows : rows.slice(0, PAGE_SES);
          fill(sesBox,
            h('div', { class: 'spread' }, h('h3', null, 'Theo buổi (G1)'),
              U.segmented([{ id: prevM, label: f.month(prevM) }, { id: curM, label: f.month(curM) }], sesMonth, function (v) { sesMonth = v; showAll = false; drawSes(); })),
            h('div', { class: 'lg-nowrap' }, U.table({
              columns: [
                { label: 'Ngày học', render: function (r) { return f.date(r.s.held_on); } },
                { label: 'HS', render: function (r) { return h('span', { class: 'mono' }, L.studentCode(L.student(r.s.student_id))); } },
                { label: 'Trạng thái', render: function (r) { return U.status(r.s.status); } },
                { label: 'thread_id', render: function (r) { return h('span', { class: 'mono small' }, r.s.thread_id); } },
                { label: 'Số lời gọi', align: 'right', render: function (r) { return f.int(r.n); } },
                { label: 'Token', align: 'right', render: function (r) { return f.int(r.tok); } },
                { label: 'Chi phí', align: 'right', render: function (r) { return f.usd(r.usd); } },
                { label: '', render: function (r) { return U.button('Lọc nhật ký', function () { setFilter({ thread: r.s.thread_id }); }, { kind: 'ghost', size: 'sm' }); } }
              ],
              rows: view, empty: 'Không có buổi nào trong ' + f.month(sesMonth) + '.'
            })),
            h('div', { class: 'spread small' },
              h('span', { class: 'muted' }, rows.length + ' buổi · tổng ' + f.usd(tot) + ' · ', U.prov('code'), ' cộng từ llm.jsonl theo thread_id'),
              rows.length > PAGE_SES ? U.button(showAll ? 'Thu gọn' : 'Xem tất cả ' + rows.length + ' buổi', function () { showAll = !showAll; drawSes(); }, { kind: 'ghost', size: 'sm' }) : null));
        };
        drawSes();
        cost.append(sesBox);
      })();
      root.append(cost);

      /* ---------- 3. Nhật ký lời gọi LLM ---------- */
      var logSec = section('log', 'Nhật ký lời gọi LLM', ['file:llm.jsonl', 'UNTRUSTED INPUT'],
        'Mỗi dòng = 1 dòng JSON trong data/logs/llm.jsonl do tutor/llm.py ghi. Mới nhất ở trên.');
      var logBox = h('div', { class: 'stack' });
      logSec.append(logBox);
      root.append(logSec);

      function matches(c) {
        return (!F.agent || c.agent === F.agent) && (!F.graph || c.graph === F.graph) && (!F.thread || c.thread_id === F.thread) &&
          (!F.student || (F.student === '-' ? !c.student_code : c.student_code === F.student));
      }
      function filtered() { return log().filter(matches).sort(function (a, b) { return a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0; }); }
      function setFilter(next) {
        F = Object.assign({ agent: '', graph: '', student: '', thread: '' }, next || {});
        shownLog = PAGE_LOG; drawLog(); scrollTo('log');
      }
      function select(label, key, options) {
        var s = h('select', { 'aria-label': label }, options.map(function (o) { return h('option', { value: o[0], selected: F[key] === o[0] }, o[1]); }));
        s.addEventListener('change', function () { F[key] = s.value; shownLog = PAGE_LOG; drawLog(); });
        return h('label', { class: 'field' }, h('span', null, label), s);
      }
      function drawLog() {
        var all = log();
        var threadIds = Array.from(new Set(all.map(function (c) { return c.thread_id; })));
        var lastTs = {}; all.forEach(function (c) { if (!lastTs[c.thread_id] || c.ts > lastTs[c.thread_id]) lastTs[c.thread_id] = c.ts; });
        threadIds.sort(function (a, b) { return lastTs[a] < lastTs[b] ? 1 : -1; });
        if (F.thread && threadIds.indexOf(F.thread) < 0) threadIds.unshift(F.thread);
        var codes = arr(D.student).map(function (s) { return L.studentCode(s); });
        var rows = filtered(), view = rows.slice(0, shownLog);
        var nRetry = rows.filter(function (c) { return c.result === 'retry'; }).length, nSchema = rows.filter(function (c) { return c.result === 'schema_error'; }).length;
        var active = F.agent || F.graph || F.student || F.thread;
        fill(logBox,
          h('div', { class: 'lg-filters' },
            select('Agent', 'agent', [['', 'Tất cả agent']].concat(agents.map(function (a) { return [a.id, a.id + ' ' + a.name]; }))),
            select('Graph', 'graph', [['', 'Tất cả graph']].concat(['G1', 'G2', 'G3', 'G4', 'G5'].map(function (g) { var d = (meta.graphs || {})[g]; return [g, g + (d ? ' · ' + d.title_vi : '')]; }))),
            select('Học sinh (mã)', 'student', [['', 'Tất cả'], ['-', 'Không có HS (ngân hàng)']].concat(codes.map(function (c) { return [c, c]; }))),
            select('Thread', 'thread', [['', 'Tất cả thread (' + threadIds.length + ')']].concat(threadIds.map(function (t) { return [t, t]; })))),
          active ? h('div', { class: 'callout callout-info' },
            h('div', { class: 'spread' }, h('span', null, 'Đang lọc: ', [F.agent && 'agent ' + F.agent, F.graph, F.student && (F.student === '-' ? 'không có HS' : F.student), F.thread && 'thread ' + F.thread].filter(Boolean).join(' · ')),
              U.button('Bỏ lọc', function () { setFilter({}); }, { kind: 'secondary', size: 'sm' }))) : null,
          h('div', { class: 'row small' },
            h('b', null, f.int(rows.length) + ' lời gọi'), h('span', { class: 'muted' }, '· ' + f.int(sum(rows, tokOf)) + ' token · ' + f.usd(sum(rows, function (c) { return c.cost_usd; }))),
            nRetry ? U.chip('retry ' + nRetry, 'warn') : null, nSchema ? U.chip('schema_error ' + nSchema, 'danger') : null),
          h('div', { class: 'lg-nowrap' }, U.table({
            columns: [
              { label: 'Giờ', render: function (c) { return h('span', { class: 'nowrap' }, f.dt(c.ts)); } },
              { label: 'Agent', render: function (c) { return agentChip(c.agent); } },
              { label: 'Graph', render: function (c) { return U.chip(c.graph, c.graph); } },
              { label: 'Thread', render: function (c) { return h('span', { class: 'mono small' }, c.thread_id); } },
              { label: 'HS (mã)', render: function (c) { return c.student_code ? h('span', { class: 'mono' }, c.student_code) : h('span', { class: 'muted' }, '—'); } },
              { label: 'prompt_version', render: function (c) { return h('span', { class: 'mono small' }, c.prompt_version); } },
              { label: 'Model', render: function (c) { return h('span', { class: 'mono small' }, c.model); } },
              { label: 'Token vào / ra / cache', align: 'right', render: function (c) { return h('span', { class: 'nowrap' }, f.int(c.tokens_in) + ' / ' + f.int(c.tokens_out) + ' / ' + f.int(c.cache_read_tokens)); } },
              { label: 'Thời gian', align: 'right', render: function (c) { return f.ms(c.ms); } },
              { label: 'Chi phí', align: 'right', render: function (c) { return f.usd(c.cost_usd); } },
              { label: 'Kết quả', render: function (c) { return U.chip(c.result, RESULT_KIND[c.result] || 'neutral'); } },
              { label: '', render: function (c) { return U.button('Xem prompt & output', function () { openCall(c); }, { kind: 'ghost', size: 'sm' }); } }
            ],
            rows: view,
            rowClass: function (c) { return c.result !== 'ok' ? 'lg-row-bad' : null; },
            empty: 'Không có lời gọi nào khớp bộ lọc.'
          })),
          rows.length > view.length ? h('div', { class: 'row' }, U.button('Xem thêm ' + Math.min(PAGE_LOG, rows.length - view.length) + ' dòng', function () { shownLog += PAGE_LOG; drawLog(); }, { kind: 'secondary', size: 'sm' }),
            h('span', { class: 'small muted' }, 'đang hiện ' + view.length + ' / ' + f.int(rows.length))) : null);
      }
      drawLog();

      /* ---------- 4. Chi tiết lời gọi (drawer) ---------- */
      function openCall(c) {
        var smp = ((M.ui || {}).api_payload_samples || {})[c.agent] || FALLBACK_PROMPT[c.agent] || null;
        var code = c.student_code;
        var costWhy = U.why(function () {
          return h('div', { class: 'stack' }, h('p', null, 'Đơn giá giả định (bản nháp):'),
            h('p', { class: 'mono small' }, '(' + f.int(c.tokens_in) + ' × ' + price.input_per_mtok + ' + ' + f.int(c.tokens_out) + ' × ' + price.output_per_mtok + ' + ' + f.int(c.cache_read_tokens) + ' × ' + price.cache_read_per_mtok + ') ÷ 1 000 000 = ' + f.usd(c.cost_usd)));
        });
        ctx.drawer({
          title: 'Lời gọi ' + c.agent + ' ' + agentName(c.agent) + ' · ' + f.dt(c.ts),
          body: function (el, api) {
            var sess = c.graph === 'G1' ? L.sessionByThread(c.thread_id) : null;
            el.append(
              U.annot(['agent:' + c.agent, c.graph, 'file:llm.jsonl']),
              U.kv([
                ['Agent', agentChip(c.agent)], ['Graph · thread', h('span', null, U.chip(c.graph, c.graph), ' ', h('span', { class: 'mono small' }, c.thread_id))],
                ['HS (mã gửi API)', code ? h('span', { class: 'mono' }, code) : 'không có — chỉ đề + lời giải ngân hàng'],
                ['prompt_version', h('span', { class: 'mono' }, c.prompt_version)], ['Model', h('span', { class: 'mono' }, c.model)],
                ['Token vào / ra / cache', f.int(c.tokens_in) + ' / ' + f.int(c.tokens_out) + ' / ' + f.int(c.cache_read_tokens)],
                ['Thời gian', f.ms(c.ms)], ['Chi phí', h('span', { class: 'row' }, f.usd(c.cost_usd) + ' (giả định)', costWhy)],
                ['Kết quả', U.chip(c.result, RESULT_KIND[c.result] || 'neutral')], ['Tóm tắt đầu ra', c.output_summary || '—']
              ]),
              c.result === 'retry' ? h('div', { class: 'callout callout-warn' }, h('p', null, 'Lỗi tạm thời (hết giờ / quá tải) → llm.py tự gọi lại; lời gọi này vẫn tính token vào.')) : null,
              c.result === 'schema_error' ? h('div', { class: 'callout callout-crit' }, h('p', null, 'Đầu ra không khớp schema Pydantic (messages.parse báo lỗi) → gọi lại; không có gì được ghi.')) : null,
              h('h3', null, 'Cấu trúc prompt'),
              smp ? h('div', { class: 'stack' },
                h('div', { class: 'lg-part' }, h('div', { class: 'row small' }, h('b', null, '① Phần cố định — được cache'), U.prov('code'), h('span', { class: 'muted' }, f.int(c.cache_read_tokens) + ' token đọc từ cache')),
                  h('pre', { class: 'code' }, smp.cached_system + (smp.cached_system.indexOf(c.prompt_version) < 0 ? '\n(' + c.prompt_version + ')' : ''))),
                h('div', { class: 'lg-part' }, h('div', { class: 'row small' }, h('b', null, '② ' + (smp.data_title || 'Bài làm học sinh — dữ liệu không tin cậy'))),
                  smp.untrusted == null ? h('p', { class: 'muted small' }, 'Không có bài làm HS trong lời gọi này.')
                    : code || smp.data_title ? h('pre', { class: 'code' + (smp.data_title ? '' : ' untrusted') }, String(smp.untrusted).split('{code}').join(code || '—'))
                      : h('p', { class: 'muted small' }, 'Lời gọi ngân hàng bài (G2/G3): không có HS; phần ② là đề + lời giải mẫu.')),
                h('div', { class: 'lg-part' }, h('div', { class: 'row small' }, h('b', null, '③ Đầu ra JSON theo schema'), U.prov('llm')),
                  h('pre', { class: 'code' }, smp.schema), h('p', { class: 'small muted' }, 'Lần này: ' + (c.output_summary || '—'))))
                : U.empty('Chưa có mẫu prompt cho agent ' + c.agent + '.'),
              h('div', { class: 'callout callout-info' }, h('p', null, h('b', null, 'Tên học sinh không bao giờ có trong prompt'), ' — chỉ mã ' + (code || 'HS') + ' (NFR7). Bài làm nằm trong khung UNTRUSTED INPUT: là dữ liệu, không phải lệnh (NFR6).')),
              h('div', { class: 'row' },
                U.button('Lọc theo thread này', function () { api.close(); setFilter({ thread: c.thread_id }); }, { kind: 'secondary', size: 'sm' }),
                (M.ui && M.ui.api_payload_samples || {})[c.agent] ? U.button('Xem nội dung gửi API', function () { U.payloadModal(c.agent, code || 'HS-03'); }, { kind: 'secondary', size: 'sm', privacy: code || null }) : null,
                U.button(c.graph === 'G1' ? 'Mở buổi học' : 'Mở màn hình liên quan', function () { openThread(c, sess); }, { kind: 'ghost', size: 'sm' })));
          }
        });
      }
      function openThread(c, sess) {
        if (c.graph === 'G1') { ctx.nav('session', sess ? { session: sess.id } : { thread: c.thread_id }); return; }
        var t = L.thread(c.thread_id);
        if (t && t.status === 'awaiting_review' && ctx.queue.open(c.thread_id)) return;
        var stu = t && t.student_id != null ? t.student_id : null;
        var to = { G2: ['bank', {}], G3: ['bank', {}], G4: ['recommend', stu ? { student: stu } : {}], G5: ['report', stu ? { student: stu } : {}] }[c.graph] || ['ops', {}];
        ctx.nav(to[0], to[1]);
      }

      /* ---------- 5. Chất lượng agent ---------- */
      var qual = section('quality', 'Chất lượng agent', ['table:mistake', 'agent:03', 'agent:04', 'agent:06', 'agent:09', 'table:report'],
        'Đo từ quyết định của thầy/cô khi duyệt (spec §12). Đề xuất bị bỏ vẫn lưu trong tutor.db (status rejected) chính là để tính các số này.');
      (function () {
        var mk = arr(D.mistake).filter(function (m) { return m.supersedes_id == null; });
        var prop = mk.filter(function (m) { return m.status !== 'added'; });
        var cnt = function (st) { return mk.filter(function (m) { return m.status === st; }).length; };
        var nRej = cnt('rejected'), nEd = cnt('edited'), nAdd = cnt('added'), nConf = cnt('confirmed');
        var kept = prop.length - nRej + nAdd;
        var ver = prop.filter(function (m) { return m.verifier_verdict; });
        var agreeN = ver.filter(function (m) { return (m.verifier_verdict === 'disagree') === (m.status === 'rejected'); }).length;
        var wc = ver.filter(function (m) { return m.verifier_verdict === 'wrong_code'; });
        var wcHit = wc.filter(function (m) { return m.status === 'edited' && m.llm_json && m.llm_json.code !== m.code; }).length;
        // Cohen's kappa over error codes: 03's code (llm_json) vs the code the teacher kept.
        var pairs = prop.filter(function (m) { return m.status !== 'rejected' && m.llm_json; }).map(function (m) { return [m.llm_json.code, m.code]; });
        var po = pairs.length ? pairs.filter(function (p) { return p[0] === p[1]; }).length / pairs.length : null;
        var pa = {}, pb = {}; pairs.forEach(function (p) { pa[p[0]] = (pa[p[0]] || 0) + 1; pb[p[1]] = (pb[p[1]] || 0) + 1; });
        var pe = Object.keys(Object.assign({}, pa, pb)).reduce(function (s, k) { return s + ((pa[k] || 0) / pairs.length) * ((pb[k] || 0) / pairs.length); }, 0);
        var kappa = po == null ? null : (po - pe) / (1 - pe);
        var stepPairs = prop.filter(function (m) { return m.status !== 'rejected' && m.llm_json && m.llm_json.step_idx != null; });
        var stepHit = stepPairs.filter(function (m) { return m.llm_json.step_idx === m.step_idx; }).length;
        var q06 = ((M.ui || {}).agent_quality || {})['06'] || {};
        var sents = []; arr(D.report).forEach(function (r) { arr(r.audit_json).forEach(function (s) { sents.push(s); }); });
        var sFail = sents.filter(function (s) { return s.result !== 'pass'; });
        var sRw = sents.filter(function (s) { return s.result === 'rewritten'; }).length, sDr = sents.filter(function (s) { return s.result === 'dropped'; }).length;
        var rs = arr(D.session).filter(function (s) { return s.status === 'committed' && s.review_seconds != null; });
        var avgSec = rs.length ? sum(rs, function (s) { return s.review_seconds; }) / rs.length : null;
        var nMkPerSes = rs.length ? arr(D.mistake).length / rs.length : null;
        var mmss = function (x) { if (x == null) return '—'; var t = Math.round(x); return Math.floor(t / 60) + ' phút ' + String(t % 60).padStart(2, '0') + ' giây'; };
        var q = function (agent, label, value, sub, whyFn, worse) {
          return h('div', { class: 'kpi' + (worse ? ' lg-kpi-warn' : '') },
            h('span', { class: 'kpi-label' }, agent ? agentChip(agent) : h('span', { class: 'chip' }, 'GV'), U.why(whyFn), U.prov('code')),
            h('span', { class: 'small' }, label),
            h('span', { class: 'kpi-value' }, value), h('span', { class: 'kpi-sub' }, sub));
        };
        qual.append(h('div', { class: 'grid cols-4' },
          q('03', 'bị bỏ / sửa / GV thêm', pct1(nRej / prop.length) + ' · ' + pct1(nEd / prop.length) + ' · ' + pct1(nAdd / kept),
            nRej + ' bỏ · ' + nEd + ' sửa trên ' + prop.length + ' đề xuất · ' + nAdd + ' lỗi GV thêm',
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Từ bảng mistake (không tính dòng sửa sau khi lưu):'),
                U.kv([['bị bỏ', nRej + ' ÷ ' + prop.length + ' đề xuất của 03 = ' + pct1(nRej / prop.length)], ['bị sửa', nEd + ' ÷ ' + prop.length + ' = ' + pct1(nEd / prop.length)],
                  ['GV thêm', nAdd + ' ÷ ' + kept + ' lỗi cuối cùng (giữ lại + thêm) = ' + pct1(nAdd / kept)], ['chấp nhận nguyên văn', nConf + ' (confirmed)']]));
            }, nRej / prop.length > 0.2),
          q('04', 'đồng ý với GV', pct1(agreeN / ver.length), agreeN + '/' + ver.length + ' lỗi · 04 báo sai mã, GV sửa ' + wcHit + '/' + wc.length,
            function () {
              return h('div', { class: 'stack' }, h('p', null, '“Đồng ý” = 04 nói không phải lỗi (disagree) đúng khi GV bỏ, và ngược lại.'),
                h('p', { class: 'mono small' }, agreeN + ' ÷ ' + ver.length + ' = ' + pct1(agreeN / ver.length)),
                h('p', null, 'wrong_code: GV sửa mã ở ' + wcHit + ' trong ' + wc.length + ' lỗi 04 báo sai mã.'),
                h('p', { class: 'small muted' }, 'Verifier đồng ý không có nghĩa lỗi đúng — model đồng ý với nhau nhiều hơn với người (sơ đồ 04).'));
            }),
          q('03', 'đúng bước sai (exact step)', pct1(stepHit / stepPairs.length), 'bước 03 chỉ ra trùng bước GV giữ: ' + stepHit + '/' + stepPairs.length + ' lỗi',
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Bước sai 03 đề xuất (llm_json.step_idx) trùng bước GV giữ (step_idx), trên ' + stepPairs.length + ' lỗi không bị bỏ. Lỗi GV tự thêm (03 bỏ sót) tính ở thẻ bỏ / sửa / thêm.'),
                h('p', { class: 'mono small' }, stepHit + ' ÷ ' + stepPairs.length + ' = ' + pct1(stepHit / stepPairs.length)),
                h('p', { class: 'small muted' }, 'Tham chiếu: đúng bước sai chỉ 42% dù đúng / sai cả bài 95% (MathEDU, sơ đồ 03) → luôn có GV duyệt.'));
            }),
          q('03', 'kappa mã lỗi GV–LLM', kappa == null ? '—' : kappa.toFixed(2), 'κ trên ' + pairs.length + ' lỗi GV giữ lại · trùng mã ' + pct1(po),
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Cohen κ giữa mã 03 đề xuất (llm_json.code) và mã cuối cùng GV giữ, trên ' + pairs.length + ' lỗi không bị bỏ.'),
                h('p', { class: 'mono small' }, 'p_o = ' + f.num(po, 3) + ' · p_e = ' + f.num(pe, 3) + ' → κ = (p_o − p_e) ÷ (1 − p_e) = ' + f.num(kappa, 2)),
                h('p', { class: 'small muted' }, 'Tham chiếu: kappa người–LLM 0.52–0.60 (sơ đồ 04, Agreement Is Not Validity).'));
            }),
          q('06', 'KC dự kiến nằm trong top-5', f.pct(q06.top5_hit), 'top-1 trùng KC GV chọn ' + f.pct(q06.top1_match) + ' · n = ' + (q06.n || '—') + ' bài',
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Lấy từ lần gắn KC ' + (q06.n || '—') + ' bài ngân hàng (G2): ' + f.pct(q06.top5_hit) + ' bài có KC người soạn dự kiến nằm trong top-5 của 06; GV chọn trùng KC hạng 1 ở ' + f.pct(q06.top1_match) + '.'),
                h('p', { class: 'small muted' }, 'Vì top-1 thấp (KC-Tagging: ~39%) nên luôn đưa top-5 cho GV chọn.'));
            }),
          q('09', 'câu trượt audit lần đầu', pct1(sFail.length / sents.length), sFail.length + '/' + sents.length + ' câu · ' + sRw + ' viết lại · ' + sDr + ' bị bỏ',
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Trên ' + arr(D.report).length + ' report đã duyệt (audit_json): câu không đạt lần đầu = viết lại + bị bỏ.'),
                h('p', { class: 'mono small' }, '(' + sRw + ' + ' + sDr + ') ÷ ' + sents.length + ' = ' + pct1(sFail.length / sents.length)));
            }),
          q(null, 'Thời gian duyệt TB / buổi', mmss(avgSec), rs.length + ' buổi đã ghi · TB ' + (nMkPerSes == null ? '—' : nMkPerSes.toFixed(1)) + ' lỗi / buổi',
            function () {
              return h('div', { class: 'stack' }, h('p', null, 'Trung bình session.review_seconds (từ lúc mở bước 4 tới lúc ghi) của ' + rs.length + ' buổi đã ghi.'),
                h('p', { class: 'mono small' }, f.int(sum(rs, function (s) { return s.review_seconds; })) + ' giây ÷ ' + rs.length + ' = ' + Math.round(avgSec) + ' giây'));
            })));
      })();
      root.append(qual);

      /* ---------- 6. Prompt & độ ổn định ---------- */
      var prm = section('prompts', 'Prompt & độ ổn định', ['file:llm.jsonl', 'agent:03', 'NFR8'],
        'Đổi prompt → chạy lại 3 lần trên cùng bài trước khi tin (Tonmoy 2026: 50–64% tiêu chí đổi điểm giữa các lần chạy). pass^3 = cả 3 lần cho cùng kết quả.');
      var prmBox = h('div', { class: 'stack' });
      prm.append(prmBox);
      root.append(prm);
      var running = {}, cells = {};
      // Progress repaints only the row's own cells, so other rows' buttons stay attached.
      function paintRow(p) {
        var c = cells[p.version]; if (!c) return;
        var st = p.stability || {}, run = running[p.version];
        var used = log().filter(function (x) { return x.prompt_version === p.version && x.ts >= p.changed_at; }).length;
        c.st.replaceChildren(run != null ? h('span', { class: 'stack lg-tight' }, h('span', { class: 'small' }, 'Đang chạy lần ' + run + '/3…'), U.bar(run, 3))
          : st.status === 'passed' ? U.chip((st.pass3 ? 'pass^3 ✓' : 'pass^3 ✗') + ' · ' + st.changed_criteria_pct + '% tiêu chí đổi điểm', st.pass3 ? 'ok' : 'danger')
            : h('span', { class: 'stack lg-tight' }, U.chip('chưa kiểm 3 lần', 'warn'),
              used ? h('span', { class: 'small lg-warn-text' }, 'đã dùng ' + used + ' lần khi chưa kiểm (NFR8)') : h('span', { class: 'small muted' }, 'chạy trước khi dùng (NFR8)')));
        c.act.replaceChildren(U.button('Chạy kiểm tra ổn định (3 lần)', function () { runStability(p); }, { kind: 'secondary', size: 'sm', disabledReason: run != null ? 'đang chạy' : null }));
        var tr = c.st.closest('tr'); if (tr) tr.classList.toggle('lg-row-warn', st.status !== 'passed');
      }
      function drawPrompts() {
        var pvs = arr((M.ui || {}).prompt_versions);
        cells = {};
        prmBox.replaceChildren(h('div', { class: 'lg-nowrap' }, U.table({
          columns: [
            { label: 'Agent', render: function (p) { return agentChip(p.agent); } },
            { label: 'Version', render: function (p) { return h('span', { class: 'mono' }, p.version); } },
            { label: 'Đổi lúc', render: function (p) { return f.dt(p.changed_at); } },
            { label: 'Lời gọi dùng bản này', align: 'right', render: function (p) {
              var mine = log().filter(function (c) { return c.prompt_version === p.version && c.ts >= p.changed_at; });
              var early = log().filter(function (c) { return c.prompt_version === p.version && c.ts < p.changed_at; }).length;
              var older = Array.from(new Set(log().filter(function (c) { return c.agent === p.agent && c.prompt_version !== p.version; }).map(function (c) { return c.prompt_version; })));
              return h('span', { class: 'stack lg-tight' }, h('span', null, f.int(mine.length)),
                older.map(function (v) { return h('span', { class: 'small muted' }, 'bản trước ' + v + ': ' + f.int(log().filter(function (c) { return c.prompt_version === v; }).length)); }),
                // shortcut: mock llm_log tags pre-change calls with the new version; drop once gen_mock labels them with the old one.
                early ? h('span', { class: 'small muted' }, 'trước lúc đổi (bản trước): ' + f.int(early)) : null);
            } },
            { label: 'Kiểm tra 3 lần', render: function (p) { var c = cells[p.version] || (cells[p.version] = {}); c.st = h('span'); return c.st; } },
            { label: '', render: function (p) { var c = cells[p.version] || (cells[p.version] = {}); c.act = h('span'); return c.act; } }
          ],
          rows: pvs,
          empty: 'Chưa có prompt_version nào.'
        })));
        pvs.forEach(paintRow);
      }
      function runStability(p) {
        if (running[p.version] != null) return;
        var passed = arr((M.ui || {}).prompt_versions).filter(function (x) { return x.stability && x.stability.status === 'passed'; })
          .map(function (x) { return +x.stability.changed_criteria_pct || 0; }).sort(function (a, b) { return a - b; });
        var prior = p.stability && p.stability.status === 'passed' ? +p.stability.changed_criteria_pct : null;
        // shortcut: the mock has no stability-run data; a first run takes the (lower) median of the checked prompts. Upgrade when evals exist.
        var pctOut = prior != null ? prior : passed.length ? passed[Math.floor((passed.length - 1) / 2)] : 0;
        running[p.version] = 1; paintRow(p);
        ctx.toast('Chạy ' + p.version + ' 3 lần trên cùng bộ bài…', { kind: 'info' });
        [700, 1400].forEach(function (ms, i) { setTimeout(function () { if (running[p.version] != null) { running[p.version] = i + 2; paintRow(p); } }, ms); });
        setTimeout(function () {
          delete running[p.version];
          p.stability = { status: 'passed', runs: 3, pass3: true, changed_criteria_pct: pctOut };
          paintRow(p);
          ctx.toast(p.version + ': pass^3 ✓ · ' + pctOut + '% tiêu chí đổi điểm', { kind: 'ok', title: 'Kiểm tra ổn định xong' });
        }, 2100);
      }
      drawPrompts();

      /* ---------- 7. Nhật ký quyết định GV ---------- */
      var dec = section('decisions', 'Nhật ký quyết định của thầy/cô', ['table:mistake', 'table:recommendation', 'table:report'],
        'Lấy từ dòng đã ghi trong tutor.db. Đề xuất gốc của LLM vẫn giữ (mistake.llm_json), nên luôn so được trước / sau.');
      (function () {
        var att = new Map(arr(D.attempt).map(function (a) { return [a.id, a]; }));
        var ses = new Map(arr(D.session).map(function (s) { return [s.id, s]; }));
        var mkById = new Map(arr(D.mistake).map(function (m) { return [m.id, m]; }));
        var items = [];
        // Teacher reads the description; the raw code stays on hover.
        var codeEl = function (c, strike) { var e = L.errorCode(c); return h(strike ? 's' : 'span', { class: 'small', title: c || '' }, e ? e.description : (c || '—')); };
        arr(D.mistake).forEach(function (m) {
          if (m.status === 'confirmed' && m.supersedes_id == null) return;
          var a = att.get(m.attempt_id) || {}, s = ses.get(a.session_id) || {}, p = L.problem(a.problem_id) || {};
          var who = L.studentCode(L.student(s.student_id));
          var it = { kind: 'mistake', at: m.reviewed_at, label: who + ' · ' + dm(s.held_on) + ' · ' + (p.ref || '?') + ' bước ' + m.step_idx, status: m.status, open: function () { ctx.nav('session', { session: s.id }); } };
          if (m.supersedes_id != null) {
            var old = mkById.get(m.supersedes_id) || {};
            it.status = 'supersede'; it.before = h('span', null, codeEl(old.code, true), h('span', { class: 'small muted' }, ' #' + old.id));
            it.after = h('span', null, codeEl(m.code), h('span', { class: 'small muted' }, ' thay #' + old.id + ' · replay skill_state'));
          } else if (m.status === 'edited') {
            it.before = codeEl(m.llm_json && m.llm_json.code, true);
            it.after = h('span', null, codeEl(m.code), m.teacher_note ? h('span', { class: 'small muted' }, ' · ' + m.teacher_note) : null);
          } else if (m.status === 'rejected') {
            it.before = codeEl(m.llm_json && m.llm_json.code); it.after = h('span', { class: 'small muted' }, 'bỏ — vẫn lưu để đo độ chính xác');
          } else if (m.status === 'added') {
            it.before = h('span', { class: 'small muted' }, '— 03 bỏ sót'); it.after = codeEl(m.code);
          }
          items.push(it);
        });
        var BUCKET = { review: 'ôn', zpd: 'vừa sức', challenge: 'thử thách' };
        arr(D.recommendation).forEach(function (r) {
          if (r.status === 'approved') return;
          var p = L.problem(r.problem_id) || {}, k = L.kc(r.kc_id) || {};
          items.push({ kind: 'reco', at: r.reviewed_at, label: L.studentCode(L.student(r.student_id)) + ' · buổi ' + dm(r.for_date) + ' · ' + (p.ref || '?'), status: r.status,
            before: r.status === 'added' ? h('span', { class: 'small muted' }, '— không có trong 6 bài code chọn') : h('span', { class: 'small' }, (BUCKET[r.bucket] || '—') + ' · ' + (k.name || '')),
            after: r.status === 'added' ? h('span', { class: 'small' }, 'GV tự thêm · ' + (k.name || '')) : h('span', { class: 'small muted' }, 'bỏ khỏi danh sách'),
            open: function () { ctx.nav('recommend', { student: r.student_id }); } });
        });
        arr(D.report).forEach(function (r) {
          var a = arr(r.audit_json), n = function (x) { return a.filter(function (s) { return s.result === x; }).length; };
          items.push({ kind: 'report', at: r.approved_at, label: L.studentCode(L.student(r.student_id)) + ' · report ' + f.month(r.month), status: 'approved',
            before: h('span', { class: 'small' }, a.length + ' câu nháp: ' + n('pass') + ' đạt · ' + n('rewritten') + ' viết lại · ' + n('dropped') + ' bị bỏ'),
            after: h('span', { class: 'small' }, 'ghi report ' + (a.length - n('dropped')) + ' câu'),
            open: function () { ctx.nav('report', { student: r.student_id, month: r.month }); } });
        });
        items.sort(function (x, y) { return x.at < y.at ? 1 : x.at > y.at ? -1 : 0; });
        var nConf = arr(D.mistake).filter(function (m) { return m.status === 'confirmed' && m.supersedes_id == null; }).length;
        var nAppr = arr(D.recommendation).filter(function (r) { return r.status === 'approved'; }).length;
        var kind = 'all', shown = PAGE_DEC, box = h('div', { class: 'stack' });
        var KINDS = [['all', 'Tất cả'], ['mistake', 'Lỗi'], ['reco', 'Gợi ý bài'], ['report', 'Report']];
        var STATUS_OF = { supersede: function () { return U.chip('sửa sau khi lưu', 'info'); } };
        var draw = function () {
          var rows = items.filter(function (it) { return kind === 'all' || it.kind === kind; }), view = rows.slice(0, shown);
          fill(box,
            U.segmented(KINDS.map(function (k) { return { id: k[0], label: k[1] + ' (' + items.filter(function (it) { return k[0] === 'all' || it.kind === k[0]; }).length + ')' }; }), kind, function (v) { kind = v; shown = PAGE_DEC; draw(); }),
            U.table({
              columns: [
                { label: 'Lúc', render: function (it) { return h('span', { class: 'nowrap' }, f.dt(it.at)); } },
                { label: 'Mục', render: function (it) { return h('span', { class: 'mono small nowrap' }, it.label); } },
                { label: 'Quyết định', render: function (it) { return (STATUS_OF[it.status] || U.status)(it.status); } },
                { label: 'Trước (đề xuất)', render: function (it) { return it.before; } },
                { label: 'Sau (GV)', render: function (it) { return it.after; } },
                { label: '', render: function (it) { return U.button('Xem', it.open, { kind: 'ghost', size: 'sm', title: 'Mở màn hình của mục này' }); } }
              ],
              rows: view, empty: 'Chưa có quyết định nào.'
            }),
            h('div', { class: 'spread small' },
              h('span', { class: 'muted' }, 'Không liệt kê từng dòng chấp nhận nguyên văn: ' + nConf + ' lỗi đã xác nhận · ' + nAppr + ' bài gợi ý đã duyệt.'),
              rows.length > view.length ? U.button('Xem thêm ' + Math.min(PAGE_DEC, rows.length - view.length) + ' dòng', function () { shown += PAGE_DEC; draw(); }, { kind: 'secondary', size: 'sm' }) : null));
        };
        draw();
        dec.append(box);
      })();
      root.append(dec);

      /* ---------- CSV + scroll from params ---------- */
      function exportCsv() {
        var rows = filtered();
        var head = ['ts', 'agent', 'graph', 'thread_id', 'student_code', 'prompt_version', 'model', 'tokens_in', 'tokens_out', 'cache_read_tokens', 'ms', 'cost_usd', 'result'];
        var text = head.join(',') + '\n' + rows.map(function (c) { return head.map(function (k) { return c[k] == null ? '' : String(c[k]); }).join(','); }).join('\n');
        U.download('llm-chi-phi' + (F.thread ? '-' + F.thread : '') + '.csv', text);
      }
      var target = ctx.params.section || ((F.agent || F.graph || F.student || F.thread) ? 'log' : '');
      if (target && secs[target]) requestAnimationFrame(function () { scrollTo(target); });
    }
  });
})();
