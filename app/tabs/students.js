/* Học sinh (P1-T06): danh sách, thêm, sửa, lưu trữ qua /api/students. Hồ sơ, Elo, lịch sử làm ở P4. */
(() => {
  'use strict';
  // Giữ qua các lần render trong phiên; token bỏ kết quả fetch cũ khi đã render lại.
  const S = { archived: false, token: 0 };

  App.registerTab('students', { title: 'Học sinh', render });

  function render(root, ctx) {
    const token = ++S.token;
    const { ui } = ctx, h = ui.h;
    root.append(h('p', { class: 'muted' }, 'Đang tải danh sách học sinh…'));
    return api.get('/students?archived=1').then((all) => {
      if (token !== S.token) return;
      const paint = () => root.replaceChildren(view(ctx, all, paint));
      paint();
      const tr = root.querySelector('tr.is-sel');
      if (tr) { tr.classList.add('flash-hl'); tr.scrollIntoView({ block: 'nearest' }); }
    }, (e) => {
      if (token !== S.token) return;
      root.replaceChildren(ui.pageHead({}), h('div', { class: 'callout callout-crit', role: 'alert' },
        h('strong', null, 'Không tải được danh sách học sinh.'), h('p', { class: 'mono small' }, e.message),
        h('div', null, ui.button('Thử lại', ctx.rerender))));
    });
  }

  function view(ctx, all, paint) {
    const { ui } = ctx, h = ui.h;
    const lead = 'Học sinh của thầy/cô. Tên chỉ lưu trên máy này; API chỉ nhận mã HS-xx, không bao giờ nhận tên.';
    if (!all.length) {
      return h('div', { class: 'stack' }, ui.pageHead({ lead }),
        ui.empty('Chưa có học sinh nào. Thêm học sinh đầu tiên để bắt đầu nộp bài.', ui.button('Thêm học sinh', () => edit(ctx, null), { kind: 'primary' })));
    }
    const sel = ctx.params.student != null && ctx.params.student !== '' ? String(ctx.params.student) : null;
    const isSel = (s) => String(s.id) === sel;
    const nArch = all.filter((s) => s.archived_at).length;
    // HS được chọn từ nơi khác vẫn hiện dù đã lưu trữ.
    const rows = all.filter((s) => S.archived || !s.archived_at || isSel(s));
    const none = (t) => h('span', { class: 'muted stu-none' }, t);

    const table = ui.table({
      columns: [
        { label: 'Mã', render: (s) => h('span', { class: 'mono' }, s.code) },
        { label: ['Tên ', h('span', { class: 'muted small' }, '(chỉ lưu trên máy này)')],
          render: (s) => [h('strong', null, s.name), s.archived_at ? [' ', h('span', { class: 'status s-locked', title: 'archived_at = ' + s.archived_at }, 'đã lưu trữ ' + ui.fmt.date(s.archived_at))] : null] },
        { label: 'Lớp', align: 'center', render: (s) => (s.grade == null ? none('—') : String(s.grade)) },
        { label: 'Ghi chú', render: (s) => s.note || none('—') },
        { label: '', align: 'right', render: (s) => h('div', { class: 'row stu-acts' },
          ui.button('Sửa', () => edit(ctx, s), { size: 'sm', title: 'Sửa ' + s.code }),
          s.archived_at ? null : ui.button('Lưu trữ', () => archive(ctx, s), { size: 'sm', kind: 'ghost', title: 'Lưu trữ ' + s.code })) }
      ],
      rows,
      empty: 'Mọi học sinh đã lưu trữ. Bật “Hiện HS đã lưu trữ” để xem.',
      rowClass: (s) => [s.archived_at ? 'is-dim' : '', isSel(s) ? 'is-sel' : ''].join(' ').trim() || null
    });
    table.classList.add('stu-list-tbl');

    return h('div', { class: 'stack' },
      ui.pageHead({ lead, actions: [ui.button('Thêm học sinh', () => edit(ctx, null), { kind: 'primary' })] }),
      h('section', { class: 'section' },
        h('div', { class: 'section-head' }, h('h2', null, 'Danh sách'), ui.privacy('HS-xx')),
        h('div', { class: 'stu-filters' },
          h('label', { class: 'stu-check' },
            h('input', { type: 'checkbox', checked: S.archived, onchange: (e) => { S.archived = e.target.checked; paint(); } }),
            'Hiện HS đã lưu trữ (' + nArch + ')'),
          h('span', { class: 'muted small' }, rows.length + '/' + all.length + ' học sinh')),
        sel && !all.some(isSel) ? h('p', { class: 'muted small' }, 'Không tìm thấy học sinh có id ' + sel + '.') : null,
        table));
  }

  /* Thêm (st = null) hoặc sửa một học sinh trong modal. */
  function edit(ctx, st) {
    const h = ctx.ui.h;
    const name = h('input', { type: 'text', id: 'stu-f-name', value: st ? st.name : '', placeholder: 'VD: Hoàng Mai Anh', autocomplete: 'off', autofocus: true });
    const grade = h('select', { id: 'stu-f-grade' }, h('option', { value: '' }, '— chưa ghi —'),
      Array.from({ length: 12 }, (_, i) => h('option', { value: String(i + 1), selected: !!st && st.grade === i + 1 }, 'Lớp ' + (i + 1))));
    const note = h('input', { type: 'text', id: 'stu-f-note', value: (st && st.note) || '', placeholder: 'VD: Ôn thi vào 10', autocomplete: 'off' });
    const err = h('p', { class: 'stu-err', role: 'alert' });
    let busy = false;
    const save = (close) => {
      if (busy) return null;
      const body = { name: name.value.trim(), grade: grade.value ? +grade.value : null, note: note.value.trim() || null };
      if (!body.name) { err.textContent = 'Cần nhập tên học sinh.'; name.focus(); return null; }
      if (st && body.name === st.name && body.grade === st.grade && body.note === (st.note || null)) {
        close(); ctx.toast('Không có gì thay đổi.'); return null;
      }
      busy = true;
      return (st ? api.send('PATCH', '/students/' + st.id, body) : api.send('POST', '/students', body)).then((r) => {
        close();
        TutorApi.refreshCounts();
        ctx.toast(st ? 'Đã lưu ' + r.code + '.' : 'Đã thêm. Mã gửi API: ' + r.code, { kind: 'ok' });
        ctx.nav('students', { student: r.id });
      }, (e) => { busy = false; err.textContent = e.message; });
    };
    ctx.modal({
      title: st ? 'Sửa ' + st.code : 'Thêm học sinh',
      body: h('div', { class: 'stack' },
        h('div', { class: 'callout callout-info' }, h('p', null,
          st ? ['API vẫn chỉ nhận mã ', h('b', { class: 'mono' }, st.code), '. Tên chỉ lưu trên máy này.']
            : 'Mã HS-xx được cấp khi lưu. Tên chỉ lưu trên máy này; API chỉ nhận mã.')),
        h('label', { class: 'field', for: 'stu-f-name' }, h('span', null, 'Tên học sinh'), name),
        h('label', { class: 'field', for: 'stu-f-grade' }, h('span', null, 'Lớp (tuỳ chọn)'), grade),
        h('label', { class: 'field', for: 'stu-f-note' }, h('span', null, 'Ghi chú (tuỳ chọn)'), note),
        err),
      actions: [{ label: 'Huỷ' }, { label: st ? 'Lưu' : 'Thêm học sinh', kind: 'primary', onClick: save }]
    });
  }

  function archive(ctx, s) {
    return ctx.confirm('Lưu trữ ' + s.code + ' · ' + s.name + '? Học sinh ẩn khỏi danh sách mặc định; dữ liệu trong tutor.db giữ nguyên. Hiện chưa bỏ lưu trữ được từ app.',
      { title: 'Lưu trữ học sinh', ok: 'Lưu trữ', danger: true }).then((yes) => {
      if (!yes) return null;
      return api.send('POST', '/students/' + s.id + '/archive').then(() => {
        TutorApi.refreshCounts();
        ctx.toast('Đã lưu trữ ' + s.code + '.', { kind: 'ok' });
        ctx.rerender();
      }, (e) => ctx.toast('Không lưu trữ được ' + s.code + ': ' + e.message, { kind: 'error' }));
    });
  }
})();
