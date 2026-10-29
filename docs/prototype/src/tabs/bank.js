/* tabs/bank.js — Ngân hàng bài (IA §3.7): danh sách bài, G2 (06 tag KC + 02 rubric), G3 (07 so cặp + bt.py).
   Params: problem=<ref|id> (drawer chi tiết) · review=<g2 thread> · difficulty=<g3 thread> · kc=<code|id> (lọc danh sách). */
(() => {
  const PAGE = 25;
  // Per-page-load view state (filters, selections); data itself lives in MOCK.
  const S = { f: { topic: '', lop: '', kc: '', st: '' }, limit: PAGE, kcParam: null, g2sel: {}, g3kc: {}, running: {} };
  const STATUS_OPTS = [['', 'Mọi trạng thái'], ['ready', 'sẵn sàng'], ['thieu_rubric', 'thiếu rubric'], ['cho_do_kho', 'chờ độ khó'], ['cho_duyet_tag', 'chờ duyệt tag']];
  const G2_DONE = ['g2.split', 'g2.06_tagger', 'g2.02_rubric'];
  const G3_DONE = ['g3.pair', 'g3.07_difficulty', 'g3.bt_fit'];

  const arr = x => (Array.isArray(x) ? x : []);
  const pad = n => String(n).padStart(2, '0');
  const hasMath = s => /\$|\\\(|\\\[|\\begin\{/.test(String(s || ''));
  const firstPara = s => String(s || '').split(/\n\s*\n/)[0].replace(/\s*\n\s*/g, ' ');
  // One-line cells: display math becomes inline so the row stays one line.
  const oneLine = s => firstPara(s).replace(/\$\$/g, '$').replace(/\\\[/g, '\\(').replace(/\\\]/g, '\\)');
  const maxId = rows => arr(rows).reduce((m, r) => Math.max(m, +r.id || 0), 0);
  // Native append/replaceChildren print null and arrays as text; drop/flatten them first.
  const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
  const viewTab = () => (document.getElementById('view') || {}).dataset?.tab;

  function nowISO(ctx) {
    const d = new Date();
    return ctx.data.meta.today + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + 'Z';
  }
  // ui.latex wraps delimiter-free text as math; plain Vietnamese text must stay text.
  function tx(ctx, src, block) {
    const h = ctx.ui.h, s = String(src == null ? '' : src);
    if (hasMath(s)) return ctx.ui.latex(s, { block });
    if (!block) return h('span', null, s);
    return h('div', { class: 'bk-ptext' }, s.split(/\n\s*\n/).map(p => h('p', null, p.trim())));
  }
  function link(ctx, tab, label, params) {
    const a = ctx.ui.h('a', { href: '#' + tab, 'data-tab-link': tab }, label);
    if (params) a.dataset.params = new URLSearchParams(params).toString();
    return a;
  }
  function lockIcon(ctx) {
    return ctx.ui.svg('<svg class="bk-lock" role="img" aria-label="δ đã khoá" width="11" height="11" viewBox="0 0 12 12"><title>δ đã khoá (difficulty_approved_at)</title><rect x="2" y="5.5" width="8" height="5.5" rx="1" fill="currentColor"/><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>');
  }
  function secHead(ctx, title, annot, right) {
    const h = ctx.ui.h;
    return h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? ctx.ui.annot(annot) : null), right || null);
  }
  function callout(ctx, kind, ...kids) { return ctx.ui.h('div', { class: 'callout callout-' + kind }, ctx.ui.h('p', null, ...kids)); }

  /* ---------- derived data (recomputed per render; ~200 problems) ---------- */
  function model(ctx) {
    const d = ctx.data.db, th = arr(ctx.data.checkpoints && ctx.data.checkpoints.threads);
    const kcOf = new Map(), att = new Map(), sess = new Map(arr(d.session).map(s => [s.id, s]));
    arr(d.problem_kc).forEach(r => { if (!kcOf.has(r.problem_id)) kcOf.set(r.problem_id, []); kcOf.get(r.problem_id).push(r); });
    const superseded = new Set(arr(d.attempt).map(a => a.supersedes_id).filter(x => x != null));
    arr(d.attempt).forEach(a => { if (superseded.has(a.id)) return; if (!att.has(a.problem_id)) att.set(a.problem_id, []); att.get(a.problem_id).push(a); });
    const g2 = th.filter(t => t.graph === 'G2' && t.status === 'awaiting_review');
    const g3 = th.filter(t => t.graph === 'G3' && t.status === 'awaiting_review');
    const pend = [];
    g2.forEach(t => arr(t.state && t.state.problems).forEach(p => pend.push(Object.assign({ pending: true, thread_id: t.thread_id }, p))));
    const deltaProp = new Map();
    g3.forEach(t => arr(t.state && t.state.proposals).forEach(pp => arr(pp.ranking).forEach(r => deltaProp.set(r.problem_id, { delta: r.delta, thread_id: t.thread_id }))));
    return { d, th, kcOf, att, sess, g2, g3, pend, deltaProp };
  }
  const g2For = (M, f) => M.g2.find(t => String((t.state || {}).bank_file || '').endsWith(f.file));
  const g3For = (M, f) => M.g3.find(t => (t.state || {}).kc_group === f.kc_group);
  function topicInfo(ctx, M, f) {
    const probs = M.d.problem.filter(p => p.topic_file === f.file);
    const g2t = g2For(M, f), g3t = g3For(M, f);
    const tagged = probs.filter(p => M.kcOf.has(p.id)).length;
    const rub = probs.filter(p => ctx.lookup.rubricFor(p.id)).length;
    const dl = probs.filter(p => p.difficulty_approved_at).length;
    const status = g2t ? 'cho_duyet_tag' : probs.length && dl < probs.length ? 'cho_do_kho' : rub < probs.length ? 'thieu_rubric' : 'ready';
    const n = probs.length || (g2t ? arr(g2t.state.problems).length : f.n_blocks);
    return { f, probs, g2t, g3t, tagged, rub, dl, status, n, canG3: !g2t && !g3t && probs.length > 1 && tagged === probs.length && dl < probs.length };
  }
  function uniquePairs(props) {
    const seen = new Map();
    arr(props).forEach(pp => arr(pp.pairs).forEach(x => { const k = x.problem_a + '-' + x.problem_b; if (!seen.has(k)) seen.set(k, x); }));
    return [...seen.values()];
  }
  const pairResult = x => (x.harder_ab !== x.harder_ba ? 'hoà' : x.harder_ab);

  /* ---------- tab ---------- */
  App.registerTab('bank', {
    title: 'Ngân hàng bài',
    render(root, ctx) {
      const p = ctx.params;
      if (p.review) return renderG2(root, ctx, p.review);
      if (p.difficulty) return renderG3(root, ctx, p.difficulty);
      return renderOverview(root, ctx);
    }
  });

  /* ---------- overview ---------- */
  function renderOverview(root, ctx) {
    const { ui } = ctx, L = ctx.lookup, M = model(ctx), p = ctx.params;
    if (p.kc && p.kc !== S.kcParam) {
      S.kcParam = p.kc;
      const k = L.kcByCode(p.kc) || L.kc(p.kc);
      if (k) { S.f = { topic: '', lop: '', kc: String(k.id), st: '' }; S.limit = PAGE; }
    }
    const topics = arr(ctx.data.files && ctx.data.files.bank).map(f => topicInfo(ctx, M, f));
    const newPairs = uniquePairs(M.g3.flatMap(t => arr(t.state && t.state.proposals))).length;
    root.append(ui.pageHead({
      lead: 'Lần đầu và mỗi khi thêm bài: nạp file .tex → 06 gợi ý KC cho từng bước (thầy/cô chọn) → 02 sinh rubric (thầy/cô duyệt) → 07 so cặp để xếp độ khó. Chấm (G1) cần rubric — bài thiếu rubric được duyệt ngay ở bước 3 của buổi học; gợi ý (G4) cần đủ KC + rubric + δ. Chưa chốt: chấm bài chưa có δ đã duyệt thì Elo dùng δ nào.',
      actions: [
        ui.button('Nạp file .tex', () => loadTex(ctx), { kind: 'primary', cli: 'tutor bank tag <bank.tex>' }),
        ui.button('Tính lại khi thêm bài', () => ctx.toast(`Fit lại BT với ${M.d.problem_pair.length} cặp cũ + ${newPairs} cặp mới${newPairs ? ' (chờ duyệt G3)' : ''} — δ đã duyệt không đổi, chỉ bài mới nhận δ.`, { kind: 'info', title: 'bt.py · giữ cặp cũ để fit lại (FR6)' }), { cli: 'tutor bank difficulty' })
      ],
      annot: ['G2', 'agent:06', '02 Grader · sinh rubric', 'G3', 'agent:07', 'bt.py']
    }));
    const list = listSection(ctx, M, topics);
    root.append(...[stepper(ctx, M, topics), progressSection(ctx, M, topics, list), qualitySection(ctx), list.el].filter(Boolean));
    if (p.problem) openDetail(ctx, p.problem);
  }

  function stepper(ctx, M, topics) {
    const { ui } = ctx, h = ui.h, d = M.d, L = ctx.lookup;
    const leaves = d.kc.filter(k => k.parent_id != null).length, groups = d.kc.length - leaves;
    const nPend = M.pend.length, total = d.problem.length + nPend;
    const tagged = d.problem.filter(p => M.kcOf.has(p.id)).length;
    const rub = d.problem.filter(p => L.rubricFor(p.id)).length;
    const dl = d.problem.filter(p => p.difficulty_approved_at).length;
    const st = d.problem.map(p => L.problemStatus(p));
    const ready = st.filter(s => s === 'ready').length;
    const g3n = M.g3.reduce((s, t) => s + arr(t.state && t.state.proposals).reduce((a, pp) => a + arr(pp.ranking).length, 0), 0);
    const noRub = d.problem.filter(p => !L.rubricFor(p.id)).map(p => p.ref);
    const whyReady = () => h('div', { class: 'stack' },
      h('p', null, 'Sẵn sàng = có ≥ 1 dòng problem_kc (KC đã duyệt) + có rubric + δ đã duyệt (difficulty_approved_at).'),
      ui.kv([['Tổng bài', `${total} = ${d.problem.length} trong tutor.db + ${nPend} trong checkpoints.db`], ['Đã tag', String(tagged)], ['Có rubric', String(rub) + (noRub.length ? ' (thiếu: ' + noRub.join(', ') + ')' : '')],
        ['δ đã duyệt', String(dl)], ['Sẵn sàng', `${ready}/${total}`]]), ui.prov('code'));
    const steps = [
      { n: 1, title: 'Danh mục KC', st: leaves ? 'done' : 'warn', lines: leaves ? [`${leaves} KC · ${groups} nhóm`, `${d.kc_prereq.length} quan hệ tiên quyết`] : ['Chưa có danh mục KC — mở Danh mục'], extra: link(ctx, 'catalog', 'Mở Danh mục') },
      { n: 2, title: 'Nạp .tex', st: 'done', lines: [`${topics.length} file · ${total} bài`, `${d.problem.length} trong tutor.db · ${nPend} trong checkpoints.db`] },
      { n: 3, title: 'Gắn KC + rubric (G2)', st: M.g2.length ? 'pend' : 'done', lines: [`${tagged}/${total} đã tag · ${rub} có rubric`, M.g2.length ? `${M.g2.length} lô chờ duyệt (${nPend} bài)` : 'không có lô chờ duyệt'], extra: M.g2.length ? link(ctx, 'review', 'Hộp duyệt') : null },
      { n: 4, title: 'Độ khó (G3)', st: dl < total ? 'pend' : 'done', lines: [`${dl}/${total} có δ đã duyệt`, M.g3.length ? `${M.g3.length} lô chờ duyệt (${g3n} bài)` : `${total - dl} bài chưa có δ`] },
      { n: 5, title: 'Sẵn sàng', st: ready === total ? 'done' : 'part', lines: [h('span', null, h('b', { class: 'num' }, `${ready}/${total}`), ' bài sẵn sàng ', ui.why(whyReady)), 'dùng để gợi ý (G4); chấm (G1) chỉ cần rubric'], extra: link(ctx, 'recommend', 'Gợi ý bài') }
    ];
    const sec = h('section', { class: 'section' }, secHead(ctx, 'Các bước chuẩn bị ngân hàng', ['table:kc', 'table:problem', 'table:problem_kc', 'table:rubric', 'table:problem_pair']));
    if (!leaves) sec.append(callout(ctx, 'crit', 'Chưa có danh mục KC — 06 không có gì để gắn. ', link(ctx, 'catalog', 'Mở Danh mục')));
    sec.append(h('ol', { class: 'bk-steps' }, steps.map(s => h('li', { class: 'bk-step is-' + s.st },
      h('span', { class: 'bk-step-n', 'aria-hidden': 'true' }, String(s.n)),
      h('div', { class: 'bk-step-body' }, h('strong', null, s.title), s.lines.map((l, i) => h('span', { class: i ? 'muted' : null }, l)), s.extra)))));
    sec.append(h('div', { class: 'grid cols-2' },
      ui.graphStrip('G2', M.g2.length ? { compact: true, current: 'g2.review', done: G2_DONE } : { compact: true }),
      ui.graphStrip('G3', M.g3.length ? { compact: true, current: 'g3.review', done: G3_DONE } : { compact: true })));
    return sec;
  }

  function meter(ctx, v, n, pendNote) {
    const { ui } = ctx, h = ui.h;
    return h('div', { class: 'bk-meter' }, ui.bar(v, n, { kind: v === n ? 'ok' : 'accent' }), h('span', { class: 'num small' }, `${v}/${n}`),
      pendNote ? h('span', { class: 'small bk-amber bk-meter-note' }, pendNote) : null);
  }

  function progressSection(ctx, M, topics, list) {
    const { ui } = ctx, h = ui.h;
    const acts = t => {
      if (t.g2t) return h('div', { class: 'bk-acts' },
        ui.button('Mở duyệt tag', () => ctx.queue.open(t.g2t.thread_id), { kind: 'primary', size: 'sm', cli: 'tutor review ' + t.g2t.thread_id }),
        ui.button('Xếp độ khó', null, { size: 'sm', disabledReason: 'cần tag KC đã duyệt (G3 chạy sau G2)' }));
      if (t.g3t) return ui.button('Mở duyệt độ khó', () => ctx.queue.open(t.g3t.thread_id), { kind: 'primary', size: 'sm', cli: 'tutor review ' + t.g3t.thread_id });
      if (t.canG3) return ui.button('Xếp độ khó', () => runG3(ctx, t.f), { kind: 'primary', size: 'sm', cli: 'tutor bank difficulty', disabledReason: S.running[t.f.file] ? 'G3 đang chạy' : null });
      const miss = t.probs.filter(p => !ctx.lookup.rubricFor(p.id));
      if (miss.length) return h('div', { class: 'bk-acts' },
        h('span', { class: 'small' }, `${t.probs.filter(p => ctx.lookup.problemStatus(p) === 'ready').length}/${t.probs.length} sẵn sàng · ${miss.length} thiếu rubric`),
        miss.map(p => ui.button('Viết rubric ' + p.ref, () => openDetail(ctx, p.ref), { size: 'sm', title: 'Mở chi tiết bài để viết rubric v1' })));
      return h('span', { class: 'small muted' }, 'đủ KC · rubric · δ');
    };
    const table = ui.table({
      columns: [
        { label: 'Chủ đề (file)', render: t => h('div', { class: 'bk-topic' }, h('strong', null, t.f.topic_vi), h('span', { class: 'mono small muted' }, t.f.file)) },
        { label: 'Lớp', align: 'center', render: t => String(t.f.lop) },
        { label: 'Đã tag', render: t => meter(ctx, t.tagged, t.n, t.g2t ? `${t.n} chờ duyệt G2` : null) },
        { label: 'Có rubric', render: t => meter(ctx, t.rub, t.n, t.g2t ? 'nháp của 02' : t.rub < t.probs.length ? `${t.probs.length - t.rub} bài thiếu` : null) },
        { label: 'Có δ', render: t => meter(ctx, t.dl, t.n, t.g3t ? `${t.probs.length - t.dl} chờ duyệt G3` : null) },
        { label: 'Trạng thái', render: t => h('div', { class: 'bk-acts' }, ui.status(t.status), t.g2t ? ui.store('checkpoint') : null) },
        { label: 'Thao tác', render: acts }
      ],
      rows: topics,
      rowClass: t => (t.g2t ? 'bk-pend' : null),
      onRow: t => list.setTopic(t.f.file)
    });
    return h('section', { class: 'section' },
      secHead(ctx, 'Tiến độ theo chủ đề', ['table:problem', 'table:problem_kc', 'table:rubric', 'file:checkpoints.db'], h('span', { class: 'small muted' }, `mỗi file ${topics.length ? topics[0].f.n_blocks : 0} bài · bấm một dòng để lọc danh sách`)),
      table);
  }

  function qualitySection(ctx) {
    const { ui } = ctx, h = ui.h, q = ((ctx.data.ui || {}).agent_quality || {})['06'];
    if (!q) return null;
    const hit = Math.round(q.top5_hit * q.n), top1 = Math.round(q.top1_match * q.n);
    const kpi = (label, value, sub, why) => h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label, ui.why(why)), h('span', { class: 'kpi-value num' }, value), h('span', { class: 'kpi-sub' }, sub));
    return h('section', { class: 'section' },
      secHead(ctx, 'Độ khớp nhãn người soạn', ['agent:06'], ui.chip('tiêu chí P5', 'info')),
      h('div', { class: 'grid cols-2' },
        kpi('% kc_du_kien nằm trong top-5 của 06', ui.fmt.pct(q.top5_hit), `${hit}/${q.n} bài đã tag`,
          () => h('div', { class: 'stack' }, ui.kv([['Công thức', 'số bài có % kc_du_kien ∈ top-5 của 06 ÷ số bài đã tag'], ['Giá trị', `${hit}/${q.n} = ${ui.fmt.pct(q.top5_hit)}`], ['Nguồn', 'so % kc_du_kien trong file .tex với đề xuất của 06 (9 lô G2 đã duyệt)']]), ui.prov('code'))),
        kpi('GV chọn trùng KC dự kiến đầu tiên', ui.fmt.pct(q.top1_match), `${top1}/${q.n} bài`,
          () => h('div', { class: 'stack' }, ui.kv([['Công thức', 'số bài GV chọn KC = kc_du_kien[0] ÷ số bài đã tag'], ['Giá trị', `${top1}/${q.n} = ${ui.fmt.pct(q.top1_match)}`]]), h('p', { class: 'small muted' }, 'Thấp là bình thường: nhãn người soạn chỉ để đối chiếu, tag thật do thầy/cô chọn.'), ui.prov('code')))),
      h('p', { class: 'small muted' }, 'Tagger chỉ đúng top-1 khoảng 39% (KC-Tagging) → app luôn hiện top-5 cho từng bước để thầy/cô chọn, không tự gắn.'));
  }

  function listSection(ctx, M, topics) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup, d = M.d;
    const all = d.problem.map(p => ({ p, ref: p.ref, status: L.problemStatus(p) }))
      .concat(M.pend.map(p => ({ p, ref: p.ref, status: 'cho_duyet_tag', pending: true })))
      .sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));
    const mkSel = (label, key, opts) => {
      const s = h('select', { 'aria-label': label }, opts.map(o => (o.group ? h('optgroup', { label: o.group }, o.items.map(x => h('option', { value: x[0] }, x[1]))) : h('option', { value: o[0] }, o[1]))));
      s.value = S.f[key];
      s.addEventListener('change', () => { S.f[key] = s.value; S.limit = PAGE; draw(); });
      return s;
    };
    const kcGroups = d.kc.filter(k => k.parent_id == null).map(g => ({ group: g.code + ' · ' + g.name, items: d.kc.filter(k => k.parent_id === g.id).map(k => [String(k.id), k.code + ' · ' + k.name]) }));
    const sels = {
      topic: mkSel('Chủ đề', 'topic', [['', 'Mọi chủ đề']].concat(topics.map(t => [t.f.file, t.f.topic_vi]))),
      lop: mkSel('Lớp', 'lop', [['', 'Lớp 8 + 9'], ['8', 'Lớp 8'], ['9', 'Lớp 9']]),
      kc: mkSel('KC', 'kc', [['', 'Mọi KC']].concat(kcGroups)),
      st: mkSel('Trạng thái', 'st', STATUS_OPTS)
    };
    const field = (label, el) => h('label', { class: 'field bk-filter' }, h('span', null, label), el);
    const countEl = h('span', { class: 'small muted' }), body = h('div', { class: 'stack' });
    const kcCell = r => {
      if (r.pending) return h('span', { class: 'chip chip-warn' }, 'chỉ trong checkpoints.db');
      const ids = [...new Set(arr(M.kcOf.get(r.p.id)).map(x => x.kc_id))];
      return h('div', { class: 'bk-kcs' }, ids.map(id => { const k = L.kc(id) || { code: '#' + id, name: '' }; const c = ui.chip(k.name || k.code, 'ok'); c.classList.add('chip-wrap'); c.title = k.code; return c; }));
    };
    const rubCell = r => {
      if (r.pending) return h('span', { class: 'small bk-amber nowrap' }, 'nháp v1 (02)');
      const rb = L.rubricFor(r.p.id);
      return rb ? h('span', { class: 'mono' }, 'v' + rb.version) : ui.chip('chưa có', 'warn');
    };
    const deltaCell = r => {
      if (r.pending) return h('span', { class: 'muted' }, '—');
      if (r.p.difficulty_approved_at) return h('span', { class: 'num nowrap' }, ui.fmt.signed(r.p.delta), lockIcon(ctx));
      const pr = M.deltaProp.get(r.p.id);
      return pr ? h('span', { class: 'num nowrap bk-amber', title: 'đề xuất trong ' + pr.thread_id }, ui.fmt.signed(pr.delta), h('span', { class: 'small' }, ' đề xuất')) : h('span', { class: 'small muted' }, 'chờ G3');
    };
    const doneCell = r => {
      const a = r.pending ? [] : arr(M.att.get(r.p.id));
      if (!a.length) return h('span', { class: 'muted' }, '0');
      const hs = new Set(a.map(x => (M.sess.get(x.session_id) || {}).student_id)).size;
      return h('div', { class: 'num nowrap' }, `${a.length} lượt`, h('div', { class: 'small muted' }, `${hs} HS`));
    };
    const columns = [
      { label: 'Mã bài', render: r => { const b = ui.button(r.ref, () => openDetail(ctx, r.ref), { kind: 'ghost', size: 'sm', title: 'Xem đề + lời giải' }); b.classList.add('bk-ref'); return b; } },
      { label: 'Đề', render: r => h('div', { class: 'bk-one' }, tx(ctx, oneLine(r.p.statement_latex))) },
      { label: 'KC đã duyệt', render: kcCell },
      { label: 'Nhãn trong file', render: r => h('div', { class: 'bk-labels small muted' }, h('span', { class: 'mono' }, arr(r.p.expected_kc).join(', ')), ` · độ khó ${r.p.expected_difficulty}/5`) },
      { label: 'Rubric', render: rubCell },
      { label: 'δ', align: 'right', render: deltaCell },
      { label: 'Lượt HS làm', align: 'right', render: doneCell },
      { label: 'Trạng thái', render: r => ui.status(r.status) }
    ];
    const anyFilter = () => Object.values(S.f).some(Boolean);
    function filtered() {
      const f = S.f;
      return all.filter(r => (!f.topic || r.p.topic_file === f.topic) && (!f.lop || String(r.p.lop) === f.lop) && (!f.st || r.status === f.st)
        && (!f.kc || (!r.pending && arr(M.kcOf.get(r.p.id)).some(x => String(x.kc_id) === f.kc))));
    }
    function draw() {
      const rows = filtered(), shown = rows.slice(0, S.limit);
      countEl.textContent = `Hiển thị ${shown.length}/${rows.length} bài` + (rows.length !== all.length ? ` · lọc từ ${all.length}` : '');
      body.replaceChildren(
        ui.table({ columns, rows: shown, empty: 'Không có bài nào cho bộ lọc này.', onRow: r => openDetail(ctx, r.ref), rowClass: r => (r.pending ? 'bk-pend' : null) }),
        h('div', { class: 'row' },
          rows.length > shown.length ? ui.button(`Xem thêm ${Math.min(PAGE, rows.length - shown.length)} bài`, () => { S.limit += PAGE; draw(); }) : null,
          anyFilter() ? ui.button('Bỏ lọc', () => { S.f = { topic: '', lop: '', kc: '', st: '' }; S.limit = PAGE; Object.keys(sels).forEach(k => { sels[k].value = ''; }); draw(); }, { kind: 'ghost', size: 'sm' }) : null));
      ctx.tex(body);
    }
    const el = h('section', { class: 'section', id: 'bk-list' },
      secHead(ctx, 'Danh sách bài', ['table:problem', 'file:tutor.db', 'file:checkpoints.db'], countEl),
      h('div', { class: 'bk-filters' }, field('Chủ đề', sels.topic), field('Lớp', sels.lop), field('KC đã duyệt', sels.kc), field('Trạng thái', sels.st)),
      h('p', { class: 'small muted' }, 'Danh sách = bài trong tutor.db ∪ bài đang chờ G2 (viền vàng nét đứt, chỉ trong checkpoints.db). “Nhãn trong file” là nhãn người soạn (% kc_du_kien, % do_kho_du_kien), chưa phải tag đã duyệt.'),
      body);
    draw();
    return {
      el,
      setTopic(file) {
        S.f.topic = file; sels.topic.value = file; S.limit = PAGE; draw();
        el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    };
  }

  /* ---------- Nạp file .tex ---------- */
  function loadTex(ctx) {
    const { ui } = ctx, h = ui.h, M = model(ctx), files = arr(ctx.data.files.bank);
    const sel = h('select', { 'aria-label': 'File ngân hàng' }, files.map(f => h('option', { value: f.file }, f.file + ' — ' + f.topic_vi)));
    const firstReady = files.find(f => M.d.problem.some(p => p.topic_file === f.file));
    if (firstReady) sel.value = firstReady.file;
    const out = h('div', { class: 'stack', 'aria-live': 'polite' });
    const parse = () => {
      const f = files.find(x => x.file === sel.value); if (!f) return;
      const inDb = M.d.problem.filter(p => p.topic_file === f.file), g2t = g2For(M, f), inCp = g2t ? arr(g2t.state.problems) : [];
      const refs = inDb.concat(inCp).map(p => p.ref.split('-').pop()).sort();
      const fresh = Math.max(0, f.n_blocks - inDb.length - inCp.length);
      out.replaceChildren(
        h('h3', null, 'Kết quả tách bài ', ui.prov('code', 'latex.py')),
        h('p', { class: 'num' }, `${f.n_blocks} bài (${refs[0] || '—'}–${refs[refs.length - 1] || '—'}) · ${inDb.length} đã có (khớp ref) · ${fresh} bài mới · 0 khối dở dang bị bỏ qua`),
        ui.kv([['File', h('span', { class: 'mono' }, f.path)], ['Đã có trong tutor.db', String(inDb.length)], ['Đang chờ duyệt (checkpoints.db)', String(inCp.length)], ['Bài mới → chạy G2', String(fresh)]]),
        inCp.length
          ? h('div', { class: 'callout callout-warn' }, h('p', null, `${inCp.length} bài của file này đang chờ duyệt tag + rubric trong ${g2t.thread_id} — không chạy G2 lần nữa.`),
            ui.button('Mở duyệt tag', () => ctx.queue.open(g2t.thread_id), { kind: 'primary', size: 'sm', cli: 'tutor review ' + g2t.thread_id }))
          : fresh ? callout(ctx, 'info', `${fresh} bài mới sẽ qua G2: 06 gợi ý KC, 02 sinh rubric, rồi DỪNG chờ thầy/cô.`)
            : callout(ctx, 'ok', 'Không có bài mới — G2 không chạy lại; KC, rubric và δ đã duyệt giữ nguyên (problem.ref UNIQUE).'),
        ui.cli('tutor bank tag ' + f.path));
    };
    ctx.modal({
      title: 'Nạp file .tex vào ngân hàng', wide: true,
      body: h('div', { class: 'stack' },
        h('label', { class: 'field' }, h('span', null, 'File trong data/inbox/bank/'), sel),
        h('p', { class: 'small muted' }, 'latex.py (pylatexenc) cắt từng khối \\begin{problem}[ref] … \\end{problem} sau \\begin{document}; khớp theo ref. Khối thiếu \\end bị bỏ qua và báo lại.'),
        h('div', { class: 'row' }, ui.button('Nạp và tách bài', parse, { kind: 'primary' })),
        out),
      actions: [{ label: 'Đóng' }]
    });
  }

  /* ---------- Chi tiết bài (drawer) ---------- */
  function openDetail(ctx, key) {
    const L = ctx.lookup, M = model(ctx);
    const p = L.problemByRef(key) || (/^\d+$/.test(String(key)) ? L.problem(key) : null);
    const pend = !p ? M.pend.find(x => x.ref === key) : null;
    if (!p && !pend) { ctx.toast(`Không tìm thấy bài ${key}.`, { kind: 'warn' }); return; }
    ctx.drawer({ title: 'Bài ' + (p || pend).ref, body: el => el.append(ctx.ui.h('div', { class: 'stack' }, p ? detailDb(ctx, M, p) : detailPend(ctx, M, pend))) });
  }

  function stepsBlock(ctx, steps, tagsByStep) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup;
    const tagList = rows => (rows.length ? h('div', { class: 'bk-tags' }, rows.map(r => {
      const k = L.kc(r.kc_id) || { code: '#' + r.kc_id, name: '' };
      return h('div', { class: 'bk-tag' }, ui.chip(k.code, 'ok'), h('span', { class: 'small' }, k.name), r.evidence_latex ? h('span', { class: 'small muted' }, 'bằng chứng: ', tx(ctx, r.evidence_latex)) : null);
    })) : null);
    const whole = tagsByStep(0);
    return h('div', { class: 'stack' },
      whole.length ? h('div', { class: 'bk-dstep' }, h('span', { class: 'eyebrow', title: 'step_idx 0' }, 'Cả bài'), tagList(whole)) : null,
      arr(steps).map(s => h('div', { class: 'bk-dstep' }, h('span', { class: 'eyebrow' }, 'Bước ' + s.idx), tx(ctx, s.latex, true), tagList(tagsByStep(s.idx)))));
  }

  function rubricView(ctx, r) {
    const { ui } = ctx, h = ui.h;
    return h('div', { class: 'bk-rub' }, arr(r.items_json).map(it => h('div', { class: 'bk-rub-row' }, h('span', { class: 'mono small muted' }, it.item_id), tx(ctx, it.text, true), h('span', { class: 'num nowrap' }, it.points + ' đ'))),
      h('div', { class: 'small' }, 'Tổng ', h('b', { class: 'num' }, String(r.max_score)), ' điểm = max_score ', ui.prov('code')));
  }

  function detailDb(ctx, M, p) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup, d = M.d;
    const status = L.problemStatus(p), tags = arr(M.kcOf.get(p.id));
    const vers = d.rubric.filter(r => r.problem_id === p.id).sort((a, b) => b.version - a.version);
    const pairs = d.problem_pair.filter(x => x.problem_a === p.id || x.problem_b === p.id);
    const pr = M.deltaProp.get(p.id);
    const att = arr(M.att.get(p.id)).slice().sort((a, b) => ((M.sess.get(a.session_id) || {}).held_on < (M.sess.get(b.session_id) || {}).held_on ? -1 : 1));
    const topic = arr(ctx.data.files.bank).find(f => f.file === p.topic_file);
    return [
      h('div', { class: 'row' }, ui.status(status), ui.chip(topic ? topic.topic_vi : p.topic_file), ui.chip('lớp ' + p.lop), ui.store('db'),
        ui.annot(['table:problem', 'table:problem_kc', 'table:rubric', 'table:problem_pair'])),
      h('p', { class: 'small muted' }, `Nhãn người soạn (chưa phải tag đã duyệt): ${arr(p.expected_kc).join(', ') || '—'} · độ khó ${p.expected_difficulty}/5`),
      h('h3', null, 'Đề bài'), tx(ctx, p.statement_latex, true),
      h('h3', null, 'Lời giải mẫu theo bước · KC đã duyệt ', ui.prov('gv', 'GV chọn')),
      stepsBlock(ctx, p.solution_steps, i => tags.filter(t => t.step_idx === i)),
      h('h3', null, 'Rubric ', ui.prov('llm', '02 sinh'), ' ', ui.prov('gv', 'GV duyệt')),
      vers.length ? vers.map((r, i) => h('div', { class: 'card ' + (i ? 'bk-old' : 'st-db') },
        h('div', { class: 'spread' }, h('strong', null, `v${r.version} · ${r.max_score} điểm`), h('span', { class: 'small muted' }, 'duyệt ' + ui.fmt.dt(r.approved_at)), i ? ui.chip('bản cũ — bài đã chấm theo nó vẫn trỏ tới', 'neutral') : ui.chip('đang dùng', 'ok')),
        rubricView(ctx, r)))
        : callout(ctx, 'warn', 'Chưa có rubric — bài chưa chấm được và chưa vào gợi ý. Có thể viết ngay ở đây, hoặc duyệt khi bài xuất hiện trong buổi học (G1, cờ no_rubric).'),
      h('div', { class: 'row' }, ui.button(vers.length ? `Sửa rubric → v${vers[0].version + 1}` : 'Viết rubric v1', () => editRubric(ctx, p), { kind: 'secondary', size: 'sm' })),
      h('h3', null, 'Độ khó ', ui.prov('llm', '07'), ' ', ui.prov('code', 'bt.py')),
      ui.kv([
        ['δ', p.difficulty_approved_at ? h('span', { class: 'num' }, ui.fmt.signed(p.delta), lockIcon(ctx), h('span', { class: 'small muted' }, ' cố định từ ' + ui.fmt.dt(p.difficulty_approved_at)))
          : pr ? h('span', { class: 'bk-amber' }, `${ui.fmt.signed(pr.delta)} — đề xuất, chờ duyệt trong ${pr.thread_id}`) : 'chưa có (chờ G3)'],
        ['bt_score', p.bt_score == null ? '—' : h('span', { class: 'num' }, ui.fmt.signed(p.bt_score, 4))],
        ['Số lần so sánh', String(p.n_comparisons || 0)],
        ['Cặp đã lưu', `${pairs.length} dòng problem_pair`]]),
      h('div', { class: 'row' }, ui.button('Xem các cặp so sánh', () => {
        if (pairs.length) return pairsModal(ctx, p.id, pairs, null);
        const t = pr && L.thread(pr.thread_id);
        return pairsModal(ctx, p.id, t ? uniquePairs(t.state.proposals) : [], t ? `Các cặp này chỉ nằm trong checkpoints.db (${t.thread_id}), chưa ghi vào problem_pair.` : null);
      }, { size: 'sm' })),
      h('h3', null, 'Học sinh đã làm'),
      ui.table({
        columns: [
          { label: 'HS', render: a => { const s = L.student((M.sess.get(a.session_id) || {}).student_id); return s ? link(ctx, 'students', L.studentCode(s) + ' · ' + s.name, { student: L.studentCode(s) }) : '—'; } },
          { label: 'Buổi', render: a => ui.fmt.date((M.sess.get(a.session_id) || {}).held_on) },
          { label: 'Điểm', align: 'right', render: a => h('span', { class: 'num' }, `${a.score}/${a.max_score}`) },
          { label: '', render: a => link(ctx, 'session', 'Xem buổi', { session: a.session_id }) }
        ],
        rows: att, empty: 'Chưa học sinh nào làm bài này.'
      })
    ];
  }

  function detailPend(ctx, M, p) {
    const { ui } = ctx, h = ui.h, t = ctx.lookup.thread(p.thread_id), st = (t && t.state) || {};
    const props = arr(st.proposals).filter(x => x.kind === 'kc_tag' && x.problem_ref === p.ref);
    return [
      h('div', { class: 'row' }, ui.status('cho_duyet_tag'), ui.store('checkpoint'), ui.annot(['G2', 'agent:06', 'file:checkpoints.db'])),
      callout(ctx, 'warn', `Bài này chỉ nằm trong checkpoints.db (${p.thread_id}) — chưa có dòng problem trong tutor.db. 06 đã đề xuất ${props.length} nhóm top-5 KC; rubric là bản nháp của 02.`),
      h('p', { class: 'small muted' }, `Nhãn người soạn: ${arr(p.expected_kc).join(', ')} · độ khó ${p.expected_difficulty}/5`),
      h('h3', null, 'Đề bài'), tx(ctx, p.statement_latex, true),
      h('h3', null, 'Lời giải mẫu theo bước'), stepsBlock(ctx, p.solution_steps, () => []),
      h('div', { class: 'row' }, ui.button('Mở duyệt tag', () => { S.g2sel[p.thread_id] = p.ref; ctx.queue.open(p.thread_id); }, { kind: 'primary', cli: 'tutor review ' + p.thread_id }))
    ];
  }

  function editRubric(ctx, p) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup;
    const cur = L.rubricFor(p.id), v = cur ? cur.version + 1 : 1;
    const base = cur ? { items_json: cur.items_json, max_score: cur.max_score }
      : { items_json: arr(p.solution_steps).map((s, i) => ({ item_id: 'r' + (i + 1), text: firstPara(s.latex), points: 1 })), max_score: arr(p.solution_steps).length };
    let draft = base;
    ctx.modal({
      title: `${cur ? 'Sửa' : 'Viết'} rubric ${p.ref} → v${v}`, wide: true,
      body: h('div', { class: 'stack' },
        h('p', { class: 'small muted' }, cur ? `Lưu thành phiên bản mới v${v} (GV soạn, có approved_at). v${cur.version} vẫn giữ — bài đã chấm theo v${cur.version} vẫn trỏ tới nó (UNIQUE(problem_id, version)).`
          : 'Bản nháp tạo từ các bước lời giải mẫu, mỗi bước 1 điểm — thầy/cô sửa rồi lưu.'),
        ui.rubricEditor(base, { onChange: r => { draft = r; } })),
      actions: [{ label: 'Huỷ' }, {
        label: `Lưu rubric v${v}`, kind: 'primary', onClick: close => {
          if (!arr(draft.items_json).length || !(draft.max_score > 0)) return ctx.toast('Rubric cần ít nhất 1 mục và tổng điểm > 0.', { kind: 'warn' });
          if (draft.items_json.some(i => !String(i.text || '').trim())) return ctx.toast('Có mục rubric chưa có nội dung.', { kind: 'warn' });
          const d = ctx.data.db;
          if (d.rubric.some(r => r.problem_id === p.id && r.version === v)) return ctx.toast(`Đã có rubric v${v} cho ${p.ref}.`, { kind: 'warn' });
          d.rubric.push({ id: maxId(d.rubric) + 1, problem_id: p.id, version: v, items_json: draft.items_json, max_score: draft.max_score, approved_at: nowISO(ctx) });
          close();
          ctx.receipt(`Rubric ${p.ref} v${v} (GV soạn)`, [['rubric', 1]], { graph: null });
          if (viewTab() === 'bank') ctx.rerender();
          openDetail(ctx, p.ref);
        }
      }]
    });
  }

  function pairsModal(ctx, pid, pairs, note) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup, p = L.problem(pid) || { ref: '#' + pid };
    const rows = arr(pairs).filter(x => x.problem_a === pid || x.problem_b === pid);
    const me = x => (x.problem_a === pid ? 'a' : 'b');
    const res = x => (pairResult(x) === 'hoà' ? 'hoà' : pairResult(x) === me(x) ? 'khó hơn' : 'dễ hơn');
    const cnt = k => rows.filter(x => res(x) === k).length;
    const refOf = id => (L.problem(id) || { ref: '#' + id }).ref;
    ctx.modal({
      title: 'Các cặp so sánh · ' + p.ref, wide: true,
      body: h('div', { class: 'stack' },
        note ? callout(ctx, 'warn', note) : null,
        h('p', null, `${rows.length} cặp · bài này khó hơn ${cnt('khó hơn')} · dễ hơn ${cnt('dễ hơn')} · hoà ${cnt('hoà')} `, ui.prov('llm', '07'),
          h('span', { class: 'small muted' }, ' — mỗi cặp hỏi 2 lần (A,B) và (B,A); hai câu trả lời lệch nhau = hoà (khử thiên lệch thứ tự).')),
        ui.table({
          columns: [
            { label: 'A', render: x => h('span', { class: 'mono' + (x.problem_a === pid ? ' bk-me' : '') }, refOf(x.problem_a)) },
            { label: 'B', render: x => h('span', { class: 'mono' + (x.problem_b === pid ? ' bk-me' : '') }, refOf(x.problem_b)) },
            { label: 'Hỏi (A, B)', render: x => h('span', { class: 'small' }, refOf(x.harder_ab === 'a' ? x.problem_a : x.problem_b) + ' khó hơn') },
            { label: 'Hỏi (B, A)', render: x => h('span', { class: 'small' }, refOf(x.harder_ba === 'a' ? x.problem_a : x.problem_b) + ' khó hơn') },
            { label: 'Bài này', render: x => ui.chip(res(x), res(x) === 'hoà' ? 'warn' : res(x) === 'khó hơn' ? 'info' : 'neutral') }
          ],
          rows, empty: 'Bài này chưa được so cặp (δ chờ G3).'
        })),
      actions: [{ label: 'Đóng' }]
    });
  }

  /* ---------- G2: duyệt tag KC + rubric ---------- */
  function crumb(ctx) {
    return ctx.ui.h('nav', { class: 'bk-crumb', 'aria-label': 'Đường dẫn' }, link(ctx, 'bank', '← Ngân hàng bài'), ctx.ui.h('span', { class: 'muted' }, '·'), link(ctx, 'review', 'Hộp duyệt'));
  }

  function renderG2(root, ctx, id) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup, t = L.thread(id);
    root.append(crumb(ctx));
    if (!t || t.graph !== 'G2') {
      root.append(ui.pageHead({ title: 'Duyệt tag KC + rubric' }), callout(ctx, 'warn', `Không tìm thấy thread G2 “${id}”. `, link(ctx, 'bank', 'Về Ngân hàng bài')));
      return;
    }
    const st = t.state || (t.state = {}), probs = arr(st.problems), file = String(st.bank_file || t.subject || '');
    root.append(ui.pageHead({
      eyebrow: 'Ngân hàng bài › G2 · ' + id, title: 'Duyệt tag KC + rubric',
      lead: `${file} · ${probs.length || '—'} bài. 06 Tagger đề xuất top-5 KC cho từng bước lời giải, 02 Grader sinh rubric từ lời giải mẫu. Thầy/cô chọn KC và duyệt rubric từng bài; chỉ lựa chọn của thầy/cô được ghi.`,
      annot: ['G2', 'agent:06', '02 Grader · sinh rubric', 'table:problem_kc', 'table:rubric', 'file:checkpoints.db', 'cli:tutor review ' + id]
    }));
    if (t.status !== 'awaiting_review') {
      root.append(ui.graphStrip('G2', { done: G2_DONE.concat(['g2.review', 'g2.commit']) }), g2Done(ctx, t));
      return;
    }
    root.append(ui.graphStrip('G2', { current: 'g2.review', done: G2_DONE }));
    st.decisions = st.decisions || {}; st.done = st.done || {};
    const tagProps = () => arr(st.proposals).filter(x => x.kind === 'kc_tag');
    const rubProps = arr(st.proposals).filter(x => x.kind === 'rubric');
    const calls = arr(ctx.data.files.llm_log).filter(c => c.thread_id === id);
    if (!probs.some(p => p.ref === S.g2sel[id])) S.g2sel[id] = (probs.find(p => !st.done[p.ref]) || probs[0] || {}).ref;
    const chosenIds = ref => [...new Set(tagProps().filter(x => x.problem_ref === ref).flatMap(x => arr((st.decisions[x.pid] || {}).kc_ids)))];
    const nPk = () => { const s = new Set(); tagProps().forEach(x => arr((st.decisions[x.pid] || {}).kc_ids).forEach(k => s.add(x.problem_ref + '|' + k + '|' + x.step_idx))); return s.size; };

    const top = h('section', { class: 'section' }), listEl = h('div', { class: 'bk-g2-list' }), panel = h('div', { class: 'stack' });
    root.append(
      h('div', { class: 'callout callout-warn' }, h('p', null, ui.store('checkpoint'), ` ${probs.length} bài của ${file} đang nằm trong checkpoints.db, CHƯA vào tutor.db. Chỉ KC thầy/cô đánh dấu mới vào problem_kc; rubric đã duyệt vào bảng rubric — tất cả trong 1 transaction khi bấm “Ghi lô vào tutor.db”.`)),
      top,
      h('div', { class: 'bk-g2' },
        h('section', { class: 'section bk-g2-side' }, h('h2', null, 'Lô ' + probs.length + ' bài'), listEl),
        h('section', { class: 'section' }, panel)));

    function drawTop() {
      const done = probs.filter(p => st.done[p.ref]).length, left = probs.length - done;
      top.replaceChildren(
        secHead(ctx, 'Tiến độ duyệt', ['G2'], ui.costChip(calls)),
        h('div', { class: 'bk-prog' }, h('strong', { class: 'num' }, `Đã duyệt ${done}/${probs.length}`), ui.bar(done, probs.length || 1, { kind: left ? 'warn' : 'ok' })),
        h('div', { class: 'row bk-commit' },
          ui.button('Ghi lô vào tutor.db', () => commitG2(ctx, t), { kind: 'primary', cli: 'tutor review ' + id, disabledReason: left ? `còn ${left} bài chưa duyệt (cần ${probs.length}/${probs.length})` : null }),
          h('span', { class: 'small muted' }, `Sẽ ghi 1 transaction: +${probs.length} problem · +${nPk()} problem_kc · +${rubProps.length} rubric v1 · kc.embedding`)),
        h('p', { class: 'small muted' }, 'Không có nút duyệt cả lô — cố ý: thầy/cô quyết từng bài (NFR4).'));
    }
    function drawList() {
      listEl.replaceChildren(...probs.map(p => {
        const dn = !!st.done[p.ref], n = chosenIds(p.ref).length, sel = S.g2sel[id] === p.ref;
        return h('button', { type: 'button', class: 'bk-g2-item' + (sel ? ' is-sel' : '') + (dn ? ' is-done' : ''), 'aria-pressed': String(sel), onclick: () => { S.g2sel[id] = p.ref; drawList(); drawPanel(); } },
          h('span', { class: 'mono' }, p.ref), h('span', { class: 'small' + (dn ? ' bk-ok' : n ? '' : ' muted') }, dn ? '✓ đã duyệt' : n ? `${n} KC đã chọn` : 'chưa chọn'));
      }));
    }
    function drawAll() { drawTop(); drawList(); drawPanel(); }
    function drawPanel() {
      const ref = S.g2sel[id], p = probs.find(x => x.ref === ref);
      if (!p) { panel.replaceChildren(ui.empty('Chọn một bài ở danh sách.')); return; }
      const dn = !!st.done[ref];
      const props = tagProps().filter(x => x.problem_ref === ref).sort((a, b) => a.step_idx - b.step_idx);
      const rp = rubProps.find(x => x.problem_ref === ref);
      const acts = h('div', { class: 'row bk-g2-acts' });
      const drawActs = () => {
        const n = chosenIds(ref).length;
        acts.replaceChildren(...(dn
          ? [ui.status('approved'), h('span', { class: 'small muted' }, `${n} KC · rubric ${(st.decisions[rp && rp.pid] || rp || {}).max_score || 0} điểm — chờ “Ghi lô”`), ui.button('Mở lại để sửa', () => { st.done[ref] = false; drawAll(); }, { kind: 'ghost' })]
          : [ui.button('Duyệt bài này', approve, { kind: 'primary', disabledReason: n ? null : 'chọn ít nhất 1 KC cho bài này' }), h('span', { class: 'small muted' }, `${n} KC đã chọn`)]));
      };
      const approve = () => {
        const r = rp ? (st.decisions[rp.pid] || rp) : null;
        if (r && (!arr(r.items_json).length || !(r.max_score > 0))) return ctx.toast('Rubric cần ít nhất 1 mục và tổng điểm > 0.', { kind: 'warn' });
        if (r && r.items_json.some(i => !String(i.text || '').trim())) return ctx.toast('Có mục rubric chưa có nội dung.', { kind: 'warn' });
        if (rp && !st.decisions[rp.pid]) st.decisions[rp.pid] = { items_json: rp.items_json, max_score: rp.max_score };
        st.done[ref] = true;
        const left = probs.filter(x => !st.done[x.ref]);
        ctx.toast(`Đã duyệt ${ref}: ${chosenIds(ref).length} KC · rubric ${r ? r.max_score : 0} điểm.` + (left.length ? ` Còn ${left.length} bài.` : ' Đủ — có thể ghi lô vào tutor.db.'), { kind: 'ok' });
        const next = left.find(x => x.ref > ref) || left[0];
        if (next) S.g2sel[id] = next.ref;
        drawAll();
      };
      const stepEl = x => {
        const cur = () => arr((st.decisions[x.pid] || {}).kc_ids);
        const head = x.step_idx ? 'Bước ' + x.step_idx : 'Cả bài';
        const rows = arr(x.candidates).map(c => {
          const k = L.kc(c.kc_id) || { code: '#' + c.kc_id, name: '' };
          const cb = h('input', { type: 'checkbox', checked: cur().includes(c.kc_id), disabled: dn, 'aria-label': `Chọn ${k.code} cho ${head}` });
          const row = h('label', { class: 'bk-cand' }, cb, h('span', { class: 'bk-cand-main' },
            h('span', null, h('b', { class: 'mono' }, k.code), ' ', k.name),
            h('span', { class: 'small muted' }, c.cosine != null ? `cosine ${ui.fmt.num(c.cosine)} · hạng LLM #${c.llm_rank}` : 'GV thêm — không qua 06'),
            c.evidence_latex ? h('span', { class: 'small' }, 'bằng chứng: ', tx(ctx, c.evidence_latex)) : null,
            c.prereq_warning ? h('span', { class: 'bk-warnline' }, '⚠ ' + c.prereq_warning) : null));
          cb.addEventListener('change', () => {
            const dec = st.decisions[x.pid] || (st.decisions[x.pid] = { kc_ids: [] });
            dec.kc_ids = cb.checked ? [...new Set(arr(dec.kc_ids).concat(c.kc_id))] : arr(dec.kc_ids).filter(v => v !== c.kc_id);
            fade(); drawActs(); drawList(); drawTop();
          });
          return { row, cb };
        });
        const fade = () => { const any = rows.some(r => r.cb.checked); rows.forEach(r => { r.row.classList.toggle('is-on', r.cb.checked); r.row.classList.toggle('is-fade', any && !r.cb.checked); }); };
        fade();
        return h('div', { class: 'bk-stepbox' + (x.added_by === 'gv' ? ' is-gv' : '') },
          h('div', { class: 'spread' }, h('span', { class: 'eyebrow', title: 'step_idx ' + x.step_idx }, head), x.added_by === 'gv' ? ui.prov('gv', 'GV thêm') : ui.prov('llm', '06 top-5')),
          x.step_idx && x.step_latex ? tx(ctx, x.step_latex, true) : null, rows.map(r => r.row));
      };
      const rdec = rp ? (st.decisions[rp.pid] || { items_json: rp.items_json, max_score: rp.max_score }) : null;
      panel.replaceChildren(
        h('div', { class: 'section-head' }, h('div', null, h('h2', { class: 'mono' }, ref), dn ? ui.status('approved') : ui.status('waiting')),
          h('span', { class: 'small muted' }, `nhãn người soạn (chưa phải tag đã duyệt): ${arr(p.expected_kc).join(', ')} · độ khó ${p.expected_difficulty}/5`)),
        tx(ctx, p.statement_latex, true),
        h('h3', null, 'Chọn KC ', ui.prov('llm', '06'), ' ', ui.prov('gv', 'GV chọn'), ' ', ui.annot(['agent:06', 'table:problem_kc'])),
        h('p', { class: 'small muted' }, 'Cosine = độ gần giữa mô tả bước (06 viết) và mô tả KC, tính bằng MiniLM chạy trên máy; hạng LLM = 06 xếp lại 5 ứng viên. Chỉ KC được đánh dấu mới vào problem_kc. Cần ≥ 1 KC cho mỗi bài.'),
        props.length ? h('div', { class: 'stack' }, props.map(stepEl)) : ui.empty('06 không có đề xuất cho bài này — dùng “Thêm KC khác”.'),
        h('div', { class: 'row' }, ui.button('Thêm KC khác', () => addKc(ctx, t, ref, drawAll), { size: 'sm', disabledReason: dn ? 'bài đã duyệt — bấm “Mở lại để sửa”' : null })),
        h('h3', null, 'Rubric v' + (rp ? rp.version : 1) + ' ', ui.prov('llm', '02'), ' ', ui.annot(['02 Grader · sinh rubric', 'table:rubric'])),
        !rp ? ui.empty('02 chưa sinh rubric cho bài này.') : h('div', { class: 'stack' },
          h('p', { class: 'small muted' }, 'Mỗi mục ứng với một đoạn lời giải mẫu; tổng điểm = max_score do code cộng.'),
          dn ? rubricView(ctx, rdec) : ui.rubricEditor(rdec, { onChange: r => { st.decisions[rp.pid] = r; } }),
          h('div', { class: 'bk-alt' }, h('span', { class: 'small muted' }, 'Cách giải khác được chấp nhận: '),
            rp.alt_methods ? tx(ctx, rp.alt_methods, true) : h('span', { class: 'small muted' }, 'không có — lời giải mẫu chỉ có 1 cách.'))),
        acts);
      drawActs();
      ctx.tex(panel);
    }
    drawAll();
  }

  function g2Done(ctx, t) {
    const { ui } = ctx, h = ui.h, M = model(ctx);
    const f = arr(ctx.data.files.bank).find(b => String((t.state || {}).bank_file || t.subject || '').includes(b.file));
    const info = f ? topicInfo(ctx, M, f) : null;
    const next = !info ? null
      : info.g3t ? ui.button('Mở duyệt độ khó', () => ctx.queue.open(info.g3t.thread_id), { kind: 'primary', cli: 'tutor review ' + info.g3t.thread_id })
        : info.canG3 ? ui.button('Xếp độ khó', () => runG3(ctx, f), { kind: 'primary', cli: 'tutor bank difficulty', disabledReason: S.running[f.file] ? 'G3 đang chạy' : null })
          : null;
    return h('section', { class: 'section' },
      callout(ctx, 'ok', ui.store('db'), ` Lô này đã ghi vào tutor.db. Tag và rubric đã duyệt không sửa ở đây — rubric sửa thành phiên bản mới trong chi tiết bài.`),
      info ? ui.kv([['File', h('span', { class: 'mono' }, f.path)], ['Bài trong tutor.db', String(info.probs.length)], ['Đã tag', `${info.tagged}/${info.n}`], ['Có rubric', `${info.rub}/${info.n}`], ['Có δ', `${info.dl}/${info.n}`]]) : null,
      info && !info.g3t && info.dl < info.probs.length ? h('p', null, 'Bước tiếp theo: xếp độ khó (G3 chạy sau G2).') : null,
      h('div', { class: 'row' }, next, link(ctx, 'bank', 'Về Ngân hàng bài')));
  }

  function addKc(ctx, t, ref, after) {
    const { ui } = ctx, h = ui.h, d = ctx.data.db, st = t.state;
    const f = arr(ctx.data.files.bank).find(b => String(st.bank_file || '').endsWith(b.file));
    const grp = d.kc.find(k => f && k.code === f.kc_group) || d.kc.find(k => k.parent_id == null);
    const leaves = d.kc.filter(k => k.parent_id != null);
    const input = h('input', { type: 'search', placeholder: 'Gõ mã hoặc tên KC…', 'aria-label': 'Tìm KC' });
    const res = h('div', { class: 'bk-kc-res' });
    const pick = k => {
      const has = st.proposals.some(x => x.kind === 'kc_tag' && x.problem_ref === ref && arr((st.decisions[x.pid] || {}).kc_ids).includes(k.id));
      if (has) { ctx.toast(`${k.code} đã được chọn cho ${ref}.`, { kind: 'info' }); return; }
      const pid = 'x' + (st.proposals.filter(x => /^x\d+$/.test(x.pid)).length + 1);
      // added_by † mock-only: marks a teacher-added tag (no 06 candidate); written as problem_kc step_idx 0.
      st.proposals.push({ pid, kind: 'kc_tag', problem_ref: ref, step_idx: 0, step_latex: null, added_by: 'gv', candidates: [{ kc_id: k.id, cosine: null, llm_rank: null, evidence_latex: null, prereq_warning: null }] });
      st.decisions[pid] = { kc_ids: [k.id] };
      ctx.toast(`Đã thêm ${k.code} cho ${ref} (GV thêm, cả bài).`, { kind: 'ok' });
      after();
    };
    let m = null;
    const draw = () => {
      const q = input.value.trim().toLowerCase();
      const hits = leaves.filter(k => (q ? (k.code + ' ' + k.name).toLowerCase().includes(q) : k.parent_id === grp.id)).slice(0, 12);
      res.replaceChildren(...(hits.length ? hits.map(k => h('div', { class: 'bk-kc-hit' },
        h('div', null, h('b', { class: 'mono' }, k.code), ' ', k.name, h('div', { class: 'small muted' }, k.description)),
        ui.button('Chọn', () => { m.close(); pick(k); }, { size: 'sm' }))) : [ui.empty('Không có KC nào khớp — có thể tạo KC mới.')]));
    };
    input.addEventListener('input', draw);
    m = ctx.modal({
      title: 'Thêm KC khác cho ' + ref, wide: true,
      body: h('div', { class: 'stack' },
        h('p', { class: 'small muted' }, `Tìm trong ${leaves.length} KC của danh mục (để trống = nhóm ${grp.code}). KC thêm ở đây mang dấu “GV thêm” và ghi vào problem_kc với step_idx 0 (cả bài).`),
        input, res,
        h('div', { class: 'row' }, ui.button('Tạo KC mới', () => newKc(ctx, grp, k => { m.close(); pick(k); }), {}),
          h('span', { class: 'small muted' }, 'khi danh mục chưa có KC phù hợp — KC mới cũng hiện trong Danh mục.'))),
      actions: [{ label: 'Đóng' }]
    });
    draw();
  }

  function newKc(ctx, grp, onCreate) {
    const { ui } = ctx, h = ui.h, d = ctx.data.db;
    const groups = d.kc.filter(k => k.parent_id == null);
    const nextCode = g => g.code + '-' + pad(d.kc.filter(k => k.parent_id === g.id).reduce((m, k) => Math.max(m, parseInt(k.code.split('-').pop(), 10) || 0), 0) + 1);
    const code = h('input', { type: 'text', value: nextCode(grp), 'aria-label': 'Mã KC' });
    const name = h('input', { type: 'text', placeholder: 'VD: Đồ thị đi qua điểm cố định', 'aria-label': 'Tên KC' });
    const desc = h('textarea', { rows: 3, placeholder: 'Mô tả ngắn, rõ — 06 dùng để embedding', 'aria-label': 'Mô tả KC' });
    const gsel = h('select', { 'aria-label': 'Nhóm KC' }, groups.map(g => h('option', { value: String(g.id) }, g.code + ' · ' + g.name)));
    gsel.value = String(grp.id);
    gsel.addEventListener('change', () => { code.value = nextCode(groups.find(g => String(g.id) === gsel.value) || grp); });
    const f = (l, el) => h('label', { class: 'field' }, h('span', null, l), el);
    ctx.modal({
      title: 'Tạo KC mới',
      body: h('div', { class: 'stack' }, f('Nhóm', gsel), f('Mã KC (UNIQUE)', code), f('Tên', name), f('Mô tả (bắt buộc — dùng để embedding)', desc),
        h('p', { class: 'small muted' }, 'GV nhập thẳng vào bảng kc (không qua graph). Embedding của KC mới được tính khi ghi lô G2 (kc.embedding).')),
      actions: [{ label: 'Huỷ' }, {
        label: 'Tạo KC và chọn', kind: 'primary', onClick: close => {
          const c = code.value.trim().toUpperCase(), n = name.value.trim(), ds = desc.value.trim();
          const g = groups.find(x => String(x.id) === gsel.value) || grp;
          if (!/^[0-9A-Z]+(-[0-9A-Z]+)+$/.test(c)) return ctx.toast('Mã KC dạng NHÓM-SỐ, ví dụ ' + nextCode(g) + '.', { kind: 'warn' });
          if (d.kc.some(k => k.code === c)) return ctx.toast(`Mã ${c} đã có trong danh mục (code UNIQUE).`, { kind: 'warn' });
          if (!n || !ds) return ctx.toast('Cần nhập tên và mô tả KC (mô tả NOT NULL, 06 dùng để embedding).', { kind: 'warn' });
          const k = { id: maxId(d.kc) + 1, code: c, name: n, description: ds, parent_id: g.id, embed_model: null, created_at: nowISO(ctx), lop: g.lop, embedding_stale: true };
          d.kc.push(k);
          close();
          ctx.receipt('Tạo KC mới ' + c + ' (GV nhập)', [['kc', 1]], { graph: null });
          onCreate(k);
        }
      }]
    });
  }

  function commitG2(ctx, t) {
    if (t.status !== 'awaiting_review') { ctx.toast('Lô này đã ghi rồi.', { kind: 'info' }); return; }
    const st = t.state, probs = arr(st.problems), d = ctx.data.db, now = nowISO(ctx);
    if (probs.some(p => !st.done[p.ref])) { ctx.toast('Còn bài chưa duyệt.', { kind: 'warn' }); return; }
    const clash = probs.filter(p => d.problem.some(x => x.ref === p.ref));
    if (clash.length) { ctx.toast(`Trùng ref đã có: ${clash.map(p => p.ref).join(', ')} (problem.ref UNIQUE).`, { kind: 'error' }); return; }
    let pid = maxId(d.problem);
    const idOf = {};
    probs.forEach(p => {
      const row = { id: ++pid, ref: p.ref, statement_latex: p.statement_latex, solution_latex: p.solution_latex, source: st.bank_file, bt_score: null, delta: null, n_comparisons: 0, difficulty_approved_at: null, created_at: now,
        topic_file: p.topic_file, lop: p.lop, expected_kc: p.expected_kc, expected_difficulty: p.expected_difficulty, solution_steps: p.solution_steps };
      d.problem.push(row); idOf[p.ref] = row.id;
    });
    const seen = new Set();
    let nPk = 0;
    arr(st.proposals).filter(x => x.kind === 'kc_tag').forEach(x => arr((st.decisions[x.pid] || {}).kc_ids).forEach(k => {
      const key = x.problem_ref + '|' + k + '|' + x.step_idx;
      if (seen.has(key) || !idOf[x.problem_ref]) return;
      seen.add(key);
      const c = arr(x.candidates).find(cc => cc.kc_id === k);
      d.problem_kc.push({ problem_id: idOf[x.problem_ref], kc_id: k, step_idx: x.step_idx, evidence_latex: (c && c.evidence_latex) || null, approved_at: now });
      nPk++;
    }));
    let rid = maxId(d.rubric), nR = 0;
    arr(st.proposals).filter(x => x.kind === 'rubric').forEach(x => {
      if (!idOf[x.problem_ref]) return;
      const r = st.decisions[x.pid] || x;
      d.rubric.push({ id: ++rid, problem_id: idOf[x.problem_ref], version: x.version || 1, items_json: r.items_json, max_score: r.max_score, approved_at: now });
      nR++;
    });
    const model = (d.kc.find(k => k.embed_model) || {}).embed_model || null;
    d.kc.forEach(k => { if (k.embedding_stale || !k.embed_model) { k.embedding_stale = false; k.embed_model = model; } });
    const f = arr(ctx.data.files.bank).find(b => String(st.bank_file || '').endsWith(b.file));
    if (f) f.status = 'cho_do_kho';
    ctx.receipt('Lô ' + (f ? f.file : t.thread_id), [['problem', probs.length], ['problem_kc', nPk], ['rubric v1', nR], ['kc.embedding', 'cập nhật']], { graph: 'G2' });
    ctx.queue.resolve(t.thread_id);
    ctx.rerender();
  }

  /* ---------- G3: xếp độ khó ---------- */
  // shortcut: 07's two answers are simulated from the author's do_kho_du_kien label (ties split deterministically, some disagree = hoà); the real G3 asks the LLM.
  function ask07(pa, pb) {
    const dd = (pa.expected_difficulty || 3) - (pb.expected_difficulty || 3);
    if (dd) return dd > 0 ? ['a', 'a'] : ['b', 'b'];
    return [['a', 'a'], ['b', 'b'], ['a', 'b'], ['b', 'a']][(pa.id * 7 + pb.id * 13) % 4];
  }
  // bt.py: Bradley-Terry by MM iterations; each answer is one game (disagreeing pair = one win each).
  // Prior: 3 wins + 3 losses vs a virtual problem of strength 1 — keeps δ on the mock bank's ±1.3 scale.
  function btFit(ids, pairs) {
    const p = {}, w = {}, opp = {};
    ids.forEach(i => { p[i] = 1; w[i] = 3; opp[i] = []; });
    pairs.forEach(x => [x.harder_ab, x.harder_ba].forEach(r => { w[r === 'a' ? x.problem_a : x.problem_b] += 1; opp[x.problem_a].push(x.problem_b); opp[x.problem_b].push(x.problem_a); }));
    for (let it = 0; it < 200; it++) {
      const np = {};
      ids.forEach(i => { np[i] = w[i] / (6 / (p[i] + 1) + opp[i].reduce((s, j) => s + 1 / (p[i] + p[j]), 0)); });
      const g = Math.exp(ids.reduce((s, i) => s + Math.log(np[i]), 0) / ids.length);
      ids.forEach(i => { p[i] = np[i] / g; });
    }
    const out = {};
    ids.forEach(i => { out[i] = Math.log(p[i]); });
    return out;
  }

  function buildG3(ctx, f, probs, steps) {
    const L = ctx.lookup, M = model(ctx), n = probs.length;
    const K = Math.max(1, Math.min(5, Math.floor((n - 1) / 2)));
    const seen = new Set(), pairs = [];
    probs.forEach((a, i) => {
      for (let s = 1; s <= K; s++) {
        const b = probs[(i + s) % n], lo = Math.min(a.id, b.id), hi = Math.max(a.id, b.id), key = lo + '-' + hi;
        if (lo === hi || seen.has(key)) continue;
        seen.add(key);
        const [ab, ba] = ask07(L.problem(lo), L.problem(hi));
        pairs.push({ problem_a: lo, problem_b: hi, harder_ab: ab, harder_ba: ba });
      }
    });
    const bt = btFit(probs.map(p => p.id), pairs);
    const nComp = id => pairs.filter(x => x.problem_a === id || x.problem_b === id).length;
    const byKc = new Map();
    probs.forEach(p => {
      const first = arr(M.kcOf.get(p.id)).slice().sort((a, b) => a.step_idx - b.step_idx)[0];
      const k = first ? first.kc_id : null;
      byKc.set(k, (byKc.get(k) || []).concat(p.id));
    });
    const code = k => (L.kc(k) || { code: '' }).code;
    const proposals = [...byKc.entries()].sort((a, b) => (code(a[0]) < code(b[0]) ? -1 : 1)).map(([kc, ids], i) => ({
      pid: 'd' + (i + 1), kind: 'difficulty', kc_id: kc,
      pairs: pairs.filter(x => ids.includes(x.problem_a) || ids.includes(x.problem_b)),
      ranking: ids.map(id => ({ problem_id: id, bt_score: +bt[id].toFixed(4), delta: +(0.6 * bt[id]).toFixed(2), n_comparisons: nComp(id), teacher_adjusted: false })).sort((a, b) => a.bt_score - b.bt_score)
    }));
    let tid = 'g3-' + f.kc_group, k = 2;
    while (L.thread(tid)) tid = 'g3-' + f.kc_group + '-' + k++;
    const now = nowISO(ctx);
    return {
      thread_id: tid, graph: 'G3', subject: 'Độ khó ' + f.kc_group, student_id: null, session_id: null, started_at: now,
      status: 'awaiting_review', current_node: 'g3.review', interrupted_at: 'g3.review', error: null,
      checkpoints: steps.map(s => ({ node: s.node, at: now, ms: s.ms || 0, tokens_in: s.tokens_in || 0, tokens_out: s.tokens_out || 0 })),
      demo_run: null,
      state: { kc_group: f.kc_group, proposals, decisions: {}, simulated: true } // simulated † mock-only: 07 answers were simulated in this draft
    };
  }

  function runG3(ctx, f) {
    const { ui } = ctx, h = ui.h, d = ctx.data.db, M = model(ctx);
    if (S.running[f.file]) { ctx.toast('G3 đang chạy cho ' + f.file + '.', { kind: 'info' }); return; }
    const probs = d.problem.filter(p => p.topic_file === f.file && !p.difficulty_approved_at).sort((a, b) => a.id - b.id);
    if (probs.length < 2) { ctx.toast('Không đủ bài để so cặp (cần ≥ 2 bài chưa có δ).', { kind: 'warn' }); return; }
    if (probs.some(p => !M.kcOf.has(p.id))) { ctx.toast('Có bài chưa tag KC đã duyệt — G3 chạy sau G2.', { kind: 'warn' }); return; }
    // Timings and LLM calls replay the latest real G3 run in the mock (template), re-labelled for this thread.
    const tpl = M.th.filter(t => t.graph === 'G3' && arr(t.checkpoints).length).sort((a, b) => (a.started_at < b.started_at ? 1 : -1))[0];
    const tplCalls = tpl ? arr(ctx.data.files.llm_log).filter(c => c.thread_id === tpl.thread_id) : [];
    const steps = ['g3.pair', 'g3.07_difficulty', 'g3.bt_fit', 'g3.review'].map(node => { const c = arr(tpl && tpl.checkpoints).find(x => x.node === node) || {}; return { node, ms: c.ms, tokens_in: c.tokens_in, tokens_out: c.tokens_out }; });
    S.running[f.file] = true;
    const strip = ui.graphStrip('G3', {}), out = h('div', { class: 'stack', 'aria-live': 'polite' }, h('p', { class: 'small muted' }, 'Đang chạy…'));
    ctx.modal({
      title: 'Xếp độ khó · ' + f.file, wide: true,
      body: h('div', { class: 'stack' },
        h('p', null, `${probs.length} bài · ghép cặp trong chủ đề ~10 cặp/bài → 07 hỏi 2 chiều (A,B) và (B,A) → bt.py fit Bradley-Terry → DỪNG chờ thầy/cô.`),
        ui.cli('tutor bank difficulty'), strip, out),
      actions: [{ label: 'Đóng' }]
    });
    if (viewTab() === 'bank') ctx.rerender();
    return ui.animateGraph(strip, steps, { stepMs: 450 }).then(() => {
      S.running[f.file] = false;
      const thread = buildG3(ctx, f, probs, steps);
      const calls = tplCalls.map(c => Object.assign({}, c, { ts: nowISO(ctx), thread_id: thread.thread_id }));
      const log = ctx.data.files.llm_log;
      calls.forEach(c => log.push(c));
      ctx.queue.add(thread);
      const nPairs = uniquePairs(thread.state.proposals).length;
      out.replaceChildren(
        callout(ctx, 'warn', ui.store('checkpoint'), ` G3 dừng chờ duyệt: ${nPairs} cặp, ${probs.length} δ đề xuất cho ${thread.state.proposals.length} KC — chưa ghi vào tutor.db.`),
        h('div', { class: 'row' }, ui.costChip(calls), h('span', { class: 'small muted' }, `${calls.length} lời gọi 07 (bản nháp: lặp lại số đo của ${tpl ? tpl.thread_id : '—'})`)),
        h('div', { class: 'row' }, ui.button('Mở duyệt độ khó', () => ctx.queue.open(thread.thread_id), { kind: 'primary', cli: 'tutor review ' + thread.thread_id })));
      ctx.toast(`G3 ${f.kc_group} đã tới DỪNG — chờ duyệt (${nPairs} cặp, ${probs.length} δ).`, { kind: 'ok' });
      if (viewTab() === 'bank') ctx.rerender();
    });
  }

  function renderG3(root, ctx, id) {
    const { ui } = ctx, h = ui.h, L = ctx.lookup, t = L.thread(id);
    root.append(crumb(ctx));
    if (!t || t.graph !== 'G3') {
      root.append(ui.pageHead({ title: 'Duyệt xếp hạng độ khó' }), callout(ctx, 'warn', `Không tìm thấy thread G3 “${id}”. `, link(ctx, 'bank', 'Về Ngân hàng bài')));
      return;
    }
    const st = t.state || (t.state = {}), props = arr(st.proposals), live = t.status === 'awaiting_review';
    st.decisions = st.decisions || {};
    const all = uniquePairs(props), nProb = props.reduce((s, pp) => s + arr(pp.ranking).length, 0);
    const btOf = new Map(props.flatMap(pp => arr(pp.ranking).map(r => [r.problem_id, r.bt_score])));
    const decisive = all.filter(x => pairResult(x) !== 'hoà');
    const against = decisive.filter(x => { const [hi, lo] = x.harder_ab === 'a' ? [x.problem_a, x.problem_b] : [x.problem_b, x.problem_a]; return btOf.get(hi) < btOf.get(lo); }).length;
    const draftNote = h('p', { class: 'small' }, st.simulated
      ? `Bản nháp: trả lời của 07 ở lô này được giả lập từ nhãn độ khó của người soạn; bt.py fit từ chính các cặp này${against ? ` — ${against}/${decisive.length} cặp phân thắng bại vẫn ngược thứ tự bt_score (fit cả lô, có prior)` : ''}.`
      : `Bản nháp: bt_score của lô mẫu này lấy từ δ ÷ 0.6, không fit từ các cặp bên dưới — ${against}/${decisive.length} cặp phân thắng bại ngược thứ tự bt_score. Bản thật: bt.py fit từ chính các cặp này.`);
    root.append(ui.pageHead({
      eyebrow: 'Ngân hàng bài › G3 · ' + id, title: 'Duyệt xếp hạng độ khó',
      lead: `${st.kc_group || t.subject} · ${nProb || '—'} bài · ${all.length} cặp; mỗi cặp hỏi 07 hai lần (A,B) và (B,A), trả lời lệch nhau = hoà. Cặp ghép trong cả chủ đề (spec §5: cặp bài cùng chủ đề), nên có cặp nối hai KC; bảng chia theo KC đầu tiên của bài. bt.py fit Bradley-Terry ra bt_score; δ = 0.6 × bt_score (giả định bản nháp).`,
      annot: ['G3', 'agent:07', 'bt.py', 'table:problem_pair', 'table:problem', 'cli:tutor review ' + id]
    }));
    root.append(ui.graphStrip('G3', live ? { current: 'g3.review', done: G3_DONE } : { done: G3_DONE.concat(['g3.review', 'g3.commit']) }));
    root.append(live
      ? h('div', { class: 'callout callout-warn' }, h('p', null, ui.store('checkpoint'), ` Xếp hạng và ${all.length} cặp đang nằm trong checkpoints.db. Khi duyệt, δ được ghi vào problem và khoá — không cập nhật theo bài làm của HS (tránh lệch khi vừa chọn bài theo δ vừa sửa δ — spec §8).`),
        draftNote)
      : h('div', { class: 'callout callout-ok' }, h('p', null, ui.store('db'), ' Đã duyệt — δ đã ghi vào problem và khoá; các cặp nằm trong problem_pair để fit lại khi thêm bài.'), props.length ? draftNote : null));
    if (!props.length) {
      const f = arr(ctx.data.files.bank).find(b => b.kc_group === st.kc_group || ('Độ khó ' + b.kc_group) === t.subject);
      const rows = f ? ctx.data.db.problem.filter(p => p.topic_file === f.file).sort((a, b) => (a.delta || 0) - (b.delta || 0)) : [];
      root.append(h('section', { class: 'section' }, secHead(ctx, 'δ đã duyệt của chủ đề', ['table:problem']),
        ui.table({ columns: [{ label: 'Mã bài', render: p => h('span', { class: 'mono' }, p.ref) }, { label: 'δ', align: 'right', render: p => h('span', { class: 'num' }, ui.fmt.signed(p.delta), p.difficulty_approved_at ? lockIcon(ctx) : null) }, { label: 'Số lần so sánh', align: 'right', render: p => String(p.n_comparisons) }], rows, empty: 'Thread lịch sử không còn state chi tiết.' })));
      return;
    }
    if (!props.some(pp => pp.pid === S.g3kc[id])) S.g3kc[id] = props[0].pid;
    const order = pp => {
      const o = arr((st.decisions[pp.pid] || {}).ranking);
      return o.length === arr(pp.ranking).length ? o : arr(pp.ranking).map(r => r.problem_id);
    };
    const record = {};
    all.forEach(x => {
      const r = pairResult(x);
      [x.problem_a, x.problem_b].forEach(id2 => { record[id2] = record[id2] || { w: 0, l: 0, t: 0 }; });
      if (r === 'hoà') { record[x.problem_a].t++; record[x.problem_b].t++; } else { record[r === 'a' ? x.problem_a : x.problem_b].w++; record[r === 'a' ? x.problem_b : x.problem_a].l++; }
    });
    const panel = h('div', { class: 'stack' });
    const sec = h('section', { class: 'section' },
      secHead(ctx, 'Xếp hạng theo KC', ['agent:07', 'bt.py']),
      ui.segmented(props.map(pp => ({ id: pp.pid, label: (L.kc(pp.kc_id) || { code: '?' }).code + ' · ' + arr(pp.ranking).length + ' bài' })), S.g3kc[id], v => { S.g3kc[id] = v; drawPanel(); }),
      panel);
    const foot = h('section', { class: 'section' });
    root.append(sec, foot);

    function drawPanel(flashPid) {
      const pp = props.find(x => x.pid === S.g3kc[id]), kc = L.kc(pp.kc_id) || { code: '?', name: '' };
      const ord = order(pp), slots = arr(pp.ranking);
      const ties = arr(pp.pairs).filter(x => pairResult(x) === 'hoà').length;
      const mine = new Set(arr(pp.ranking).map(r => r.problem_id)), cross = arr(pp.pairs).filter(x => !mine.has(x.problem_a) || !mine.has(x.problem_b)).length;
      const move = (i, dir) => {
        const o = ord.slice(); [o[i], o[i + dir]] = [o[i + dir], o[i]];
        st.decisions[pp.pid] = { ranking: o };
        drawPanel(o[i + dir]); drawFoot();
      };
      const rows = ord.map((pid, i) => ({ i, pid, p: L.problem(pid) || { ref: '#' + pid }, own: slots.find(r => r.problem_id === pid) || {}, slot: slots[i] || {}, adj: (slots[i] || {}).problem_id !== pid }));
      const whyDelta = r => () => h('div', { class: 'stack' }, ui.kv([
        ['bt_score (bt.py)', ui.fmt.signed(r.own.bt_score, 4)],
        ['δ gốc = 0.6 × bt_score', ui.fmt.signed(r.own.delta)],
        ['Kết quả so cặp', `khó hơn ${(record[r.pid] || {}).w || 0} · dễ hơn ${(record[r.pid] || {}).l || 0} · hoà ${(record[r.pid] || {}).t || 0}`],
        ['GV chỉnh', r.adj ? `đổi chỗ → nhận δ của hạng ${r.i + 1}: ${ui.fmt.signed(r.slot.delta)}` : 'không']]),
        h('p', { class: 'small muted' }, '† 0.6 là giả định bản nháp — cách đổi BT → δ chưa chốt (tài liệu thiết kế §11.4). Đổi chỗ giữ nguyên dãy δ, chỉ đổi bài nào nhận δ nào.'), ui.prov('code'));
      const rankTable = ui.table({
        columns: [
          { label: 'Hạng', align: 'center', render: r => h('span', { class: 'num' }, String(r.i + 1)) },
          { label: 'Mã bài', render: r => h('span', { class: 'mono nowrap' }, r.p.ref) },
          { label: 'Đề', render: r => h('div', { class: 'bk-one bk-one-sm' }, tx(ctx, oneLine(r.p.statement_latex))) },
          { label: 'Nhãn người soạn', align: 'center', render: r => h('span', { class: 'small muted' }, `${r.p.expected_difficulty}/5`) },
          { label: 'bt_score', align: 'right', render: r => h('span', { class: 'num' }, ui.fmt.signed(r.own.bt_score, 4)) },
          { label: 'δ', align: 'right', render: r => h('span', { class: 'num nowrap' + (r.adj ? ' bk-adj' : '') }, ui.fmt.signed(r.slot.delta), live ? null : lockIcon(ctx), ' ', ui.why(whyDelta(r))) },
          { label: 'Số lần so', align: 'right', render: r => h('span', { class: 'num' }, String(r.own.n_comparisons || 0)) },
          { label: 'Đổi chỗ', render: r => (live ? h('div', { class: 'bk-mv' },
            r.i > 0 ? mvBtn('▲', `Đưa ${r.p.ref} lên (dễ hơn)`, () => move(r.i, -1)) : h('span', { class: 'bk-mv-gap' }),
            r.i < rows.length - 1 ? mvBtn('▼', `Đưa ${r.p.ref} xuống (khó hơn)`, () => move(r.i, 1)) : h('span', { class: 'bk-mv-gap' })) : h('span', { class: 'small muted' }, 'đã khoá')) },
          { label: '', render: r => h('div', { class: 'row' }, r.adj ? ui.prov('gv', 'GV chỉnh') : null, ui.button('Xem cặp', () => pairsModal(ctx, r.pid, all, live ? 'Các cặp này chỉ nằm trong checkpoints.db, chưa ghi vào problem_pair.' : null), { size: 'sm', kind: 'ghost', title: 'Xem các cặp so sánh' })) }
        ],
        rows, rowClass: r => (r.pid === flashPid ? 'flash-hl' : r.adj ? 'bk-adj-row' : null)
      });
      const pairRows = arr(pp.pairs);
      const refOf = x => (L.problem(x) || { ref: '#' + x }).ref;
      put(panel,
        h('p', null, h('b', { class: 'mono' }, kc.code), ' ', kc.name, h('span', { class: 'small muted' }, ` · ${rows.length} bài · ${pairRows.length} cặp có bài của KC này (${cross} cặp với bài KC khác) · ${ties} hoà · hạng 1 = dễ nhất`)),
        rows.length < 2 ? callout(ctx, 'info', 'KC này chỉ có 1 bài — không đủ bài để so cặp trong KC; δ của bài lấy từ các cặp với bài cùng chủ đề (KC khác).') : null,
        rankTable,
        h('h3', null, 'Các cặp so sánh ', ui.prov('llm', '07'), ' ', ui.annot(['table:problem_pair'])),
        h('div', { class: 'bk-scroll' }, ui.table({
          columns: [
            { label: 'A', render: x => h('span', { class: 'mono' }, refOf(x.problem_a)) },
            { label: 'B', render: x => h('span', { class: 'mono' }, refOf(x.problem_b)) },
            { label: 'Trả lời (A, B)', render: x => h('span', { class: 'small' }, refOf(x.harder_ab === 'a' ? x.problem_a : x.problem_b) + ' khó hơn') },
            { label: 'Trả lời (B, A)', render: x => h('span', { class: 'small' }, refOf(x.harder_ba === 'a' ? x.problem_a : x.problem_b) + ' khó hơn') },
            { label: 'Kết quả', render: x => { const r = pairResult(x); return ui.chip(r === 'hoà' ? 'hoà (lệch)' : r.toUpperCase() + ' khó hơn', r === 'hoà' ? 'warn' : 'neutral'); } }
          ],
          rows: pairRows, empty: 'Không có cặp nào.'
        })));
      ctx.tex(panel);
    }
    function drawFoot() {
      const adj = props.reduce((s, pp) => { const o = order(pp); return s + o.filter((pid, i) => arr(pp.ranking)[i].problem_id !== pid).length; }, 0);
      foot.replaceChildren(live
        ? h('div', { class: 'stack' },
          secHead(ctx, 'Duyệt và khoá δ', ['G3', 'table:problem_pair', 'table:problem']),
          h('p', { class: 'small muted' }, `Sẽ ghi 1 transaction: +${all.length} problem_pair · ${nProb} δ (problem.bt_score, delta, difficulty_approved_at)` + (adj ? ` · ${adj} bài GV đổi chỗ` : '') + '. Sau khi duyệt, δ cố định.'),
          h('div', { class: 'row' }, ui.button('Duyệt độ khó', () => commitG3(ctx, t), { kind: 'primary', cli: 'tutor review ' + id })))
        : h('div', { class: 'row' }, link(ctx, 'bank', 'Về Ngân hàng bài'), link(ctx, 'recommend', 'Bài sẵn sàng là ứng viên trong Gợi ý bài')));
    }
    function mvBtn(label, aria, fn) {
      const b = ui.button(label, fn, { size: 'sm', kind: 'secondary', title: aria });
      b.setAttribute('aria-label', aria);
      return b;
    }
    drawPanel(); drawFoot();
  }

  function commitG3(ctx, t) {
    if (t.status !== 'awaiting_review') { ctx.toast('Lô độ khó này đã duyệt rồi.', { kind: 'info' }); return; }
    const st = t.state, d = ctx.data.db, L = ctx.lookup, now = nowISO(ctx);
    let nd = 0;
    arr(st.proposals).forEach(pp => {
      const o = arr((st.decisions[pp.pid] || {}).ranking), ord = o.length === arr(pp.ranking).length ? o : arr(pp.ranking).map(r => r.problem_id);
      ord.forEach((pid, i) => {
        const p = L.problem(pid), own = arr(pp.ranking).find(r => r.problem_id === pid);
        if (!p || !own) return;
        p.bt_score = own.bt_score; p.delta = pp.ranking[i].delta; p.n_comparisons = own.n_comparisons; p.difficulty_approved_at = now;
        nd++;
      });
    });
    const pairs = uniquePairs(st.proposals);
    let pid = maxId(d.problem_pair);
    pairs.forEach(x => d.problem_pair.push({ id: ++pid, problem_a: x.problem_a, problem_b: x.problem_b, harder_ab: x.harder_ab, harder_ba: x.harder_ba, created_at: now }));
    const f = arr(ctx.data.files.bank).find(b => b.kc_group === st.kc_group);
    if (f) f.status = 'ready';
    ctx.receipt('Độ khó ' + st.kc_group, [['problem_pair', pairs.length], [nd + ' δ', 'cập nhật']], { graph: 'G3' });
    ctx.queue.resolve(t.thread_id);
    ctx.rerender();
  }
})();
