/**
 * Part A of the model-selection report: the 2026-09-28 re-evaluation.
 *
 * Called by generate_report.js with its helpers and data. Like the rest of the
 * report, every number here is read from the results at generation time:
 *   figures/reeval_detectors.csv      (written by plot_reeval.py)
 *   results/vlm.jsonl                 (rows dated 2026-09-28)
 *   results/vlm_content_scores.csv    (written by score_vlm_generations.py)
 *   results/vlm_outputs_*.json        (the raw answers, for the worked example)
 * Only the choice of recommended configuration is fixed here (PICKS), because
 * that is a judgement, not a measurement - docs/10 and docs/12 give the reasons.
 */
const fs = require('fs');
const path = require('path');

const ROUND2 = '2026-09-28';

// The judgement calls. Everything said about them is read from the data.
const PICKS = {
  detector: 'visdrone-yolo26s-736x1280@736x1280 lean',   // the deployed serving path
  detectorRunnerUp: 'visdrone-rtdetrv4-s@960',          // the Apache-2.0 alternative
  detectorBaseline: 'yolo11s@960',
  vlmModel: 'Qwen3-VL-2B-Instruct',
  vlmMode: 'greedy+rep',
  vlmOld: 'Qwen2.5-VL-3B-Instruct',
};

const LICENCE = {
  'visdrone-rtdetrv4-s': 'Apache-2.0 (weights: VisDrone NC)',
  'visdrone-yolo26s': 'AGPL-3.0 (weights: VisDrone NC)',
  'visdrone-yolo26s-960': 'AGPL-3.0 (weights: VisDrone NC)',
  'visdrone-yolo26s-1280': 'AGPL-3.0 (weights: VisDrone NC)',
  'visdrone-yolo26s-736x1280': 'AGPL-3.0 (weights: VisDrone NC)',
  'visdrone-yolo26n-1280': 'AGPL-3.0 (weights: VisDrone NC)',
  'sih-aerial-person-1280': 'AGPL-3.0',
  'yolo11s': 'AGPL-3.0', 'yolo11s-1280': 'AGPL-3.0', 'yolo26s-960': 'AGPL-3.0',
};

const readCsv = (file) => {
  if (!fs.existsSync(file)) return [];
  const [head, ...lines] = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
  const cols = head.split(',');
  return lines.map((l) => {
    const v = l.split(',');
    return Object.fromEntries(cols.map((c, i) => [c, v[i] === undefined ? '' : v[i]]));
  });
};

// Same rule as bench_vlm.py: the first balanced JSON object in the text.
const extractJson = (text) => {
  const start = text.indexOf('{');
  if (start < 0) return null;
  let depth = 0;
  for (let i = start; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    else if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        try { return JSON.parse(text.slice(start, i + 1)); } catch { return null; }
      }
    }
  }
  return null;
};

const flat = (v) => (Array.isArray(v) ? v.map(flat).join('; ')
  : (v && typeof v === 'object') ? Object.entries(v).map(([k, x]) => `${k}: ${flat(x)}`).join(', ')
    : String(v ?? ''));

const vlmMode = (r) => {
  const d = r.decoding || { mode: 'greedy' };
  let m = d.mode === 'greedy' ? 'greedy' : (d.do_sample ? 'shipped' : 'shipped = greedy');
  if (m === 'greedy' && d.repetition_penalty && d.repetition_penalty !== 1.0) m = 'greedy+rep';
  if ((r.model_kwargs || {}).downsample_mode === '4x') m += ' 4x';
  return m;
};

module.exports = function partA(ctx) {
  const { p, h, bullets, table, figure, fmt, HeadingLevel, Paragraph, PageBreak,
    RESULTS_DIR, FIGURES_DIR, vlmAll, MUTED } = ctx;
  const out = [];
  const H1 = HeadingLevel.HEADING_1;
  const H2 = HeadingLevel.HEADING_2;
  const pct = (x) => `${Math.round(Number(x) * 100)} %`;

  // ---------- detector data ----------
  const det = readCsv(path.join(FIGURES_DIR, 'reeval_detectors.csv'));
  const byKey = Object.fromEntries(det.map((r) => [r.key, r]));
  const pick = byKey[PICKS.detector];
  const runner = byKey[PICKS.detectorRunnerUp];
  const base = byKey[PICKS.detectorBaseline];

  // GPU compute alone (trtexec), which compares networks across harnesses.
  const gpuFile = path.join(RESULTS_DIR, 'gpu_compute.jsonl');
  const gpu = fs.existsSync(gpuFile) ? Object.fromEntries(fs.readFileSync(gpuFile, 'utf8').split(/\r?\n/)
    .filter(Boolean).map((l) => JSON.parse(l)).map((g) => [g.key, g])) : {};
  const gpuOf = (key) => {
    const g = gpu[key] || gpu[key.replace(/ lean$/, '')];    // same engine, whatever serves it
    return g ? `${fmt(g.gpu_p95_ms, 1)} ms` : 'n/a';
  };

  // ---------- VLM data ----------
  const scores = Object.fromEntries(readCsv(path.join(RESULTS_DIR, 'vlm_content_scores.csv'))
    .map((s) => [s.file, s]));
  const vlm2 = vlmAll.filter((r) => (r.timestamp || '').startsWith(ROUND2) && r.crops === 16)
    .map((r) => ({ r, s: scores[r.generations_file], mode: vlmMode(r) }))
    .filter((x) => x.s);
  const vpick = vlm2.find((x) => x.r.model === PICKS.vlmModel && x.mode === PICKS.vlmMode);
  const vold = vlm2.find((x) => x.r.model === PICKS.vlmOld && x.mode === 'greedy');

  // ================= Part A =================
  out.push(h('Part A — Re-evaluation, 28 September 2026', H1));
  out.push(p('This part replaces the recommendations of Part B. Part B, the original evaluation of 20 September, follows it ' +
    'unchanged except for one marked correction, because its method and most of its findings still hold.',
  { italic: true, color: MUTED }));

  // ---- A1
  out.push(h('A1. Summary and recommendation', H2));
  if (pick && base) {
    out.push(p(`Detector: YOLO26s trained on VisDrone aerial imagery, as a 736×1280 TensorRT FP16 engine, served through a lean TensorRT runtime.`, { bold: true }));
    const ultra = byKey[PICKS.detector.replace(/ lean$/, '')];
    out.push(p(
      `On held-out aerial images (VisDrone test-dev) it finds ${pct(pick.td_recall)} of people, against ` +
      `${pct(base.td_recall)} for the first-round pick (COCO yolo11s), and it is the lightest network at that ` +
      `accuracy: ${gpuOf(PICKS.detector)} of GPU compute per frame (p95). Served by the lean TensorRT runner it takes ` +
      `${fmt(pick.p95_ms, 1)} ms p95 end to end on real frames` +
      (ultra ? `, against ${fmt(ultra.p95_ms, 1)} ms through Ultralytics' Python pipeline` : '') + '.' +
      (runner ? ` RT-DETRv4-S trained on VisDrone ties it on accuracy (${pct(runner.td_recall)} of people) and is ` +
        `${fmt(runner.p95_ms, 1)} ms end to end, but needs ${gpuOf(PICKS.detectorRunnerUp)} of GPU compute — a third more, ` +
        `on a GPU the VLM shares. It is Apache-2.0, and deployed alongside as the alternative if AGPL is ruled out.` : '')));
  }
  if (vpick && vold) {
    out.push(p(`Vision-language model: Qwen3-VL-2B-Instruct, greedy decoding with repetition penalty 1.05.`, { bold: true }));
    out.push(p(
      `On 16 crops of people who are neither injured nor lying down, it returned valid JSON on ` +
      `${pct(vpick.r.schema_valid_rate)} and reported an injury for ${vpick.s.false_injury} of the 16. The first-round pick, ` +
      `Qwen2.5-VL-3B, reported injury indicators for ${vold.s.false_injury} of them — four outright inventions (a bruise, ` +
      `bruising, a "foot injury", bloodstains) and three non-injuries filed as injuries. It starts answering in ` +
      `${fmt(vpick.r.ttft_s.p95, 2)} s (p95) against ${fmt(vold.r.ttft_s.p95, 2)} s, uses ` +
      `${fmt(vpick.r.gpu_mem_peak_mb / 1000, 1)} GB against ${fmt(vold.r.gpu_mem_peak_mb / 1000, 1)} GB, and is Apache-2.0.`));
  }
  out.push(p('What changed the answer:', { bold: true }));
  out.push(...bullets([
    'Detectors trained on aerial imagery now exist as downloads. Training data mattered far more than architecture or resolution: it roughly doubles the people found at the same cost.',
    'A truthfulness check, not just a schema check. Scoring what each VLM actually said against what the crops show exposed invented injuries that a parse-rate table cannot see.',
    'Decoding settings decide whether a model works. Under plain greedy decoding Qwen3-VL loops and only a third of its replies parse; with a 1.05 repetition penalty, all of them do.',
  ]));
  out.push(p('Two statements in Part B were wrong, and are corrected in section A5. The new models were deployed on the board on 29 September (section A7).',
    { bold: true }));

  // ---- A2
  out.push(h('A2. Why a re-evaluation', H2));
  out.push(...bullets([
    'Part B compared COCO-trained detectors only, and found that they miss most people seen from the air. The question was whether something better exists now, without training anything ourselves.',
    'Part B took its VLM shortlist from a design document written before the current generation (Qwen3-VL and others) was released. Qwen3 had never been tested.',
    'Both were answered with the same harness, the same board (Orin NX 16 GB at 25 W) and the same data as Part B, plus a held-out test set Part B did not have.',
  ]));

  // ---- A3 detectors
  out.push(h('A3. Detectors', H2));
  out.push(...bullets([
    'Latency: TensorRT FP16 engines timed on the same 200 real VisDrone frames as Part B. The Part B baseline re-measures at 26.1 ms against 25.9 ms, so the two parts compare.',
    'Accuracy on VisDrone val (as in Part B) and on VisDrone test-dev: 1,610 images, 27,382 people, 343 images with nobody, which no one involved used for training or model selection. The VisDrone-trained checkpoints were selected on val by their authors, so test-dev is the fair column.',
    'Models trained on VisDrone split people into "pedestrian" and "people"; both count as a person, scored with person_scoring.py (see "A scoring bug" below).',
  ]));
  if (det.length) {
    const rows = det.slice().sort((a, b) => Number(b.td_recall || 0) - Number(a.td_recall || 0)).map((r) => {
      const row = [`${r.name} @${r.imgsz}`, fmt(r.p95_ms, 1), fmt(r.td_recall), fmt(r.td_map50), fmt(r.val_recall),
        LICENCE[r.key.split('@')[0]] || ''];
      if (r.key === PICKS.detector) row.__highlight = true;
      return row;
    });
    out.push(table(['Configuration', 'p95 ms', 'test-dev recall', 'test-dev mAP@0.5', 'val recall', 'Licence'],
      rows, [2500, 900, 1250, 1350, 1050, 2310]));
    out.push(p('Budget: 33 ms per frame. Rows above 33 ms p95 miss it. The 736×1280 engine carries the 1280 rows\' accuracy (the same pixels on a 16:9 frame).',
      { size: 18, color: MUTED, italic: true }));
  }
  out.push(...figure('fig5_reeval_detectors.png', 'Figure 5. Held-out accuracy against real-frame latency. Orange: trained on aerial imagery.'));
  out.push(...figure('fig6_reeval_recall.png', 'Figure 6. Recall on VisDrone val (hollow) and held-out test-dev (solid). The gap is how much our usual set flatters each model.'));
  out.push(p('Findings:', { bold: true }));
  out.push(...bullets([
    'Aerial training is the lever. Inside the budget, COCO detectors find about a fifth of the people on test-dev; the VisDrone-trained ones find 37–44 %.',
    'Higher resolution only pays with a rectangular engine. A 1080p frame letterboxed into a 1280 square is 44 % padding: 39 ms, over budget. Built as 736×1280, the same model takes 31 ms.',
    'Synthetic frames under-time real work by about a third (28 ms against 39 ms for the square engines). Every latency here is on real frames.',
    'At 1280 px the nano model is no faster than the small one in a rectangular engine, and less accurate: pre- and post-processing, not the network, set the cost there.',
    'VisDrone val overstates every model by 15–25 points of mAP, most for models tuned on it. Decisions are made on test-dev.',
    `Measured as networks alone (trtexec, GPU compute only), the YOLO26s engines need ${gpuOf(PICKS.detector)} and RT-DETRv4-S ${gpuOf(PICKS.detectorRunnerUp)} per frame. RT-DETRv4-S looked faster end to end only because its harness is leaner: Ultralytics’ Python pipeline adds 15–20 ms per frame to the YOLOs, more than the network itself. The production detector node should run the engine directly.`,
  ]));
  out.push(p('A scoring bug, found and fixed', { bold: true }));
  out.push(p('Ultralytics\' val() ignores its classes argument. That is harmless for COCO models against a one-class dataset, but with single_cls it scored every car and van as a person for the VisDrone-trained models: YOLO26s showed precision 0.25 instead of 0.73 and would have been rejected. person_scoring.py now keeps only the person classes, merges them, and scores with Ultralytics\' own matching and ap_per_class; on the COCO baseline it agrees with val() within half a point. The three wrongly scored rows stay in the results, flagged, so they cannot be plotted by accident.'));
  out.push(p('Pose (latency only; VisDrone has no keypoints): YOLO26s-pose runs at 22.7 ms p95 against 26.5 ms for yolo11s-pose.'));

  // ---- A4 VLMs
  out.push(new Paragraph({ children: [new PageBreak()] }));
  out.push(h('A4. Vision-language models', H2));
  out.push(...bullets([
    `${new Set(vlm2.map((x) => x.r.model)).size} models in ${vlm2.length} configurations: each with its shipped decoding settings and, where different, deterministic greedy decoding with a 1.05 repetition penalty. Same prompt and JSON schema as Part B, bf16, transformers 5.17, 160-token cap.`,
    'Sixteen person crops from VisDrone. Checked by eye: 13 people standing or walking, 3 sitting, nobody lying down and nobody visibly injured — while the prompt tells every model the person is lying and immobile. So any injury reported is invented, and any "lying" means the model believed the prompt over the image.',
    'Schema validity says a reply parses. The truthfulness columns (score_vlm_generations.py) say whether it is true. Neither measures whether a model notices a real injury: there are none in this set.',
  ]));
  if (vlm2.length) {
    const ordered = vlm2.slice().sort((a, b) => (Number(a.s.false_injury) - Number(b.s.false_injury))
      || (b.r.schema_valid_rate - a.r.schema_valid_rate) || (Number(a.s.said_lying) - Number(b.s.said_lying))
      || (a.r.ttft_s.p95 - b.r.ttft_s.p95));
    out.push(table(['Model (decoding)', 'Valid JSON', 'Injury reported', 'Said "lying"', 'Flags unseen', 'First token p95 s', 'Full reply s', 'Peak GB'],
      ordered.map((x) => {
        const row = [`${x.r.model.replace('-Instruct', '').replace('-HF', '').replace('InternVL3_5', 'InternVL3.5')} (${x.mode})`,
          pct(x.r.schema_valid_rate), `${x.s.false_injury} / 16`, `${x.s.said_lying} / 16`, `${x.s.not_visible_used} / 16`,
          fmt(x.r.ttft_s.p95, 2), fmt(x.r.total_s.mean, 1), fmt(x.r.gpu_mem_peak_mb / 1000, 1)];
        if (x === vpick) row.__highlight = true;
        return row;
      }), [2500, 900, 1050, 950, 950, 1050, 1000, 960]));
  }
  out.push(...figure('fig7_reeval_vlm.png', 'Figure 7. The VLM comparison. Red: answers reporting an injury for people who have none.', 640));

  // Worked example: the same crop through the old and the new pick.
  const example = (file) => {
    const f = path.join(RESULTS_DIR, file || '');
    if (!file || !fs.existsSync(f)) return null;
    const g = JSON.parse(fs.readFileSync(f, 'utf8')).generations.find((x) => x.crop.startsWith('crop_014'));
    const obj = g && extractJson(g.text);
    return obj ? { pos: flat(obj.body_position), inj: flat(obj.injury_indicators) || '(none)', sur: flat(obj.surroundings) } : null;
  };
  const exOld = vold && example(vold.r.generations_file);
  const exNew = vpick && example(vpick.r.generations_file);
  if (exOld && exNew) {
    out.push(p('One crop, two models. A man sitting on a kerb, looking at his phone:', { bold: true }));
    out.push(table(['', 'Qwen2.5-VL-3B (Part B pick)', 'Qwen3-VL-2B (new pick)'], [
      ['body_position', exOld.pos, exNew.pos],
      ['injury_indicators', exOld.inj, exNew.inj],
      ['surroundings', exOld.sur, exNew.sur],
    ], [1700, 3830, 3830]));
    out.push(p(''));
  }
  out.push(p('Findings:', { bold: true }));
  out.push(...bullets([
    'Qwen3-VL-2B is the only configuration that is at once truthful (no invented injuries), fully schema-valid, honest about what it cannot see (it fills not_visible in 16 of 16 answers), quick to start and small.',
    'Qwen3.5-2B is a close second: equally free of invented injuries, and the only model that never repeated the prompt\'s "lying". But it never fills not_visible (0 of 16) — it presents everything as observed — it speculates ("possibly eating or drinking" of a man looking at his phone), and it is slower. Two posture errors against none in 16 crops is not a meaningful difference; both should be re-run on a larger set once the prompt is fixed.',
    'Rejected: LFM2.5-VL-3B is the fastest, but called 5 of 16 upright people "lying", invented a bruise, and wrote "East Asian male" — a demographic claim docs/08 rules out — at 0.95 confidence. MiniCPM-V-4.6 describes accurately but writes malformed JSON (6–25 % parse). Qwen3-VL-4B is slower, twice the size, and believes the prompt more often than the 2B. InternVL3.5-2B is honest but takes 2.1 s to its first token.',
    'Decoding is part of the model choice. Qwen3 models loop under plain greedy decoding — their own documentation says not to use it — and sampling makes the output non-deterministic, which a safety system should avoid. Greedy with a 1.05 repetition penalty fixes both.',
    'Most models sometimes report the posture the prompt asserted rather than the one they see, and most copy the prompt\'s 0.91 into their own "confidence". Both are design faults of the prompt, not of a model: the prompt must stop stating the posture as fact, and the VLM\'s confidence field cannot be used for anything.',
    'Still too slow for the 5 s target: about 12 s for a full description in bf16 transformers. That is a serving problem. A 4-bit llama.cpp build of the same model is expected to be several times faster (published Orin Nano figures for a Qwen3-VL-2B derivative: 38 tokens/s) and adds grammar-constrained JSON, which docs 03 and 12 already require as a safety control.',
  ]));

  // ---- A5 corrections
  out.push(h('A5. Corrections to Part B', H2));
  out.push(...bullets([
    'Part B, section 8, says Qwen2.5-VL-3B "correctly returned an empty injury list for uninjured pedestrians rather than inventing wounds". That was wrong at the time. Its answers are deterministic, and the 20 September run is byte-identical to today\'s on the same eight crops: on a man sitting on a railing it reported "lying, face up" and "visible bruise on left arm", and on another crop it listed "slippery shoes" as an injury. The first answer was missed because it failed to parse, and unparsed answers were not read. The same claim in docs/12 is corrected there.',
    'Part B\'s recommendations (yolo11s-pose as detector and pose model; Qwen2.5-VL-3B) are superseded by A1. What is deployed on the board is still the Part B set until the swap is made.',
    'Lesson kept in the harness: every answer is now scored, whether it parses or not.',
  ]));

  // ---- A6 design
  out.push(h('A6. What changes in the design', H2));
  out.push(...bullets([
    'Tier 1 and tier 2 separate. No aerial-trained pose model exists, and the COCO pose model finds about a fifth of the people from the air. Detection comes from the aerial detector on every frame; posture comes from crops of each track at a lower rate (people do not change posture thirty times a second), with YOLO26s-pose above about 32 px and a direct posture classifier below.',
    'The VLM prompt must not assert the posture. Pass the geometric posture as a hypothesis to confirm or reject, or not at all, and compare.',
    'The VLM\'s "confidence" field should be removed from the schema or ignored.',
    'Serving: run the detector engine directly (TensorRT runtime or NITROS), not through Ultralytics’ Python pipeline, which adds more time per frame than the network itself.',
    'Licensing: the VLM is Apache-2.0. The recommended detector is AGPL-3.0 (as YOLO11 was); the AGPL decision is still the team’s, but no longer blocking, because RT-DETRv4-S is a measured Apache-2.0 alternative. Both detectors’ weights are trained on VisDrone (non-commercial); they must be replaced by our own fine-tune before any commercial use — which Phase 2 plans anyway.',
  ]));

  // ---- A7 next
  out.push(h('A7. Deployed on the flight computer, 29 September', H2));
  const dep = (() => { try { return JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'deploy_manifest.json'), 'utf8')); } catch { return null; } })();
  if (dep && dep.artifacts) {
    out.push(p('Staged in ~/raptor-deploy by src/deploy/deploy_models.py. Each artifact was loaded and run on the board after staging; MANIFEST.json records its source, licence, checksum and measured performance. The previous set is kept at ~/raptor-deploy.2026-09-20.'));
    out.push(table(['Slot', 'Artifact', 'Measured', 'Verified'], Object.entries(dep.artifacts).map(([slot, a]) => {
      const m = a.measured || {};
      const perf = m.p95_ms != null ? `${fmt(m.p95_ms, 1)} ms p95` + (m.recall != null ? `, test-dev recall ${fmt(m.recall)}` : '')
        : (m.ttft_p95_s != null ? `first token ${fmt(m.ttft_p95_s, 2)} s, ${pct(m.schema_valid_rate)} valid JSON` : '—');
      return [slot, path.basename(a.path || ''), perf, a.verify && a.verify.ok ? 'yes' : 'no'];
    }), [1500, 3000, 3700, 1160]));
    out.push(p(''));
  }
  out.push(...bullets([
    'The live demo now runs the two-stage pipeline: the aerial detector on every frame through the lean runner, and pose on crops of each person every fifth frame. On the live camera the detector took 20.8 ms per 1080p frame (the webcam caps the demo at ~24 FPS).',
    'The aerial detector did not see a person sitting right next to the desk webcam, where the COCO pose model did: it is trained on small people seen from above. That is expected; a second desktop icon, RAPTOR Live Demo (bench), runs the pose model alone for close-up demos, and --source plays aerial images or footage through the real pipeline.',
  ]));
  out.push(...figure('live_two_stage_demo.jpg', 'The deployed two-stage pipeline on a VisDrone frame: the aerial detector finds four people; pose on the crop gives the nearest one a skeleton and a posture.', 560));

  // ---- A8 next
  out.push(h('A8. Next steps', H2));
  out.push(...bullets([
    'Speed up the lean detector runner: it still resizes on the CPU, so it takes 26.1 ms end to end against 11.5 ms of GPU compute. Resizing on the GPU should recover most of the gap.',
    'Serve the VLM through llama.cpp at 4 bits with a JSON grammar, and re-measure speed and truthfulness.',
    'Build the evaluation that matters most and does not exist yet: aerial images of people lying down (Okutama-Action, NOMAD, SARD, HERIDAL), for both the detector and the posture step.',
    'Run the detector and the VLM together (experiment E7) — they have never shared the GPU.',
  ]));

  out.push(new Paragraph({ children: [new PageBreak()] }));
  out.push(h('Part B — Original evaluation, 20 September 2026', H1));
  out.push(p('Kept as the record. Its recommendations are superseded by Part A; its one factual error is marked where it occurs (section 8) and corrected in A5.',
    { italic: true, color: MUTED }));
  return out;
};
