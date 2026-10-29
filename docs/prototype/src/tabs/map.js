/* map — Bản đồ hệ thống (IA §3.11). Text from diagrams 00–12, spec §2–§13, tài liệu thiết kế §11. Params: section, node. */
(function () {
  'use strict';
  var arr = function (x) { return Array.isArray(x) ? x : []; };
  var pc = function (x) { return Math.round((+x || 0) * 100) + '%'; };
  var vn = function (x) { return String(x).replace('-', '−'); };

  // Agent cards (diagrams 01–09). Steps: [provenance, text | fn(settings)].
  var AGENT = {
    '01': {
      input: ['Bài làm HS: .tex (ưu tiên) hoặc PDF xuất từ LaTeX', 'Ngân hàng bài (đề + lời giải mẫu)', 'Mẫu quy ước \\begin{problem}[id] … \\end{problem}'],
      steps: [['code', '1a. Có .tex → pylatexenc cắt theo môi trường problem; giữ pos / pos_end làm bằng chứng'],
        ['llm', '1b. Chỉ có PDF → gửi PDF cho Claude, chép lại LaTeX nguyên văn, không sửa lỗi'],
        ['code', '2. Kiểm tra trung thực: số và biến trong bản chép phải có trong text layer PDF; lệch → cờ mismatch (đề xuất thêm, chưa có trong spec)'],
        ['llm', '3. Khớp problem_ref: có id → tra ngân hàng; không có id → LLM so đề với ngân hàng'],
        ['gv', '4. Thầy/cô xác nhận bài khớp không chắc (DỪNG 1 của G1)'],
        ['code', '5. Tách bước: mỗi dòng / phương trình là 1 bước']],
      output: 'Attempt: problem_ref · solution_latex · steps[] {idx, latex, pos} · source tex | pdf · flags[] (low_match, mismatch, no_rubric)',
      rule: 'Giữ nguyên mọi lỗi của học sinh khi chép.',
      papers: ['LaTA (Rodríguez, 2026): ingest → segment → grade → report cho bài LaTeX', 'Yu et al. (ICML 2026): cố định khuôn bài làm thay vì tách tự động', 'FERMAT (ACL 2025): đưa LaTeX thay vì ảnh giúp định vị lỗi tốt hơn', 'Seong et al. (2026): model chép lại hay tự “sửa” lỗi của HS → kiểm bằng code', 'MathEDU (EACL 2026): mỗi lỗi gắn với một phương trình cụ thể']
    },
    '02': {
      input: ['Attempt (từ 01 Ingest)', 'Đề + lời giải mẫu', 'Rubric cache (bảng rubric, có version)'],
      steps: [['code', '1. Bài đã có rubric được duyệt? → dùng luôn; chưa có → bước 2'],
        ['llm', '2. Sinh rubric từ lời giải mẫu: mục nhị phân bám từng ý; ghi rõ cách giải khác được chấp nhận'],
        ['gv', '3. Thầy/cô duyệt rubric lần đầu (G2, hoặc DỪNG 1 của G1); lưu version'],
        ['llm', '4. Chấm: rubric + lời giải mẫu + 1 ví dụ + bài HS trong khung UNTRUSTED INPUT; mỗi mục đạt / không + trích LaTeX'],
        ['code', '5. Kiểm bằng code: tổng = tổng các mục; mục đạt phải có bằng chứng; cờ “cách giải khác” → hàng duyệt']],
      output: 'Grade: rubric_version · items[] {item_id, passed, evidence_latex} · score / max_score · alt_method',
      rule: 'Không viết nhận xét cho học sinh (tránh lộ lời giải mẫu).',
      papers: ['RefGrader (2025): sinh rubric riêng từng bài từ lời giải mẫu, cache', 'LaTA (2026): rubric nhị phân bám bài con, bài HS trong khung UNTRUSTED INPUT', 'Lambdafeedback (2026): điểm nhạy với câu chữ → cố định wording, GV duyệt', 'VUB human-in-the-loop (2026): ghi rõ cách giải khác, trả cờ “cách làm khác nhưng hợp lý”']
    },
    '03': {
      input: ['Attempt (steps[]) từ 01', 'Grade: các mục trượt (từ 02)', 'Đề + lời giải mẫu', 'Taxonomy 18 mã + 1 ví dụ mỗi mã', '5 lỗi đã duyệt gần nhất của HS, mọi KC (SQL) — chờ chốt'],
      steps: [['llm', '1. Lượt 1: viết lại lời giải ĐÚNG theo chính cách làm của HS, sửa tối thiểu'],
        ['llm', '2. Lượt 2: so bài HS với bản sửa → bước sai đầu tiên + các bước sai khác'],
        ['llm', '3. Gắn mã lỗi: nhóm (tính toán / khái niệm / ký hiệu / trình bày / không rõ) + mã con; prompt có 1 ví dụ mỗi mã'],
        ['llm', '4. Mỗi lỗi: mô tả + đoạn LaTeX của phương trình sai + confidence']],
      output: 'Mistake[]: step_idx · category.subcategory · kc_id (trong KC của bài) · description · evidence_latex · confidence 0–1 — chỉ nằm trong checkpoint',
      rule: 'Không đặt bộ lọc “bài có lỗi không” trước bước 1; lịch sử lỗi lấy sẵn bằng SQL, không bắt LLM tự suy.',
      papers: ['Srivatsa, Maurya, Kochmar (EMNLP 2025): viết lại đúng theo cách HS rồi so', 'FERMAT (ACL 2025): taxonomy + ví dụ trong prompt; sửa trực tiếp tốt hơn chuỗi lọc', 'MathEDU (EACL 2026): đúng bước sai chỉ 42% → bắt buộc GV duyệt', 'LongTutor (ACL 2026): chẩn đoán từ lịch sử kém → SQL chọn sẵn', 'MIME / Kaggle MAP (2025): giữ nhãn “unclear”']
    },
    '04': {
      input: ['1 Mistake — chỉ kết luận (từ 03)', 'Attempt + lời giải mẫu'],
      steps: [['code', '1. Tách context: không thấy lý luận hay prompt của 03; mỗi lần xét 1 lỗi'],
        ['llm', '2. Phản biện: bước này có thật sự sai? mã lỗi đúng không? không chắc → không đồng ý'],
        ['llm', '3. Verdict agree / disagree / wrong_code + lý do; không lặp, không tự hoà giải'],
        ['code', '4. Xếp hàng duyệt: bất đồng trước, rồi confidence thấp, rồi phần còn lại'],
        ['gv', '5. Thầy/cô duyệt TẤT CẢ lỗi: chấp nhận / sửa / bỏ / thêm lỗi bị sót']],
      output: 'Verdict: verifier_verdict · verifier_reason · suggested_code',
      rule: 'Verifier đồng ý không có nghĩa lỗi đúng — các model đồng ý với nhau nhiều hơn với người.',
      papers: ['Pers et al. (2026): lượt chấm độc lập, bất đồng → người duyệt', 'Kortemeyer et al. (2025): vẫn phải gửi ~70% bài cho người → duyệt hết', 'Agreement Is Not Validity* (2026): kappa model–model 0.76–0.78, người–LLM 0.52–0.60', 'AI-Marker-Suite* (2026): 2 model độc lập, lệch → người', 'Cognition* (blog 04/2026): verifier tốt nhất khi không chung context; chỉ một luồng ghi']
    },
    '05': {
      input: ['Mistake đã duyệt + Grade (từ 04, 02)', 'problem_kc: bài → KC theo bước (từ 06)', 'δ độ khó của bài (từ 07)', 'skill_state, misconception_log cũ'],
      steps: [['code', '1. Kết quả theo (attempt, KC): X = 0 nếu có lỗi còn hiệu lực gắn KC đó, ngược lại X = 1'],
        ['code', function (S, U) { return ['2. Elo theo KC: ', U.latex('P = \\frac{1}{1 + e^{-(\\theta - \\delta)}}'), '; ', U.latex('\\theta \\leftarrow \\theta + K\\,(X - P)'), ', K = ' + vn(S.elo.K) + '; δ giữ cố định']; }],
        ['code', function (S) { return '3. misconception_log: first_seen, last_seen, count; hết khi ≥ ' + S.misconception.resolve_streak + ' lần đúng liên tiếp sau lần sai cuối'; }],
        ['code', '4. So với buổi trước: Δθ theo KC; mã lỗi lặp lại / mới / đã hết'],
        ['llm', '5. LLM viết knowledge_state ≤ 150 từ CHỈ từ số liệu bước 2–4; không tự chấm mức thành thạo'],
        ['code', '6. Commit node ghi một lần, nguyên tử']],
      output: 'skill_event · skill_state (θ, n_attempts, correct_streak) · misconception_log · session.knowledge_state · Δθ, lỗi lặp / mới / hết',
      rule: 'Test tự động: không cập nhật nào được làm θ tăng sau một lần sai.',
      papers: ['Keeping Elo alive (BJMSP 2025): giữ δ cố định khi vừa chọn bài theo rating', 'Responsible-DKT (2026): luật 2 lần đúng liên tiếp = đã vững', 'Hooshyar et al. (2025): LLM tự giữ mức thành thạo cập nhật sai hướng → code giữ', 'Language Bottleneck Models (2025): trạng thái dạng văn bản ngắn song song với số', 'IntelliCode (EACL 2026): learner state tập trung, chỉ orchestrator ghi']
    },
    '06': {
      input: ['Bài trong ngân hàng (đề + lời giải mẫu .tex)', 'Danh sách KC thầy/cô nhập (tên + định nghĩa)', 'kc_prereq: KC tiên quyết'],
      steps: [['code', '1. Tách lời giải mẫu thành bước (dùng lại bộ tách của 01)'],
        ['llm', '2. LLM viết mô tả kỹ năng cho từng bước, chưa chọn mã KC'],
        ['code', '3. Embedding mô tả ↔ định nghĩa KC (MiniLM, cosine) → top-5 ứng viên mỗi bước'],
        ['llm', '4. LLM xếp hạng top-5, trích LaTeX làm bằng chứng; kiểm tra nhất quán với kc_prereq'],
        ['gv', '5. Thầy/cô chọn / sửa; thêm KC còn thiếu vào danh sách'],
        ['code', '6. Lưu problem_kc — chỉ tag thầy/cô đã chọn']],
      output: 'problem_kc: problem_id · kc_id · step_idx · evidence_latex · approved_at',
      rule: 'Tag top-1 chỉ đúng ~39% → luôn đưa top-5 cho thầy/cô chọn.',
      papers: ['KC-Tagging (ICCE 2025): LLM mô tả → SBERT khớp danh sách; top-1 ~39%, top-10 ~87%', 'LBG competency tagging* (2026): shortlist → LLM chọn kèm bằng chứng', 'KCGen-KT* (ACL 2026 Findings): sinh danh sách KC từ ngân hàng khi chưa có', 'K12-KGraph (2026): kiểm DAG cho quan hệ tiên quyết']
    },
    '07': {
      input: ['Bài đã gắn KC (từ 06)', 'Mức nhận thức thầy/cô gắn (tuỳ chọn)'],
      steps: [['code', '1. Ghép cặp bài cùng KC, khoảng 10 so sánh mỗi bài'],
        ['llm', '2. Hỏi “bài nào khó hơn” theo cả (A, B) và (B, A); hai câu trả lời khác nhau → hoà'],
        ['code', '3. Fit Bradley-Terry (bt.py) → điểm khó → quy về thang δ của Elo'],
        ['gv', '4. Thầy/cô xem bảng xếp hạng theo KC, đổi chỗ nếu sai'],
        ['code', '5. Ghi δ cố định; không cập nhật δ theo kết quả HS']],
      output: 'problem.bt_score · δ · n_comparisons · problem_pair (giữ để fit lại khi thêm bài)',
      rule: 'Không bắt LLM đóng vai học sinh yếu để đoán độ khó.',
      papers: ['Li, Abulela, Gushta (AIME-Con 2026): so cặp + Bradley-Terry, 10 so sánh / bài, hỏi 2 chiều', 'Kolesnikova et al.* (2026): bài mới → so cặp tốt hơn chấm tuyệt đối', 'Human-AI Difficulty Alignment* (ACL 2026): model không mô phỏng được HS yếu', 'Ballon et al. (2025): khớp chuyên gia nhưng với điểm HS thật yếu → δ chỉ là ước lượng thô']
    },
    '08': {
      input: ['skill_state θ theo KC + knowledge_state (từ 05)', 'misconception_log (lỗi chưa hết)', 'problem_kc + δ (từ 06, 07)', 'Bài HS đã làm + kc_prereq'],
      steps: [['code', function (S) { var r = S.reco; return '1. Chọn KC: ' + pc(r.ratios.review) + ' ôn (lỗi chưa hết), ' + pc(r.ratios.zpd) + ' vừa sức (θ − δ ∈ [' + vn(r.zpd_window[0]) + ', ' + vn(r.zpd_window[1]) + ']), ' + pc(r.ratios.challenge) + ' thử thách (đủ KC tiên quyết)'; }],
        ['code', function (S) { return '2. Lọc bài: đúng KC, chưa làm trong ' + S.reco.no_repeat_days + ' ngày, đã có rubric, δ đã duyệt; xếp theo |θ − δ|'; }],
        ['code', function (S) { return '3. Trộn ≥ ' + S.reco.min_kc_mix + ' KC trong một buổi, không dồn một dạng bài'; }],
        ['llm', '4. LLM nhận danh sách đã lọc: kiểm tra phù hợp + viết lý do 1 dòng; không chọn ngoài danh sách'],
        ['gv', '5. Thầy/cô duyệt / bỏ / thay bài']],
      output: 'recommendation: problem_id · kc_id · bucket (ôn | vừa sức | thử thách) · reason 1 dòng · status',
      rule: 'Luật trộn dạng bài lấy từ Rohrer et al. 2020 (RCT lớp 7) — nằm ngoài bộ paper 2025+.',
      papers: ['IntelliCode (EACL 2026): 0.4 ôn / 0.5 vùng phát triển / 0.1 thử thách', 'MALPP* (2026): LLM chỉ xếp hạng danh sách ứng viên đã lọc', 'IB-GRPO* (2026): nhắm bài hơi trên mức hiện tại', 'Chung et al.* (2026): chọn bài thích nghi +0.15 SD', 'PersonaPath* (2026): LLM tự lập lộ trình kém → luật chọn']
    },
    '09': {
      input: ['DB tháng: attempt, mistake đã duyệt, skill_state theo thời gian, misconception_log', 'Recommendation đã duyệt (từ 08)'],
      steps: [['code', '1. SQL → facts.json: mỗi fact có id (số bài, tỉ lệ đạt rubric, Δθ theo KC, mã lỗi thường gặp, lỗi hết / còn lặp)'],
        ['code', '2. Chọn 3 insight bằng code: xu hướng, điểm đổi, ngoại lệ, đa số'],
        ['llm', '3. LLM viết: KC vững → khen + mở rộng; KC yếu → lời khuyên gắn KC tiên quyết và bài gợi ý'],
        ['code', '4. Audit: mỗi câu trích ≥ 1 fact_id; mọi số trong câu khớp fact'],
        ['llm', '5. Câu trượt audit → viết lại 1 lần → vẫn trượt → bỏ câu'],
        ['gv', '6. Thầy/cô sửa câu, duyệt → report .md ngắn']],
      output: 'report: facts_json · text_md (mỗi câu kèm [fact_id]) · audit_json · approved_at',
      rule: 'Không có lớp kể chuyện; không khen quá tay khi kết quả thấp.',
      papers: ['StoryLensEdu (PacificVis 2026): insight tính bằng thuật toán, LLM chỉ diễn đạt', 'distillLA (2026): audit grounding + self-closure', 'Davalos et al. (2025): GV chê “bức tường chữ”', 'Steinbach et al.* (L@S 2025), Maus et al.*: người đọc không nhận ra phản hồi sai → kiểm bằng code']
    }
  };

  var NODE = {
    'ui:gv': { label: 'Giáo viên', sub: 'người dùng duy nhất', kind: 'gv' },
    'ui:app': { label: 'App (bản nháp này)', sub: 'web, chạy local', kind: 'code' },
    'ui:cli': { label: 'tutor/cli.py', sub: 'CLI typer · 6 lệnh', kind: 'code' },
    'orch:checkpoint': { label: 'checkpoint + interrupt()', sub: 'dừng chờ GV, chạy tiếp', kind: 'stop' },
    'orch:commit': { label: 'commit node', sub: 'nơi duy nhất ghi tutor.db', kind: 'commit' },
    'orch:repo': { label: 'tutor/db/repo.py', sub: 'sqlite3 · WAL', kind: 'code' },
    'svc:latex': { label: 'latex.py', sub: 'cắt bài, tách bước', kind: 'code' },
    'svc:pdftext': { label: 'pdftext.py', sub: 'text layer, kiểm trung thực', kind: 'code' },
    'svc:elo': { label: 'elo.py', sub: 'P, θ, streak, resolved', kind: 'code' },
    'svc:bt': { label: 'bt.py', sub: 'Bradley-Terry → δ', kind: 'code' },
    'svc:select': { label: 'select.py', sub: 'chọn KC, lọc, trộn', kind: 'code' },
    'svc:facts': { label: 'facts.py', sub: 'SQL → facts.json', kind: 'code' },
    'svc:audit': { label: 'audit.py', sub: 'câu ↔ fact_id, số khớp', kind: 'code' },
    'svc:embed': { label: 'embed.py', sub: 'cosine, top-5 KC', kind: 'code' },
    'infra:llm': { label: 'tutor/llm.py', sub: 'LLM gateway, mọi agent gọi qua', kind: 'code' },
    'infra:minilm': { label: 'MiniLM (local)', sub: 'embedding chạy trên máy', kind: 'code' },
    'infra:api': { label: 'Anthropic API', sub: 'ngoài máy · chỉ nhận mã HS', kind: 'ext' },
    'store:inbox': { label: 'data/inbox/', sub: 'bài HS, file ngân hàng', kind: 'file' },
    'store:out': { label: 'data/out/', sub: 'gợi ý, report .md', kind: 'file' },
    'store:checkpoints': { label: 'data/checkpoints.db', sub: 'state thread + đề xuất chờ duyệt', kind: 'pending' },
    'store:tutor': { label: 'data/tutor.db', sub: '16 bảng + 2 view, chỉ dòng đã duyệt', kind: 'db' },
    'store:llm': { label: 'data/logs/llm.jsonl', sub: 'mỗi lời gọi LLM 1 dòng', kind: 'file' },
    'store:backup': { label: 'data/backup/', sub: 'sao lưu trước mỗi commit', kind: 'file' }
  };
  var LAYERS = [
    { no: 1, title: 'Giao diện', sub: 'Thầy/cô dùng app hoặc CLI; cả hai chạy cùng các graph.', nodes: ['ui:gv', 'ui:app', 'ui:cli'] },
    { no: 2, title: 'Điều phối', sub: 'tutor/graphs/ — LangGraph StateGraph, graph cố định, mỗi lệnh CLI chạy 1 graph.', nodes: ['graph:G1', 'graph:G2', 'graph:G3', 'graph:G4', 'graph:G5', 'orch:checkpoint', 'orch:commit', 'orch:repo'] },
    { no: 3, title: 'Agent LLM', sub: 'tutor/agents/ — mỗi agent 1 file: prompt + schema Pydantic; trả đề xuất, không ghi DB.', nodes: ['01', '02', '03', '04', '05', '06', '07', '08', '09'].map(function (a) { return 'agent:' + a; }) },
    { no: 4, title: 'Dịch vụ code', sub: 'tutor/services/ — mọi con số (Elo, δ, tỉ lệ, audit) tính ở đây.', nodes: ['svc:latex', 'svc:pdftext', 'svc:elo', 'svc:bt', 'svc:select', 'svc:facts', 'svc:audit', 'svc:embed'] },
    { no: 5, title: 'Hạ tầng', sub: '1 máy · 1 người dùng · không đăng nhập (NFR1).', nodes: ['infra:llm', 'infra:minilm', 'infra:api'] }
  ];
  var STORES = ['store:inbox', 'store:out', 'store:checkpoints', 'store:tutor', 'store:llm', 'store:backup'];
  var GRAPH_TAB = { G1: 'session', G2: 'bank', G3: 'bank', G4: 'recommend', G5: 'report' };
  var GRAPH_PHASE = { G1: ['bản đầu · P0–P4', 'ok'], G2: ['làm sau bản đầu · P5', 'neutral'], G3: ['làm sau bản đầu · P5', 'neutral'], G4: ['làm sau bản đầu · P6', 'neutral'], G5: ['làm sau bản đầu · P7', 'neutral'] };
  var KIND_TXT = { code: 'code', llm: 'LLM', stop: 'DỪNG', commit: 'commit' };
  var TABLE_COLS = {
    kc: 'id, code, name, description, parent_id, embedding, embed_model', kc_prereq: 'kc_id, prereq_id — CHECK kc_id ≠ prereq_id',
    error_code: 'code, category, description, example, active', problem: 'ref, statement_latex, solution_latex, bt_score, delta, n_comparisons, difficulty_approved_at',
    problem_kc: 'problem_id, kc_id, step_idx, evidence_latex, approved_at', rubric: 'problem_id, version, items_json, max_score, approved_at — UNIQUE(problem_id, version)',
    problem_pair: 'problem_a, problem_b, harder_ab, harder_ba', student: 'name, grade, note, archived_at',
    session: 'student_id, held_on, source_path, source_kind, source_sha256, transcript_latex, knowledge_state, thread_id, status — UNIQUE(student_id, source_sha256)',
    attempt: 'session_id, seq, problem_id, rubric_id, steps_json, flags_json, grade_json, score, max_score, supersedes_id',
    mistake: 'attempt_id, step_idx, code, kc_id, description, evidence_latex, confidence, verifier_verdict, status, llm_json, teacher_note, supersedes_id',
    skill_event: 'student_id, kc_id, attempt_id, outcome (X), p_expected, theta_before, theta_after, delta', skill_state: 'student_id, kc_id, theta, n_attempts, correct_streak, last_seen',
    misconception_log: 'student_id, code, kc_id, first_seen, last_seen, count, resolved_at', recommendation: 'student_id, for_date, problem_id, kc_id, bucket, reason, status — UNIQUE(student_id, for_date, problem_id)',
    report: 'student_id, month, facts_json, text_md, audit_json, approved_at — UNIQUE(student_id, month)',
    attempt_current: 'attempt chưa bị dòng nào thay (supersedes_id)', mistake_current: 'mistake không rejected, không bị thay, attempt còn hiệu lực'
  };
  var TABLE_TAB = { kc: 'catalog', kc_prereq: 'catalog', error_code: 'catalog', problem: 'bank', problem_kc: 'bank', rubric: 'bank', problem_pair: 'bank',
    student: 'students', session: 'session', attempt: 'session', mistake: 'session', skill_event: 'students', skill_state: 'students', misconception_log: 'students',
    recommendation: 'recommend', report: 'report', attempt_current: 'session', mistake_current: 'session' };
  // spec §7: [group, title, ai ghi]
  var GROUPS = [['A', 'Ngân hàng bài', 'GV nhập; G2 / G3 commit'], ['B', 'Học sinh, buổi học', 'GV nhập HS; G1 commit'], ['C', 'Trạng thái học sinh', 'G1 commit (05 Profiler tính)'], ['D', 'Đầu ra', 'G4 / G5 commit'], ['view', 'View (đọc, không lưu)', null]];
  var PRINCIPLES = [
    ['Một nơi ghi', 'Agent chỉ trả đề xuất; chỉ commit node ghi tutor.db, mỗi lần duyệt = 1 transaction (NFR5, IntelliCode).', 'Biên nhận “1 transaction · …” sau mỗi lần ghi; hai đồng hồ trên thanh trên cùng.', 'review'],
    ['Verifier độc lập', '04 không thấy lý luận của 03, chỉ 1 vòng; bất đồng → gắn cờ cho thầy/cô, không tự hoà giải (Pers 2026).', 'Buổi học › bước 4: hai ô “Diagnoser (03) nói” | “Verifier (04) nói”.', 'session'],
    ['Số do code tính', 'Elo, Δθ, δ, tỉ lệ, audit đều là code; LLM chỉ trích xuất và diễn đạt (Hooshyar 2025).', 'Dấu “code” vuông và nút “?” — Con số này từ đâu?', 'students'],
    ['Graph cố định', 'Không agent nào tự chọn gọi agent khác; tự điều phối kém 39–70% với việc tuần tự (Kim 2025).', 'Dải graph G1–G5 trên mọi màn hình chạy graph.', 'ops'],
    ['Không gì vào DB trước khi duyệt', 'Đề xuất nằm trong checkpoints.db; không có nút “Duyệt tất cả” (NFR4).', 'Viền vàng nét đứt = chưa ghi; Hộp duyệt.', 'review'],
    ['Chỉ thêm dòng (append-only)', 'attempt, mistake không sửa tại chỗ: sửa = dòng mới + supersedes_id; skill_state dựng lại được từ skill_event.', 'Buổi học › “Sửa lỗi đã lưu”; Học sinh › “Dựng lại trạng thái từ lịch sử”.', 'students'],
    ['Không cần train', 'θ bắt đầu từ 0 cho mọi KC, cập nhật sau từng bài; không cần dữ liệu có nhãn (NFR2).', 'Học sinh mới: “θ = 0 cho mọi KC”.', 'students']
  ];
  var SKIPPED = [
    ['Chatbot cho học sinh', 'Hệ thống dành cho thầy/cô; non-goal trong spec §2.'],
    ['OCR chữ viết tay', 'Đầu vào là .tex hoặc PDF xuất từ LaTeX (yêu cầu cứng); non-goal §2.'],
    ['LMS', 'Không quản lý lớp, bài tập, điểm danh; non-goal §2.'],
    ['Đăng nhập / phân quyền', 'Một người dùng, chạy local (NFR1); non-goal “nhiều giáo viên”.'],
    ['Nút “Duyệt tất cả”', 'NFR4; sơ đồ 04: “Verifier đồng ý không có nghĩa lỗi đúng”; đúng bước sai chỉ ~42–64%.'],
    ['Nút “Tạo cho cả lớp”', 'Graph chạy theo từng HS (CLI: tutor recommend <hs>, tutor report <hs> <tháng>).'],
    ['Lịch học / thời khoá biểu', 'Schema chỉ có session.held_on và recommendation.for_date.'],
    ['Tìm kiếm toàn cục', 'Dữ liệu nhỏ (1 GV, vài chục HS); mỗi màn hình có bộ lọc riêng.'],
    ['Train knowledge tracing', 'Quá ít học sinh; Elo chạy ngay không cần train (non-goal §2, NFR2).']
  ];
  var QUESTIONS = [
    'Ngân hàng bài hiện ở dạng gì (.tex, Word, giấy)? Bao nhiêu bài? Lời giải có đủ các bước không?',
    'HS có nộp được .tex theo mẫu \\begin{problem}[id]…\\end{problem} không, hay chỉ PDF?',
    'Danh sách KC: bắt đầu lớp nào, chương nào? Ai viết?',
    'Có 20–50 bài cũ thật của HS để làm bộ đánh giá không?',
    'Report gửi GV hay phụ huynh đọc? Giọng văn và độ dài khác nhau.',
    'Ngân sách API mỗi tháng? Có đồng ý gửi bài HS lên Anthropic API không?',
    'App chạy kiểu nào: web chạy local trong trình duyệt hay app desktop? Có cần dùng trên điện thoại / máy tính bảng không (bản nháp đã chạy ở bề rộng 390 px)?',
    'Có giữ CLI song song với app không (bản nháp in lệnh CLI tương đương dưới mỗi nút)?',
    'Phụ huynh nhận report qua file (.md / PDF) hay xem trong app?'
  ];
  // tài liệu thiết kế §11.2: [điểm, đề xuất, vì sao, thấy trong app, tab, params]
  var CHOICES = [
    ['Phạm vi bản đầu', 'FR1–FR5 (P0–P4); màn hình Hôm nay, Hộp duyệt, Buổi học, Học sinh, Danh mục, Vận hành', 'Gợi ý và report cần dữ liệu vài buổi', 'chip “làm sau bản đầu” ở Gợi ý bài, Báo cáo tháng, Ngân hàng bài', null],
    ['Nhánh nhập PDF', 'Bỏ nếu HS nộp được .tex', 'Bớt pdftext.py và bước kiểm tra chép lại', 'Buổi học › bước 3 (cờ mismatch của PDF)', 'session'],
    ['Model', 'Opus 5.5 cho mọi agent, đo chi phí rồi mới hạ', 'Chưa có số đo chi phí', 'Vận hành › Cài đặt; Nhật ký & chi phí', 'logs'],
    ['Ẩn danh', 'Chỉ gửi mã HS', 'Giảm rủi ro dữ liệu', 'Vận hành › Riêng tư (“đề xuất, chờ chốt”)', 'ops'],
    ['Mã lỗi', 'Giữ 18 mã seed; GV viết 1 ví dụ cho mỗi mã', 'FERMAT: có ví dụ thì đúng hơn 0.03', 'Danh mục › Mã lỗi', 'catalog'],
    ['Giao diện cho GV', 'Đã chốt 21/10: app cho GV, bản nháp HTML là tham chiếu; CLI giữ làm lệnh tương đương', 'Chủ dự án chốt; đề xuất cũ “CLI trước, web sau” bỏ', 'bản nháp web này + dòng >_ dưới mỗi nút', null],
    ['Số bài gợi ý mỗi buổi', '6 bài, tỉ lệ 40/50/10', 'IntelliCode; chỉnh được', 'Gợi ý bài › Luật; Vận hành › Cài đặt', 'recommend'],
    ['Repo', 'git init + project uv', 'Thư mục chưa là git repo', '—', null],
    ['Spec và các thay đổi', 'Duyệt', 'Gồm các điểm ở §11.3 và mục 4 (vd. duyệt buổi theo thứ tự ngày, bỏ proposed khỏi DB)', 'Hộp duyệt (khoá theo ngày); tutor.db không có trạng thái proposed', 'review'],
    ['Ngữ cảnh lỗi cũ cho 03', '5 lỗi đã duyệt gần nhất của HS, mọi KC (như §3.5 và query §8.6)', 'Hình B.03 (bản 0.1) ghi “cùng KC”; spec §5 ghi “5 lỗi gần nhất của HS”', 'Bản đồ › 9 agent › 03; Buổi học › bước 4 “Ngữ cảnh 03 đã dùng”', 'session'],
    ['Khoá khi buổi trước lỗi hoặc đang chạy', 'Khoá luôn: buổi sau chờ buổi trước chạy xong và được duyệt', 'Elo cập nhật theo thứ tự ngày; bỏ qua buổi lỗi thì θ tính sai thứ tự', 'Hộp duyệt (nút Mở bị khoá, ghi lý do); Buổi học; Vận hành', 'review'],
    ['Huỷ buổi lỗi rồi nộp lại cùng file', 'Huỷ thì xoá dòng session failed (chưa có attempt vì ② chưa chạy); phương án khác: giữ failed và cho nộp lại file của buổi failed', 'UNIQUE(student_id, source_sha256) đang chặn nộp lại; bản nháp giữ dòng failed', 'Vận hành › Huỷ thread; Buổi học › Nộp bài (“Đã chặn: trùng sha256”)', 'ops'],
    ['Sửa lỗi đã lưu và skill_event', '(a) coi skill_event là bản tóm tắt, xoá rồi replay như skill_state; phương án khác (b): thêm supersedes_id, bỏ UNIQUE(attempt_id, kc_id)', 'Quy tắc 3 (§8.1) nói chỉ thêm, nhưng schema không cho dòng thứ 2 cho cùng (attempt, KC); (a) không đổi schema', 'Buổi học › buổi đã duyệt › Sửa lỗi đã lưu (biên nhận ghi “chưa chốt”)', 'session'],
    ['Số lần trong lý do bài ôn', 'Ghi số lần của mã lỗi, kèm tổng của cả KC khi khác nhau', 'select.py xếp KC theo tổng mọi mã lỗi; thầy/cô đọc lý do theo từng mã', 'Gợi ý bài › Bước 1 (lý do nhóm ôn)', 'recommend'],
    ['Rubric duyệt ở bước xác nhận G1', 'Ghi rubric trong cùng commit ②', 'attempt.rubric_id NOT NULL; Hình 3 và spec chưa liệt kê rubric trong ② (bảng G1 §3.4 ghi là đề xuất)', 'Buổi học › bước 3 (cờ “chưa có rubric”)', 'session']
  ];
  var CLI = [
    ['tutor ingest <hs> <file>', 'G1', 'Buổi học › “Bắt đầu xử lý” (cũng: nút “Nộp bài” trên thanh trên, Hôm nay, Học sinh)', 'session', { step: 1 }],
    ['tutor review [id]', 'G1–G5', 'Hộp duyệt › “Mở” (không có id = Hôm nay › “Duyệt tiếp”)', 'review', {}],
    ['tutor recommend <hs> [--date]', 'G4', 'Gợi ý bài › “Tạo gợi ý”', 'recommend', {}],
    ['tutor report <hs> <tháng>', 'G5', 'Báo cáo tháng › “Tạo report”', 'report', {}],
    ['tutor bank tag <bank.tex>', 'G2', 'Ngân hàng bài › “Nạp file .tex”, rồi duyệt tag + rubric', 'bank', {}],
    ['tutor bank difficulty', 'G3', 'Ngân hàng bài › “Xếp độ khó”', 'bank', {}]
  ];
  var SECTIONS = [['layers', '5 tầng'], ['graphs', '5 graph'], ['agents', '9 agent'], ['data', 'Dữ liệu'], ['cli', 'CLI ↔ app'],
    ['principles', 'Nguyên tắc'], ['glossary', 'Thuật ngữ'], ['skipped', 'Không làm'], ['open', 'Chưa chốt']];

  App.registerTab('map', {
    title: 'Bản đồ hệ thống',
    render: function (root, ctx) {
      var U = ctx.ui, h = U.h, f = U.fmt, M = ctx.data, D = M.db || {}, S = M.settings || {}, L = ctx.lookup;
      var meta = M.meta || {}, graphs = meta.graphs || {}, agents = arr(meta.agents);
      var threads = function () { return arr((M.checkpoints || {}).threads); };
      var log = function () { return arr((M.files || {}).llm_log); };
      var agentOf = function (id) { return agents.find(function (a) { return a.id === id; }) || { id: id, name: '', role_vi: '', graphs: [] }; };
      var secs = {};
      var stepText = function (s) { return typeof s[1] === 'function' ? s[1](S, U) : s[1]; };
      var tabTitle = function (id) { var t = arr(App.tabs).find(function (x) { return x.id === id; }); return t ? t.title : id; };

      /* ---------- live numbers ---------- */
      var dbRows = function () { return Object.keys(D).reduce(function (s, k) { return s + (Array.isArray(D[k]) ? D[k].length : 0); }, 0); };
      var tableRows = function (name) {
        if (Array.isArray(D[name])) return D[name].length;
        if (name === 'attempt_current') { var sup = new Set(arr(D.attempt).map(function (a) { return a.supersedes_id; }).filter(function (x) { return x != null; })); return arr(D.attempt).filter(function (a) { return !sup.has(a.id); }).length; }
        if (name === 'mistake_current' && ctx.calc.currentMistakes) return ctx.calc.currentMistakes(D).length;
        return null;
      };
      var thStats = function (g) {
        var o = { running: 0, awaiting_review: 0, failed: 0, committed: 0, proposals: 0 };
        threads().forEach(function (t) { if (g && t.graph !== g) return; o[t.status] = (o[t.status] || 0) + 1; if (t.status === 'awaiting_review') o.proposals += arr(t.state && t.state.proposals).length; });
        return o;
      };
      var callsOf = function (pred) { var cs = log().filter(pred); return { n: cs.length, usd: cs.reduce(function (s, c) { return s + (+c.cost_usd || 0); }, 0) }; };
      var firstWaiting = function (g, node) {
        var list = ctx.queue.list({ graph: g }).filter(function (t) { return !t.locked && (!node || (t.interrupted_at || t.current_node) === node); });
        list.sort(function (a, b) { return arr(b.state && b.state.proposals).length - arr(a.state && a.state.proposals).length; });
        return list[0] || null;
      };
      // "Xem trong app": the open thread that shows this agent's output, else the screen itself.
      var agentScreen = function (id) {
        var t;
        if (id === '01') { t = firstWaiting('G1', 'g1.confirm_match'); return ['session', t ? { thread: t.thread_id, step: 3 } : {}]; }
        if (id === '02' || id === '03' || id === '04') { t = firstWaiting('G1', 'g1.review'); return ['session', t ? { thread: t.thread_id, step: 4 } : {}]; }
        if (id === '05') {
          var last = arr(D.session).filter(function (s) { return s.status === 'committed'; }).sort(function (a, b) { return a.committed_at < b.committed_at ? 1 : -1; })[0];
          return ['students', last ? { student: last.student_id, tab: 'progress' } : {}];
        }
        if (id === '06') { t = firstWaiting('G2'); return ['bank', t ? { review: t.thread_id } : {}]; }
        if (id === '07') { t = firstWaiting('G3'); return ['bank', t ? { difficulty: t.thread_id } : {}]; }
        if (id === '08') { t = firstWaiting('G4'); return ['recommend', t ? { thread: t.thread_id } : {}]; }
        if (id === '09') { t = firstWaiting('G5'); return ['report', t ? { thread: t.thread_id } : {}]; }
        return [agentOf(id).tab || 'today', {}];
      };

      var section = function (id, title, lead, annot) {
        var el = h('section', { class: 'section mp-sec', id: 'mp-' + id },
          h('div', { class: 'section-head' }, h('div', null, h('h2', null, title), annot ? U.annot(annot) : null)),
          lead ? h('p', { class: 'muted' }, lead) : null);
        secs[id] = el; return el;
      };
      var jump = function (id) {
        var el = secs[id]; if (!el) return;
        el.scrollIntoView({ block: 'start', behavior: 'smooth' });
        el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
      };
      var openBtn = function (label, tab, params) { return U.button(label, function () { ctx.nav(tab, params || {}); }, { kind: 'secondary', size: 'sm' }); };

      /* ---------- drawers ---------- */
      function drawerFor(id) {
        if (id.indexOf('agent:') === 0) return agentDrawer(id.slice(6));
        if (id.indexOf('graph:') === 0) return graphDrawer(id.slice(6));
        if (id.indexOf('table:') === 0) return tableDrawer(id.slice(6));
        var n = NODE[id]; if (!n) return;
        var info = nodeInfo(id);
        ctx.drawer({
          title: n.label,
          body: function (el, api) {
            el.append(h('div', { class: 'row' }, kindMark(n.kind), h('span', { class: 'muted' }, n.sub)),
              info.annot ? U.annot(info.annot) : null,
              h('div', { class: 'stack' }, info.what.map(function (p) { return typeof p === 'string' ? h('p', null, p) : p; })),
              info.facts && info.facts.length ? h('div', { class: 'card' }, h('span', { class: 'eyebrow' }, 'Số liệu lúc này (dữ liệu mẫu)'), U.kv(info.facts)) : null,
              h('div', { class: 'row' }, info.open.map(function (o) {
                return o.section ? U.button(o.label, function () { api.close(); jump(o.section); }, { kind: 'secondary', size: 'sm' })
                  : openBtn(o.label || 'Mở màn hình liên quan: ' + tabTitle(o.tab), o.tab, o.params);
              })));
          }
        });
      }
      function kindMark(k) {
        if (k === 'llm') return U.prov('llm');
        if (k === 'gv') return U.prov('gv');
        if (k === 'stop') return U.chip('DỪNG', 'warn');
        if (k === 'commit') return U.chip('commit', 'ok');
        if (k === 'db') return U.store('db');
        if (k === 'pending') return U.store('checkpoint');
        if (k === 'file') return U.store('file');
        if (k === 'ext') return U.chip('ngoài máy', 'danger');
        return U.prov('code');
      }
      function nodeInfo(id) {
        var st = thStats(), d = dbRows(), files = M.files || {}, all = log();
        var K = (S.elo || {}).K, r = S.reco || {};
        var m = {
          'ui:gv': { what: ['Người dùng duy nhất. Mọi đề xuất của LLM dừng ở checkpoints.db cho tới khi thầy/cô duyệt (NFR4).', 'Thầy/cô cũng nhập danh mục: KC, KC tiên quyết, mã lỗi + ví dụ, học sinh.'],
            facts: [['Đang chờ duyệt', st.awaiting_review + ' thread · ' + st.proposals + ' đề xuất'], ['Học sinh', arr(D.student).filter(function (s) { return !s.archived_at; }).length + ' đang theo dõi']],
            open: [{ tab: 'review', label: 'Mở Hộp duyệt' }, { tab: 'today', label: 'Mở Hôm nay' }], annot: ['cli:tutor review'] },
          'ui:app': { what: ['Bản nháp web này: đọc tutor.db, mở các thread đang dừng, bấm duyệt. Mỗi nút chạy graph có dòng >_ là lệnh CLI tương ứng.', 'Đã chốt 21/10: thầy/cô dùng app; CLI giữ làm lệnh tương đương. Bản nháp này là tham chiếu cho app.'],
            facts: [['Màn hình', arr(App.tabs).length + ' màn hình']], open: [{ tab: 'today', label: 'Mở Hôm nay' }] },
          'ui:cli': { what: ['tutor/cli.py (typer). Mỗi lệnh chạy 1 graph cố định; “tutor review [id]” dùng chung cho mọi graph đang dừng.'],
            facts: CLI.map(function (c) { return [c[1], h('span', { class: 'mono small' }, c[0])]; }), open: [{ section: 'cli', label: 'Xem bảng CLI ↔ app' }, { tab: 'review', label: 'Mở Hộp duyệt' }] },
          'orch:checkpoint': { what: ['LangGraph SqliteSaver lưu state từng thread vào data/checkpoints.db. Tới điểm DỪNG, interrupt() lưu state rồi thoát; thầy/cô duyệt trong app (CLI: “tutor review”) thì chạy tiếp.', 'Lỗi giữa chừng → chạy lại từ checkpoint cuối, các bài đã xong không chạy lại (NFR9).'],
            facts: [['Thread', f.int(threads().length)], ['Chờ duyệt', st.awaiting_review + ' (' + st.proposals + ' đề xuất)'], ['Đang chạy / lỗi', st.running + ' / ' + st.failed]],
            open: [{ tab: 'review', label: 'Mở Hộp duyệt' }, { tab: 'ops', label: 'Mở Vận hành' }], annot: ['interrupt()', 'checkpoint', 'file:checkpoints.db'] },
          'orch:commit': { what: ['Bước duy nhất ghi tutor.db; mỗi lần thầy/cô duyệt = 1 transaction (NFR5). Trước commit G1 sao lưu tutor.db.', 'Đề xuất bị bỏ vẫn được ghi với status rejected — để đo độ chính xác của agent.'],
            facts: [['tutor.db', f.int(d) + ' dòng đã duyệt'], ['Sao lưu gần nhất', (arr(files.backups)[0] || {}).path || 'chưa có']],
            open: [{ tab: 'ops', params: { section: 'storage' }, label: 'Mở Vận hành › Lưu trữ' }], annot: ['commit node', 'file:tutor.db'] },
          'orch:repo': { what: ['tutor/db/repo.py: sqlite3 (stdlib), chế độ WAL. Hàm ghi chỉ commit node gọi; hàm đọc node nào cũng dùng — vd. 03 lấy 5 lỗi đã duyệt gần nhất của HS bằng SQL.'],
            facts: [['Bảng', '16 bảng + 2 view'], ['Dòng', f.int(d)]], open: [{ section: 'data', label: 'Xem Dữ liệu' }, { tab: 'ops', params: { section: 'storage' } }] },
          'svc:latex': { what: ['Cắt bài theo \\begin{problem}[ref] … \\end{problem}, tách bước, giữ pos / pos_end làm bằng chứng (pylatexenc 2.11). Dùng ở 01 Ingest và bước tách của G2.'],
            facts: [['File ngân hàng', arr(files.bank).length + ' file'], ['Bài đã nạp', f.int(arr(D.problem).length)]], open: [{ tab: 'bank' }, { tab: 'session', params: { step: 1 }, label: 'Mở Buổi học › Nộp bài' }] },
          'svc:pdftext': { what: ['Đọc text layer của PDF để kiểm bản 01 chép: mọi số và biến phải có trong text layer; lệch → cờ mismatch. Lý do: model hay tự “sửa” lỗi HS khi chép (Seong 2026).', 'Bỏ được nếu mọi HS nộp .tex (tài liệu thiết kế §11.2 #2).'],
            facts: [['Buổi nộp PDF', arr(D.session).filter(function (s) { return s.source_kind === 'pdf'; }).length]], open: [{ tab: 'session' }] },
          'svc:elo': { what: [U.latex('P = \\frac{1}{1 + e^{-(\\theta - \\delta)}}, \\quad \\theta \\leftarrow \\theta + ' + K + '\\,(X - P)', { block: true }), 'K = ' + vn(K) + ', θ ban đầu = ' + (S.elo || {}).theta0 + ', δ cố định. Misconception hết khi ≥ ' + (S.misconception || {}).resolve_streak + ' lần đúng liên tiếp.', 'K và ngưỡng cố định theo spec §8 — chỉ đọc trong Cài đặt.'],
            facts: [['skill_event', f.int(arr(D.skill_event).length) + ' dòng'], ['skill_state', f.int(arr(D.skill_state).length) + ' dòng']], open: [{ tab: 'students' }] },
          'svc:bt': { what: ['Fit Bradley-Terry từ các cặp so 2 chiều → điểm khó → quy về thang δ (cách quy đổi còn để ngỏ, tài liệu thiết kế §11.4). δ khoá sau khi thầy/cô duyệt.'],
            facts: [['problem_pair', f.int(arr(D.problem_pair).length) + ' cặp'], ['Bài có δ đã duyệt', f.int(arr(D.problem).filter(function (p) { return p.difficulty_approved_at; }).length)]], open: [{ tab: 'bank' }] },
          'svc:select': { what: ['Chia ' + r.n_problems + ' bài theo tỉ lệ ' + pc((r.ratios || {}).review) + ' ôn / ' + pc((r.ratios || {}).zpd) + ' vừa sức / ' + pc((r.ratios || {}).challenge) + ' thử thách; lọc đúng KC, chưa làm ' + r.no_repeat_days + ' ngày, có rubric; trộn ≥ ' + r.min_kc_mix + ' KC. Không gọi LLM.'],
            facts: [['recommendation', f.int(arr(D.recommendation).length) + ' dòng đã duyệt']], open: [{ tab: 'recommend' }, { tab: 'ops', params: { section: 'settings' }, label: 'Mở Vận hành › Cài đặt' }] },
          'svc:facts': { what: ['SQL → facts.json: mỗi con số có fact_id (số bài, tỉ lệ đạt rubric, Δθ theo KC, mã lỗi thường gặp, lỗi hết / còn lặp). 09 chỉ được dùng các số này.'],
            facts: [['Report đã duyệt', arr(D.report).length]], open: [{ tab: 'report' }] },
          'svc:audit': { what: ['Mỗi câu report phải trích ≥ 1 fact_id; mọi số trong câu phải khớp fact đã trích. Trượt → viết lại 1 lần → vẫn trượt → bỏ câu.'],
            facts: [['Câu đã audit (report đã duyệt)', arr(D.report).reduce(function (s, x) { return s + arr(x.audit_json).length; }, 0)]], open: [{ tab: 'report' }] },
          'svc:embed': { what: ['Cosine giữa mô tả bước (06 viết) và định nghĩa KC → top-5 ứng viên. Đổi mô tả KC → embedding cũ, cần chạy lại 06.'],
            facts: [['KC', arr(D.kc).length], ['Embedding cũ', arr(D.kc).filter(function (k) { return k.embedding_stale; }).length]], open: [{ tab: 'catalog' }, { tab: 'bank' }] },
          'infra:llm': { what: ['tutor/llm.py: mọi agent gọi qua đây. Anthropic SDK · messages.parse (schema Pydantic) · cache phần cố định (taxonomy, rubric, lời giải mẫu) · retry · ghi llm.jsonl.'],
            facts: [['Lời gọi', f.int(all.length)], ['retry / schema_error', all.filter(function (c) { return c.result === 'retry'; }).length + ' / ' + all.filter(function (c) { return c.result === 'schema_error'; }).length]],
            open: [{ tab: 'logs' }], annot: ['file:llm.jsonl'] },
          'infra:minilm': { what: ['sentence-transformers MiniLM chạy trên máy (như KC-Tagging) để embedding mô tả KC; không gửi gì ra ngoài.'], facts: [], open: [{ tab: 'catalog' }] },
          'infra:api': { what: ['Phần duy nhất ngoài máy. Chỉ nhận mã HS (vd. HS-03), không bao giờ nhận tên; bài làm nằm trong khung UNTRUSTED INPUT (NFR6, NFR7).'],
            facts: [['Model mặc định', h('span', { class: 'mono' }, (S.models || {})['03'] || '—')], ['Lời gọi có mã HS', f.int(all.filter(function (c) { return c.student_code; }).length)]],
            open: [{ tab: 'ops', params: { section: 'privacy' }, label: 'Mở Vận hành › Riêng tư' }] },
          'store:inbox': { what: ['Bài HS (.tex, .pdf) chờ nộp và file ngân hàng .tex chờ nạp.'],
            facts: [['Bài HS trong inbox', arr(files.inbox).length], ['File ngân hàng', arr(files.bank).length]], open: [{ tab: 'session', params: { step: 1 }, label: 'Mở Buổi học › Nộp bài' }, { tab: 'bank' }] },
          'store:out': { what: ['File .md của gợi ý bài và report, app xuất sau khi thầy/cô duyệt trên màn hình. Không sửa .md để duyệt.'],
            facts: [['File .md', arr(files.out).length]], open: [{ tab: 'recommend' }, { tab: 'report' }] },
          'store:checkpoints': { what: ['State của từng thread LangGraph, gồm mọi đề xuất đang chờ duyệt. Chưa phải dữ liệu chính thức; huỷ thread xoá đề xuất, riêng buổi học (G1) vẫn giữ dòng session trong tutor.db với trạng thái failed.'],
            facts: [['Thread', f.int(threads().length)], ['Chờ duyệt', st.awaiting_review + ' · ' + st.proposals + ' đề xuất'], ['Đã commit (dọn được)', st.committed]],
            open: [{ tab: 'ops' }, { tab: 'review' }], annot: ['file:checkpoints.db'] },
          'store:tutor': { what: ['SQLite 16 bảng + 2 view; chỉ chứa dòng thầy/cô đã duyệt; chỉ commit node ghi.'],
            facts: [['Dòng', f.int(d)]], open: [{ section: 'data', label: 'Xem 16 bảng' }, { tab: 'ops', params: { section: 'storage' }, label: 'Mở Vận hành › Lưu trữ' }], annot: ['file:tutor.db'] },
          'store:llm': { what: ['Mỗi lời gọi LLM một dòng JSON: agent, prompt_version, token, thời gian, kết quả. Để ngoài tutor.db cho đúng một nơi ghi.'],
            facts: [['Dòng', f.int(all.length)]], open: [{ tab: 'logs' }], annot: ['file:llm.jsonl'] },
          'store:backup': { what: ['Bản sao tutor.db (sqlite3 .backup) trước mỗi commit G1 (tài liệu thiết kế §8.7, NFR9).'],
            facts: [['Bản sao', arr(files.backups).length], ['Mới nhất', (arr(files.backups)[0] || {}).path || '—']], open: [{ tab: 'ops', params: { section: 'backup' }, label: 'Mở Vận hành › Sao lưu' }] }
        };
        var x = m[id] || { what: [], facts: [], open: [] };
        x.open = arr(x.open); return x;
      }
      function agentBody(id, inDrawer) {
        var A = AGENT[id] || { input: [], steps: [], papers: [] };
        var pv = arr((M.ui || {}).prompt_versions).find(function (p) { return p.agent === id; });
        var c = callsOf(function (x) { return x.agent === id; });
        var scr = agentScreen(id);
        return h('div', { class: 'stack mp-agent-body' },
          h('div', { class: 'mp-io' },
            h('div', null, h('span', { class: 'eyebrow' }, 'Đầu vào'), h('ul', { class: 'mp-list' }, A.input.map(function (x) { return h('li', null, x); }))),
            h('div', null, h('span', { class: 'eyebrow' }, 'Các bước'), h('ol', { class: 'mp-steps' }, A.steps.map(function (s) { return h('li', null, U.prov(s[0]), ' ', stepText(s)); }))),
            h('div', null, h('span', { class: 'eyebrow' }, 'Đầu ra (schema)'), h('p', { class: 'mono small mp-out' }, A.output))),
          h('p', { class: 'small' }, h('b', null, id === '05' ? 'Code tính, commit node ghi — 05 không tự ghi DB. ' : 'Trả đề xuất, không ghi DB. '), A.rule || ''),
          h('details', { class: 'mp-papers', open: inDrawer || null }, h('summary', null, 'Nguồn (paper từ 2025, sơ đồ ' + id + ')'),
            h('ul', { class: 'mp-list small' }, A.papers.map(function (p) { return h('li', null, p); })),
            h('p', { class: 'small muted' }, '* = nguồn mới qua 1 lượt mở trang, chưa được phản biện kiểm lại.')),
          h('div', { class: 'row small muted' }, U.chip(pv ? pv.version : '—', 'neutral'), h('span', null, h('span', { class: 'mono' }, (S.models || {})[id] || '—')),
            h('span', null, '· ' + f.int(c.n) + ' lời gọi · ' + f.usd(c.usd) + ' (giả định)'), U.prov('code')),
          h('div', { class: 'row' },
            U.button('Xem trong app', function () { ctx.nav(scr[0], scr[1]); }, { kind: 'secondary', size: 'sm', title: 'Mở ' + tabTitle(scr[0]) }),
            U.button('Xem hoạt động thật', function () { ctx.nav('logs', { agent: id }); }, { kind: 'ghost', size: 'sm', title: 'Nhật ký & chi phí, lọc theo agent ' + id })));
      }
      function agentHead(id) {
        var a = agentOf(id);
        return h('div', { class: 'mp-agent-head' }, U.chip(id + ' ' + a.name, 'agent' + id), h('span', { class: 'small' }, a.role_vi),
          h('span', { class: 'row' }, arr(a.graphs).map(function (g) { return U.chip(g, g); })), U.annot(['agent:' + id].concat(arr(a.graphs))));
      }
      function agentDrawer(id) {
        ctx.drawer({ title: 'Agent ' + id + ' ' + agentOf(id).name, body: function (el) { el.append(agentHead(id), agentBody(id, true)); } });
      }
      function graphDrawer(g) {
        var G = graphs[g]; if (!G) return;
        var st = thStats(g);
        ctx.drawer({
          title: g + ' · ' + G.name,
          body: function (el) {
            el.append(h('div', { class: 'row' }, U.chip(g, g), h('b', null, G.title_vi), U.chip(GRAPH_PHASE[g][0], GRAPH_PHASE[g][1])), U.cli(G.cli),
              h('ol', { class: 'mp-steps' }, arr(G.nodes).map(function (n) {
                return h('li', null, kindMark(n.kind), ' ', n.label, n.lane ? h('span', { class: 'small muted' }, ' · chạy song song, mỗi bài một làn') : null);
              })),
              h('p', { class: 'small' }, 'Commit ghi: ', arr(G.commit_tables).map(function (t) { return h('span', { class: 'mono' }, t + ' '); })),
              U.kv([['Chờ duyệt', st.awaiting_review + ' thread · ' + st.proposals + ' đề xuất'], ['Đang chạy / lỗi', st.running + ' / ' + st.failed], ['Đã commit', st.committed]]),
              h('div', { class: 'row' }, openBtn('Mở màn hình: ' + tabTitle(GRAPH_TAB[g]), GRAPH_TAB[g], {}), openBtn('Xem thread trong Vận hành', 'ops', {})));
          }
        });
      }
      function tableDrawer(name) {
        var t = arr(meta.tables).find(function (x) { return x.name === name; }) || { name: name, note: '', writer: '—', group: '' };
        var n = tableRows(name), tab = TABLE_TAB[name] || 'ops';
        ctx.drawer({
          title: (t.group === 'view' ? 'View ' : 'Bảng ') + name,
          body: function (el) {
            el.append(U.annot(['table:' + name]), h('p', null, t.note),
              U.kv([['Nhóm', t.group === 'view' ? 'view (tính khi đọc)' : 'nhóm ' + t.group], ['Ai ghi', t.writer], ['Số dòng', n == null ? '—' : f.int(n)], ['Cột chính', h('span', { class: 'mono small' }, TABLE_COLS[name] || '—')]]),
              name === 'mistake' ? h('div', { class: 'callout callout-info' }, h('p', null, 'status chỉ có confirmed / edited / rejected / added — bản “proposed” chỉ nằm trong checkpoints.db. llm_json giữ đề xuất gốc của 03.')) : null,
              h('div', { class: 'row' }, openBtn('Mở màn hình liên quan: ' + tabTitle(tab), tab, {})));
          }
        });
      }

      /* ---------- page head + TOC ---------- */
      var explainBtn = U.button(ctx.explain ? 'Tắt chú thích hệ thống' : 'Bật chú thích hệ thống', function (ev, b) {
        var on = !ctx.explain; ctx.setExplain(on);
        b.textContent = on ? 'Tắt chú thích hệ thống' : 'Bật chú thích hệ thống'; b.setAttribute('aria-pressed', String(on));
        ctx.toast(on ? 'Đã bật: chip đỏ [G1] [03 Diagnoser] [bảng mistake] [>_ tutor review] hiện trên mọi màn hình.' : 'Đã tắt chú thích hệ thống.', { kind: 'info' });
      }, { kind: 'secondary' });
      explainBtn.setAttribute('aria-pressed', String(!!ctx.explain));
      root.append(U.pageHead({
        lead: 'Cả hệ thống trên một trang: 5 tầng, 5 graph, 9 agent, 16 bảng. Bấm vào một ô để xem nó làm gì và mở màn hình dùng nó.',
        annot: ['G1', 'G2', 'G3', 'G4', 'G5', 'file:tutor.db'],
        actions: [explainBtn, U.button('Chạy thử một vòng', function () { App.tour.start(); }, { kind: 'primary', noAutoclick: true })]
      }));
      var tour = arr(App.tour && App.tour.steps);
      root.append(h('div', { class: 'callout callout-info mp-intro' },
        h('p', null, h('b', null, 'Chạy thử một vòng: '), tour.length + ' bước, chỉ chuyển màn hình và chú thích, không ghi gì: ', tour.map(function (s) { return s.title; }).join(' → ') + '.'),
        h('div', { class: 'row mp-toc', role: 'navigation', 'aria-label': 'Mục lục bản đồ' }, SECTIONS.map(function (s) { return U.button(s[1], function () { jump(s[0]); }, { kind: 'ghost', size: 'sm' }); }))));

      /* ---------- 1. 5 tầng ---------- */
      var lay = section('layers', '5 tầng', 'Đọc từ trên xuống: tầng trên gọi tầng dưới. Cột phải là nơi lưu (file local, 1 máy). Theo sơ đồ 10.', ['cli:tutor', 'file:checkpoints.db', 'file:tutor.db', 'file:llm.jsonl']);
      var nodeBtn = function (id) {
        var label, sub, kind, style = null;
        if (id.indexOf('agent:') === 0) { var a = agentOf(id.slice(6)); label = a.id + ' ' + a.name; sub = a.role_vi; kind = 'llm'; style = '--c: var(--a' + a.id + ')'; }
        else if (id.indexOf('graph:') === 0) { var g = graphs[id.slice(6)] || {}; label = id.slice(6) + ' · ' + (g.name || ''); sub = g.title_vi || ''; kind = 'graph'; style = '--c: var(--' + id.slice(6).toLowerCase() + ')'; }
        else { var n = NODE[id]; label = n.label; sub = n.sub; kind = n.kind; }
        return h('button', { type: 'button', class: 'mp-node k-' + kind, style: style, 'data-node-id': id, onclick: function () { drawerFor(id); }, 'aria-label': label + ' — ' + sub },
          h('span', { class: 'mp-node-t' }, label), h('span', { class: 'mp-node-s' }, sub));
      };
      lay.append(h('div', { class: 'mp-arch' },
        h('div', { class: 'mp-layers' }, LAYERS.map(function (Ly, i) {
          return [i ? h('div', { class: 'mp-down', 'aria-hidden': 'true' }, '↓ gọi xuống') : null,
            h('div', { class: 'mp-layer' }, h('div', { class: 'mp-layer-head' }, h('span', { class: 'mp-no' }, Ly.no), h('h3', null, Ly.title), h('span', { class: 'small muted' }, Ly.sub)),
              h('div', { class: 'mp-nodes' }, Ly.nodes.map(nodeBtn)))];
        })),
        h('div', { class: 'mp-stores' }, h('div', { class: 'mp-layer-head' }, h('h3', null, 'Lưu trữ'), h('span', { class: 'small muted' }, 'file local')), STORES.map(nodeBtn))),
        h('p', { class: 'small muted mp-legend' }, 'Viền bo tròn = LLM · góc vuông = code · nét đứt đỏ = giáo viên · nét đứt vàng = DỪNG / checkpoints.db · xanh liền = tutor.db · chấm = ngoài máy.'));
      root.append(lay);

      /* ---------- 2. 5 graph ---------- */
      var gs = section('graphs', '5 graph', 'Mỗi lệnh CLI chạy một graph cố định (sơ đồ 11). Bàn tay = DỪNG chờ thầy/cô; ô xanh = commit node, nơi duy nhất ghi tutor.db.', ['interrupt()', 'commit node', 'checkpoint']);
      gs.append(h('div', { class: 'stack' }, ['G1', 'G2', 'G3', 'G4', 'G5'].filter(function (g) { return graphs[g]; }).map(function (g) {
        var G = graphs[g], st = thStats(g);
        var stop = arr(G.nodes).find(function (n) { return n.kind === 'stop' && /\.review$/.test(n.id); });
        return h('div', { class: 'card mp-graph', style: '--c: var(--' + g.toLowerCase() + ')' },
          h('div', { class: 'spread' }, h('div', { class: 'row' }, U.chip(g, g), h('b', null, G.title_vi), h('span', { class: 'mono small muted' }, G.name), U.chip(GRAPH_PHASE[g][0], GRAPH_PHASE[g][1]), U.annot([g])),
            h('div', { class: 'row small' }, st.awaiting_review ? U.chip(st.awaiting_review + ' chờ duyệt', 'warn') : null, st.running ? U.status('running') : null, st.failed ? U.chip(st.failed + ' lỗi', 'danger') : null,
              h('span', { class: 'muted' }, st.committed + ' đã commit'))),
          U.graphStrip(g, { current: st.awaiting_review && stop ? stop.id : null, compact: true }),
          h('div', { class: 'spread' }, h('div', { class: 'stack mp-tight' }, U.cli(G.cli), h('span', { class: 'small muted' }, 'Commit ghi: ' + arr(G.commit_tables).join(', '))),
            h('div', { class: 'row' }, U.button('Giải thích các node', function () { graphDrawer(g); }, { kind: 'ghost', size: 'sm' }), openBtn('Mở màn hình: ' + tabTitle(GRAPH_TAB[g]), GRAPH_TAB[g], {}))));
      })));
      root.append(gs);

      /* ---------- 3. 9 agent ---------- */
      var ag = section('agents', '9 agent', 'Mỗi agent = một lượt gọi LLM có vai trò, prompt riêng, đầu ra theo schema. Đánh dấu từng bước: LLM / code / GV (chú giải sơ đồ 01–09).', ['file:llm.jsonl']);
      ag.append(h('div', { class: 'grid cols-2 mp-agents' }, agents.map(function (a) {
        return h('article', { class: 'card mp-agent', style: '--c: var(--a' + a.id + ')', id: 'mp-agent-' + a.id }, agentHead(a.id), agentBody(a.id, false));
      })));
      root.append(ag);

      /* ---------- 4. Dữ liệu ---------- */
      var data = section('data', 'Dữ liệu', 'Hai nơi lưu tách biệt: đề xuất chờ duyệt nằm trong checkpoints.db; tutor.db chỉ nhận dòng đã duyệt. Số dòng lấy trực tiếp từ dữ liệu mẫu.', ['file:checkpoints.db', 'file:tutor.db']);
      var st0 = thStats();
      data.append(h('div', { class: 'grid cols-2' },
        h('div', { class: 'card st-pending' }, h('div', { class: 'row' }, U.store('checkpoint'), h('b', null, 'Đề xuất, chưa phải dữ liệu chính thức')),
          h('p', { class: 'small' }, f.int(threads().length) + ' thread · ' + st0.awaiting_review + ' chờ duyệt (' + st0.proposals + ' đề xuất) · ' + st0.running + ' đang chạy · ' + st0.failed + ' lỗi'),
          h('p', { class: 'small muted' }, 'Huỷ thread: đề xuất bị xoá. Buổi học (G1) vẫn giữ dòng session trong tutor.db với trạng thái failed; graph khác không đổi tutor.db.')),
        h('div', { class: 'card st-db' }, h('div', { class: 'row' }, U.store('db'), h('b', null, 'Đã duyệt — chỉ commit node ghi')),
          h('p', { class: 'small' }, f.int(dbRows()) + ' dòng trong 16 bảng'),
          h('p', { class: 'small muted' }, 'Bị bỏ vẫn lưu (status rejected) để đo độ chính xác; sửa = dòng mới + supersedes_id.'))));
      data.append(h('div', { class: 'grid cols-3 mp-groups' }, GROUPS.map(function (gr) {
        var ts = arr(meta.tables).filter(function (t) { return t.group === gr[0]; });
        return h('div', { class: 'card' }, h('div', { class: 'row' }, h('span', { class: 'mp-no' }, gr[0] === 'view' ? 'V' : gr[0]), h('b', null, gr[1])),
          h('div', { class: 'stack mp-tight' }, ts.map(function (t) {
            var n = tableRows(t.name);
            return h('button', { type: 'button', class: 'mp-table' + (t.group === 'view' ? ' is-view' : ''), title: t.note + ' · ghi bởi ' + t.writer, onclick: function () { tableDrawer(t.name); } },
              h('span', { class: 'mono' }, t.name), h('span', { class: 'small muted mp-table-w' }, t.writer), h('span', { class: 'num small' }, n == null ? '—' : f.int(n)));
          })),
          h('p', { class: 'small muted' }, gr[2] ? 'Ai ghi: ' + gr[2] : 'Tính lại mỗi lần đọc từ attempt, mistake.'));
      })));
      root.append(data);

      /* ---------- 5. CLI ↔ app ---------- */
      var cl = section('cli', 'CLI ↔ app', 'Mỗi lệnh CLI có một nút tương ứng trong app; dòng >_ dưới nút là lệnh đó.', ['cli:tutor ingest', 'cli:tutor review']);
      cl.append(U.table({
        columns: [
          { label: 'Lệnh', render: function (r) { return h('code', { class: 'nowrap' }, r[0]); } },
          { label: 'Graph', render: function (r) { return /^G\d$/.test(r[1]) ? U.chip(r[1], r[1]) : U.chip(r[1]); } },
          { label: 'Màn hình › nút', render: function (r) { return r[2]; } },
          { label: 'Ghi vào', render: function (r) { var g = graphs[r[1]]; return h('span', { class: 'small mono' }, g ? arr(g.commit_tables).join(', ') : 'commit của graph đang dừng'); } },
          { label: '', render: function (r) { return openBtn('Mở', r[3], r[4]); } }
        ],
        rows: CLI
      }));
      root.append(cl);

      /* ---------- 6. Nguyên tắc ---------- */
      var pr = section('principles', 'Nguyên tắc', 'Bảy luật không đổi của hệ thống (spec §4, §7, §8).', ['commit node']);
      pr.append(h('div', { class: 'grid cols-3' }, PRINCIPLES.map(function (p, i) {
        return h('div', { class: 'card' }, h('div', { class: 'mp-ph' }, h('span', { class: 'mp-no' }, i + 1), h('b', null, p[0])), h('p', { class: 'small' }, p[1]),
          h('p', { class: 'small muted' }, 'Thấy ở: ' + p[2]), openBtn('Mở: ' + tabTitle(p[3]), p[3], {}));
      })));
      root.append(pr);

      /* ---------- 7. Thuật ngữ ---------- */
      var gl = section('glossary', 'Thuật ngữ', 'Cũng là nội dung chú thích khi bật “Chú thích hệ thống” (di chuột lên chip đỏ).');
      gl.append(h('dl', { class: 'mp-gloss' }, arr(meta.glossary).map(function (g) { return h('div', { class: 'mp-gloss-i' }, h('dt', null, g.term), h('dd', null, g.vi)); })));
      root.append(gl);

      /* ---------- 8. Không làm (cố ý) ---------- */
      var sk = section('skipped', 'Không làm (cố ý)', 'Bỏ có chủ đích, không phải thiếu sót.');
      sk.append(h('ul', { class: 'mp-skip' }, SKIPPED.map(function (s) { return h('li', { class: 'st-rejected' }, h('s', null, s[0]), h('span', { class: 'small' }, s[1])); })));
      root.append(sk);

      /* ---------- 9. Chưa chốt ---------- */
      var op = section('open', 'Chưa chốt', 'Các điểm chủ dự án cần trả lời / duyệt (tài liệu thiết kế §11.1–11.2). Màn hình nào dựa trên đề xuất chưa chốt đều ghi nhãn “đề xuất, chờ chốt”.');
      var r = S.reco || {};
      op.append(h('h3', null, 'Câu hỏi cho chủ dự án (' + QUESTIONS.length + ')'),
        h('ol', { class: 'mp-list' }, QUESTIONS.map(function (q) { return h('li', null, q); })),
        h('h3', null, 'Lựa chọn có đề xuất (' + CHOICES.length + ')'),
        U.table({
          columns: [
            { label: '#', render: function (c) { return CHOICES.indexOf(c) + 1; } },
            { label: 'Điểm cần chốt', render: function (c) { return h('b', null, c[0]); } },
            { label: 'Đề xuất', render: function (c) {
              return h('span', null, c[1], c[0] === 'Số bài gợi ý mỗi buổi' && r.ratios ? h('span', { class: 'small muted' }, ' · đang cài: ' + r.n_problems + ' bài, ' + [r.ratios.review, r.ratios.zpd, r.ratios.challenge].map(function (x) { return Math.round(x * 100); }).join('/')) : null);
            } },
            { label: 'Vì sao', render: function (c) { return h('span', { class: 'small' }, c[2]); } },
            { label: 'Thấy trong app', render: function (c) { return h('span', { class: 'small' }, c[3]); } },
            { label: '', render: function (c) { return c[4] ? openBtn('Mở', c[4], {}) : null; } }
          ],
          rows: CHOICES
        }));
      root.append(op);

      /* ---------- params ---------- */
      var target = ctx.params.section;
      if (target && secs[target]) requestAnimationFrame(function () { jump(target); });
      if (ctx.params.node) setTimeout(function () { if (root.isConnected) drawerFor(ctx.params.node); }, 0);
    }
  });
})();
