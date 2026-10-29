/* Appended to src/mock.js by mock/gen_mock.py. Mirrors the Python generator: change both together. */

/* Hydrate: fields left out of the JSON because they are derived 1:1 from other fields (keeps mock.js small). */
(function (M) {
  if (!M || !M.db) return;
  var split = function (s) { return String(s || '').split(/\n\s*\n/).map(function (x) { return x.trim(); }).filter(Boolean); };
  var refOf = {}, byId = {};
  var steps = function (p) { p.solution_steps = split(p.solution_latex).map(function (latex, i) { return { idx: i + 1, latex: latex }; }); };
  M.db.problem.forEach(function (p) { refOf[p.id] = p.ref; byId[p.id] = p; steps(p); });
  ((M.checkpoints || {}).threads || []).forEach(function (t) { ((t.state || {}).problems || []).forEach(steps); });
  var bySession = {};
  M.db.attempt.forEach(function (a) {
    var pos = 0;
    a.steps_json.forEach(function (s) {
      if (s.latex == null) s.latex = byId[a.problem_id].solution_steps[s.idx - 1].latex;   // student step = model step
      s.pos = [pos, pos + s.latex.length]; pos += s.latex.length + 2;
    });
    a.solution_latex = a.steps_json.map(function (s) { return s.latex; }).join('\n\n');
    (bySession[a.session_id] = bySession[a.session_id] || []).push(a);
  });
  M.db.session.forEach(function (s) {
    var atts = bySession[s.id];
    if (s.transcript_latex != null || !atts) return;
    atts.sort(function (a, b) { return a.seq - b.seq; });
    s.transcript_latex = (s.source_kind === 'pdf' ? '% 01 Ingest chép từ PDF\n' : '') + atts.map(function (a) {
      return '\\begin{problem}[' + refOf[a.problem_id] + ']\n' + a.solution_latex + '\n\\end{problem}';
    }).join('\n\n');
  });
  var table = function (t) {   // {cols, rows} → array of objects
    return t.rows.map(function (r) { var o = {}; t.cols.forEach(function (c, i) { o[c] = r[i]; }); return o; });
  };
  ['problem_pair', 'skill_event'].forEach(function (k) { if (!Array.isArray(M.db[k])) M.db[k] = table(M.db[k]); });
  M.db.mistake.forEach(function (m) {
    if (m.llm_json === 'same') m.llm_json = { step_idx: m.step_idx, code: m.code, kc_id: m.kc_id, description: m.description,
      evidence_latex: m.evidence_latex, confidence: m.confidence };
  });
  var f = M.files, P = M.settings.price_assumption, L = f.llm_log;
  if (L && !Array.isArray(L)) {
    f.llm_log = table(L).map(function (o) {
      o.thread_id = L.threads[o.thread_id];
      o.ts = new Date((L.ts_base + o.ts) * 1000).toISOString().replace('.000Z', 'Z');
      o.model = M.settings.models[o.agent];
      // † cost from settings.price_assumption, not real pricing
      o.cost_usd = Math.round(o.tokens_in * P.input_per_mtok + o.tokens_out * P.output_per_mtok + o.cache_read_tokens * P.cache_read_per_mtok) / 1e6;
      return o;
    });
  }
})(window.MOCK);

window.TutorCalc = (function () {
  var r4 = function (x) { return Math.round(x * 1e4) / 1e4; };
  var cmp = function (a, b) { return a < b ? -1 : a > b ? 1 : 0; };
  var cfg = function (settings) {
    var S = settings || (window.MOCK && window.MOCK.settings) || {};
    return {
      K: S.elo ? S.elo.K : 0.3, theta0: S.elo ? S.elo.theta0 : 0,
      need: S.misconception ? S.misconception.resolve_streak : 2, reco: S.reco
    };
  };

  function elo(theta, delta, X, K) {
    if (K == null) K = 0.3;
    var P = 1 / (1 + Math.exp(-(theta - delta)));
    return { P: P, thetaAfter: theta + K * (X - P) };
  }

  function currentMistakes(db) {
    var supM = {}, supA = {};
    db.mistake.forEach(function (m) { if (m.supersedes_id != null) supM[m.supersedes_id] = 1; });
    db.attempt.forEach(function (a) { if (a.supersedes_id != null) supA[a.supersedes_id] = 1; });
    return db.mistake.filter(function (m) { return m.status !== 'rejected' && !supM[m.id] && !supA[m.attempt_id]; });
  }

  function xFor(attempt, kcId, mistakes) {
    var sup = {};
    mistakes.forEach(function (m) { if (m.supersedes_id != null) sup[m.supersedes_id] = 1; });
    return mistakes.some(function (m) {
      return m.attempt_id === attempt.id && m.kc_id === kcId && m.status !== 'rejected' && !sup[m.id];
    }) ? 0 : 1;
  }

  function kcIndex(db) {
    var by = {};
    db.problem_kc.slice().sort(function (a, b) { return (a.step_idx - b.step_idx) || (a.kc_id - b.kc_id); })
      .forEach(function (r) { var l = by[r.problem_id] || (by[r.problem_id] = []); if (l.indexOf(r.kc_id) < 0) l.push(r.kc_id); });
    return by;
  }

  // Elo + streak + misconception log from committed attempts in (held_on, seq) order; beforeDate = state as of that day.
  function replay(db, studentId, beforeDate, settings) {
    var c = cfg(settings), sess = {}, supA = {};
    db.session.forEach(function (s) {
      if (s.student_id === studentId && s.status === 'committed' && (!beforeDate || s.held_on < beforeDate)) sess[s.id] = s;
    });
    db.attempt.forEach(function (a) { if (a.supersedes_id != null) supA[a.supersedes_id] = 1; });
    var atts = db.attempt.filter(function (a) { return sess[a.session_id] && !supA[a.id]; }).sort(function (a, b) {
      return cmp(sess[a.session_id].held_on, sess[b.session_id].held_on) || (a.session_id - b.session_id) || (a.seq - b.seq);
    });
    var mBy = {};
    currentMistakes(db).forEach(function (m) { (mBy[m.attempt_id] = mBy[m.attempt_id] || []).push(m); });
    var delta = {};
    db.problem.forEach(function (p) { delta[p.id] = p.delta; });
    var kcs = kcIndex(db), state = {}, stateOrder = [], mis = {}, misOrder = [], events = [];
    atts.forEach(function (a) {
      var s = sess[a.session_id], day = s.held_on, seen = {};
      var ms = (mBy[a.id] || []).filter(function (m) { return m.kc_id != null; });
      ms.forEach(function (m) {
        var key = m.code + '|' + m.kc_id;
        if (seen[key]) return;
        seen[key] = 1;
        var e = mis[key];
        if (e) { e.count += 1; e.last_seen = day; e.resolved_at = null; }
        else { mis[key] = { student_id: studentId, code: m.code, kc_id: m.kc_id, first_seen: day, last_seen: day, count: 1, resolved_at: null }; misOrder.push(key); }
      });
      (kcs[a.problem_id] || []).forEach(function (kc) {
        var st = state[kc];
        if (!st) { st = state[kc] = { student_id: studentId, kc_id: kc, theta: c.theta0, n_attempts: 0, correct_streak: 0, last_seen: null, updated_at: null }; stateOrder.push(kc); }
        var X = ms.some(function (m) { return m.kc_id === kc; }) ? 0 : 1;
        var d = delta[a.problem_id], r = elo(st.theta, d, X, c.K), after = r4(r.thetaAfter);
        events.push({ student_id: studentId, kc_id: kc, attempt_id: a.id, outcome: X, p_expected: r4(r.P),
          theta_before: st.theta, theta_after: after, delta: d, created_at: s.committed_at });
        st.theta = after; st.n_attempts += 1; st.correct_streak = X ? st.correct_streak + 1 : 0;
        st.last_seen = day; st.updated_at = s.committed_at;
        if (X && st.correct_streak >= c.need) misOrder.forEach(function (k) {
          var e = mis[k]; if (e.kc_id === kc && e.resolved_at == null) e.resolved_at = day;
        });
      });
    });
    return {
      skill_event: events,
      skill_state: stateOrder.map(function (k) { return state[k]; }),
      misconception_log: misOrder.map(function (k) { return mis[k]; })
    };
  }

  function codesOf(db, sessionId, cur) {
    var ids = {}, out = [];
    db.attempt.forEach(function (a) { if (a.session_id === sessionId) ids[a.id] = 1; });
    cur.forEach(function (m) { if (ids[m.attempt_id] && out.indexOf(m.code) < 0) out.push(m.code); });
    return out.sort();
  }

  // → { kcs:[{kc_id, theta_before, theta_after, d}], repeat, new, gone, resolved:[{code, kc_id}] }
  function deltaVsPrevious(db, sessionId) {
    var s = db.session.find(function (x) { return x.id === sessionId; });
    if (!s) return null;
    var rep = replay(db, s.student_id), ids = {}, per = {}, order = [];
    db.attempt.forEach(function (a) { if (a.session_id === sessionId) ids[a.id] = 1; });
    rep.skill_event.forEach(function (e) {
      if (!ids[e.attempt_id]) return;
      if (!per[e.kc_id]) { per[e.kc_id] = { kc_id: e.kc_id, theta_before: e.theta_before, theta_after: e.theta_after, d: 0 }; order.push(e.kc_id); }
      per[e.kc_id].theta_after = e.theta_after;
    });
    var kcs = order.map(function (k) { var p = per[k]; p.d = r4(p.theta_after - p.theta_before); return p; });
    var prev = db.session.filter(function (x) { return x.student_id === s.student_id && x.status === 'committed' && x.held_on < s.held_on; })
      .sort(function (a, b) { return cmp(a.held_on, b.held_on); }).pop() || null;
    var cur = currentMistakes(db), now = codesOf(db, s.id, cur), before = prev ? codesOf(db, prev.id, cur) : [];
    return {
      session_id: s.id, previous_session_id: prev ? prev.id : null, kcs: kcs,
      repeat: now.filter(function (c) { return before.indexOf(c) >= 0; }),
      new: now.filter(function (c) { return before.indexOf(c) < 0; }),
      gone: before.filter(function (c) { return now.indexOf(c) < 0; }),
      resolved: rep.misconception_log.filter(function (m) { return m.resolved_at === s.held_on; }).map(function (m) { return { code: m.code, kc_id: m.kc_id }; })
    };
  }

  function passRate(attempts) {
    var s = 0, m = 0;
    attempts.forEach(function (a) { s += a.score || 0; m += a.max_score || 0; });
    return m ? s / m : 0;
  }

  function fmtFact(f) { return f.unit === '%' ? Math.round(f.value * 100) + '%' : String(f.value).replace('-', '−'); }

  // audit.py: ≥1 [Fxx]; every number must equal a cited fact value (±0.005; 68% ≡ 0.68).
  function audit(sentence, facts) {
    var text = typeof sentence === 'string' ? sentence : (sentence && sentence.text) || '';
    var ids = (text.match(/\[F\d+\]/g) || []).map(function (x) { return x.slice(1, -1); });
    if (!ids.length) return { ok: false, reason: 'không trích fact_id' };
    var cited = [];
    for (var i = 0; i < ids.length; i++) {
      var f = facts.find(function (x) { return x.fact_id === ids[i]; });
      if (!f) return { ok: false, reason: 'fact_id ' + ids[i] + ' không có trong facts' };
      if (cited.indexOf(f) < 0) cited.push(f);
    }
    var nums = text.replace(/\[F\d+\]/g, '').match(/[-−]?\d+(?:[.,]\d+)?%?/g) || [];
    for (var j = 0; j < nums.length; j++) {
      var tok = nums[j], pct = tok.charAt(tok.length - 1) === '%';
      var v = parseFloat(tok.replace('−', '-').replace(',', '.').replace('%', ''));
      if (pct) v = v / 100;
      var hit = cited.some(function (f) { return typeof f.value === 'number' && Math.abs(f.value - v) <= 0.005 + 1e-9; });
      if (!hit) {
        var ref = (pct && cited.find(function (f) { return f.unit === '%'; })) || cited[0];
        return { ok: false, reason: 'số ' + tok + ' không khớp ' + ref.fact_id + ' = ' + fmtFact(ref) };
      }
    }
    return { ok: true, reason: null };
  }

  function largestRemainder(n, ratios) {
    var raw = ratios.map(function (r) { return n * r; });
    var fl = raw.map(function (x) { return Math.floor(x + 1e-9); });
    var left = n - fl.reduce(function (a, b) { return a + b; }, 0);
    raw.map(function (x, i) { return i; })
      .sort(function (a, b) { return ((raw[b] - fl[b]) - (raw[a] - fl[a])) || (a - b); })
      .slice(0, Math.max(0, left)).forEach(function (i) { fl[i] += 1; });
    return fl;
  }

  // select.py: buckets 40/50/10 (largest remainder), one problem per KC, review = easiest eligible problem.
  // One problem per KC meets min_kc_mix whenever enough KCs have candidates; kc_mix_ok:false means the bank ran short.
  function selectRecommendations(db, settings, studentId, forDate) {
    var c = cfg(settings), R = c.reco, minMix = R.min_kc_mix != null ? R.min_kc_mix : 3;
    var student = db.student.find(function (s) { return s.id === studentId; });
    var rep = replay(db, studentId, forDate, settings), theta = {};
    rep.skill_state.forEach(function (s) { theta[s.kc_id] = s.theta; });
    var th = function (k) { return theta[k] != null ? theta[k] : c.theta0; };
    var kcCode = {}; db.kc.forEach(function (k) { kcCode[k.id] = k.code; });
    var codeDesc = {}; db.error_code.forEach(function (e) { codeDesc[e.code] = e.description; });
    var prereq = {}; db.kc_prereq.forEach(function (r) { (prereq[r.kc_id] = prereq[r.kc_id] || []).push(r.prereq_id); });
    var rubricV = {}; db.rubric.forEach(function (r) { if (!rubricV[r.problem_id] || r.version > rubricV[r.problem_id]) rubricV[r.problem_id] = r.version; });
    var sess = {}; db.session.forEach(function (s) { if (s.student_id === studentId && s.status === 'committed' && s.held_on < forDate) sess[s.id] = s; });
    var lastDone = {};
    db.attempt.forEach(function (a) { var s = sess[a.session_id]; if (s && (!lastDone[a.problem_id] || s.held_on > lastDone[a.problem_id])) lastDone[a.problem_id] = s.held_on; });
    var kcs = kcIndex(db), byKc = {}, kcOrder = [], day = 86400000;
    db.problem.filter(function (p) { return p.lop === student.grade; }).sort(function (a, b) { return a.id - b.id; }).forEach(function (p) {
      (kcs[p.id] || []).forEach(function (k) {
        var ld = lastDone[p.id] || null, ex = null;
        if (!rubricV[p.id]) ex = 'chưa có rubric';
        else if (p.delta == null || !p.difficulty_approved_at) ex = 'δ chưa duyệt';
        else if (ld && (Date.parse(forDate) - Date.parse(ld)) / day < R.no_repeat_days) ex = 'đã làm ' + ld + ' (< ' + R.no_repeat_days + ' ngày)';
        if (!byKc[k]) { byKc[k] = []; kcOrder.push(k); }
        byKc[k].push({ problem_id: p.id, kc_id: k, delta: p.delta, gap: p.delta == null ? null : r4(th(k) - p.delta),
          last_done: ld, rubric_version: rubricV[p.id] || null, excluded: ex });
      });
    });
    var counts = largestRemainder(R.n_problems, [R.ratios.review, R.ratios.zpd, R.ratios.challenge]);
    var used = {}, chosen = {}, picks = [], lo = R.zpd_window[0], hi = R.zpd_window[1];
    var free = function (k) { return (byKc[k] || []).filter(function (x) { return !x.excluded && !used[x.problem_id]; }); };
    var add = function (cand, bucket, extra) {
      used[cand.problem_id] = 1; chosen[cand.kc_id] = 1;
      var p = { problem_id: cand.problem_id, kc_id: cand.kc_id, bucket: bucket, theta: th(cand.kc_id), delta: cand.delta, gap: cand.gap,
        last_done: cand.last_done, rubric_version: cand.rubric_version };
      for (var x in extra) p[x] = extra[x];
      picks.push(p);
    };
    // review: KCs with unresolved misconceptions, count desc, last_seen desc, code asc
    var agg = {};
    rep.misconception_log.forEach(function (m) {
      if (m.resolved_at != null) return;
      var a = agg[m.kc_id] || (agg[m.kc_id] = { kc_id: m.kc_id, count: 0, last_seen: '', code: null, codeCount: -1 });
      a.count += m.count;
      if (m.last_seen > a.last_seen) a.last_seen = m.last_seen;
      if (m.count > a.codeCount || (m.count === a.codeCount && m.code < a.code)) { a.code = m.code; a.codeCount = m.count; }
    });
    var rev = Object.keys(agg).map(function (k) { return agg[k]; }).sort(function (a, b) {
      return (b.count - a.count) || cmp(b.last_seen, a.last_seen) || cmp(kcCode[a.kc_id], kcCode[b.kc_id]);
    });
    var nRev = 0;
    rev.forEach(function (a) {
      if (nRev >= counts[0] || chosen[a.kc_id]) return;
      var el = free(a.kc_id).sort(function (x, y) { return (x.delta - y.delta) || (x.problem_id - y.problem_id); });
      if (!el.length) return;
      add(el[0], 'review', { code: a.code, count: a.count, codeCount: a.codeCount, codeDesc: codeDesc[a.code] });   // count = whole KC
      nRev += 1;
    });
    var greedy = function (n, bucket, keyOf) {
      for (var i = 0; i < n; i++) {
        var best = null;
        kcOrder.forEach(function (k) {
          if (chosen[k]) return;
          free(k).forEach(function (cand) {
            var key = keyOf(cand);
            if (!key) return;
            key = key.concat([cand.delta, kcCode[k], cand.problem_id]);
            if (!best || cmpKey(key, best.key) < 0) best = { key: key, cand: cand };
          });
        });
        if (!best) return i;
        var extra = {};
        if (bucket === 'challenge') extra.prereq = (prereq[best.cand.kc_id] || []).map(function (p) { return kcCode[p]; });
        add(best.cand, bucket, extra);
      }
      return n;
    };
    var cmpKey = function (a, b) { for (var i = 0; i < a.length; i++) { var d = cmp(a[i], b[i]); if (d) return d; } return 0; };
    var zN = counts[1] + (counts[0] - nRev);
    var nZ = greedy(zN, 'zpd', function (x) { return x.gap >= lo && x.gap <= hi ? [Math.abs(x.gap)] : null; });
    var cN = counts[2] + (zN - nZ);
    var nC = greedy(cN, 'challenge', function (x) {
      var ok = (prereq[x.kc_id] || []).every(function (p) { return th(p) >= 0; });
      return ok && -x.gap > 0.5 ? [-x.gap] : null;
    });
    greedy(cN - nC, 'zpd', function (x) { return [Math.abs(x.gap)]; });   // fallback: closest remaining
    var picked = {};
    picks.forEach(function (p) { picked[p.kc_id] = 1; });
    var candidates = [];
    picks.forEach(function (p) {
      byKc[p.kc_id].slice().sort(function (a, b) {
        return cmp(a.gap == null ? 1 : 0, b.gap == null ? 1 : 0) || (Math.abs(a.gap || 0) - Math.abs(b.gap || 0)) || (a.problem_id - b.problem_id);
      }).forEach(function (x) { candidates.push({ problem_id: x.problem_id, kc_id: x.kc_id, gap: x.gap, last_done: x.last_done, rubric_version: x.rubric_version, excluded: x.excluded }); });
    });
    return {
      counts: { review: counts[0], zpd: counts[1], challenge: counts[2] },
      kc_selection: picks.map(function (p) { return { kc_id: p.kc_id, bucket: p.bucket, theta: p.theta }; }),
      candidates: candidates,
      picks: picks,
      kc_mix: Object.keys(picked).length,
      min_kc_mix: minMix,
      kc_mix_ok: Object.keys(picked).length >= minMix
    };
  }

  return { elo: elo, xFor: xFor, replay: replay, deltaVsPrevious: deltaVsPrevious, passRate: passRate, audit: audit,
    selectRecommendations: selectRecommendations, largestRemainder: largestRemainder, currentMistakes: currentMistakes };
})();
