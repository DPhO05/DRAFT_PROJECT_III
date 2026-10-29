/* Học sinh (IA §3.6): read view of tutor.db per student — every number by code, 05 Profiler only writes the summary. */
(() => {
  'use strict';
  const SUBS = [
    { id: 'progress', label: 'Tiến bộ' }, { id: 'skills', label: 'Kỹ năng (Elo)' }, { id: 'misconceptions', label: 'Lỗi đã ghi' },
    { id: 'history', label: 'Lịch sử buổi' }, { id: 'outputs', label: 'Gợi ý & báo cáo' }
  ];
  const CATS = [['computational', 'Tính toán'], ['conceptual', 'Khái niệm'], ['notational', 'Ký hiệu'], ['presentation', 'Trình bày'], ['other', 'Khác']];
  const BUCKET = { review: ['ôn', 'info'], zpd: ['vừa sức', 'ok'], challenge: ['thử thách', 'warn'] };
  // Per-page view state; params on each nav override it.
  const S = { grade: 'all', archived: false, sub: {}, kc: {}, editing: null, replay: {}, running: null, token: 0 };

  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const mean = (v) => (v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0);
  const dm = (d) => { const m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(d || '')); return m ? m[2] + '/' + m[1] : '—'; };
  const pad2 = (n) => String(n).padStart(2, '0');
  const n2 = (x) => (+x).toFixed(2);
  const p2 = (x) => (x < 0 ? '(' + n2(x) + ')' : n2(x));

  App.registerTab('students', { title: 'Học sinh', render });

  function render(root, ctx) {
    const token = ++S.token;
    const p = ctx.params;
    const st = findStudent(ctx, p.student);
    if (st) {
      if (SUBS.some((s) => s.id === p.tab)) S.sub[st.id] = p.tab;
      const k = p.kc ? findKc(ctx, p.kc) : null;
      if (k) { S.kc[st.id] = k.id; if (!p.tab) S.sub[st.id] = 'skills'; }
    }
    S.editing = null;
    const E = { ctx, ui: ctx.ui, h: ctx.ui.h, fmt: ctx.ui.fmt, calc: ctx.calc, db: ctx.data.db, token, root };
    E.today = (ctx.data.meta || {}).today || '2026-10-21';
    E.month = E.today.slice(0, 7);
    E.paint = () => {
      if (token !== S.token) return;
      E.cur = E.calc.currentMistakes(E.db);
      E.attSession = new Map(E.db.attempt.map((a) => [a.id, a.session_id]));
      let body;
      if (p.student && !st) body = notFound(E, p.student);
      else body = st ? profileView(E, st) : listView(E);
      root.replaceChildren(body);
      ctx.tex(root);
    };
    E.paint();
  }

  /* ---------------- lookups + derived numbers (all from db / TutorCalc) ---------------- */
  function findStudent(ctx, v) {
    if (v == null || v === '') return null;
    return (/^\d+$/.test(String(v)) && ctx.lookup.student(+v)) || ctx.lookup.studentByCode(String(v).toUpperCase()) || null;
  }
  function findKc(ctx, v) { return (/^\d+$/.test(String(v)) && ctx.lookup.kc(+v)) || ctx.lookup.kcByCode(String(v)) || null; }
  function code(E, s) { return E.ctx.lookup.studentCode(s); }
  function nowISO(E) { const d = new Date(); return E.today + 'T' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()) + 'Z'; }

  function derive(E, sid) {
    const db = E.db;
    const sessions = db.session.filter((s) => s.student_id === sid).sort((a, b) => cmp(a.held_on, b.held_on) || a.id - b.id);
    const done = sessions.filter((s) => s.status === 'committed');
    const supA = new Set(db.attempt.filter((a) => a.supersedes_id != null).map((a) => a.supersedes_id));
    const sIds = new Set(sessions.map((s) => s.id));
    const atts = db.attempt.filter((a) => sIds.has(a.session_id) && !supA.has(a.id));
    const attBy = {};
    atts.forEach((a) => (attBy[a.session_id] = attBy[a.session_id] || []).push(a));
    const attIds = new Set(atts.map((a) => a.id));
    const mistakes = E.cur.filter((m) => attIds.has(m.attempt_id));
    const misBy = {};
    mistakes.forEach((m) => { const s = E.attSession.get(m.attempt_id); (misBy[s] = misBy[s] || []).push(m); });
    const events = db.skill_event.filter((e) => e.student_id === sid).sort((a, b) => a.id - b.id);
    const evBy = {};
    events.forEach((e) => { const s = E.attSession.get(e.attempt_id); (evBy[s] = evBy[s] || []).push(e); });
    const states = db.skill_state.filter((x) => x.student_id === sid);
    const mis = db.misconception_log.filter((x) => x.student_id === sid);
    const th = {};
    const series = done.map((s) => { (evBy[s.id] || []).forEach((e) => (th[e.kc_id] = e.theta_after)); return { s, y: mean(Object.values(th)) }; });
    const doneAtts = done.flatMap((s) => attBy[s.id] || []);
    return {
      sessions, done, attBy, misBy, events, evBy, states, mis, series, doneAtts, mistakes,
      last: done[done.length - 1] || null,
      thetaMean: states.length ? mean(states.map((x) => x.theta)) : 0,
      repeatOpen: mis.filter((m) => !m.resolved_at && m.count >= 2),
      monthDone: done.filter((s) => s.held_on.slice(0, 7) === E.month)
    };
  }

  /* ---------------- small builders ---------------- */
  function section(E, title, annot, extra, ...body) {
    const { h, ui } = E;
    return h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? ui.annot(annot) : null), extra || null), ...body);
  }
  function kcLabel(E, kcId, short) {
    const k = E.ctx.lookup.kc(kcId);
    if (!k) return E.h('span', { class: 'muted' }, 'KC #' + kcId);
    return E.h('span', { class: 'stu-kc', title: k.description || k.name }, E.h('span', { class: 'mono' }, k.code), short ? null : E.h('span', null, k.name));
  }
  function codeChip(E, c) {
    const e = E.ctx.lookup.errorCode(c);
    return E.h('span', { class: 'chip chip-wrap', title: c }, e ? e.description : c);
  }
  function resolvedChip(E, x, kind) {
    const e = E.ctx.lookup.errorCode(x.code), k = E.ctx.lookup.kc(x.kc_id);
    return E.h('span', { class: 'chip chip-wrap chip-' + kind, title: x.code + (k ? ' · ' + k.code : '') }, (e ? e.description : x.code) + (k ? ' · ' + k.name : ''));
  }
  function catOf(E, c) { const e = E.ctx.lookup.errorCode(c); return e ? e.category : String(c).split('.')[0]; }
  function signedEl(E, x, d) { return E.h('span', { class: 'num stu-signed ' + (x > 0.0005 ? 'is-pos' : x < -0.0005 ? 'is-neg' : '') }, E.fmt.signed(x, d)); }
  function pre(E, text) { return E.h('pre', { class: 'code' }, text); }

  /* ---------------- list view ---------------- */
  function listView(E) {
    const { h, ui, ctx, fmt } = E;
    const all = E.db.student;
    const rows = all.filter((s) => (S.grade === 'all' || String(s.grade) === S.grade) && (S.archived || !s.archived_at));
    const nArch = all.filter((s) => s.archived_at).length;
    const D = new Map(rows.map((s) => [s.id, derive(E, s.id)]));
    const open = (s) => ctx.nav('students', { student: s.id });

    const head = ui.pageHead({
      lead: 'Trạng thái đã duyệt của từng học sinh — đọc từ tutor.db. Mọi con số do code tính; 05 Profiler chỉ viết đoạn tóm tắt.',
      actions: [ui.button('Thêm học sinh', () => addStudent(E), { kind: 'primary' })],
      annot: ['agent:05', 'file:tutor.db', 'table:student', 'table:skill_state']
    });

    const filters = h('div', { class: 'stu-filters' },
      ui.segmented([{ id: 'all', label: 'Tất cả' }, { id: '9', label: 'Lớp 9' }, { id: '8', label: 'Lớp 8' }], S.grade, (v) => { S.grade = v; E.paint(); }),
      h('label', { class: 'stu-check' },
        h('input', { type: 'checkbox', checked: S.archived, onchange: (e) => { S.archived = e.target.checked; E.paint(); } }),
        'Hiện HS đã lưu trữ (' + nArch + ')'),
      h('span', { class: 'muted small' }, rows.length + '/' + all.length + ' học sinh'));

    const thetaWhy = ui.why(() => h('div', { class: 'stack' },
      h('p', null, 'θ TB = trung bình θ trên mọi KC học sinh đã làm (bảng skill_state). Đường nhỏ: θ TB sau từng buổi đã duyệt.'),
      ui.latex('\\theta_{\\text{sau}} = \\theta + K\\,(X - P),\\quad P = \\dfrac{1}{1 + e^{-(\\theta - \\delta)}}', { block: true }),
      h('p', { class: 'small muted' }, 'K = ' + elo(E).K + ', θ ban đầu = ' + elo(E).theta0 + ' (cố định theo spec §8). X = 0 nếu bài có lỗi đã duyệt gắn KC đó.')));
    const repWhy = ui.why(() => h('div', { class: 'stack' },
      h('p', null, 'Lỗi lặp = dòng misconception_log có count ≥ 2 và resolved_at còn trống. Cột này đếm số dòng như vậy.'),
      h('p', { class: 'small muted' }, 'Một lỗi “hết” khi KC của nó đạt ' + need(E) + ' lần đúng liên tiếp sau lần sai cuối (settings.misconception.resolve_streak).')));

    const table = ui.table({
      columns: [
        { label: 'Mã', render: (s) => h('span', { class: 'mono' }, code(E, s)) },
        { label: ['Tên ', h('span', { class: 'muted small' }, '(chỉ lưu trên máy)')], render: (s) => [h('strong', null, s.name), s.note ? h('div', { class: 'muted small' }, s.note) : null] },
        { label: 'Lớp', align: 'center', render: (s) => String(s.grade) },
        { label: 'Buổi gần nhất', render: (s) => { const l = D.get(s.id).last; return l ? [fmt.date(l.held_on), h('div', { class: 'muted small' }, fmt.ago(l.held_on))] : h('span', { class: 'muted' }, 'chưa có'); } },
        { label: 'Buổi tháng ' + (+E.month.slice(5)), align: 'right', render: (s) => String(D.get(s.id).monthDone.length) },
        { label: ['θ TB ', thetaWhy], render: (s) => { const d = D.get(s.id); return h('span', { class: 'stu-theta' }, signedEl(E, d.thetaMean), ui.sparkline(d.series.map((x) => x.y), { w: 72, h: 20 })); } },
        { label: ['Lỗi lặp chưa hết ', repWhy], align: 'right', render: (s) => { const n = D.get(s.id).repeatOpen.length; return n ? ui.chip(String(n), 'warn') : h('span', { class: 'muted' }, '0'); } },
        { label: 'Trạng thái', render: (s) => statusCell(E, s) },
        { label: '', render: (s) => ui.button('Xem hồ sơ', () => open(s), { size: 'sm' }) }
      ],
      rows,
      empty: 'Không có học sinh nào cho bộ lọc này.',
      onRow: open,
      rowClass: (s) => (s.archived_at ? 'is-dim' : null)
    });
    table.classList.add('stu-list-tbl');

    return h('div', { class: 'stack' }, head,
      section(E, 'Danh sách', ['table:student', 'table:session', 'table:skill_state'], ui.store('db'), filters, table),
      heatmap(E, rows));
  }

  function statusCell(E, s) {
    const { h, ui } = E;
    const out = [];
    const th = ((E.ctx.data.checkpoints || {}).threads || []).filter((t) => t.graph === 'G1' && t.student_id === s.id);
    const wait = th.filter((t) => t.status === 'awaiting_review').length;
    if (s.archived_at) out.push(h('span', { class: 'status s-locked' }, 'đã lưu trữ'));
    if (wait) out.push(h('span', { class: 'status s-pending', title: 'G1 dừng chờ duyệt — nằm trong checkpoints.db' }, 'có buổi chờ duyệt' + (wait > 1 ? ' (' + wait + ')' : '')));
    if (th.some((t) => t.status === 'failed')) out.push(h('span', { class: 'status s-crit' }, 'buổi hỏng'));
    if (th.some((t) => t.status === 'running')) out.push(ui.status('running'));
    return out.length ? h('span', { class: 'stu-stack' }, out) : h('span', { class: 'muted' }, '—');
  }

  function elo(E) { return (E.ctx.data.settings || {}).elo || { K: 0.3, theta0: 0 }; }
  function need(E) { return ((E.ctx.data.settings || {}).misconception || {}).resolve_streak || 2; }

  /* ---------------- class heatmap HS × KC ---------------- */
  function heatmap(E, students) {
    const { h, ui, ctx, fmt } = E;
    const blocks = [9, 8].map((grade) => {
      const sts = students.filter((s) => s.grade === grade);
      if (!sts.length) return null;
      const theta = new Map();
      E.db.skill_state.forEach((x) => { if (sts.some((s) => s.id === x.student_id)) theta.set(x.student_id + '|' + x.kc_id, x); });
      const kcIds = [...new Set(E.db.skill_state.filter((x) => sts.some((s) => s.id === x.student_id)).map((x) => x.kc_id))]
        .map((id) => ctx.lookup.kc(id)).filter(Boolean).sort((a, b) => a.id - b.id);
      if (!kcIds.length) return h('div', { class: 'stack' }, h('h3', null, 'Lớp ' + grade), ui.empty('Chưa có dữ liệu θ cho lớp ' + grade + '.'));
      const groups = [];
      kcIds.forEach((k) => { const g = groups[groups.length - 1]; if (g && g.id === k.parent_id) g.kcs.push(k); else groups.push({ id: k.parent_id, kcs: [k] }); });
      const gRow = h('tr', null, h('th', { scope: 'col' }, ''), groups.map((g) => {
        const gk = ctx.lookup.kc(g.id);
        const short = gk ? gk.code.replace(/^\dDS-/, '') : '';
        return h('th', { colspan: g.kcs.length, class: 'stu-heat-g', title: gk ? gk.code + ' · ' + gk.name : '' }, gk && gk.lop !== grade ? gk.lop + '·' + short : short);
      }));
      const kRow = h('tr', null, h('th', { scope: 'col', class: 'stu-heat-corner' }, 'HS \\ KC'), kcIds.map((k) => h('th', { scope: 'col', title: k.code + ' · ' + k.name }, k.code.split('-').pop())));
      const body = sts.map((s) => h('tr', null,
        h('th', { scope: 'row' }, h('span', { class: 'mono' }, code(E, s)), h('span', { class: 'muted small stu-heat-name' }, s.name.split(' ').pop())),
        kcIds.map((k) => {
          const x = theta.get(s.id + '|' + k.id);
          if (!x) return h('td', null, h('span', { class: 'stu-cell-empty', title: code(E, s) + ' · ' + k.code + ': chưa có dữ liệu' }));
          // sqrt so small θ (most of the class sits within ±0.3) still reads as a colour
          const a = Math.round(Math.sqrt(Math.min(1, Math.abs(x.theta))) * 75);
          return h('td', null, h('button', {
            type: 'button', class: 'stu-cell',
            style: '--c: var(' + (x.theta < 0 ? '--crit' : '--accent') + '); --a: ' + a + '%',
            title: code(E, s) + ' · ' + k.code + ' ' + k.name + ' · θ = ' + fmt.signed(x.theta) + ' · ' + x.n_attempts + ' lượt · lần cuối ' + fmt.date(x.last_seen),
            'aria-label': code(E, s) + ' ' + k.code + ' θ ' + fmt.signed(x.theta),
            onclick: () => ctx.nav('students', { student: s.id, tab: 'skills', kc: k.id })
          }, fmt.signed(x.theta, 1)));
        })));
      return h('div', { class: 'stack stu-heat-block' },
        h('h3', null, 'Lớp ' + grade + ' ', h('span', { class: 'muted small' }, sts.length + ' HS × ' + kcIds.length + ' KC có dữ liệu')),
        h('div', { class: 'table-wrap stu-heat-wrap' }, h('table', { class: 'stu-heat' }, h('thead', null, gRow, kRow), h('tbody', null, body))));
    }).filter(Boolean);
    const legend = h('div', { class: 'stu-legend' },
      h('span', { class: 'small' }, '−1'), h('span', { class: 'stu-legend-bar', 'aria-hidden': 'true' }), h('span', { class: 'small' }, '+1'),
      h('span', { class: 'small muted' }, 'màu = θ (đỏ: dưới mức bài trung bình, xanh: trên)'),
      h('span', { class: 'stu-cell-empty stu-legend-empty', 'aria-hidden': 'true' }), h('span', { class: 'small muted' }, 'chưa có dữ liệu'));
    return section(E, 'Bản đồ nhiệt cả lớp', ['table:skill_state', 'θ', 'Elo'], ui.prov('code'),
      h('p', { class: 'muted small' }, 'Hàng = học sinh, cột = KC (nhóm theo chủ đề, chỉ KC đã có dữ liệu). Bấm một ô để mở Kỹ năng (Elo) của HS đó tại KC đó.'),
      legend, blocks.length ? blocks : ui.empty('Không có học sinh nào cho bộ lọc này.'));
  }

  /* ---------------- add / edit / archive ---------------- */
  function addStudent(E) {
    const { h, ctx } = E;
    const ids = E.db.student.map((s) => s.id);
    const id = (ids.length ? Math.max(...ids) : 0) + 1;
    const newCode = 'HS-' + pad2(id);
    const name = h('input', { type: 'text', id: 'stu-new-name', placeholder: 'VD: Hoàng Mai Anh', autofocus: true });
    const grade = h('select', { id: 'stu-new-grade' }, h('option', { value: '9' }, 'Lớp 9'), h('option', { value: '8' }, 'Lớp 8'));
    const note = h('input', { type: 'text', id: 'stu-new-note', placeholder: 'VD: Ôn thi vào 10' });
    const err = h('p', { class: 'stu-err', role: 'alert' });
    ctx.modal({
      title: 'Thêm học sinh',
      body: h('div', { class: 'stack' },
        h('div', { class: 'callout callout-info' }, h('p', null, 'Mã gửi API sẽ là ', h('b', { class: 'mono' }, newCode), '. Tên chỉ lưu trên máy này — prompt chỉ có mã (NFR7).')),
        h('label', { class: 'field', for: 'stu-new-name' }, h('span', null, 'Tên học sinh'), name),
        h('label', { class: 'field', for: 'stu-new-grade' }, h('span', null, 'Lớp'), grade),
        h('label', { class: 'field', for: 'stu-new-note' }, h('span', null, 'Ghi chú (tuỳ chọn)'), note),
        err),
      actions: [{ label: 'Huỷ' }, {
        label: 'Thêm học sinh', kind: 'primary', onClick: (close) => {
          if (!name.value.trim()) { err.textContent = 'Cần nhập tên học sinh.'; name.focus(); return; }
          E.db.student.push({ id, name: name.value.trim(), grade: +grade.value, note: note.value.trim() || null, created_at: nowISO(E), archived_at: null, code: newCode });
          close();
          ctx.receipt('Thêm học sinh ' + newCode, [['student', 1]], {});
          ctx.toast('Đã thêm · mã gửi API: ' + newCode, { kind: 'ok' });
          ctx.nav('students', { student: id });
        }
      }]
    });
  }

  function editForm(E, st) {
    const { h, ui, ctx } = E;
    const name = h('input', { type: 'text', id: 'stu-ed-name', value: st.name });
    const grade = h('select', { id: 'stu-ed-grade' }, [9, 8].map((g) => h('option', { value: String(g), selected: st.grade === g }, 'Lớp ' + g)));
    const note = h('textarea', { id: 'stu-ed-note', rows: 2, value: st.note || '' });
    const err = h('p', { class: 'stu-err', role: 'alert' });
    const save = () => {
      if (!name.value.trim()) { err.textContent = 'Tên không được để trống.'; return; }
      const changed = [];
      if (name.value.trim() !== st.name) changed.push('name');
      if (+grade.value !== st.grade) changed.push('grade');
      if ((note.value.trim() || null) !== (st.note || null)) changed.push('note');
      st.name = name.value.trim(); st.grade = +grade.value; st.note = note.value.trim() || null;
      S.editing = null;
      if (changed.length) ctx.receipt('Sửa thông tin ' + code(E, st), [['student', 'cập nhật']], {});
      ctx.toast(changed.length ? 'Đã lưu ' + changed.join(', ') + ' của ' + code(E, st) + ' — API vẫn chỉ nhận mã ' + code(E, st) + '.' : 'Không có gì thay đổi.', { kind: changed.length ? 'ok' : 'info' });
      E.paint();
    };
    return h('div', { class: 'stack stu-edit' },
      h('div', { class: 'grid cols-3' },
        h('label', { class: 'field', for: 'stu-ed-name' }, h('span', null, 'Tên (chỉ lưu trên máy)'), name),
        h('label', { class: 'field', for: 'stu-ed-grade' }, h('span', null, 'Lớp'), grade),
        h('label', { class: 'field', for: 'stu-ed-note' }, h('span', null, 'Ghi chú'), note)),
      h('p', { class: 'muted small' }, 'Đổi lớp chỉ đổi bộ bài được gợi ý từ nay (lớp 9 chỉ nhận bài 9DS); lịch sử giữ nguyên. Ghi vào student.name, grade, note.'),
      err,
      h('div', { class: 'row' }, ui.button('Lưu', save, { kind: 'primary' }), ui.button('Huỷ sửa', () => { S.editing = null; E.paint(); }, { kind: 'ghost' })));
  }

  function archive(E, st) {
    const { ctx } = E;
    ctx.confirm('Lưu trữ ' + code(E, st) + ' · ' + st.name + '? Ghi student.archived_at. Lịch sử buổi, θ và báo cáo giữ nguyên (chỉ thêm, không xoá); HS ẩn khỏi danh sách mặc định.',
      { title: 'Lưu trữ học sinh', ok: 'Lưu trữ' }).then((yes) => {
      if (!yes) return;
      st.archived_at = nowISO(E);
      ctx.receipt('Lưu trữ ' + code(E, st), [['student', 'cập nhật']], {});
      E.paint();
    });
  }

  /* ---------------- profile ---------------- */
  function notFound(E, v) {
    const { h, ui, ctx } = E;
    return h('div', { class: 'stack' }, ui.pageHead({}),
      ui.empty('Không tìm thấy học sinh “' + v + '”.', ui.button('Về danh sách học sinh', () => ctx.nav('students'), { kind: 'primary' })));
  }

  function profileView(E, st) {
    const { h, ui, ctx } = E;
    const d = derive(E, st.id);
    const c = code(E, st);
    const sw = h('select', { 'aria-label': 'Chọn học sinh', class: 'stu-switch', onchange: (e) => ctx.nav('students', { student: e.target.value, tab: S.sub[st.id] || 'progress' }) },
      E.db.student.map((s) => h('option', { value: String(s.id), selected: s.id === st.id }, code(E, s) + ' · ' + s.name + (s.archived_at ? ' (đã lưu trữ)' : ''))));
    const head = ui.pageHead({
      lead: 'Hồ sơ đọc từ tutor.db: θ theo KC, cặp lỗi đã ghi, lịch sử buổi, gợi ý và báo cáo đã duyệt.',
      actions: [ui.button('← Danh sách cả lớp', () => ctx.nav('students'), { kind: 'ghost' }), sw],
      annot: ['agent:05', 'G1', 'table:skill_event', 'table:skill_state', 'table:misconception_log', 'file:tutor.db']
    });
    const sub = S.sub[st.id] || 'progress';
    const body = h('div', { class: 'stack stu-sub' });
    const paintSub = (id) => { S.sub[st.id] = id; body.replaceChildren(subView(E, st, d, id, paintSub)); ctx.tex(body); };
    body.append(subView(E, st, d, sub, paintSub));
    return h('div', { class: 'stack' }, head,
      st.archived_at ? h('div', { class: 'callout callout-warn', role: 'status' },
        h('strong', null, 'Đã lưu trữ ' + E.fmt.date(st.archived_at)),
        h('p', null, 'Học sinh không còn trong danh sách mặc định. Lịch sử, θ và báo cáo vẫn giữ nguyên trong tutor.db.'),
        ui.button('Bỏ lưu trữ', () => { st.archived_at = null; ctx.receipt('Bỏ lưu trữ ' + c, [['student', 'cập nhật']], {}); E.paint(); }, { size: 'sm' })) : null,
      profileHead(E, st, d),
      (S.running === st.id || S.replay[st.id]) ? replayCard(E, st) : null,
      h('div', { class: 'stu-tabs' }, ui.segmented(SUBS, sub, paintSub)),
      body);
  }

  function profileHead(E, st, d) {
    const { h, ui, ctx, fmt } = E;
    const c = code(E, st);
    const noMonth = !d.monthDone.length;
    const info = S.editing === st.id ? editForm(E, st) : h('div', { class: 'stu-id' },
      h('div', { class: 'stu-avatar', 'aria-hidden': 'true' }, st.name.split(' ').pop().charAt(0)),
      h('div', { class: 'stack', style: 'gap:6px' },
        h('div', { class: 'row' }, h('h2', { class: 'stu-name' }, st.name), ui.chip(c, 'info'), ui.chip('Lớp ' + st.grade), ui.privacy(c)),
        h('p', { class: 'small' }, st.note ? [ui.prov('gv', 'GV'), ' ', st.note] : h('span', { class: 'muted' }, 'Chưa có ghi chú.')),
        h('p', { class: 'muted small' }, 'Thêm ngày ' + fmt.date(st.created_at) + ' · ' + d.done.length + ' buổi đã duyệt · ' + d.states.length + ' KC có θ · tên chỉ lưu trên máy này, API chỉ nhận mã ' + c + '.')));
    const flows = h('div', { class: 'row stu-actions' },
      ui.button('Nộp bài cho HS này', () => ctx.nav('session', { step: 1, student: st.id }), { kind: 'primary', cli: 'tutor ingest ' + c + ' <file>', disabledReason: st.archived_at ? 'HS đã lưu trữ — bỏ lưu trữ trước' : null }),
      ui.button('Gợi ý buổi sau', () => ctx.nav('recommend', { student: st.id }), { cli: 'tutor recommend ' + c }),
      ui.button('Tạo report tháng', () => ctx.nav('report', { student: st.id, month: E.month }), { cli: 'tutor report ' + c + ' ' + E.month, disabledReason: noMonth ? '0 buổi đã duyệt trong tháng ' + (+E.month.slice(5)) : null }));
    const tools = h('div', { class: 'row stu-actions' },
      ui.button('Sửa thông tin', () => { S.editing = st.id; E.paint(); }, { size: 'sm' }),
      st.archived_at ? null : ui.button('Lưu trữ', () => archive(E, st), { size: 'sm' }),
      ui.button('Xem dữ liệu gửi API', () => ui.payloadModal('03', c), { size: 'sm' }),
      ui.button('Dựng lại trạng thái từ lịch sử', () => startReplay(E, st), { size: 'sm', title: 'Tính lại skill_state + misconception_log từ skill_event và lỗi đã duyệt, rồi so với bảng đã lưu', disabledReason: S.running ? 'đang dựng lại' : null }));
    return h('section', { class: 'section stu-head' + (st.archived_at ? ' st-rejected' : '') },
      h('div', { class: 'section-head' }, h('div', null, h('span', { class: 'eyebrow' }, 'Hồ sơ học sinh'), ui.annot(['table:student', 'UNTRUSTED INPUT'])), ui.store('db')),
      info, S.editing === st.id ? null : flows, S.editing === st.id ? null : tools);
  }

  /* ---------------- replay (schema rule 4) ---------------- */
  function startReplay(E, st) {
    if (S.running) return;
    S.running = st.id; delete S.replay[st.id];
    E.paint();
    const r = E.calc.replay(E.db, st.id);
    const steps = [
      'Đọc ' + r.skill_event.length + ' skill_event theo thứ tự (held_on, seq)…',
      'Tính lại skill_state cho ' + r.skill_state.length + ' KC (Elo, K = ' + elo(E).K + ')…',
      'Tính lại misconception_log: ' + r.misconception_log.length + ' cặp (mã lỗi, KC)…',
      'So với các dòng đã lưu trong tutor.db…'
    ];
    let i = 0;
    const tick = () => {
      if (E.token === S.token) {
        const card = E.root.querySelector('[data-stu-replay]');
        if (card) card.replaceChildren(...replayBody(E, st, { step: i, steps }));
      }
      if (i < steps.length) { i++; setTimeout(tick, 280); return; }
      S.running = null;
      S.replay[st.id] = compareReplay(E, st, r);
      const res = S.replay[st.id];
      E.ctx.toast('Dựng lại từ ' + r.skill_event.length + ' skill_event — khớp ' + res.pct + '%', { kind: res.pct === 100 ? 'ok' : 'warn' });
      if (E.token === S.token) E.paint();
    };
    tick();
  }

  function compareReplay(E, st, r) {
    const db = E.db;
    const sS = db.skill_state.filter((x) => x.student_id === st.id);
    const sM = db.misconception_log.filter((x) => x.student_id === st.id);
    const sE = db.skill_event.filter((x) => x.student_id === st.id);
    const okS = r.skill_state.filter((x) => sS.some((y) => y.kc_id === x.kc_id && Math.abs(y.theta - x.theta) < 5e-5 && y.n_attempts === x.n_attempts && y.correct_streak === x.correct_streak && y.last_seen === x.last_seen));
    const okM = r.misconception_log.filter((x) => sM.some((y) => y.code === x.code && y.kc_id === x.kc_id && y.count === x.count && y.first_seen === x.first_seen && y.last_seen === x.last_seen && (y.resolved_at || null) === (x.resolved_at || null)));
    const okE = r.skill_event.filter((x) => sE.some((y) => y.attempt_id === x.attempt_id && y.kc_id === x.kc_id && y.outcome === x.outcome && Math.abs(y.theta_after - x.theta_after) < 5e-5)).length;
    const tot = Math.max(r.skill_state.length, sS.length) + Math.max(r.misconception_log.length, sM.length) + Math.max(r.skill_event.length, sE.length);
    const ok = okS.length + okM.length + okE;
    const bad = r.skill_state.filter((x) => okS.indexOf(x) < 0).map((x) => ({ x, y: sS.find((y) => y.kc_id === x.kc_id) || null }));
    return { at: nowISO(E), pct: tot ? Math.floor((ok / tot) * 1000) / 10 : 100, ev: [r.skill_event.length, sE.length, okE], st: [r.skill_state.length, sS.length, okS.length], mis: [r.misconception_log.length, sM.length, okM.length], bad };
  }

  function replayCard(E, st) {
    const { h, ui } = E;
    const run = S.running === st.id;
    return h('section', { class: 'section stu-replay' },
      h('div', { class: 'section-head' },
        h('div', null, h('h2', null, 'Dựng lại trạng thái từ lịch sử'), ui.annot(['table:skill_event', 'table:skill_state', 'table:misconception_log', 'table:mistake_current'])),
        ui.prov('code')),
      h('div', { class: 'stack', 'data-stu-replay': '' }, ...(run ? [h('p', { class: 'muted' }, 'Đang dựng lại…')] : replayBody(E, st, null))));
  }

  function replayBody(E, st, prog) {
    const { h, ui, fmt } = E;
    if (prog) {
      return [h('div', { class: 'row' }, h('span', { class: 'stu-prog', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': prog.steps.length, 'aria-valuenow': prog.step },
        h('span', { style: 'width:' + Math.round((prog.step / prog.steps.length) * 100) + '%' }))),
      h('ol', { class: 'stu-steps' }, prog.steps.map((t, i) => h('li', { class: i < prog.step ? 'is-done' : i === prog.step ? 'is-cur' : '' }, t)))];
    }
    const r = S.replay[st.id];
    if (!r) return [];
    const line = (lbl, v) => [lbl, h('span', null, h('b', { class: 'num' }, v[2] + '/' + Math.max(v[0], v[1])), ' khớp · dựng lại ' + v[0] + ' · đã lưu ' + v[1])];
    return [
      h('div', { class: 'callout ' + (r.pct === 100 ? 'callout-ok' : 'callout-warn') },
        h('strong', null, 'Khớp ' + r.pct + '% với tutor.db'),
        h('p', null, r.pct === 100 ? 'Trạng thái hiện tại đúng bằng kết quả tính lại từ lịch sử. Vì bảng chỉ thêm dòng (append-only + supersedes), có thể dựng lại bất cứ lúc nào (schema rule 4, FR5).'
          : 'Có dòng lệch giữa bảng đã lưu và kết quả tính lại — xem bảng dưới. Trong hệ thật, commit node ghi lại bằng kết quả tính lại.')),
      ui.kv([line('skill_event', r.ev), line('skill_state', r.st), line('misconception_log', r.mis), ['Lúc chạy', fmt.dt(r.at)]]),
      r.bad.length ? ui.table({
        columns: [{ label: 'KC', render: (b) => kcLabel(E, b.x.kc_id, true) }, { label: 'θ đã lưu', align: 'right', render: (b) => (b.y ? fmt.signed(b.y.theta) : 'không có') }, { label: 'θ tính lại', align: 'right', render: (b) => fmt.signed(b.x.theta) }],
        rows: r.bad.slice(0, 8)
      }) : null
    ];
  }

  /* ---------------- sub-tabs ---------------- */
  function subView(E, st, d, id, paintSub) {
    if (id === 'skills') return skillsView(E, st, d, paintSub);
    if (id === 'misconceptions') return misView(E, st, d);
    if (id === 'history') return historyView(E, st, d);
    if (id === 'outputs') return outputsView(E, st, d);
    return progressView(E, st, d);
  }

  function noData(E) {
    return E.h('div', { class: 'callout callout-info' }, E.h('strong', null, 'Chưa có buổi đã duyệt · θ = 0 cho mọi KC'),
      E.h('p', null, 'Không cần train mô hình (NFR2): θ bắt đầu từ 0 và cập nhật ngay từ buổi đầu tiên được duyệt.'));
  }

  function kpi(E, label, value, sub, why) {
    const { h } = E;
    return h('div', { class: 'kpi' }, h('span', { class: 'kpi-label' }, label, why), h('span', { class: 'kpi-value' }, value), sub ? h('span', { class: 'kpi-sub' }, sub) : null);
  }

  function progressView(E, st, d) {
    const { h, ui, fmt, calc } = E;
    const c = code(E, st);
    if (!d.done.length) return h('div', { class: 'stack' }, noData(E), pendingNote(E, st, d));
    const months = (E.ctx.data.meta || {}).months || [];
    const atts = d.doneAtts;
    const sc = atts.reduce((s, a) => s + (a.score || 0), 0), mx = atts.reduce((s, a) => s + (a.max_score || 0), 0);
    const rate = calc.passRate(atts);
    const dv = calc.deltaVsPrevious(E.db, d.last.id) || { kcs: [], repeat: [], new: [], gone: [], resolved: [] };
    const dMean = mean(dv.kcs.map((k) => k.d));
    const prev = dv.previous_session_id ? E.db.session.find((s) => s.id === dv.previous_session_id) : null;
    const resolved = d.mis.filter((m) => m.resolved_at);

    const kpis = h('div', { class: 'grid stu-kpis' },
      kpi(E, 'Số buổi đã duyệt', String(d.done.length), months.map((m) => 'T' + (+m.slice(5)) + ': ' + d.done.filter((s) => s.held_on.slice(0, 7) === m).length).join(' · '),
        ui.why(() => h('div', { class: 'stack' }, h('p', null, 'Đếm buổi có status = committed (đã ghi vào tutor.db). Buổi chờ duyệt / lỗi không tính: ' + (d.sessions.length - d.done.length) + '.'),
          h('p', { class: 'small' }, d.done.map((s) => dm(s.held_on)).join(' · ')),
          pre(E, "SELECT COUNT(*) FROM session\nWHERE student_id = " + st.id + " AND status = 'committed'")))),
      kpi(E, 'Tỉ lệ đạt rubric', fmt.pct(rate), 'Σ điểm ' + sc + '/' + mx + ' · ' + atts.length + ' bài',
        ui.why(() => h('div', { class: 'stack' }, h('p', null, 'Σ score / Σ max_score trên attempt_current của các buổi đã duyệt = ' + sc + ' / ' + mx + ' = ' + fmt.pct(rate) + '.'),
          ui.kv(months.map((m) => { const a = d.done.filter((s) => s.held_on.slice(0, 7) === m).flatMap((s) => d.attBy[s.id] || []); return ['Tháng ' + fmt.month(m), a.length ? fmt.pct(calc.passRate(a)) + ' (' + a.length + ' bài)' : '—']; })),
          h('p', { class: 'small muted' }, 'score = số mục rubric đạt (02 Grader chấm, code kiểm tổng = tổng các mục).')))),
      kpi(E, 'Δθ TB so với buổi trước', fmt.signed(dMean), 'buổi ' + dm(d.last.held_on) + ' · ' + dv.kcs.length + ' KC',
        ui.why(() => h('div', { class: 'stack' }, h('p', null, 'Mỗi KC làm trong buổi ' + dm(d.last.held_on) + ': θ sau buổi − θ trước lần làm đầu tiên trong buổi. Lấy trung bình.'),
          ui.kv(dv.kcs.map((k) => [(E.ctx.lookup.kc(k.kc_id) || {}).code || k.kc_id, fmt.signed(k.theta_before, 3) + ' → ' + fmt.signed(k.theta_after, 3) + ' = ' + fmt.signed(k.d)])),
          h('p', { class: 'small' }, 'TB = ' + dv.kcs.map((k) => fmt.signed(k.d)).join(' ') + ' ÷ ' + dv.kcs.length + ' = ' + fmt.signed(dMean))))),
      kpi(E, 'Cặp lỗi đã hết', resolved.length + '/' + d.mis.length, 'cặp (mã lỗi, KC) đã ghi trong misconception_log',
        ui.why(() => h('div', { class: 'stack' }, h('p', null, 'resolved_at được đặt khi KC đạt ' + need(E) + ' lần đúng liên tiếp sau lần sai cuối (settings.misconception.resolve_streak = ' + need(E) + ', cố định theo spec §8). Lỗi tái xuất hiện thì xoá resolved_at, count + 1.'),
          h('p', { class: 'small' }, 'Đã hết: ' + resolved.length + ' · chưa hết: ' + (d.mis.length - resolved.length) + ' (trong đó lỗi lặp, count ≥ 2: ' + d.repeatOpen.length + ')')))));

    const maxD = Math.max(0.3, ...dv.kcs.map((k) => Math.abs(k.d)));
    const bars = dv.kcs.length ? h('div', { class: 'stack', style: 'gap:8px' }, dv.kcs.slice().sort((a, b) => b.d - a.d).map((k) => h('div', { class: 'stu-drow' },
      kcLabel(E, k.kc_id), ui.bar(k.d, maxD, { signed: true }),
      h('span', { class: 'num small nowrap' }, fmt.signed(k.theta_before, 3) + ' → ' + fmt.signed(k.theta_after, 3) + ' ', signedEl(E, k.d))))) : ui.empty('Buổi này không chạm KC nào.');
    const chips = (lbl, list, kind, hint) => h('div', { class: 'stu-codes' }, h('span', { class: 'stu-codes-l' }, lbl, ' ', h('span', { class: 'muted small' }, hint)),
      list.length ? h('span', { class: 'row' }, list.map((x) => (typeof x === 'string' ? codeChip(E, x) : resolvedChip(E, x, kind)))) : h('span', { class: 'muted small' }, 'không có'));
    const compare = section(E, 'So với buổi trước', ['agent:05', 'table:skill_event'], ui.prov('code'),
      h('p', { class: 'muted small' }, 'Buổi ' + fmt.date(d.last.held_on) + (prev ? ' so với buổi ' + fmt.date(prev.held_on) : ' (buổi đầu tiên — chưa có buổi trước)') + '. Thanh: Δθ theo KC (θ sau − θ trước).'),
      bars,
      h('div', { class: 'stack', style: 'gap:8px' },
        chips('Có ở cả 2 buổi', dv.repeat, 'warn', 'buổi này và buổi trước'), chips('Mới', dv.new, 'info', 'chỉ buổi này'), chips('Đã hết', dv.gone, 'ok', 'chỉ buổi trước'),
        chips('Hết hẳn sau buổi này', dv.resolved, 'ok', 'hết ngày ' + dm(d.last.held_on))));

    const ks = d.last.knowledge_state;
    const summary = section(E, 'Tóm tắt của 05 Profiler', ['agent:05'], h('span', { class: 'row' }, ui.prov('llm', 'LLM · 05'), ui.store('db')),
      ks ? h('blockquote', { class: 'stu-ks' }, ks) : ui.empty('Buổi này chưa có knowledge_state.'),
      h('p', { class: 'muted small' }, '05 viết từ số liệu do code tính (Elo, Δθ, lỗi lặp) — không tự chấm, không tự đổi con số. session.knowledge_state ≤ 150 từ, buổi ' + fmt.date(d.last.held_on) + '.'));

    const trend = section(E, 'θ trung bình sau mỗi buổi', ['θ', 'table:skill_event'], ui.prov('code'),
      ui.lineChart(d.series.map((x) => ({ x: dm(x.s.held_on), y: x.y })), { h: 170, yLabel: 'θ TB · ' + c }));

    return h('div', { class: 'stack' }, kpis, pendingNote(E, st, d), h('div', { class: 'grid cols-2' }, compare, h('div', { class: 'stack' }, summary, trend)));
  }

  function pendingNote(E, st, d) {
    const { h, ui, ctx, fmt } = E;
    const open = d.sessions.filter((s) => s.status !== 'committed');
    if (!open.length) return null;
    return h('div', { class: 'callout callout-warn st-pending' },
      h('strong', null, open.length + ' buổi chưa vào tutor.db — chưa tính vào số liệu ở đây'),
      h('div', { class: 'row' }, open.map((s) => h('span', { class: 'row', style: 'gap:6px' }, fmt.date(s.held_on), ui.status(s.status),
        ui.button('Xem buổi ' + dm(s.held_on), () => ctx.nav('session', { session: s.id }), { size: 'sm', kind: 'ghost' })))));
  }

  /* ---------------- skills (Elo) ---------------- */
  function skillsView(E, st, d, paintSub) {
    const { h, ui, ctx, fmt } = E;
    if (!d.states.length) return h('div', { class: 'stack' }, noData(E));
    const byKc = {};
    d.events.forEach((e) => (byKc[e.kc_id] = byKc[e.kc_id] || []).push(e));
    let sel = S.kc[st.id];
    if (!d.states.some((x) => x.kc_id === sel)) {
      sel = d.states.slice().sort((a, b) => (byKc[b.kc_id] || []).length - (byKc[a.kc_id] || []).length || a.kc_id - b.kc_id)[0].kc_id;
    }
    const pick = (kcId) => { S.kc[st.id] = kcId; paintSub('skills'); };
    const k = ctx.lookup.kc(sel) || { code: '?', name: '' };
    const evs = byKc[sel] || [];
    const stt = d.states.find((x) => x.kc_id === sel);
    const select = h('select', { 'aria-label': 'Chọn KC', class: 'stu-kc-select', onchange: (e) => pick(+e.target.value) },
      d.states.slice().sort((a, b) => a.kc_id - b.kc_id).map((x) => { const kk = ctx.lookup.kc(x.kc_id) || {}; return h('option', { value: String(x.kc_id), selected: x.kc_id === sel }, kk.code + ' · ' + kk.name); }));
    const chart = evs.length >= 2
      ? ui.lineChart([{ x: 'đầu', y: evs[0].theta_before }].concat(evs.map((e) => ({ x: dm(sessionOf(E, e).held_on), y: e.theta_after }))), { h: 180, yLabel: 'θ · ' + k.code })
      : h('div', { class: 'callout callout-info' }, h('p', null, 'KC này mới có ' + evs.length + ' sự kiện — cần ≥ 2 sự kiện để vẽ đường θ.'),
        evs[0] ? h('p', { class: 'small' }, 'Sự kiện duy nhất: θ ' + fmt.signed(evs[0].theta_before) + ' → ' + fmt.signed(evs[0].theta_after) + ' (X = ' + evs[0].outcome + ', δ = ' + fmt.signed(evs[0].delta) + ').') : null);
    const panel = section(E, 'θ theo thời gian', ['table:skill_event', 'Elo', 'θ', 'δ'], ui.prov('code'),
      h('div', { class: 'row' }, h('label', { class: 'small muted' }, 'KC'), select),
      h('p', null, kcLabel(E, sel), ' ', h('span', { class: 'muted small' }, k.description || '')),
      ui.kv([
        ['θ hiện tại', [signedEl(E, stt ? stt.theta : 0), ' ', ui.why(() => thetaWhy(E, evs[evs.length - 1]))]],
        ['Số lượt', stt ? String(stt.n_attempts) : '0'],
        ['Đúng liên tiếp', stt ? String(stt.correct_streak) : '0'],
        ['Lần cuối', stt ? fmt.date(stt.last_seen) : '—']
      ]),
      chart,
      h('div', { class: 'row' },
        ui.button('Xem các sự kiện (' + evs.length + ')', () => eventsDrawer(E, st, sel, evs), { size: 'sm', disabledReason: evs.length ? null : 'chưa có skill_event' }),
        ui.button('Xem cách tính θ', () => calcModal(E, evs[evs.length - 1]), { size: 'sm' }),
        ui.button('Mở KC trong Danh mục', () => ctx.nav('catalog', { kc: k.code }), { size: 'sm', kind: 'ghost' })));

    const groups = [];
    d.states.slice().sort((a, b) => { const ka = ctx.lookup.kc(a.kc_id) || {}, kb = ctx.lookup.kc(b.kc_id) || {}; return (ka.parent_id - kb.parent_id) || (a.kc_id - b.kc_id); })
      .forEach((x) => { const pid = (ctx.lookup.kc(x.kc_id) || {}).parent_id; const g = groups[groups.length - 1]; if (g && g.id === pid) g.rows.push(x); else groups.push({ id: pid, rows: [x] }); });
    const tables = groups.map((g) => {
      const gk = ctx.lookup.kc(g.id) || {};
      return h('div', { class: 'stack', style: 'gap:6px' },
        h('h3', null, gk.name || 'Nhóm', ' ', h('span', { class: 'mono muted small' }, gk.code || ''), ' ', h('span', { class: 'muted small' }, '· θ TB ' + fmt.signed(mean(g.rows.map((x) => x.theta))))),
        ui.table({
          columns: [
            { label: 'KC', render: (x) => kcLabel(E, x.kc_id) },
            { label: 'θ', render: (x) => h('span', { class: 'stu-theta' }, signedEl(E, x.theta), h('span', { class: 'stu-tbar' }, ui.bar(x.theta, 1, { signed: true }))) },
            { label: 'Lượt', align: 'right', render: (x) => String(x.n_attempts) },
            { label: 'Đúng liên tiếp', align: 'right', render: (x) => String(x.correct_streak) },
            { label: 'Lần cuối', render: (x) => fmt.date(x.last_seen) }
          ],
          rows: g.rows,
          onRow: (x) => pick(x.kc_id),
          rowClass: (x) => (x.kc_id === sel ? 'is-sel' : null)
        }));
    });
    const list = section(E, 'Bảng θ theo KC', ['table:skill_state'], h('span', { class: 'row' }, ui.prov('code'), ui.store('db')),
      h('p', { class: 'muted small' }, d.states.length + ' KC · nhóm theo chủ đề · bấm một dòng để xem đường θ của KC đó.'), tables);
    return h('div', { class: 'grid cols-2 stu-skills' }, panel, list);
  }

  function sessionOf(E, ev) { const sid = E.attSession.get(ev.attempt_id); return E.db.session.find((s) => s.id === sid) || {}; }

  function thetaWhy(E, ev) {
    const { h, ui, fmt } = E;
    const K = elo(E).K;
    if (!ev) return h('p', null, 'Chưa có skill_event: θ = ' + elo(E).theta0 + ' (NFR2).');
    return h('div', { class: 'stack' },
      h('p', null, 'Lần cập nhật cuối (skill_event #' + ev.id + ', buổi ' + fmt.date(sessionOf(E, ev).held_on) + '):'),
      ui.latex('P = \\dfrac{1}{1 + e^{-(' + n2(ev.theta_before) + ' - ' + p2(ev.delta) + ')}} = ' + n2(ev.p_expected), { block: true }),
      ui.latex('\\theta_{\\text{sau}} = ' + n2(ev.theta_before) + ' + ' + K + '\\,(' + ev.outcome + ' - ' + n2(ev.p_expected) + ') = ' + n2(ev.theta_after), { block: true }),
      h('p', { class: 'small muted' }, 'X = ' + ev.outcome + (ev.outcome ? ' (không có lỗi đã duyệt gắn KC này)' : ' (có lỗi đã duyệt gắn KC này)') + ' · δ = độ khó bài đã duyệt (G3).'));
  }

  function eventsDrawer(E, st, kcId, evs) {
    const { h, ui, ctx, fmt } = E;
    const k = ctx.lookup.kc(kcId) || {};
    ctx.drawer({
      title: 'Sự kiện Elo · ' + code(E, st) + ' · ' + k.code,
      body: h('div', { class: 'stack' },
        h('p', { class: 'muted small' }, evs.length + ' dòng skill_event của ' + k.code + ' (' + k.name + '), cũ → mới. Mỗi dòng = 1 bài làm có KC này.'),
        evs.map((e) => {
          const a = E.db.attempt.find((x) => x.id === e.attempt_id) || {};
          const p = ctx.lookup.problem(a.problem_id) || {};
          const ms = E.cur.filter((m) => m.attempt_id === e.attempt_id && m.kc_id === kcId);
          const s = sessionOf(E, e);
          return h('div', { class: 'card st-db' },
            h('div', { class: 'spread' }, h('strong', null, fmt.date(s.held_on) + ' · bài ' + (p.ref || '?')), e.outcome ? ui.chip('X = 1 · đúng', 'ok') : ui.chip('X = 0 · có lỗi', 'danger')),
            ui.kv([
              ['P (kỳ vọng)', n2(e.p_expected)],
              ['θ trước → sau', [fmt.signed(e.theta_before, 3) + ' → ' + fmt.signed(e.theta_after, 3) + ' ', signedEl(E, e.theta_after - e.theta_before)]],
              ['δ bài', fmt.signed(e.delta)],
              ['Điểm bài', a.max_score ? a.score + '/' + a.max_score : '—']
            ]),
            ms.length ? h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Lỗi làm X = 0:'), ms.map((m) => codeChip(E, m.code))) : null,
            p.statement_latex ? h('details', { class: 'stu-details' }, h('summary', null, 'Đề bài ' + p.ref), ui.latex(p.statement_latex, { block: true })) : null,
            h('div', { class: 'row' }, ui.button('Xem buổi', () => ctx.nav('session', { session: s.id }), { size: 'sm', kind: 'ghost' })));
        }))
    });
  }

  function calcModal(E, ev) {
    const { h, ui, ctx } = E;
    const K = elo(E).K;
    const spec = { theta_before: 0.10, delta: 0.35, outcome: 0 };
    const th = h('input', { type: 'number', step: '0.01', id: 'stu-c-theta', value: n2(ev ? ev.theta_before : spec.theta_before) });
    const de = h('input', { type: 'number', step: '0.01', id: 'stu-c-delta', value: n2(ev ? ev.delta : spec.delta) });
    const x = h('select', { id: 'stu-c-x' }, h('option', { value: '1' }, '1 — đúng (không có lỗi gắn KC)'), h('option', { value: '0' }, '0 — có lỗi đã duyệt gắn KC'));
    x.value = String(ev ? ev.outcome : spec.outcome);
    const out = h('div', { class: 'stack stu-calc-out', 'aria-live': 'polite' });
    const src = h('p', { class: 'small muted' });
    const calc = () => {
      const t = parseFloat(th.value) || 0, dd = parseFloat(de.value) || 0, X = +x.value;
      const r = E.calc.elo(t, dd, X, K);
      const same = ev && Math.abs(t - ev.theta_before) < 0.005 && Math.abs(dd - ev.delta) < 0.005 && X === ev.outcome;
      out.replaceChildren(
        ui.latex('P = \\dfrac{1}{1 + e^{-(\\theta - \\delta)}} = \\dfrac{1}{1 + e^{-(' + n2(t) + ' - ' + p2(dd) + ')}} = ' + n2(r.P), { block: true }),
        ui.latex('\\theta_{\\text{sau}} = \\theta + K\\,(X - P) = ' + n2(t) + ' + ' + K + '\\,(' + X + ' - ' + n2(r.P) + ') = ' + n2(r.thetaAfter), { block: true }),
        ui.kv([['P', n2(r.P)], ['θ sau', E.fmt.signed(r.thetaAfter)], ['Δθ', E.fmt.signed(r.thetaAfter - t)]]),
        same ? h('p', { class: 'small' }, ui.chip('khớp skill_event #' + ev.id + ' (θ sau = ' + E.fmt.signed(ev.theta_after) + ')', 'ok')) : '');
      ctx.tex(out);
    };
    const load = (v, label) => { th.value = n2(v.theta_before); de.value = n2(v.delta); x.value = String(v.outcome); src.textContent = label; calc(); };
    [th, de, x].forEach((el) => el.addEventListener('input', calc));
    src.textContent = ev ? 'Đang dùng sự kiện thật: skill_event #' + ev.id + ' (attempt #' + ev.attempt_id + ').' : 'Chưa có sự kiện thật — dùng ví dụ trong spec.';
    ctx.modal({
      title: 'Cách tính θ (Elo)', wide: true,
      body: h('div', { class: 'stack' },
        h('p', null, 'Sau mỗi bài, code (elo.py) cập nhật θ của từng KC trong bài. Sửa θ, δ, X để thử — K cố định = ' + K + ' (spec §8).'),
        h('div', { class: 'grid cols-4' },
          h('label', { class: 'field', for: 'stu-c-theta' }, h('span', null, 'θ trước'), th),
          h('label', { class: 'field', for: 'stu-c-delta' }, h('span', null, 'δ (độ khó bài)'), de),
          h('label', { class: 'field', for: 'stu-c-x' }, h('span', null, 'X'), x),
          h('div', { class: 'field' }, h('span', null, 'K'), h('span', { class: 'mono stu-k' }, String(K), ' ', ui.prov('code')))),
        src,
        h('div', { class: 'row' },
          ev ? ui.button('Dùng sự kiện thật', () => load(ev, 'Đang dùng sự kiện thật: skill_event #' + ev.id + '.'), { size: 'sm' }) : null,
          ui.button('Ví dụ trong spec (θ = 0.10, δ = 0.35, X = 0)', () => load(spec, 'Ví dụ trong spec: P = 0.44, θ sau = −0.03.'), { size: 'sm' })),
        out),
      actions: [{ label: 'Đóng' }]
    });
    calc();
  }

  /* ---------------- misconceptions ---------------- */
  function misView(E, st, d) {
    const { h, ui, fmt } = E;
    const months = (E.ctx.data.meta || {}).months || [];
    const streak = new Map(d.states.map((x) => [x.kc_id, x.correct_streak]));
    const rows = d.mis.slice().sort((a, b) => (a.resolved_at ? 1 : 0) - (b.resolved_at ? 1 : 0) || b.count - a.count || cmp(b.last_seen, a.last_seen));
    const latest = (m) => d.mistakes.filter((x) => x.code === m.code && x.kc_id === m.kc_id).sort((a, b) => b.attempt_id - a.attempt_id)[0];
    const table = ui.table({
      columns: [
        { label: 'Mã lỗi', render: (m) => codeChip(E, m.code) },
        { label: 'KC', render: (m) => kcLabel(E, m.kc_id) },
        { label: 'Lần đầu', render: (m) => fmt.date(m.first_seen) },
        { label: 'Lần cuối', render: (m) => fmt.date(m.last_seen) },
        { label: 'Số lần', align: 'right', render: (m) => (m.count >= 2 && !m.resolved_at ? ui.chip(String(m.count), 'warn') : String(m.count)) },
        { label: 'Tiến độ', render: (m) => (m.resolved_at ? h('span', { class: 'muted small' }, 'đủ ' + need(E) + '/' + need(E))
          : h('span', { class: 'small nowrap' }, 'đúng liên tiếp ' + Math.min(streak.get(m.kc_id) || 0, need(E)) + '/' + need(E))) },
        { label: 'Trạng thái', render: (m) => (m.resolved_at ? h('span', { class: 'status s-ok' }, 'đã hết ' + dm(m.resolved_at)) : h('span', { class: 'status s-warn' }, 'chưa hết')) },
        { label: 'Bằng chứng gần nhất', render: (m) => { const x = latest(m); return x && x.evidence_latex ? h('span', { class: 'stu-ev' }, ui.latex(x.evidence_latex)) : h('span', { class: 'muted' }, '—'); } }
      ],
      rows,
      empty: 'Chưa có lỗi nào gắn KC (misconception_log trống).',
      rowClass: (m) => (m.resolved_at ? 'is-dim' : null)
    });

    const counts = {};
    d.mistakes.forEach((m) => {
      const s = E.db.session.find((x) => x.id === E.attSession.get(m.attempt_id));
      if (!s || s.status !== 'committed') return;
      const key = catOf(E, m.code) + '|' + s.held_on.slice(0, 7);
      counts[key] = (counts[key] || 0) + 1;
    });
    const max = Math.max(1, ...Object.values(counts));
    const kinds = ['accent', 'warn'];
    const bars = h('div', { class: 'stu-cat' }, CATS.map(([cat, lbl]) => [
      h('span', { class: 'stu-cat-l' }, lbl, h('span', { class: 'mono muted small' }, cat)),
      h('span', { class: 'stack', style: 'gap:3px' }, months.map((mo, i) => h('span', { class: 'stu-cat-row' },
        h('span', { class: 'small muted stu-cat-m' }, 'T' + (+mo.slice(5))), ui.bar(counts[cat + '|' + mo] || 0, max, { kind: kinds[i % 2] }), h('b', { class: 'num small' }, String(counts[cat + '|' + mo] || 0)))))
    ]));
    const unres = d.mis.filter((m) => !m.resolved_at).length;
    return h('div', { class: 'stack' },
      section(E, 'Cặp lỗi đã ghi (misconception_log)', ['table:misconception_log', 'misconception', 'table:mistake_current'], h('span', { class: 'row' }, ui.prov('code'), ui.store('db')),
        h('p', { class: 'muted small' }, d.mis.length + ' cặp (mã lỗi, KC) đã ghi · ' + unres + ' chưa hết, trong đó ' + d.repeatOpen.length + ' lỗi lặp (count ≥ 2, số lần tô vàng) · lỗi “hết” khi KC đạt ' + need(E) + ' lần đúng liên tiếp sau lần sai cuối. Lỗi không gắn KC không vào bảng này (không ảnh hưởng Elo).'),
        table),
      section(E, 'Tần suất theo nhóm lỗi', ['table:mistake_current', 'table:error_code'], ui.prov('code'),
        h('p', { class: 'muted small' }, 'Số lỗi đã duyệt (mistake_current, cả lỗi không gắn KC) theo 5 nhóm mã, tháng 9 so với tháng 10' + (months.indexOf(E.month) >= 0 ? ' (tháng 10 chưa hết)' : '') + '.'),
        h('div', { class: 'row small' }, h('span', { class: 'stu-key stu-key-accent' }), 'Tháng ' + fmt.month(months[0] || ''), h('span', { class: 'stu-key stu-key-warn' }), 'Tháng ' + fmt.month(months[1] || '')),
        bars));
  }

  /* ---------------- session history ---------------- */
  function historyView(E, st, d) {
    const { h, ui, ctx, fmt } = E;
    const c = code(E, st);
    if (!d.sessions.length) return h('div', { class: 'stack' }, noData(E));
    const items = d.sessions.slice().reverse().map((s) => {
      const committed = s.status === 'committed';
      const t = ctx.lookup.thread(s.thread_id);
      const atts = committed ? d.attBy[s.id] || [] : ((t && t.state && t.state.attempts) || []);
      const sc = atts.reduce((a, x) => a + (x.score || 0), 0), mx = atts.reduce((a, x) => a + (x.max_score || 0), 0);
      const nm = (d.misBy[s.id] || []).length;
      const dv = committed ? E.calc.deltaVsPrevious(E.db, s.id) : null;
      const dmean = dv && dv.kcs.length ? mean(dv.kcs.map((k) => k.d)) : null;
      const cls = committed ? 'is-db' : s.status === 'failed' ? 'is-failed' : 'is-pending';
      const props = t && t.state && t.state.proposals ? t.state.proposals.length : 0;
      return h('li', { class: cls },
        h('div', { class: 'card ' + (committed ? 'st-db' : s.status === 'failed' ? 'stu-failed' : 'st-pending') },
          h('div', { class: 'spread' },
            h('div', { class: 'row' }, h('strong', null, fmt.date(s.held_on)), ui.status(s.status), ui.chip(s.source_kind === 'pdf' ? 'PDF' : '.tex', s.source_kind === 'pdf' ? 'warn' : 'neutral'), h('span', { class: 'mono small muted stu-path' }, s.source_path)),
            ui.button('Xem buổi', () => ctx.nav('session', { session: s.id }), { size: 'sm' })),
          h('div', { class: 'stu-hist-nums' },
            h('span', null, h('span', { class: 'muted small' }, 'Số bài '), h('b', { class: 'num' }, String(atts.length))),
            h('span', null, h('span', { class: 'muted small' }, 'Điểm '), h('b', { class: 'num' }, mx ? sc + '/' + mx : '—')),
            committed ? h('span', null, h('span', { class: 'muted small' }, 'Lỗi đã duyệt '), h('b', { class: 'num' }, String(nm))) : h('span', null, h('span', { class: 'muted small' }, 'Đề xuất chờ duyệt '), h('b', { class: 'num' }, String(props))),
            dmean != null ? h('span', null, h('span', { class: 'muted small' }, 'Δθ TB '), signedEl(E, dmean)) : null,
            s.review_seconds ? h('span', null, h('span', { class: 'muted small' }, 'Thời gian duyệt '), h('b', { class: 'num' }, Math.floor(s.review_seconds / 60) + ' phút ' + pad2(s.review_seconds % 60) + ' giây')) : null),
          h('div', { class: 'row small muted' }, h('span', { class: 'mono' }, s.thread_id), committed ? 'đã ghi ' + fmt.dt(s.committed_at) : (t && t.error ? h('span', { class: 'stu-errtxt' }, t.error) : 'nằm trong checkpoints.db, chưa vào tutor.db'))));
    });
    return section(E, 'Lịch sử buổi', ['table:session', 'table:attempt', 'G1', 'cli:tutor review'], h('span', { class: 'row' },
      ui.button('Xem lời gọi LLM của ' + c, () => ctx.nav('logs', { student: c }), { size: 'sm', kind: 'ghost' })),
    h('p', { class: 'muted small' }, d.sessions.length + ' buổi (mới → cũ) · ' + d.done.length + ' đã ghi vào tutor.db · viền xanh = đã duyệt, viền vàng đứt = còn trong checkpoints.db.'),
    h('ol', { class: 'stu-tl' }, items));
  }

  /* ---------------- recommendations + reports ---------------- */
  function outputsView(E, st, d) {
    const { h, ui, ctx, fmt } = E;
    const c = code(E, st);
    const out = (E.ctx.data.files || {}).out || [];
    const mdBtn = (kind, key) => {
      const f = out.find((x) => x.kind === kind && x.student_id === st.id && x.key === key);
      return f ? h('span', { class: 'row', style: 'gap:6px' }, h('span', { class: 'store st-file' }, f.path),
        ui.button('Xem .md', () => ctx.modal({ title: f.path, wide: true, body: pre(E, f.text), actions: [{ label: 'Đóng' }] }), { size: 'sm', kind: 'ghost' })) : null;
    };
    const ths = ((ctx.data.checkpoints || {}).threads || []).filter((t) => t.student_id === st.id && t.status === 'awaiting_review');
    const pend = (g) => ths.filter((t) => t.graph === g).map((t) => h('div', { class: 'card st-pending' },
      h('div', { class: 'spread' }, h('div', { class: 'row' }, ui.chip(g, g), h('strong', null, t.subject || t.thread_id), ui.status('awaiting_review'), ui.store('checkpoint')),
        ui.button(g === 'G4' ? 'Mở danh sách chờ duyệt' : 'Mở báo cáo chờ duyệt', () => ctx.queue.open(t.thread_id), { size: 'sm', cli: 'tutor review ' + t.thread_id })),
      h('p', { class: 'small muted' }, ((t.state && t.state.proposals) || []).length + ' đề xuất · chưa vào tutor.db cho tới khi thầy/cô duyệt.')));

    const recs = E.db.recommendation.filter((r) => r.student_id === st.id);
    const dates = [...new Set(recs.map((r) => r.for_date))].sort().reverse();
    const recBlocks = dates.map((fd) => {
      const rows = recs.filter((r) => r.for_date === fd);
      const nA = rows.filter((r) => r.status === 'approved').length, nR = rows.filter((r) => r.status === 'rejected').length, nAd = rows.filter((r) => r.status === 'added').length;
      return h('div', { class: 'stack', style: 'gap:6px' },
        h('div', { class: 'spread' }, h('h3', null, 'Cho buổi ' + fmt.date(fd), ' ', h('span', { class: 'muted small' }, rows.length + ' bài · ' + nA + ' duyệt' + (nR ? ' · ' + nR + ' bỏ' : '') + (nAd ? ' · ' + nAd + ' GV thêm' : '') + ' · duyệt ' + fmt.dt(rows[0].reviewed_at))), mdBtn('recommend', fd)),
        ui.table({
          columns: [
            { label: 'Bài', render: (r) => h('span', { class: 'mono' }, (ctx.lookup.problem(r.problem_id) || {}).ref || '?') },
            { label: 'KC', render: (r) => kcLabel(E, r.kc_id) },
            { label: 'Nhóm', render: (r) => (BUCKET[r.bucket] ? ui.chip(BUCKET[r.bucket][0], BUCKET[r.bucket][1]) : ui.chip('GV tự chọn')) },
            { label: 'Trạng thái', render: (r) => ui.status(r.status) },
            { label: 'Lý do', render: (r) => (r.reason ? h('span', { class: 'small' }, ui.prov(r.status === 'added' ? 'gv' : 'llm', r.status === 'added' ? 'GV' : '08'), ' ', r.reason) : h('span', { class: 'muted' }, '—')) }
          ],
          rows,
          rowClass: (r) => (r.status === 'rejected' ? 'is-dim stu-strike' : null)
        }));
    });

    const reps = E.db.report.filter((r) => r.student_id === st.id);
    const months = (ctx.data.meta || {}).months || [];
    const repBlocks = months.slice().reverse().map((m) => {
      const r = reps.find((x) => x.month === m);
      const pendingG5 = ths.some((t) => t.graph === 'G5' && t.state && t.state.month === m);
      if (!r) {
        return h('div', { class: 'card stu-month' }, h('div', { class: 'spread' },
          h('div', { class: 'row' }, h('strong', null, 'Tháng ' + fmt.month(m)), pendingG5 ? ui.status('awaiting_review') : ui.chip('chưa tạo'), m === E.month ? h('span', { class: 'muted small' }, 'tháng chưa hết') : null),
          pendingG5 ? null : ui.button('Mở Báo cáo tháng', () => ctx.nav('report', { student: st.id, month: m }), { size: 'sm', kind: 'ghost' })));
      }
      return h('div', { class: 'card st-db' },
        h('div', { class: 'spread' }, h('div', { class: 'row' }, h('strong', null, 'Tháng ' + fmt.month(m)), ui.status('approved'), h('span', { class: 'muted small' }, 'duyệt ' + fmt.dt(r.approved_at))), mdBtn('report', m)),
        reportText(E, r),
        h('div', { class: 'row' }, h('span', { class: 'small muted' }, r.facts_json.length + ' fact · ' + r.audit_json.filter((x) => x.result !== 'dropped').length + ' câu qua audit'),
          ui.button('Mở trong Báo cáo tháng', () => ctx.nav('report', { student: st.id, month: m }), { size: 'sm', kind: 'ghost' })));
    });

    return h('div', { class: 'stack stu-outputs' },
      section(E, 'Gợi ý bài đã duyệt', ['G4', 'agent:08', 'table:recommendation', 'file:data/out/'], ui.store('db'),
        ...pend('G4'), recBlocks.length ? recBlocks : ui.empty('Chưa có danh sách gợi ý nào được duyệt cho ' + c + '.', ui.button('Gợi ý buổi sau', () => ctx.nav('recommend', { student: st.id }), { size: 'sm' }))),
      section(E, 'Báo cáo tháng', ['G5', 'agent:09', 'table:report', 'fact_id'], ui.store('db'), ...pend('G5'), repBlocks));
  }

  function reportText(E, r) {
    const { h } = E;
    const lines = String(r.text_md || '').split('\n').filter((l) => l.trim() && !/^\*\*.*\*\*$/.test(l.trim()));
    const facts = new Map(r.facts_json.map((f) => [f.fact_id, f]));
    return h('div', { class: 'stu-report' }, lines.map((l) => h('p', null, l.split(/(\[F\d+\])/).map((part) => {
      const m = /^\[(F\d+)\]$/.exec(part);
      if (!m) return part;
      const f = facts.get(m[1]);
      return h('span', { class: 'chip stu-fact', title: f ? f.label + ' = ' + (f.unit === '%' ? Math.round(f.value * 100) + '%' : f.value + (f.unit ? ' ' + f.unit : '')) : m[1] }, m[1]);
    }))));
  }
})();
