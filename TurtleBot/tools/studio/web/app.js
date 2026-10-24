/* TurtleBot Studio UI. Plain ES2020, no dependencies. Talks to studio.py (see spec section 3). */
'use strict';

/* ---------- helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v, d = 1, unit = '') => (v === null || v === undefined || Number.isNaN(v)) ? '<span class="dim">&ndash;</span>' : (+v).toFixed(d) + (unit ? '&nbsp;' + unit : '');
const txt = v => (v === null || v === undefined || v === '') ? '<span class="dim">&ndash;</span>' : esc(v);
const tag = (kind, label) => {
  const icon = { ok: '&#10003;', warn: '&#9888;', bad: '&#10007;', dim: '&middot;' }[kind] || '';
  return `<span class="tag ${kind}">${icon} ${esc(label)}</span>`;
};
const yesNo = (v, yes = 'Yes', no = 'No') => v === null || v === undefined ? tag('dim', 'unknown') : (v ? tag('ok', yes) : tag('dim', no));
const rows = list => list.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('');
function fmtUptime(s) {
  if (s == null) return '–';
  s = Math.floor(s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return (d ? d + 'd ' : '') + (h || d ? h + 'h ' : '') + m + 'm';
}
function fmtSize(n) { if (n == null) return '–'; if (n < 1024) return n + ' B'; if (n < 1048576) return (n / 1024).toFixed(1) + ' KB'; return (n / 1048576).toFixed(1) + ' MB'; }
function splitArgs(s) { // shell-like split: quotes and backslash escapes
  const out = []; let cur = '', q = null, has = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === q) q = null;
      else if (c === '\\' && q === '"' && i + 1 < s.length && '"\\'.includes(s[i + 1])) cur += s[++i];
      else cur += c;
    } else if (c === '"' || c === "'") { q = c; has = true; }
    else if (/\s/.test(c)) { if (cur || has) { out.push(cur); cur = ''; has = false; } }
    else if (c === '\\' && i + 1 < s.length) cur += s[++i];
    else cur += c;
  }
  if (q) throw new Error('Unclosed quote in the arguments');
  if (cur || has) out.push(cur);
  return out;
}
const raf = (() => { const pending = new Set(); return fn => { if (pending.has(fn)) return; pending.add(fn); requestAnimationFrame(() => { pending.delete(fn); fn(); }); }; })();

/* ---------- token, theme ---------- */
const qs = new URLSearchParams(location.search);
let TOKEN = qs.get('token') || '';
try { if (TOKEN) sessionStorage.setItem('studio_token', TOKEN); else TOKEN = sessionStorage.getItem('studio_token') || ''; } catch (e) { /* storage blocked */ }
if (qs.has('token')) { qs.delete('token'); const rest = qs.toString(); history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash); }
if (qs.get('theme') === 'dark' || qs.get('theme') === 'light') document.documentElement.dataset.theme = qs.get('theme');

/* ---------- state ---------- */
const MOTION_DEFAULT = ['drive_test.py', 'motion_shapes.py', 'motion_test.sh', 'more_shapes.py', 'wall_approach.py', 'keep_distance.py', 'campaign.sh'];
const MAX_LINES = 2000;
const S = {
  conn: { state: 'disconnected' }, hello: null, status: null, statusAt: 0, sse: false,
  settings: {}, cands: [], applog: [], files: [], args: {},
  runs: {}, selRun: null, local: null, remote: null, selFile: null,
  topics: [], watches: {}, action: null, estopLocal: false, hostTyped: '',
  catalog: { programs: {}, templates: [] }, desc: {}, open: {}, laptop: null, wifi: null,
  defaults: {}, trusted: [], labKey: null, wifiJob: null, wifiJobOpen: false,
  deep: { running: false, done: 0, total: 0 }, reconn: null, update: null,
};
const motionSet = () => new Set([...MOTION_DEFAULT, ...(S.settings.motion_files || [])]);
const isMotion = name => {
  const n = name.split('/').pop(), c = S.catalog.programs[n], d = S.desc[n];
  return motionSet().has(n) || !!(c && c.moves) || !!(d && d.moves_detected);
};
const remoteDir = () => S.settings.remote_dir || '~/robot_code';
const connected = () => S.conn.state === 'connected';

/* ---------- api ---------- */
async function api(path, body) {
  const opt = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Studio-Token': TOKEN } };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(path, opt); } catch (e) { return { ok: false, error: 'Cannot reach Studio: ' + e.message }; }
  let j; try { j = await r.json(); } catch (e) { j = { ok: false, error: 'HTTP ' + r.status }; }
  if (!r.ok && j.ok !== false) j = { ok: false, error: j.error || 'HTTP ' + r.status };
  return j;
}
async function call(path, body, opts = {}) {
  const j = await api(path, body);
  if (!j.ok && !opts.quiet) notify('error', (opts.what ? opts.what + ': ' : '') + (j.error || 'failed'));
  return j;
}
const bridge = (cmd, args = {}, opts) => call('/api/bridge', { cmd, ...args }, { what: cmd, ...opts });

/* ---------- toasts, app log ---------- */
function notify(kind, msg) {
  addLog(kind === 'error' ? 'error' : kind === 'warn' ? 'warn' : 'info', msg, true);
  const t = document.createElement('div');
  t.className = 'toast ' + kind; t.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const icon = { error: '&#10007;', ok: '&#10003;', warn: '&#9888;', info: '&#9432;' }[kind] || '';
  t.innerHTML = `<span aria-hidden="true">${icon}</span><span class="msg">${esc(msg)}</span><button type="button" aria-label="Dismiss">&times;</button>`;
  const close = () => t.remove();
  t.querySelector('button').onclick = close;
  $('#toasts').appendChild(t);
  while ($('#toasts').children.length > 5) $('#toasts').firstChild.remove();
  setTimeout(close, kind === 'error' ? 10000 : 5000);
}
function addLog(level, text, local) {
  S.applog.push({ level, text, local: !!local, at: new Date() });
  if (S.applog.length > 500) S.applog.shift();
  raf(renderAppLog);
}
function renderAppLog() {
  const el = $('#appLog'); if (!el) return;
  const stick = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  el.innerHTML = S.applog.map(l => `<div class="lvl-${esc(l.level)}">${l.at.toTimeString().slice(0, 8)} ${{ error: '&#10007;', warn: '&#9888;', info: '&middot;' }[l.level] || '&middot;'} ${esc(l.text)}</div>`).join('');
  if (stick) el.scrollTop = el.scrollHeight;
}

/* ---------- modal ---------- */
function modal({ title, body, buttons, onOpen }) {
  return new Promise(resolve => {
    const prev = document.activeElement;
    const ov = document.createElement('div'); ov.className = 'overlay';
    ov.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3><div class="mbody">${body}</div><div class="actions"></div></div>`;
    const acts = $('.actions', ov);
    const done = v => { ov.remove(); if (prev && prev.focus) prev.focus(); resolve(v); };
    const btns = buttons.map(b => {
      const el = document.createElement('button'); el.type = 'button'; el.textContent = b.label;
      if (b.kind) el.className = b.kind; if (b.disabled) el.disabled = true;
      el.onclick = () => done(b.value); acts.appendChild(el); return el;
    });
    ov.style.paddingTop = ($('#head').offsetHeight + 16) + 'px';
    $('#modalRoot').appendChild(ov);
    if (onOpen) onOpen(ov, btns);
    const first = $('input,button:not(:disabled)', ov); if (first) first.focus();
  });
}
const confirmDialog = (title, bodyHtml, okLabel = 'Confirm', kind = 'primary') =>
  modal({ title, body: bodyHtml, buttons: [{ label: 'Cancel', value: false }, { label: okLabel, value: true, kind }] });
const infoDialog = (title, bodyHtml) => modal({ title, body: bodyHtml, buttons: [{ label: 'Close', value: true, kind: 'primary' }] });
function confirmMotion(what) {
  return modal({
    title: 'Confirm robot movement',
    body: `<p>${what}</p><label class="checkrow"><input type="checkbox" id="chkClear" aria-label="I am next to the robot and about 1 m around it is clear"> <span>I am next to the robot and about 1 m around it is clear</span></label>
           <p class="dim small">Stay close and keep the E-STOP in reach (Esc or Space).</p>`,
    buttons: [{ label: 'Cancel', value: false }, { label: 'Start moving', value: true, kind: 'primary', disabled: true }],
    onOpen: (ov, btns) => { const c = $('#chkClear', ov); c.onchange = () => { btns[1].disabled = !c.checked; }; },
  });
}

/* ---------- e-stop ---------- */
function renderTree(v) {
  if (v === null || v === undefined) return '<span class="dim">–</span>';
  if (typeof v !== 'object') return esc(String(v));
  return '<ul class="steps">' + Object.entries(v).map(([k, x]) => {
    const ok = x && typeof x === 'object' && 'success' in x ? (x.success ? tag('ok', 'ok') : tag('bad', 'failed')) : '';
    return `<li><strong>${esc(k)}</strong> ${ok} ${typeof x === 'object' && x ? '<div class="kv">' + renderTree(x) + '</div>' : esc(String(x))}</li>`;
  }).join('') + '</ul>';
}
let estopBusy = false;
async function doEstop() {
  if (estopBusy) return; estopBusy = true;
  S.estopLocal = true; renderEstop();
  try {
    const j = await api('/api/estop', {});
    const ok = j.ok !== false;
    addLog(ok ? 'warn' : 'error', 'E-stop sent' + (ok ? '' : ': ' + (j.error || 'failed')), true);
    const rest = { ...j }; delete rest.ok; delete rest.error;
    infoDialog(ok ? 'E-stop sent' : 'E-stop may have FAILED',
      (ok ? '<p>Drive motors should be off. Check the robot is stopped.</p>' : `<div class="note bad">${esc(j.error || 'The e-stop request failed.')} Hold the robot or switch off its power if it still moves.</div>`) +
      '<h3 style="margin-top:10px">Steps</h3>' + renderTree(rest.steps || rest));
  } finally { estopBusy = false; }
}
async function releaseEstop() {
  const ok = await confirmDialog('Release e-stop?', '<p>This turns drive power back on. Only release when the area around the robot is clear and the cause is fixed.</p>', 'Release e-stop', 'danger');
  if (!ok) return;
  const j = await bridge('estop_release');
  if (j.ok) { S.estopLocal = false; notify('ok', 'E-stop released'); }
  renderEstop();
}
function estopOn() { return S.estopLocal || (S.status && S.status.estop && S.status.estop.on === true); }
function renderEstop() { $('#bannerEstop').classList.toggle('hidden', !estopOn()); }

document.addEventListener('keydown', e => {
  if (e.repeat) return;
  if (e.ctrlKey && e.shiftKey && (e.key === 'E' || e.key === 'e')) { e.preventDefault(); doEstop(); return; } // works everywhere, also in the editor
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target, typing = t.closest && t.closest('input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable="true"]');
  if (typing) return; // in text fields and the code editor Esc and Space do nothing special
  if (e.key === 'Escape') { e.preventDefault(); doEstop(); }
  else if (e.key === ' ' && !(t.closest && t.closest('button,a,summary,[role=tab],input'))) { e.preventDefault(); doEstop(); }
});

/* ---------- connection ---------- */
function connHint(c) { // connection errors the setup wizard can fix
  const e = c.error || '', kind = c.kind || (/key not set up|permission denied/i.test(e) ? 'key_not_set_up' : /host key|identification has changed|not the trusted/i.test(e) ? 'host_key' : /no ssh|ssh.*not found|cannot find.*ssh/i.test(e) ? 'no_ssh' : '');
  if (kind === 'key_not_set_up') return { kind, title: '&#9888; Key not set up.', text: 'The robot did not accept this computer\'s key yet. Use Set up key login: a terminal window opens and you type the robot password there (never in this app).' };
  if (kind === 'host_key') return { kind, title: '&#9888; Robot identity not trusted.', text: 'The robot\'s identity key is not one you trusted, or it changed. The setup wizard shows its fingerprint so you can compare and trust it.' };
  if (kind === 'no_ssh') return { kind, title: '&#9888; ssh not found.', text: 'Studio needs the ssh program on this computer. The setup wizard shows how to install it.' };
  return null;
}
function renderConn() {
  const c = S.conn, pill = $('#connPill');
  const map = { connected: ['ok', '&#10003; Connected'], connecting: ['warn', '&#8987; Connecting'], reconnecting: ['warn', '&#8987; Reconnecting'], discovering: ['warn', '&#8987; Searching'], error: ['bad', '&#10007; Error'], disconnected: ['', 'Disconnected'] };
  const [cls, label] = map[c.state] || ['', c.state];
  pill.className = 'pill ' + cls;
  pill.innerHTML = label + (c.host ? ` &middot; <span class="mono">${esc(c.host)}</span>` : '') + (c.via ? ` (${esc(c.via)})` : '');
  $('#btnConnect').disabled = ['connected', 'connecting', 'discovering'].includes(c.state);
  $('#btnDisconnect').disabled = c.state === 'disconnected';
  $('#connDetail').textContent = c.error || '';
  $('#btnDiagErr').classList.toggle('hidden', !(c.state === 'error' || (c.state === 'disconnected' && c.error)));
  renderReconn();
  const hint = c.state === 'error' ? connHint(c) : null;
  $('#keyHint').classList.toggle('hidden', !hint);
  if (hint) { $('#keyHintTitle').innerHTML = hint.title; $('#keyHintText').textContent = hint.text; $('#btnKeyHint').classList.toggle('hidden', hint.kind !== 'key_not_set_up'); }
  renderMotionButtons();
}
function renderCands() {
  const has = S.cands.length > 0;
  $('#candWrap').classList.toggle('hidden', !has); $('#candEmpty').classList.toggle('hidden', has);
  $('#candBody').innerHTML = S.cands.map((c, i) => `<tr><td class="mono">${esc(c.host)}${candBadge(c)}</td><td>${esc(c.via)}</td>
    <td>${c.reachable ? tag('ok', 'Reachable') : tag('bad', 'No answer')}</td><td class="num">${c.ms == null ? '–' : Math.round(c.ms)}</td>
    <td><button type="button" class="small${c.identity === 'confirmed' ? ' primary' : ''}" data-cand="${i}" aria-label="Connect to ${esc(c.host)}" ${c.reachable ? '' : 'title="Did not answer on port 22"'}>Connect</button></td></tr>`).join('');
}
const candBadge = c => c.identity === 'confirmed' ? ' <span class="badge-ok">&#10003; Your robot (identity confirmed)</span>' : c.label ? ` <span class="dim">${esc(c.label)}</span>` : '';
async function doDiscover() {
  const j = await call('/api/discover', {}, { what: 'Discover' });
  if (j.ok && j.candidates) { S.cands = j.candidates; renderCands(); }
}
/* v1.3: search the whole network (explicit button; progress comes as deep_progress events) */
function renderDeep() {
  const d = S.deep, pct = d.total ? Math.min(100, Math.round(100 * d.done / d.total)) : 0;
  $('#deepWrap').classList.toggle('hidden', !d.running);
  $('#deepBar').style.width = pct + '%';
  $('#deepText').textContent = d.running ? (d.total ? `Checking addresses: ${d.done} of ${d.total}` : 'Starting…') : '';
  $('#btnDeep').disabled = d.running;
  if (W.open && W.render) W.render();
}
async function doDeepDiscover() {
  if (S.deep.running) return null;
  S.deep = { running: true, done: 0, total: 0 }; renderDeep();
  const j = await call('/api/deep_discover', {}, { what: 'Search the whole network' });
  S.deep.running = false; renderDeep();
  if (j.ok && j.candidates) {
    S.cands = j.candidates; renderCands();
    const mine = j.candidates.find(c => c.identity === 'confirmed');
    if (mine) notify('ok', 'Found your robot at ' + mine.host + ' (identity confirmed)');
    else notify('info', j.candidates.length ? 'Found ' + j.candidates.length + ' device(s) with ssh, but none is confirmed as your robot. Check the address on the robot\'s screen.' : 'No device with ssh answered on this network.');
  }
  return j;
}
async function doConnect(host) {
  host = host || $('#hostInput').value.trim();
  const j = await call('/api/connect', host ? { host } : {}, { what: 'Connect' });
  return j;
}

/* v1.3: automatic reconnect banner (the server counts the backoff, this only shows it) */
function renderReconn() {
  const c = S.conn, on = c.state === 'reconnecting';
  $('#bannerReconn').classList.toggle('hidden', !on);
  if (!on) return;
  const r = S.reconn || { since: Date.now() / 1000, attempt: c.attempt || 1, nextAt: performance.now() };
  const at = new Date(r.since * 1000).toTimeString().slice(0, 5), left = Math.max(0, Math.ceil((r.nextAt - performance.now()) / 1000));
  $('#reconnText').textContent = `Connection lost at ${at}. Reconnecting (attempt ${r.attempt}, ${left ? 'next in ' + left + ' s' : 'trying now'}).`;
}

/* ---------- status / dashboard ---------- */
function battState(b) {
  const cur = b.current_a, amps = cur == null ? '' : ' (' + (cur < 0 ? '−' : '') + Math.abs(cur).toFixed(2) + ' A)';
  if (b.full) return tag('ok', 'Full');
  if (b.charging === true) return tag('ok', 'Charging' + amps);
  if (cur != null && cur < 0) return tag('dim', 'On battery' + amps);
  if (b.charging === false) return tag('dim', 'Not charging' + amps);
  return tag('dim', 'Unknown');
}
function renderDash() {
  const st = S.status; if (!st) { renderMotionButtons(); return; }
  const b = st.battery || {}, d = st.dock || {}, o = st.odom || {}, sc = st.scan || {}, sy = st.system || {}, n = st.net || {}, cl = st.clock || {};
  const pct = b.percent;
  $('#battBar').style.width = (pct == null ? 0 : Math.max(0, Math.min(100, pct))) + '%';
  $('#battBar').className = pct != null && pct < 20 ? 'low' : '';
  $('#rowsBatt').innerHTML = rows([
    ['Charge', pct == null ? txt(null) : `<strong>${Math.round(pct)}&nbsp;%</strong>` + (pct < 20 ? ' ' + tag('bad', 'low') : '')],
    ['Voltage', num(b.voltage, 2, 'V')],
    ['Power', battState(b)],
    ['Current', b.current_a == null ? txt(null) : num(b.current_a, 2, 'A')],
  ]);
  $('#rowsDock').innerHTML = rows([
    ['Docked', yesNo(d.is_docked, 'Docked', 'Undocked')],
    ['Dock visible', yesNo(d.dock_visible)],
    ['E-stop', st.estop && st.estop.on ? tag('bad', 'ON') : st.estop && st.estop.on === false ? tag('ok', 'Off') : tag('dim', 'unknown')],
  ]);
  const age = o.age_s, ageBad = age != null && age > 0.5;
  $('#rowsPose').innerHTML = rows([
    ['Position x / y', `${num(o.x, 2)} / ${num(o.y, 2)}&nbsp;m`],
    ['Heading', num(o.yaw_deg, 0, '°')],
    ['Speed', `${num(o.vx, 2, 'm/s')} &middot; ${num(o.wz, 2, 'rad/s')}`],
    ['Odometry rate', num(o.rate_hz, 1, 'Hz')],
    ['Odometry age', age == null ? txt(null) : ageBad ? tag('bad', age.toFixed(2) + ' s old') : tag('ok', age.toFixed(2) + ' s')],
  ]);
  const hz = st.hazards || [];
  $('#rowsScan').innerHTML = rows([
    ['Nearest ahead', num(sc.front_m, 2, 'm')],
    ['Nearest any', num(sc.min_m, 2, 'm')],
    ['Lidar rate', sc.rate_hz == null ? tag('warn', 'off') : num(sc.rate_hz, 1, 'Hz')],
    ['Hazards', hz.length ? hz.map(h => tag('bad', h)).join(' ') : tag('ok', 'none')],
  ]);
  const lidarOff = d.is_docked === false && sc.rate_hz == null;
  const lh = $('#lidarHint');
  lh.classList.toggle('hidden', !(lidarOff || (d.is_docked === true && sc.rate_hz == null)));
  lh.innerHTML = lidarOff
    ? `<strong>&#9888; Lidar off.</strong> No scan data while undocked. <div class="row" style="margin-top:6px"><button type="button" class="small" id="btnLidar">Start lidar motor</button></div>`
    : '<span class="dim">The lidar is off while the robot is docked. This is normal.</span>';
  const ad = n.addresses || {};
  $('#rowsNet').innerHTML = rows([
    ['Mode', n.wifi_mode ? tag(n.wifi_mode === 'down' ? 'bad' : 'ok', n.wifi_mode) : txt(null)],
    ['SSID', txt(n.ssid)],
    ['Signal', n.signal_dbm == null ? txt(null) : `${n.signal_dbm}&nbsp;dBm` + (n.link_quality != null ? ` (${n.link_quality})` : '')],
    ['Addresses', Object.keys(ad).length ? Object.entries(ad).map(([k, v]) => `<span class="mono">${esc(k)} ${esc(v)}</span>`).join('<br>') : txt(null)],
    ['Wi-Fi power save', txt(n.powersave ?? n.powersave_students)],
  ]);
  const thr = sy.throttled;
  $('#rowsSys').innerHTML = rows([
    ['CPU', num(sy.cpu_pct, 0, '%') + ' &middot; load ' + num(sy.load1, 2)],
    ['Temperature', sy.temp_c == null ? txt(null) : (sy.temp_c > 75 ? tag('bad', sy.temp_c.toFixed(1) + ' °C') : sy.temp_c > 65 ? tag('warn', sy.temp_c.toFixed(1) + ' °C') : sy.temp_c.toFixed(1) + '&nbsp;°C')],
    ['Throttled', thr == null ? txt(null) : (thr === '0x0' ? tag('ok', 'No') : tag('warn', thr))],
    ['Memory', sy.mem_total_mb ? `${Math.round(sy.mem_used_mb)} / ${Math.round(sy.mem_total_mb)}&nbsp;MB` : txt(null)],
    ['Disk free', num(sy.disk_free_gb, 1, 'GB')],
    ['Uptime', esc(fmtUptime(sy.uptime_s))],
    ['ROS service', st.ros_service ? (st.ros_service === 'active' ? tag('ok', st.ros_service) : tag('bad', st.ros_service)) : txt(null)],
  ]);
  const cw = $('#clockWarn'), bad = cl.synced === false || (cl.year != null && cl.year < 2026);
  cw.classList.toggle('hidden', !bad);
  if (bad) cw.innerHTML = `<strong>&#9888; Robot clock looks wrong</strong> (${cl.synced === false ? 'not synced' : 'synced'}, year ${esc(cl.year)}). Log times and file timestamps will be off.`;
  renderMotionButtons();
}
function renderMotionButtons() {
  const ok = connected(), d = S.status && S.status.dock ? S.status.dock : {};
  $('#btnUndock').disabled = !ok || d.is_docked === false;
  $('#btnDock').disabled = !ok || d.is_docked === true;
  $('#btnHealth').disabled = !ok;
}
function tickStale() {
  const age = S.statusAt ? (performance.now() - S.statusAt) / 1000 : Infinity;
  const stale = age > 3 || !connected();
  $$('.card.live').forEach(c => c.classList.toggle('stale', stale));
}

async function doAction(cmd, label) {
  const ok = await confirmMotion(`<strong>${label}</strong>. The robot will move by itself. Is the area clear?`);
  if (!ok) return;
  const j = await bridge(cmd, { confirmed: true });
  if (j.ok) notify('info', label + ' started');
}
async function doHealth() {
  $('#healthOut').innerHTML = 'Running&hellip;';
  const j = await bridge('health');
  if (!j.ok) { $('#healthOut').innerHTML = tag('bad', 'Health check failed: ' + (j.error || '')); return; }
  const c = j.checks || [];
  $('#healthOut').innerHTML = `<div class="scroll"><table aria-label="Health check results"><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>` +
    c.map(x => `<tr><td>${esc(x.name)}</td><td>${x.ok === true ? tag('ok', 'OK') : x.ok === false ? tag('bad', 'Problem') : tag('dim', 'Unknown')}</td><td>${esc(x.detail || '')}</td></tr>`).join('') + '</tbody></table></div>';
}

/* ---------- programs ---------- */
async function loadPrograms() {
  $('#progDir').textContent = remoteDir();
  if (!connected()) { renderPrograms(); renderCodeFiles(); return; }
  const j = await bridge('ls', { dir: remoteDir() });
  if (j.ok) { S.files = (j.files || []).filter(f => !f.is_dir && /\.(py|sh)$/.test(f.name)).sort((a, b) => a.name.localeCompare(b.name)); renderPrograms(); renderCodeFiles(); }
  loadDescribe();
}
async function loadDescribe() {
  if (!connected()) return;
  const j = await bridge('describe', { dir: remoteDir() }, { quiet: true });
  if (j.ok) { S.desc = {}; (j.programs || []).forEach(p => { S.desc[p.name] = p; }); renderPrograms(); }
}
async function loadCatalog() {
  const c = await api('/api/catalog');
  if (c && c.ok !== false && c.programs) S.catalog = { programs: c.programs || {}, templates: c.templates || [] };
  renderPrograms();
}
const badge = (kind, text) => '<span class="badge ' + kind + '">' + text + '</span>';
function progDetails(f, c, d) {
  let h = '';
  if (!c) h += '<p style="margin:4px 0">This is not one of Studio\'s ready-made programs. Below is what the file says about itself.</p>';
  if (c) {
    if (c.args && c.args.length) h += '<h4>What you can type in the arguments box</h4><table aria-label="Arguments"><thead><tr><th>Argument</th><th>Meaning</th></tr></thead><tbody>' +
      c.args.map(x => '<tr><td class="mono">' + esc(x.name) + '</td><td>' + esc(x.help) + '</td></tr>').join('') + '</tbody></table>';
    if (c.examples && c.examples.length) h += '<h4>Examples (click one to fill the box)</h4>' +
      c.examples.map((x, j) => '<button type="button" class="small exbtn" data-ex="' + f.idx + ':' + j + '"><code>' + esc(x.args) + '</code> &mdash; ' + esc(x.what) + '</button>').join('');
    if (c.stop) h += '<h4>How to stop it</h4><div>' + esc(c.stop) + '</div>';
    if (c.notes && c.notes.length) h += '<h4>Good to know</h4><ul class="plain" style="margin:0">' + c.notes.map(n => '<li>' + esc(n) + '</li>').join('') + '</ul>';
    if (c.doc) h += '<h4>More</h4><div>' + (/^https?:\/\//.test(c.doc) ? '<a href="' + esc(c.doc) + '" target="_blank" rel="noopener noreferrer">More in the docs</a>' : 'More in the docs: <code>' + esc(c.doc) + '</code>') + '</div>';
  }
  if (d) {
    if (d.docstring && (!c || !(c.summary || '').includes(d.docstring.slice(0, 40)))) h += '<h4>Written in the file on the robot</h4><pre>' + esc(d.docstring) + '</pre>';
    if (!c && d.usage && d.usage.length) h += '<h4>Options found in the file</h4><pre>' + esc(d.usage.join('\n')) + '</pre>';
    if (!c && d.moves_detected) h += '<h4>Why we think it moves the robot</h4><div>It mentions: ' + esc((d.moves_reasons || []).join(', ')) + '. Studio will ask you to confirm before running it.</div>';
  }
  if (!h) h = '<div class="dim">No description yet.</div>';
  return h;
}
function renderPrograms() {
  $('#progEmpty').classList.toggle('hidden', S.files.length > 0);
  $('#progEmpty').textContent = connected() ? 'No .py or .sh files found in this folder.' : 'Connect to list programs.';
  const focus = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.args : undefined;
  $('#progBody').innerHTML = S.files.map((f, i) => {
    f.idx = i;
    const c = S.catalog.programs[f.name] || null, d = S.desc[f.name] || null, mot = isMotion(f.name), helper = c && c.category === 'helper';
    const bd = [];
    if (helper) bd.push(badge('dim', 'helper, not run directly'));
    else {
      if (mot) bd.push(badge('', '&#9888; moves the robot' + (!c && d && d.moves_detected ? ' (detected)' : '')));
      if (c && c.safe_on_dock) bd.push(badge('ok', '&#10003; safe on the dock'));
      if (c && c.needs_undock) bd.push(badge('', 'undock first'));
      if (!c) bd.push(badge('dim', 'your own program'));
    }
    const builtin = MOTION_DEFAULT.includes(f.name) || (c && c.moves);
    return '<div class="prog"><div class="prow"><span class="ptitle">' + esc(c ? c.title : f.name) + '</span>' + bd.join(' ') + '</div>' +
      '<div class="pfile">' + esc(f.name) + '</div>' +
      (c && c.summary ? '<div class="psum">' + esc(c.summary) + '</div>' : '') +
      '<div class="prow"><input type="text" data-args="' + i + '" value="' + esc(S.args[f.name] || '') + '" placeholder="arguments (optional)" aria-label="Arguments for ' + esc(f.name) + '" autocomplete="off">' +
      '<button type="button" class="small primary" data-run="' + i + '" aria-label="Run ' + esc(f.name) + '" ' + (connected() && !helper ? '' : 'disabled') + '>Run</button>' +
      (builtin || helper ? '' : '<label class="small dim"><input type="checkbox" data-mark="' + i + '" ' + (mot ? 'checked' : '') + ' aria-label="Mark ' + esc(f.name) + ' as moving the robot"> it moves the robot</label>') + '</div>' +
      '<details data-det="' + esc(f.name) + '" ' + (S.open[f.name] ? 'open' : '') + '><summary>What does it do?</summary>' + progDetails(f, c, d) + '</details></div>';
  }).join('');
  if (focus !== undefined) { const el = $('[data-args="' + focus + '"]'); if (el) el.focus(); }
}
async function runProgram(name, argStr, opts = {}) {
  let args; try { args = splitArgs(argStr || ''); } catch (e) { notify('error', e.message); return null; }
  const motion = isMotion(name);
  if (motion) {
    const ok = await confirmMotion(`<strong>${esc(name)}</strong> moves the robot${args.length ? ' with arguments <code>' + esc(args.join(' ')) + '</code>' : ''}.`);
    if (!ok) return null;
  }
  if (!S.catalog.programs[name] && !S.desc[name]) await loadDescribe();
  const j = await bridge('run', { path: name, dir: remoteDir(), args, motion: isMotion(name), confirmed: motion ? true : false });
  if (j.ok && j.run_id) {
    const r = ensureRun(j.run_id); r.name = name; r.pid = j.pid; r.alive = true; r.log = j.log;
    S.selRun = j.run_id; renderRuns(); renderLog(); notify('ok', `Started ${name}`);
  }
  return j;
}
function ensureRun(id) { return S.runs[id] || (S.runs[id] = { id, name: id, lines: [], alive: true, code: null, pid: null }); }
function renderRuns() {
  const list = Object.values(S.runs).sort((a, b) => (b.started || 0) - (a.started || 0));
  $('#runEmpty').classList.toggle('hidden', list.length > 0);
  $('#btnStopAll').disabled = !list.some(r => r.alive);
  $('#runBody').innerHTML = list.map(r => `<tr class="${r.id === S.selRun ? 'sel' : ''}"><td class="mono">${esc(r.name)} ${r.motion ? '<span class="badge">&#9888; moves</span>' : ''}</td>
    <td>${r.alive ? tag('ok', 'Running') : tag('dim', 'Finished' + (r.code != null ? ' (exit ' + r.code + ')' : ''))}</td><td class="num">${esc(r.pid ?? '–')}</td>
    <td><button type="button" class="small" data-viewrun="${esc(r.id)}" aria-label="Show log of ${esc(r.name)}">Log</button>
    <button type="button" class="small danger" data-stoprun="${esc(r.id)}" aria-label="Stop ${esc(r.name)}" ${r.alive ? '' : 'disabled'}>Stop</button></td></tr>`).join('');
}
function renderLog() {
  const r = S.runs[S.selRun], el = $('#logView');
  $('#logTitle').textContent = r ? r.name : '';
  if (!r) { el.textContent = 'Select a run to see its output.'; return; }
  el.textContent = r.lines.length ? r.lines.join('\n') : (r.alive ? '(waiting for output)' : '(no output)');
  if ($('#autoScroll').checked) el.scrollTop = el.scrollHeight;
  renderCodeLog();
}
function onRunOutput(ev) {
  const r = ensureRun(ev.run_id);
  r.lines.push(...(ev.lines || []));
  if (r.lines.length > MAX_LINES) r.lines.splice(0, r.lines.length - MAX_LINES);
  if (!S.selRun) S.selRun = ev.run_id;
  if (S.selRun === ev.run_id) raf(renderLog);
}
function mergeRuns(list) {
  let changed = false;
  for (const x of list || []) {
    const r = ensureRun(x.run_id);
    const next = { name: x.name || r.name, pid: x.pid, alive: !!x.alive, started: x.started_wall, motion: !!x.motion };
    for (const k in next) if (r[k] !== next[k]) { r[k] = next[k]; changed = true; }
  }
  if (changed) raf(renderRuns);
}
async function stopRun(id) {
  const j = await bridge('stop', { run_id: id });
  if (j.ok) notify('info', 'Stop sent' + (j.stopped && j.stopped.length ? ` (${j.stopped.length} run${j.stopped.length > 1 ? 's' : ''})` : ''));
}

/* ---------- files ---------- */
const LOCAL_DIR = () => $('#localDir').value.trim();
async function saveSettingsPatch(patch) { // sends only the changed keys (trusted keys and addresses are managed by the server)
  const j = await call('/api/settings', patch, { what: 'Save settings' });
  if (j.ok) { if (j.settings) takeSettings(j); else S.settings = { ...S.settings, ...patch }; }
  return j;
}
async function compareFiles() {
  const dir = LOCAL_DIR();
  if (!dir) { notify('warn', 'Enter a local folder first'); return; }
  const [l, r] = await Promise.all([
    call('/api/local_files', { dir }, { what: 'Local files' }),
    connected() ? bridge('ls', { dir: $('#remoteDir').value.trim() || remoteDir(), recursive: true }) : Promise.resolve({ ok: true, files: [], offline: true }),
  ]);
  S.local = l.ok ? (l.files || []).filter(f => !f.is_dir) : null;
  S.remote = r.ok ? (r.files || []).filter(f => !f.is_dir) : null;
  if (!connected()) notify('warn', 'Not connected: showing local files only');
  renderCompare();
}
function compareRows() {
  const L = new Map((S.local || []).map(f => [f.name, f])), R = new Map((S.remote || []).map(f => [f.name, f]));
  const names = [...new Set([...L.keys(), ...R.keys()])].sort();
  return names.map(n => {
    const a = L.get(n), b = R.get(n); let st;
    if (a && !b) st = 'new'; else if (!a && b) st = 'robot only';
    else if (a.sha1 && b.sha1) st = a.sha1 === b.sha1 ? 'same' : 'changed';
    else st = a.size === b.size ? 'same' : 'changed';
    return { name: n, st, a, b };
  });
}
function renderCompare() {
  const list = compareRows();
  $('#cmpEmpty').classList.toggle('hidden', list.length > 0);
  const stTag = { same: tag('ok', 'Same'), changed: tag('warn', 'Changed'), new: tag('warn', 'New (only here)'), 'robot only': tag('dim', 'Robot only') };
  $('#cmpBody').innerHTML = list.map((x, i) => {
    const runnable = /\.(py|sh)$/.test(x.name) && x.st !== 'robot only' || (/\.(py|sh)$/.test(x.name) && x.b);
    return `<tr class="${S.selFile === x.name ? 'sel' : ''}"><td>${runnable ? `<input type="radio" name="selfile" data-sel="${i}" ${S.selFile === x.name ? 'checked' : ''} aria-label="Select ${esc(x.name)} for Sync and run">` : ''}</td>
      <td class="mono">${esc(x.name)}</td><td>${stTag[x.st]}</td><td class="num">${fmtSize(x.a && x.a.size)}</td><td class="num">${fmtSize(x.b && x.b.size)}</td></tr>`;
  }).join('');
  const cnt = k => list.filter(x => x.st === k).length;
  $('#cmpSummary').textContent = list.length ? `${cnt('same')} same, ${cnt('changed')} changed, ${cnt('new')} new, ${cnt('robot only')} robot only` : '';
}
async function doSync(direction, dry) {
  const body = { local_dir: LOCAL_DIR(), remote_dir: $('#remoteDir').value.trim() || remoteDir(), direction, delete: false, dry_run: !!dry };
  if (!body.local_dir) { notify('warn', 'Enter a local folder first'); return null; }
  if (direction === 'down' && !dry) {
    const ok = await confirmDialog('Download from the robot?', '<p>Files from the robot overwrite files with the same name in your local folder. Use <em>Preview</em> first if unsure.</p>', 'Download');
    if (!ok) return null;
  }
  showSync({ state: 'running', uploaded: [], skipped: 0, deleted: [] }, dry);
  const j = await call('/api/sync', body, { what: dry ? 'Preview' : 'Sync' });
  if (dry) showSync({ state: j.ok ? 'preview' : 'error', ...j }, true);
  else if (j.ok) { showSync({ state: 'done', ...j }); compareFiles(); loadPrograms(); }
  else showSync({ state: 'error', error: j.error });
  return j;
}
function showSync(e, dry) {
  $('#syncCard').classList.remove('hidden');
  const label = { running: tag('warn', 'Working…'), done: tag('ok', 'Done'), error: tag('bad', 'Error'), preview: tag('ok', 'Preview (nothing changed)') }[e.state] || esc(e.state);
  const up = e.uploaded || e.would_upload || [], del = e.deleted || e.would_delete || [];
  const dir = e.direction === 'down' ? 'Downloaded' : 'Uploaded';
  $('#syncOut').innerHTML = `<div class="row">${label}</div>
    ${e.error ? `<div class="note bad">${esc(e.error)}</div>` : ''}
    <div class="small" style="margin-top:6px">${e.state === 'preview' ? 'Would transfer' : dir}: <strong>${up.length}</strong> file(s), skipped (already same): <strong>${e.skipped ?? 0}</strong>${del.length ? `, would delete: <strong>${del.length}</strong>` : ''}</div>
    ${up.length ? '<pre class="log" style="height:auto;max-height:140px;margin-top:6px">' + esc(up.join('\n')) + '</pre>' : ''}`;
}
async function syncAndRun() {
  if (!S.selFile) { notify('warn', 'Select a file in the table first (radio button)'); return; }
  const j = await doSync('up', false);
  if (!j || !j.ok) return;
  const argStr = S.args[S.selFile.split('/').pop()] || '';
  const r = await runProgram(S.selFile, argStr);
  if (r && r.ok) $('#tab-prog').click();
}

/* ---------- topics ---------- */
async function loadTopics() {
  const j = await bridge('topics');
  if (j.ok) { S.topics = (j.topics || []).sort((a, b) => a.name.localeCompare(b.name)); renderTopics(); }
}
function renderTopics() {
  const f = $('#topicFilter').value.trim().toLowerCase();
  const list = S.topics.filter(t => !f || t.name.toLowerCase().includes(f) || (t.types || []).join(' ').toLowerCase().includes(f));
  $('#topicEmpty').classList.toggle('hidden', S.topics.length > 0);
  const full = Object.keys(S.watches).length >= 4, watched = new Set(Object.values(S.watches).map(w => w.topic));
  $('#topicBody').innerHTML = list.map(t => `<tr><td class="mono">${esc(t.name)}</td><td class="small dim mono">${esc((t.types || []).join(', '))}</td><td class="num">${t.publishers ?? ''}</td>
    <td><button type="button" class="small" data-watch="${esc(t.name)}" aria-label="Watch ${esc(t.name)}" ${full || watched.has(t.name) ? 'disabled' : ''}>${watched.has(t.name) ? 'Watching' : 'Watch'}</button></td></tr>`).join('');
}
async function watchTopic(topic) {
  if (Object.keys(S.watches).length >= 4) { notify('warn', 'At most 4 topics can be watched at once'); return; }
  const j = await bridge('watch', { topic, max_hz: 5 });
  if (j.ok && j.watch_id != null) { const w = S.watches[j.watch_id] || (S.watches[j.watch_id] = { id: j.watch_id, data: null, rate: null }); w.topic = topic; renderWatches(); renderTopics(); }
}
async function unwatch(id) {
  const j = await bridge('unwatch', { watch_id: +id });
  if (j.ok || /unknown|not found/i.test(j.error || '')) { delete S.watches[id]; renderWatches(); renderTopics(); }
}
function renderWatches() {
  const ids = Object.keys(S.watches);
  $('#watchEmpty').classList.toggle('hidden', ids.length > 0);
  $('#watchCount').textContent = ids.length + ' / 4';
  const list = $('#watchList');
  for (const id of ids) {
    let el = list.querySelector(`[data-wid="${CSS.escape(id)}"]`);
    if (!el) {
      el = document.createElement('div'); el.className = 'watch'; el.dataset.wid = id;
      el.innerHTML = `<div class="row"><strong class="mono" data-w="t"></strong><span class="dim small" data-w="r"></span><span class="spacer" style="flex:1"></span><button type="button" class="small" data-unwatch="${esc(id)}">Unwatch</button></div><pre class="json" data-w="d" tabindex="0"></pre>`;
      el.querySelector('button').setAttribute('aria-label', 'Stop watching ' + S.watches[id].topic);
      list.appendChild(el);
    }
    const w = S.watches[id];
    el.querySelector('[data-w=t]').textContent = w.topic || '';
    el.querySelector('[data-w=r]').textContent = w.rate != null ? w.rate.toFixed(1) + ' Hz' : 'waiting…';
    el.querySelector('[data-w=d]').textContent = w.data == null ? '(waiting for first message)' : JSON.stringify(w.data, null, 2);
  }
  for (const el of Array.from(list.children)) if (!S.watches[el.dataset.wid]) el.remove();
}

/* ---------- tools ---------- */
async function openVscode() {
  let j = await call('/api/open_vscode', {}, { quiet: true, what: 'VS Code' });
  if (j.needs_confirm) {
    const ok = await confirmDialog('Add a block to your ssh config?', `<p>VS Code needs this block in your ssh config file (it is only added, nothing existing is changed):</p><pre>${esc(j.preview || '')}</pre>`, 'Add and open');
    if (!ok) return;
    j = await call('/api/open_vscode', { confirm_write_ssh_config: true }, { what: 'VS Code' });
  } else if (!j.ok) notify('error', 'VS Code: ' + (j.error || 'failed'));
  if (j.ok) notify('ok', 'Opening VS Code');
}
const DEFAULTS_FALLBACK = { robot_hostname: 'turtlebot4', robot_user: 'ubuntu', hotspot_ssid: 'Turtlebot4', hotspot_addr: '10.42.0.1', cable_addr: '192.168.185.3' };
const dflt = k => (S.defaults && S.defaults[k]) || DEFAULTS_FALLBACK[k] || '';
const setv = k => S.settings[k] || dflt(k);
const hsName = () => setv('hotspot_ssid');
const sleep = ms => new Promise(r => setTimeout(r, ms));
function takeSettings(j) { // accepts the GET/POST /api/settings answer (plan: settings + defaults + lab_host_key + trusted)
  if (!j || j.ok === false) return;
  if (j.settings) S.settings = j.settings;
  else if (!('settings' in j)) { const o = { ...j }; ['ok', 'defaults', 'lab_host_key', 'trusted'].forEach(k => delete o[k]); S.settings = o; }
  if (j.defaults) S.defaults = j.defaults;
  if (j.lab_host_key !== undefined) S.labKey = j.lab_host_key;
  if (j.trusted) S.trusted = j.trusted;
}
async function loadSettings() {
  const s = await api('/api/settings');
  if (s.ok === false) { notify('error', 'Settings: ' + (s.error || 'cannot load')); return false; }
  takeSettings(s); fillSettings(); return true;
}
function applyNames() { // texts that used to say Turtlebot4 / 10.42.0.1 / 192.168.185.3 / turtlebot4.local
  const hs = hsName(), host = setv('robot_hostname');
  $$('.nmHotspot').forEach(e => { e.textContent = hs; });
  $$('.nmHotspotAddr').forEach(e => { e.textContent = setv('hotspot_addr'); });
  $$('.nmCable').forEach(e => { e.textContent = setv('cable_addr'); });
  $$('.nmMdns').forEach(e => { e.textContent = host + '.local'; });
  $('#btnJoinHotspot').textContent = 'Join ' + hs;
  $('#hostInput').placeholder = 'e.g. ' + setv('hotspot_addr') + ' or ' + host + '.local';
  $('#sHostnameHint').textContent = host + '.local';
  [['#sHostname', 'robot_hostname'], ['#sUser', 'robot_user'], ['#sHsName', 'hotspot_ssid'], ['#sHsAddr', 'hotspot_addr'], ['#sCable', 'cable_addr']].forEach(([id, k]) => { $(id).placeholder = dflt(k); });
}
function renderTrusted() {
  const list = S.trusted || [];
  $('#trustedEmpty').classList.toggle('hidden', list.length > 0);
  $('#trustedBody').innerHTML = list.map((t, i) => {
    const label = t.label || (t.builtin ? 'Built-in key' : 'Unnamed robot');
    return `<tr><td>${esc(label)}${t.builtin ? ' <span class="dim small">(built in)</span>' : ''}</td><td class="mono small">${txt(t.fingerprint)}</td>
      <td><button type="button" class="small danger" data-untrust="${i}" aria-label="Remove ${esc(label)} from the trusted robots">Remove</button></td></tr>`;
  }).join('');
}
async function untrustRobot(i) {
  const t = (S.trusted || [])[i]; if (!t) return;
  const key = t.key || (t.builtin ? S.labKey : null), label = t.label || (t.builtin ? 'Built-in key' : 'Unnamed robot');
  if (!key) { notify('error', 'This entry has no key to remove'); return; }
  const ok = await confirmDialog('Stop trusting this robot?', `<p>Studio will refuse to connect to <strong>${esc(label)}</strong> until you trust it again.</p>${t.fingerprint ? '<p class="mono small">' + esc(t.fingerprint) + '</p>' : ''}`, 'Remove', 'danger');
  if (!ok) return;
  const j = await call('/api/untrust_host_key', { key, confirm: true }, { what: 'Remove trusted robot' });
  if (j.ok) { notify('ok', 'Removed ' + label); await loadSettings(); }
}
async function trustPasted() {
  const key = $('#sTrust').value.trim(), label = $('#sTrustLabel').value.trim() || 'My robot';
  if (!key) { notify('warn', 'Paste the robot key first (a line starting with ssh-ed25519)'); return; }
  const ok = await confirmDialog('Trust this robot key?', '<div class="note warn">Only do this for a TurtleBot that you own. If the key is wrong, someone else could pose as the robot and see everything you send. Compare its fingerprint with the one shown on the robot first.</div>', 'Trust this key', 'danger');
  if (!ok) return;
  const j = await call('/api/trust_host_key', { key, label, confirm: true }, { what: 'Trust key' });
  if (j.ok) { $('#sTrust').value = ''; $('#sTrustLabel').value = ''; notify('ok', 'Trusted ' + label); await loadSettings(); }
}
function fillSettings() {
  const s = S.settings;
  $('#sLastHost').value = s.last_host || ''; $('#sKey').value = s.key_path || ''; $('#sLocal').value = s.local_dir || '';
  $('#sRemote').value = s.remote_dir || '~/robot_code'; $('#sMotion').value = (s.motion_files || []).join('\n');
  $('#sHostname').value = s.robot_hostname || ''; $('#sUser').value = s.robot_user || ''; $('#sHsName').value = s.hotspot_ssid || '';
  $('#sHsAddr').value = s.hotspot_addr || ''; $('#sCable').value = s.cable_addr || '';
  $('#sWindowMode').value = s.window_mode === 'browser' ? 'browser' : 'app';
  $('#sAutoReconnect').checked = s.auto_reconnect !== false; $('#sUpdateCheck').checked = s.update_check !== false;
  if (document.activeElement !== $('#localDir')) $('#localDir').value = s.local_dir || '';
  if (document.activeElement !== $('#remoteDir')) $('#remoteDir').value = s.remote_dir || '~/robot_code';
  if (!$('#hostInput').value && s.last_host) $('#hostInput').value = s.last_host;
  applyNames(); renderTrusted();
}
async function saveSettingsForm(ev) {
  ev.preventDefault();
  const v = (id, k) => $(id).value.trim() || dflt(k);
  const next = { last_host: $('#sLastHost').value.trim(), key_path: $('#sKey').value.trim(), local_dir: $('#sLocal').value.trim(), remote_dir: $('#sRemote').value.trim() || '~/robot_code',
    motion_files: $('#sMotion').value.split('\n').map(x => x.trim()).filter(Boolean),
    robot_hostname: v('#sHostname', 'robot_hostname'), robot_user: v('#sUser', 'robot_user'), hotspot_ssid: v('#sHsName', 'hotspot_ssid'),
    hotspot_addr: v('#sHsAddr', 'hotspot_addr'), cable_addr: v('#sCable', 'cable_addr'),
    window_mode: $('#sWindowMode').value, auto_reconnect: $('#sAutoReconnect').checked, update_check: $('#sUpdateCheck').checked };
  const j = await saveSettingsPatch(next);
  if (j.ok) { takeSettings(j); notify('ok', 'Settings saved'); fillSettings(); renderPrograms(); if (S.wifi || S.laptop) renderWifi(); }
}
function renderAbout() {
  const h = S.hello;
  $('#rowsAbout').innerHTML = rows(h ? [
    ['Robot host', txt(h.hostname)], ['Bridge', txt((h.bridge || '') + ' v' + (h.version || '?') + (h.fake ? ' (fake)' : ''))],
    ['ROS', h.ros ? tag('ok', h.ros_distro || 'yes') : tag('dim', 'not available')], ['RMW', txt(h.rmw)], ['ROS domain', txt(h.domain)],
    ['Python (robot)', txt(h.python)], ['Bridge PID', txt(h.pid)],
  ] : [['Robot', tag('dim', 'not connected')]]);
}

/* ---------- v1.3: diagnostics, update notice ---------- */
async function copyText(text, ta) {
  try { if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* fall back */ }
  try { ta.focus(); ta.select(); return document.execCommand('copy'); } catch (e) { return false; }
}
function saveTextFile(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' })), a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
async function showDiagnostics() {
  const j = await call('/api/diagnostics', undefined, { what: 'Diagnostics' });
  if (!j.ok) return;
  modal({
    title: 'Diagnostics', buttons: [{ label: 'Close', value: true, kind: 'primary' }],
    body: '<p style="margin:0 0 6px">Paste this into your message when you ask for help. Passwords, keys and the session token are removed. Read it once before you send it.</p><div class="row" style="margin-bottom:6px"><button type="button" id="diagCopy" class="primary">Copy</button><button type="button" id="diagSave">Save as file</button></div><textarea id="diagText" class="diagtext" readonly spellcheck="false" aria-label="Diagnostics text"></textarea>',
    onOpen: ov => {
      const ta = $('#diagText', ov); ta.value = j.text;
      $('#diagCopy', ov).onclick = async () => { const ok = await copyText(j.text, ta); notify(ok ? 'ok' : 'warn', ok ? 'Diagnostics copied' : 'Could not copy by itself: select the text and press Ctrl+C'); };
      $('#diagSave', ov).onclick = () => saveTextFile('studio-diagnostics.txt', j.text);
    },
  });
}
const UPDATE_PAGE_OK = u => typeof u === 'string' && u.startsWith('https://github.com/aniskoubaa/alfaisalx_students_projects/');
function renderUpdate() {
  const u = S.update, show = !!(u && u.latest && u.newer !== false && S.settings.update_dismissed !== u.latest);
  $('#bannerUpdate').classList.toggle('hidden', !show);
  if (!show) return;
  $('#updVer').textContent = u.latest;
  if (UPDATE_PAGE_OK(u.page)) $('#updLink').href = u.page;
  $('#bannerUpdate').title = u.notes || '';
}
async function checkUpdates() {
  const out = $('#updResult'); out.textContent = 'Checking…';
  const j = await call('/api/check_updates', { force: true }, { quiet: true });
  out.textContent = '';
  if (!j.ok || j.result === 'failed') { out.textContent = 'Could not check'; return; }
  if (j.result === 'latest') { out.textContent = 'You have the latest version'; return; }
  S.update = j; if (S.settings.update_dismissed) await saveSettingsPatch({ update_dismissed: '' }); renderUpdate();
  out.textContent = 'Version ' + j.latest + ' is available. ';
  const a = document.createElement('a'); a.textContent = 'How to update'; a.target = '_blank'; a.rel = 'noopener';
  if (UPDATE_PAGE_OK(j.page)) a.href = j.page; out.appendChild(a);
}

/* ---------- v1.3: quit ---------- */
function showStopped() {
  S.stopped = true;
  try { es && es.close(); } catch (e) { /* ignore */ }
  clearTimeout(retryTimer); clearInterval(countdown);
  $('#bannerLost').classList.add('hidden'); $('#stopped').classList.remove('hidden');
}
async function quitStudio() {
  if (!await confirmDialog('Quit Studio?', '<p>Studio will close its connection to the robot and stop. Stop any robot program that is running first.</p>', 'Quit Studio', 'danger')) return;
  const j = await call('/api/quit', {}, { what: 'Quit' });
  if (j.ok) showStopped();
}

/* ---------- code editor ---------- */
const C = { name: null, orig: '', sha1: null, dirty: false };
const SKELETON = '#!/usr/bin/env python3\n"""My program. Describe here what it does."""\n\nprint("Hello from the TurtleBot")\n';
const nowStr = () => new Date().toTimeString().slice(0, 8);
const runningOf = name => Object.values(S.runs).filter(r => r.alive && r.name === name);
function updateGutter() {
  const n = $('#editor').value.split('\n').length;
  $('#gutter').textContent = Array.from({ length: n }, (_, i) => i + 1).join('\n');
}
function updateCodeButtons() {
  const open = !!C.name, ok = connected();
  $('#btnCodeSave').disabled = !open || !ok;
  $('#btnCodeRun').disabled = !open || !ok;
  $('#btnCodeRevert').disabled = !open || !C.dirty;
  $('#btnCodeStop').disabled = !open || !runningOf(C.name).length;
}
function setDirty(v) {
  C.dirty = v; $('#codeDirty').classList.toggle('hidden', !v);
  renderCodeFiles(); updateCodeButtons();
}
function renderCodeFiles() {
  const el = $('#codeFiles'); if (!el) return;
  $('#codeFilesEmpty').classList.toggle('hidden', S.files.length > 0);
  $('#codeFilesEmpty').textContent = connected() ? 'No .py or .sh files yet. Press New program.' : 'Connect to see the files on the robot.';
  el.innerHTML = S.files.map((f, i) => '<button type="button" role="listitem" data-open="' + i + '"' + (f.name === C.name ? ' aria-current="true"' : '') + '>' +
    esc(f.name) + (f.name === C.name && C.dirty ? ' <span class="dirty" aria-label="unsaved">&#9679;</span>' : '') + '</button>').join('');
  $('#codeName').textContent = C.name || 'No file open';
  updateCodeButtons();
}
function renderCodeLog() {
  const el = $('#codeLog'); if (!el) return;
  const r = S.runs[S.selRun];
  $('#codeLogTitle').textContent = r ? r.name + (r.alive ? ' (running)' : ' (finished)') : '';
  if (!r) { el.textContent = 'Output appears here when you run the program.'; return; }
  el.textContent = r.lines.length ? r.lines.join('\n') : (r.alive ? '(waiting for output)' : '(no output)');
  el.scrollTop = el.scrollHeight;
  updateCodeButtons();
}
async function openFile(name, force) {
  if (C.dirty && !force && name !== C.name) {
    const ok = await confirmDialog('Leave without saving?', '<p>You have unsaved changes in <strong>' + esc(C.name) + '</strong>. If you open another file they are lost.</p>', 'Discard changes', 'danger');
    if (!ok) return;
  }
  const j = await bridge('read_file', { path: name, dir: remoteDir() });
  if (!j.ok) return;
  C.name = name; C.orig = j.text || ''; C.sha1 = j.sha1 || null;
  const ta = $('#editor'); ta.value = C.orig; ta.disabled = false; ta.scrollTop = 0;
  updateGutter(); $('#codeStatus').textContent = 'Opened from robot'; setDirty(false);
}
async function saveCode() {
  if (!C.name || !connected()) return false;
  const text = $('#editor').value, base = { path: C.name, dir: remoteDir(), text, overwrite: true };
  let j = await bridge('write_file', { ...base, expect_sha1: C.sha1 || undefined }, { quiet: true });
  if (!j.ok && /changed on the robot/i.test(j.error || '')) {
    const ok = await confirmDialog('File changed on the robot', '<p>This file was changed on the robot after you opened it. Saving now replaces that newer version. The newer version is kept as a <code>.bak</code> copy.</p>', 'Save anyway', 'danger');
    if (!ok) return false;
    j = await bridge('write_file', base, { quiet: true });
  }
  if (!j.ok) { notify('error', 'Save failed: ' + (j.error || 'unknown error')); return false; }
  C.sha1 = j.sha1 || C.sha1; C.orig = text; setDirty(false);
  if (j.unchanged) { $('#codeStatus').textContent = 'No changes to save'; notify('info', 'No changes to save'); return true; }
  $('#codeStatus').textContent = 'Saved to robot at ' + nowStr();
  loadDescribe();
  return true;
}
async function saveAndRun() {
  if (!(await saveCode())) return;
  await loadDescribe();
  const j = await runProgram(C.name, $('#codeArgs').value);
  if (j && j.ok) renderCodeLog();
}
async function revertCode() {
  const ok = await confirmDialog('Throw away your changes?', '<p>The editor goes back to the last version saved on the robot.</p>', 'Revert', 'danger');
  if (!ok) return;
  $('#editor').value = C.orig; updateGutter(); setDirty(false);
}
function editorKey(e) {
  const ta = e.target;
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === 's' || e.key === 'S')) { e.preventDefault(); saveCode(); return; }
  if (e.key !== 'Tab' || e.ctrlKey || e.altKey || e.metaKey) return;
  e.preventDefault();
  const v = ta.value, s = ta.selectionStart, en = ta.selectionEnd;
  if (s === en && !e.shiftKey) { ta.setRangeText('    ', s, en, 'end'); }
  else {
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    let le = v.indexOf('\n', en > s && v[en - 1] === '\n' ? en - 1 : en); if (le < 0) le = v.length;
    const lines = v.slice(ls, le).split('\n');
    const out = lines.map(l => e.shiftKey ? l.replace(/^ {1,4}/, '') : '    ' + l);
    const first = out[0].length - lines[0].length, total = out.join('\n').length - (le - ls);
    ta.setRangeText(out.join('\n'), ls, le, 'preserve');
    ta.selectionStart = Math.max(ls, s + first); ta.selectionEnd = en + total;
  }
  ta.dispatchEvent(new Event('input'));
}
const templateList = () => (S.catalog.templates || []).map(t => typeof t === 'string' ? { name: t, entry: S.catalog.programs[t] || {} } : { name: t.name || t.file, entry: t.entry || t }).filter(t => t.name);
async function fetchTemplate(name) {
  try {
    const r = await fetch('/api/templates/' + encodeURIComponent(name), { headers: { 'X-Studio-Token': TOKEN } });
    const t = await r.text();
    if (!r.ok) throw new Error(t.slice(0, 120) || 'HTTP ' + r.status);
    if (t.trim().startsWith('{')) { let j = null; try { j = JSON.parse(t); } catch (e) { /* plain text that starts with a brace */ } if (j && j.ok === false) throw new Error(j.error || 'failed'); if (j && typeof j.text === 'string') return j.text; }
    return t;
  } catch (e) { notify('error', 'Template: ' + e.message); return null; }
}
async function newProgram() {
  const tl = templateList(), pick = { tmpl: tl.length ? 0 : -1, file: '', replace: false };
  const nameFor = i => i >= 0 ? 'my_' + tl[i].name.replace(/^my_/, '') : 'my_program.py';
  pick.file = nameFor(pick.tmpl);
  const sel = tl.map((t, i) => '<option value="' + i + '">' + esc(t.entry.title || t.name) + '</option>').join('') + '<option value="-1">Empty program</option>';
  const body = '<label class="field"><span>Start from</span><select id="npTmpl" aria-label="Template">' + sel + '</select></label><div class="tmplsum" id="npSum"></div>' +
    '<label class="field"><span>File name</span><input id="npName" type="text" autocomplete="off" aria-label="New file name"><span class="hint">Letters, digits, - and _ , ending in .py</span></label>' +
    '<div id="npMsg" class="note warn hidden"></div>';
  const ok = await modal({
    title: 'New program', body, buttons: [{ label: 'Cancel', value: false }, { label: 'Create', value: true, kind: 'primary' }],
    onOpen: (ov, btns) => {
      const t = $('#npTmpl', ov), n = $('#npName', ov), msg = $('#npMsg', ov);
      t.value = String(pick.tmpl); n.value = pick.file;
      const check = () => {
        pick.tmpl = +t.value; pick.file = n.value.trim();
        $('#npSum', ov).textContent = pick.tmpl >= 0 ? (tl[pick.tmpl].entry.summary || '') : 'A tiny file that just prints a line. Good for starting from scratch.';
        const valid = /^[A-Za-z0-9_-]+\.py$/.test(pick.file), exists = S.files.some(f => f.name === pick.file);
        msg.classList.toggle('hidden', valid && !exists);
        if (!valid) msg.innerHTML = 'The name must be letters, digits, <code>-</code> or <code>_</code>, then <code>.py</code> (for example <code>my_spin.py</code>).';
        else if (exists) msg.innerHTML = '<strong>' + esc(pick.file) + '</strong> already exists on the robot.<label class="row" style="margin-top:6px"><input type="checkbox" id="npRep"> Replace it (the old version is kept as .bak)</label>';
        const rep = $('#npRep', ov); if (rep) rep.onchange = () => { pick.replace = rep.checked; check2(); };
        check2();
      };
      const check2 = () => { const valid = /^[A-Za-z0-9_-]+\.py$/.test(pick.file), exists = S.files.some(f => f.name === pick.file); btns[1].disabled = !valid || (exists && !pick.replace); };
      t.onchange = () => { n.value = nameFor(+t.value); pick.replace = false; check(); };
      n.oninput = () => { pick.replace = false; check(); };
      check();
    },
  });
  if (!ok) return;
  const text = pick.tmpl >= 0 ? await fetchTemplate(tl[pick.tmpl].name) : SKELETON;
  if (text === null) return;
  const exists = S.files.some(f => f.name === pick.file);
  const j = await bridge('write_file', { path: pick.file, dir: remoteDir(), text, overwrite: exists });
  if (!j.ok) return;
  notify('ok', 'Created ' + pick.file);
  await loadPrograms();
  openFile(pick.file, false);
}
function wireCode() {
  const ta = $('#editor');
  ta.addEventListener('input', () => { updateGutter(); setDirty(ta.value !== C.orig); });
  ta.addEventListener('scroll', () => { $('#gutter').scrollTop = ta.scrollTop; });
  ta.addEventListener('keydown', editorKey);
  $('#codeFiles').onclick = e => { const b = e.target.closest('[data-open]'); if (b) openFile(S.files[+b.dataset.open].name, false); };
  $('#btnNewProg').onclick = newProgram;
  $('#btnCodeSave').onclick = saveCode; $('#btnCodeRun').onclick = saveAndRun; $('#btnCodeRevert').onclick = revertCode;
  $('#btnCodeStop').onclick = () => runningOf(C.name).forEach(r => stopRun(r.id));
  $('#btnCodeVscode').onclick = openVscode;
  $('#codeArgs').addEventListener('keydown', e => { if (e.key === 'Enter') saveAndRun(); });
}

/* ---------- Wi-Fi guide ---------- */
const PROTECTED_WIFI = ['netplan-wlan0-Turtlebot4', 'netplan-eth0', 'netplan-usb0'];
const isProtectedWifi = name => PROTECTED_WIFI.includes(name) || name === 'netplan-wlan0-' + hsName();
async function loadWifi() {
  const jobs = [api('/api/laptop_net').then(j => { S.laptop = j && j.ok !== false ? j : null; S.laptopErr = j && j.ok === false ? j.error : null; })];
  if (connected()) jobs.push(bridge('wifi_info', {}, { quiet: true }).then(j => { S.wifi = j.ok ? j : null; }));
  else S.wifi = null;
  await Promise.all(jobs);
  renderWifi();
}
function robotMode() {
  const wl = S.wifi && S.wifi.wlan0, st = S.status && S.status.net;
  const m = (wl && wl.mode) || (st && st.wifi_mode) || null;
  if (m === 'ap') return 'ap';
  if (m === 'infrastructure' || m === 'client') return 'client';
  return null;
}
/* Which scanned networks can the robot join with just a password? WPA/WPA2 personal only. */
function wifiSecurity(sec) {
  const s = String(sec ?? '').trim();
  if (!s || s === '--' || /^(open|none|owe)$/i.test(s)) return { ok: false, kind: 'open', label: 'Open network', why: 'Open networks are not supported.' };
  if (/802\.1x|eap|enterprise/i.test(s)) return { ok: false, kind: 'enterprise', label: 'Enterprise (802.1X)', why: 'Enterprise networks (802.1X, username and password) are not supported yet.' };
  const t = s.toUpperCase().split(/[\s,/]+/).filter(Boolean);
  const wpa12 = t.some(x => x === 'WPA' || x === 'WPA1' || x === 'WPA2');
  if (t.includes('WPA3') && !wpa12) return { ok: false, kind: 'wpa3', label: 'WPA3 only', why: 'WPA3-only networks are not supported yet.' };
  if (t.includes('WEP') && !wpa12) return { ok: false, kind: 'wep', label: 'WEP', why: 'WEP networks are not supported.' };
  return { ok: true, kind: 'personal', label: s };
}
const validPsk = p => /^[\x20-\x7e]{8,63}$/.test(p) || /^[0-9a-fA-F]{64}$/.test(p);
const scanFor = ssid => {
  const l = ((S.wifi && S.wifi.scan) || []).filter(x => x.ssid === ssid);
  return l.find(x => wifiSecurity(x.security).ok) || l[0] || null;
};
function renderWifi() {
  const lap = S.laptop, w = lap && lap.wifi, lssid = w && w.ssid;
  $('#wLaptop').innerHTML = rows([
    ['Wi-Fi network', lssid ? '<strong>' + esc(lssid) + '</strong>' : (lap ? tag('dim', 'not on Wi-Fi') : tag('warn', 'cannot tell'))],
    ['Signal', w && w.signal_pct != null ? esc(w.signal_pct) + '&nbsp;%' : txt(null)],
    ['State', txt(w && w.state)],
    ['System', txt(lap && lap.os)],
  ]);
  const wired = (lap && lap.wired) || [];
  $('#wLaptopWired').innerHTML = '<strong>Cables (Ethernet):</strong> ' + (wired.length ? wired.map(x => esc(x.name) + ' ' + (x.up ? tag('ok', 'up') : tag('dim', 'down')) + (x.ipv4 && x.ipv4.length ? ' <span class="mono">' + esc(x.ipv4.join(', ')) + '</span>' : '')).join('<br>') : '<span class="dim">none found</span>') +
    (S.laptopErr ? '<div class="note warn">Could not read this computer\'s network info: ' + esc(S.laptopErr) + '</div>' : '');
  const wl = (S.wifi && S.wifi.wlan0) || {}, st = (S.status && S.status.net) || {}, mode = robotMode();
  if (!connected()) {
    $('#wRobot').innerHTML = rows([['Status', tag('dim', 'not connected')]]);
    $('#wRobotNote').textContent = 'Not connected yet. Connect by cable (C) or join its hotspot (A) first.';
  } else {
    const ip = wl.ip || (st.addresses && st.addresses.wlan0);
    $('#wRobot').innerHTML = rows([
      ['Wi-Fi mode', mode === 'ap' ? tag('warn', 'hotspot (its own Wi-Fi)') : mode === 'client' ? tag('ok', 'joined a network') : txt(null)],
      ['Network', txt(wl.ssid || st.ssid)],
      ['Wi-Fi address', ip ? '<span class="mono">' + esc(ip) + '</span>' : txt(null)],
      ['Signal', (wl.signal_dbm ?? st.signal_dbm) == null ? txt(null) : esc(wl.signal_dbm ?? st.signal_dbm) + '&nbsp;dBm'],
      ['Power save', txt(wl.powersave || st.powersave || st.powersave_students)],
      ['Studio talks to it via', txt(S.conn.via)],
    ]);
    $('#wRobotNote').textContent = mode === 'ap' ? 'The robot found no saved network, so it made its own hotspot.' : '';
  }
  // where you are
  const via = S.conn.via; let here = null;
  if (connected()) { if (via === 'cable') here = 'C'; else if (via === 'hotspot' || mode === 'ap') here = 'A'; else here = 'B'; }
  else if (lssid === hsName()) here = 'A';
  for (const k of ['A', 'B', 'C']) { $('#here' + k).classList.toggle('hidden', here !== k); $('#w' + k).classList.toggle('hot', here === k); }
  $('#wbSsid').textContent = lssid ? lssid + (w.ssid_guess ? ' (Windows network name, check it)' : '') : '(cannot tell)';
  $('#btnUseLaptopSsid').classList.toggle('hidden', !lssid);
  // the name box follows the detected network until the user types their own
  const nameEl = $('#wbName');
  if (!nameEl.value || nameEl.value === S.wbAuto) nameEl.value = lssid || '';
  S.wbAuto = lssid || '';
  $('#wbNote').textContent = (w && w.note) || ''; $('#wbNote').classList.toggle('hidden', !(w && w.note));
  // saved
  const saved = (S.wifi && S.wifi.saved) || [];
  $('#wSavedEmpty').classList.toggle('hidden', saved.length > 0);
  $('#wSaved').innerHTML = saved.map((x, i) => '<tr><td class="mono">' + esc(x.name) + '</td><td>' + txt(x.ssid) + '</td><td class="num">' + txt(x.priority) + '</td><td>' + yesNo(x.autoconnect) + '</td><td>' + txt(x.powersave) + '</td><td>' + (x.active ? tag('ok', 'active') : tag('dim', 'no')) + '</td>' +
    '<td>' + (isProtectedWifi(x.name) ? '<span class="dim small">protected</span>' : '<button type="button" class="small danger" data-wrm="' + i + '" aria-label="Remove ' + esc(x.name) + ' from the robot">Remove</button>') + '</td></tr>').join('');
  // scan
  const scan = (S.wifi && S.wifi.scan) || [];
  $('#wScanNote').textContent = (S.wifi && S.wifi.scan_note) || (!S.wifi ? 'Connect to the robot to see what it can see.' : (scan.length ? '' : 'No networks found.'));
  $('#wScan').innerHTML = scan.map((x, i) => {
    const sec = wifiSecurity(x.security);
    const secCell = sec.ok ? tag('ok', sec.label) : tag('warn', sec.label + ': not supported');
    return '<tr><td>' + txt(x.ssid) + '</td><td class="num">' + txt(x.signal) + '</td><td>' + secCell + '</td><td class="num">' + txt(x.chan) + '</td>' +
      '<td>' + (x.ssid ? '<button type="button" class="small" data-wuse="' + i + '" aria-label="Use ' + esc(x.ssid) + ' as the network to join"' + (sec.ok ? '' : ' disabled title="' + esc(sec.why) + '"') + '>Use</button>' : '') + '</td></tr>';
  }).join('');
  // datalist: robot scan + this computer's SSID
  const names = [...new Set([lssid, ...scan.map(x => x.ssid)].filter(Boolean))];
  $('#wbList').innerHTML = names.map(n => '<option value="' + esc(n) + '"></option>').join('');
  updateWifiAdd();
}
async function joinHotspot() {
  const hs = hsName();
  const j = await call('/api/join_hotspot', {}, { quiet: true });
  if (j.needs_settings) {
    const ok = await confirmDialog('Join ' + hs + ' yourself', '<p>Studio cannot join the network for you on this computer. Open the Wi-Fi settings, pick <strong>' + esc(hs) + '</strong> and enter its password (in the TurtleBot 4 manual, or ask whoever set up the robot).</p><p class="dim">While you are on the hotspot this computer has no internet.</p>', 'Open Wi-Fi settings');
    if (ok) call('/api/laptop_wifi_settings', {}, { what: 'Wi-Fi settings' });
  } else if (!j.ok) notify('error', 'Join hotspot: ' + (j.error || 'failed'));
  else { notify('info', j.warning || j.message || 'Joining ' + hs + '. This computer has no internet while it is on the hotspot.'); setTimeout(loadWifi, 4000); }
}
/* What stops the Add button, and what the security of the chosen network is. Never reads the password text. */
function wifiFormState() {
  const ssid = $('#wbName').value.trim(), hasPsk = $('#wbPsk').value.length > 0, pskOk = validPsk($('#wbPsk').value);
  const already = !!(ssid && S.wifi && (S.wifi.saved || []).some(n => n.ssid === ssid));
  const hit = ssid ? scanFor(ssid) : null, sec = hit ? wifiSecurity(hit.security) : null;
  let why = '';
  if (!connected()) why = 'Connect to the robot first (cable or hotspot).';
  else if (!ssid) why = 'Type or pick a network name.';
  else if (ssid === hsName()) why = 'That is the robot\'s own hotspot. Pick another network.';
  else if (already) why = '“' + ssid + '” is already saved. To change its password, remove it below and add it again.';
  else if (sec && !sec.ok) why = sec.why;
  else if (!hasPsk) why = 'Type the Wi-Fi password.';
  else if (!pskOk) why = 'The password must be 8 to 63 characters (or 64 hex digits).';
  return { ssid, already, sec, hit, why };
}
function updateWifiAdd() {
  const f = wifiFormState();
  const add = $('#btnWifiAdd'); add.disabled = !!f.why;
  add.textContent = f.already ? '“' + f.ssid + '” is already saved on the robot' : (f.ssid ? 'Add “' + f.ssid + '” to the robot' : 'Add this Wi-Fi to the robot');
  $('#wbWhy').textContent = f.why;
  $('#wbSec').innerHTML = !f.ssid ? '' : f.sec ? (f.sec.ok ? tag('ok', 'Security: ' + f.sec.label + ' (supported)') : tag('warn', f.sec.why))
    : '<span class="dim">The robot did not list this network (hidden, out of range, or it cannot scan now), so its security cannot be checked.</span>';
}
/* Add flow: confirm, send ssid+password once, then follow the result. */
const JOB_KEY = 'studio_wifi_job'; // sessionStorage: nonce + ssid only, never a password
const jobSave = j => { try { if (j) sessionStorage.setItem(JOB_KEY, JSON.stringify({ nonce: j.nonce, ssid: j.ssid, now: j.now, t: j.t, base: j.base ?? null })); else sessionStorage.removeItem(JOB_KEY); } catch (e) { /* storage blocked */ } };
const jobLoad = () => { try { const j = JSON.parse(sessionStorage.getItem(JOB_KEY) || 'null'); return j && typeof j.nonce === 'string' && typeof j.ssid === 'string' ? j : null; } catch (e) { return null; } };
async function addWifi() {
  const f = wifiFormState(); if (f.why) { notify('warn', f.why); return; }
  const ssid = f.ssid, now = $('#chkNow').checked, pskEl = $('#wbPsk');
  const ok = await confirmDialog('Add “' + ssid + '” to the robot?',
    '<p>A terminal window opens. In it you type <strong>one password</strong>: the robot\'s own password (sudo asks for it before it changes system settings). Type it only in that window.</p>' +
    '<p>The Wi-Fi password was typed here in Studio. Studio sends it once, through the secure link, to the robot\'s memory for at most 3 minutes. It is used to save the network and is never stored by Studio.</p>' +
    '<p>Check the network name: it must match the Wi-Fi exactly, including capitals. The robot keeps its own hotspot as a backup. To undo it later, use Remove in the saved networks table.</p>' +
    (now ? '<div class="note warn"><strong>The robot will switch to this network now and test it.</strong> If it fails, it removes the entry and goes back to its current network. You may lose the connection for a moment. Join <strong>' + esc(ssid) + '</strong> on this computer too, then press Discover.</div>' : '<p class="dim">The robot will use it the next time it starts, or when its current network is out of range.</p>'),
    'Open terminal');
  let psk = pskEl.value; pskEl.value = ''; // cleared whether or not the dialog was confirmed
  if (!ok) { psk = ''; updateWifiAdd(); return; }
  let j;
  try { j = await call('/api/robot_wifi_add', { ssid, psk, connect_now: now, confirm: true }, { what: 'Add Wi-Fi' }); } finally { psk = ''; }
  updateWifiAdd();
  if (!j.ok) return;
  if (!j.nonce) { notify('ok', 'Terminal opened. Finish there, then press Refresh.'); return; }
  const job = { nonce: j.nonce, ssid, now, t: Date.now(), fake: !!j.fake };
  S.wifiJob = job; jobSave(job);
  wifiDialog(job, wifiView(job, null, false), true);
}
/* Pure: turns the last robot_wifi_status answer into the five progress steps. */
function wifiView(job, r, lost) {
  const secret = (r && r.secret) || null;
  let jn = r && r.join ? r.join : null;
  if (jn && ((jn.ssid && jn.ssid !== job.ssid) || (job.base != null && jn.t === job.base))) jn = null; // status file of an older attempt
  const state = jn && jn.state;
  const fetched = secret === 'fetched' || !!jn;
  const expired = secret === 'expired' && !jn;
  const steps = [{ t: 'Password sent to the robot (memory only)', s: 'ok' }];
  steps.push({ t: job.fake ? 'Robot password (test mode: not needed)' : 'Type the robot password in the terminal', s: fetched ? 'ok' : expired ? 'bad' : 'wait' });
  steps.push({ t: 'Saving the network on the robot', s: fetched ? (job.now && !jn ? 'run' : 'ok') : 'idle' });
  if (job.now) steps.push({ t: 'Joining “' + job.ssid + '” (up to 45 s)', s: state === 'joining' ? 'run' : (state === 'joined' || state === 'failed') ? 'ok' : 'idle' });
  const result = state === 'joined' ? 'joined' : state === 'failed' ? 'failed' : (!job.now && fetched) ? 'saved' : expired ? 'expired' : null;
  steps.push({ t: 'Result', s: result === 'joined' || result === 'saved' ? 'ok' : result === 'failed' || result === 'expired' ? 'bad' : lost ? 'warn' : 'idle' });
  return { steps, done: !!result, result, jn };
}
function wifiHtml(job, v, flag, err) {
  const mk = { ok: tag('ok', 'Done'), bad: tag('bad', 'Problem'), run: tag('warn', 'Working…'), wait: tag('warn', 'Waiting for you'), idle: tag('dim', 'Later'), warn: tag('warn', 'Unknown') };
  let h = '<ol class="wiz" aria-label="Progress">' + v.steps.map((s, i) => `<li class="wizstep"><div class="wiztop"><span>${i + 1}. ${esc(s.t)}</span>${mk[s.s]}</div></li>`).join('') + '</ol>';
  const jn = v.jn || {};
  if (v.result === 'joined') {
    h += `<div class="note ok"><strong>The robot joined ${esc(job.ssid)}.</strong> Its address there: <code>${esc(jn.ip || 'unknown')}</code>.<br>Join this computer to <strong>${esc(job.ssid)}</strong> too, then use the address below or press Discover.</div>
      <div class="row" style="margin-top:8px">${jn.ip ? `<button type="button" class="primary" data-wp="use" data-ip="${esc(jn.ip)}">Use this address</button>` : ''}<button type="button" data-wp="discover">Discover</button></div>`;
  } else if (v.result === 'failed') {
    const fb = jn.fallback;
    h += `<div class="note bad"><strong>The robot could not join ${esc(job.ssid)}.</strong> ${esc(jn.reason || 'Unknown reason')}.<br>` +
      (fb ? (jn.fallback_ok === false ? `It tried to return to <strong>${esc(fb)}</strong> but that did not work yet. It should reach it or its hotspot within about 1.5 minutes.` : `It is back on <strong>${esc(fb)}</strong>.`) : 'It stays on its previous network.') +
      (jn.removed ? ' The saved entry was removed, so you can try again with the right password.' : '') + '</div>';
  } else if (v.result === 'saved') {
    h += `<div class="note ok"><strong>${esc(job.ssid)} is saved on the robot.</strong> It joins it by itself when it is in range and no better network is available. Press Refresh to see it in the saved list.</div>`;
  } else if (v.result === 'expired') {
    h += '<div class="note bad"><strong>The password handoff timed out.</strong> Nothing was saved. The robot password was not entered in time. Close this and start again.</div>';
  } else if (flag === 'lost') {
    h += `<div class="note warn"><strong>Studio lost the connection to the robot.</strong> This is expected when the robot changes network${err ? ' (' + esc(err) + ')' : ''}. Join this computer to <strong>${esc(job.ssid)}</strong>, then press Discover and Connect. Studio then shows the result. If the join failed, the robot returns to its previous network within about 1.5 minutes.</div>`;
  } else if (flag === 'timeout') {
    h += '<div class="note warn"><strong>No final answer yet.</strong> The robot may still be working. Reconnect to it later and Studio shows the result then.</div>';
  }
  return h;
}
function wifiDialog(job, view0, poll) {
  S.wifiJobOpen = true;
  let closed = false, ovRef = null;
  const render = (view, flag, err) => { if (ovRef && ovRef.isConnected) $('#wpBody', ovRef).innerHTML = wifiHtml(job, view, flag, err); };
  const p = modal({
    title: 'Adding “' + job.ssid + '” to the robot', body: '<div id="wpBody" aria-live="polite"></div>', buttons: [{ label: 'Close', value: true, kind: 'primary' }],
    onOpen: ov => {
      ovRef = ov; render(view0);
      ov.addEventListener('click', e => {
        const b = e.target.closest('[data-wp]'); if (!b) return;
        $('.actions button', ov).click();
        if (b.dataset.wp === 'use') { $('#hostInput').value = b.dataset.ip; selectTab('dash'); notify('ok', 'Address filled in. Press Connect.'); }
        else { selectTab('dash'); doDiscover(); }
      });
    },
  });
  p.then(() => { closed = true; S.wifiJobOpen = false; });
  if (poll) pollWifiJob(job, render, () => closed);
  return p;
}
async function pollWifiJob(job, render, isClosed) {
  const t0 = performance.now(); let fails = 0, last = null;
  for (;;) {
    const j = await api('/api/robot_wifi_status', { nonce: job.nonce });
    if (isClosed()) return;
    if (j.ok) {
      fails = 0; last = j;
      if (job.base === undefined) { job.base = j.join && j.join.t != null ? j.join.t : null; jobSave(job); }
    } else fails++;
    const v = wifiView(job, last, false);
    if (v.done) { render(v); S.wifiJob = null; jobSave(null); if (connected()) loadWifi(); return; }
    if (fails >= 3 || (!j.ok && !connected())) { render(wifiView(job, last, true), 'lost', j.error); return; }
    if (performance.now() - t0 > 150000) { render(v, 'timeout'); return; }
    render(v);
    await sleep(2000);
  }
}
/* After a reconnect: ask once for the stored result of the last add. */
async function checkPendingWifiJob() {
  const job = S.wifiJob || jobLoad();
  if (!job || job.asked || S.wifiJobOpen) return;
  if (Date.now() - job.t > 3600e3) { S.wifiJob = null; jobSave(null); return; }
  job.asked = true;
  const r = await api('/api/robot_wifi_status', { nonce: job.nonce });
  if (!r.ok) { job.asked = false; return; }
  const v = wifiView(job, r, false);
  if (v.done) { S.wifiJob = null; jobSave(null); wifiDialog(job, v, false); if ($('#p-wifi').classList.contains('active')) loadWifi(); }
  else if (r.secret === 'none' && !r.join) { S.wifiJob = null; jobSave(null); }
  else { job.asked = false; S.wifiJob = job; } // still joining: ask again at the next reconnect
}
async function removeWifi(x) {
  const ok = await confirmDialog('Remove “' + x.name + '” from the robot?', '<p>A terminal window opens and asks for the robot\'s password to delete this saved network. The robot will no longer join it by itself.</p>', 'Open terminal', 'danger');
  if (!ok) return;
  const j = await call('/api/robot_wifi_remove', { name: x.name, confirm: true }, { what: 'Remove Wi-Fi' });
  if (j.ok) notify('ok', 'Terminal opened. Finish there, then press Refresh.');
}
function wireWifi() {
  $('#btnLaptopNet').onclick = loadWifi; $('#btnWifiInfo').onclick = loadWifi;
  $('#btnJoinHotspot').onclick = joinHotspot;
  $('#btnWifiSettings').onclick = () => call('/api/laptop_wifi_settings', {}, { what: 'Wi-Fi settings' });
  $('#btnWifiDiscover').onclick = () => { selectTab('dash'); doDiscover(); };
  $('#btnWifiAdd').onclick = addWifi;
  $('#wbName').oninput = updateWifiAdd; $('#wbPsk').oninput = updateWifiAdd;
  $('#btnUseLaptopSsid').onclick = () => { const s = S.laptop && S.laptop.wifi && S.laptop.wifi.ssid; if (s) { $('#wbName').value = s; updateWifiAdd(); $('#wbPsk').focus(); } };
  $('#wScan').onclick = e => { const b = e.target.closest('[data-wuse]'); if (b) { const x = S.wifi.scan[+b.dataset.wuse]; $('#wbName').value = x.ssid; updateWifiAdd(); $('#wB').scrollIntoView({ block: 'nearest' }); $('#wbPsk').focus(); } };
  $('#wSaved').onclick = e => { const b = e.target.closest('[data-wrm]'); if (b) removeWifi(S.wifi.saved[+b.dataset.wrm]); };
}

/* ---------- first-run setup wizard ---------- */
const W = { open: false, busy: false, st: {}, msg: {}, setup: null, host: '', hostUsed: null, scan: null, key: null, sure: false, label: '', hostname: null, render: null };
const wizOs = () => { const o = String((W.setup && W.setup.os) || navigator.platform || navigator.userAgent || '').toLowerCase(); return /mac|darwin/.test(o) ? 'mac' : /win/.test(o) ? 'win' : 'linux'; };
const SSH_HELP = {
  win: 'Open <strong>Settings &gt; System &gt; Optional features</strong>, add <strong>OpenSSH Client</strong>, then press Retry.',
  mac: 'ssh is built into macOS. If it is missing, run <code>xcode-select --install</code> in Terminal, then press Retry.',
  linux: 'Install it with <code>sudo apt install openssh-client</code> (or your distribution\'s package manager), then press Retry.',
};
const WIZ_KIND_HELP = {
  key_not_set_up: 'The robot did not accept the key yet. Do step 5 (type the robot password in the terminal window), then test again.',
  host_key: 'The robot\'s identity does not match the one you trusted. Redo step 3 and compare the fingerprints.',
  no_ssh: 'ssh was not found. Redo step 1.',
};
function wizReset(from) { // forget results that depend on the address
  if (from <= 3) { W.scan = null; W.sure = false; W.st[3] = 'idle'; W.msg[3] = ''; }
  W.st[5] = W.st[5] === 'ok' ? 'idle' : W.st[5]; W.st[6] = 'idle'; W.msg[6] = ''; W.hostname = null;
}
function wizHtml() {
  const st = W.st, s = W.setup, host = W.host.trim();
  const en = n => n === 1 || st[n - 1] === 'ok' || (n === 6 && st[5] === 'wait');
  const tg = x => ({ idle: tag('dim', 'To do'), run: tag('warn', 'Working…'), ok: tag('ok', 'Done'), bad: tag('bad', 'Problem'), wait: tag('warn', 'Waiting for you') }[x] || '');
  const dis = n => (!en(n) || W.busy) ? ' disabled' : '';
  const b = (n, act, label, kind) => `<button type="button" class="${kind || ''}" data-wact="${act}"${dis(n)}>${esc(label)}</button>`;
  const note = n => W.msg[n] ? `<div class="note ${st[n] === 'bad' ? 'bad' : st[n] === 'ok' ? 'ok' : 'warn'}">${esc(W.msg[n])}</div>` : '';
  const step = (n, title, body, actions) => `<li class="wizstep${en(n) ? '' : ' dis'}"><div class="wiztop"><strong>${n}. ${esc(title)}</strong>${tg(st[n])}</div><div class="wizbody">${body}${note(n)}</div><div class="row">${actions}</div></li>`;
  const retry = (n, label) => st[n] === 'bad' ? 'Retry' : label;
  let b1 = !s ? '<span class="dim">Checking&hellip;</span>' : s.ssh && s.ssh.found ? `OpenSSH found: <span class="mono">${esc(s.ssh.version || s.ssh.path || 'yes')}</span>` : `<strong>ssh was not found on this computer.</strong> ${SSH_HELP[wizOs()]}`;
  if (s && s.ssh && s.ssh.found && s.keygen && !s.keygen.found) b1 += '<div class="note warn">ssh-keygen was not found, so step 4 cannot create a key.</div>';
  if (s && s.ssh && s.ssh.found && s.keyscan && !s.keyscan.found) b1 += '<div class="note warn">ssh-keyscan was not found, so step 3 cannot read the robot\'s identity.</div>';
  const cands = (S.cands || []).map((c, i) => `<div class="crow"><span class="mono">${esc(c.host)}${candBadge(c)}</span>${c.reachable ? tag('ok', 'Reachable') : tag('bad', 'No answer')}<button type="button" class="small${c.identity === 'confirmed' ? ' primary' : ''}" data-wact="cand" data-i="${i}" aria-label="Use ${esc(c.host)}"${W.busy ? ' disabled' : ''}>Use</button></div>`).join('');
  const b2 = `<label class="field"><span>Robot address</span><input id="wzHost" type="text" value="${esc(W.host)}" placeholder="IP address or name, for example ${esc(setv('robot_hostname'))}.local" aria-label="Robot address" autocomplete="off" spellcheck="false"></label>` +
    (cands ? `<div class="wizcands" aria-label="Robots found">${cands}</div>` : '<div class="dim small" style="margin-top:4px">Press Discover to look for the robot on the cable and Wi-Fi, or type its address.</div>') +
    (S.deep.running ? `<div class="bar" role="status"><i style="width:${S.deep.total ? Math.round(100 * S.deep.done / S.deep.total) : 0}%"></i></div><div class="dim small">${S.deep.total ? 'Checking addresses: ' + S.deep.done + ' of ' + S.deep.total : 'Starting…'}</div>` : '') +
    '<div class="dim small" style="margin-top:4px">Search the whole network checks every address on this computer\'s network for your robot (about 15 s). Or read the address on the robot\'s screen and type it.</div>';
  const sc = W.scan;
  let b3 = '<p style="margin:0 0 4px">Studio asks the robot for its identity key (fingerprint) so you know you are talking to the right robot.</p>';
  if (sc && sc.trusted) b3 += `<div class="note ok">Known robot${sc.label ? ': <strong>' + esc(sc.label) + '</strong>' : ''}. Fingerprint <span class="mono">${esc(sc.fingerprint)}</span></div>`;
  else if (sc) b3 += `<div class="note warn"><div>Fingerprint reported by ${esc(host)}:</div><div class="mono">${esc(sc.fingerprint)}</div>
      <p style="margin:6px 0 0">Compare it with the robot. On the robot (display and keyboard, or another trusted terminal) run <code>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code>. The fingerprints must be identical.</p></div>
      <label class="row small" style="margin-top:6px"><input type="checkbox" id="wzSure"${W.sure ? ' checked' : ''}> <span>I compared them and they are the same</span></label>
      <label class="field" style="margin-top:6px"><span>Name for this robot</span><input id="wzLabel" type="text" value="${esc(W.label)}" placeholder="for example Robot 1" aria-label="Name for this robot" autocomplete="off"></label>`;
  const a3 = b(3, 'scan', retry(3, sc ? 'Check again' : 'Check robot identity')) + (sc && !sc.trusted ? `<button type="button" class="primary" data-wact="trust"${dis(3)}${W.sure ? '' : ' disabled'}>Trust this robot</button>` : '');
  const k = W.key;
  const b4 = k && k.path ? `<div>Key file: <span class="mono">${esc(k.path)}</span></div>${k.fingerprint ? '<div>Fingerprint: <span class="mono">' + esc(k.fingerprint) + '</span></div>' : ''}` : '<span>Studio makes a key pair for this computer. The private part never leaves it.</span>';
  const b5 = '<span>A terminal window opens and asks for the <strong>robot password</strong> once. Type it <strong>in that window</strong>. Studio never sees it. Afterwards logging in needs no password.</span>';
  const b6 = W.hostname ? `<span>Logged in to <strong>${esc(W.hostname)}</strong>.</span>` : '<span>Studio logs in with the key (no password) and reads the robot\'s name.</span>';
  const a6 = b(6, 'test', retry(6, 'Test login')) + (st[6] === 'ok' ? '<button type="button" class="primary" data-wact="connect"' + (W.busy ? ' disabled' : '') + '>Connect</button>' : '');
  return '<p class="dim small" style="margin:0">Six steps to your first connection. You can stop at any time and come back from the Dashboard.</p><ol class="wiz">' +
    step(1, 'Check that ssh is installed', b1, b(1, 'check', retry(1, 'Check again'))) +
    step(2, 'Find the robot', b2, b(2, 'discover', 'Discover') + b(2, 'deep', 'Search the whole network') + b(2, 'useaddr', 'Use this address', 'primary')) +
    step(3, 'Check the robot\'s identity', b3, a3) +
    step(4, 'Create this computer\'s key', b4, b(4, 'mkkey', retry(4, k && k.path ? 'Create again' : 'Create key'))) +
    step(5, 'Allow key login', b5, b(5, 'term', retry(5, 'Open terminal'))) +
    step(6, 'Test the login', b6, a6) + '</ol>';
}
async function wizAct(act, el) {
  if (W.busy) return;
  const set = (n, v, msg) => { W.st[n] = v; W.msg[n] = msg || ''; };
  const begin = n => { set(n, 'run'); W.busy = true; W.render(); };
  try {
    switch (act) {
      case 'check': {
        begin(1);
        const j = await api('/api/setup_status');
        if (!j.ok) { set(1, 'bad', j.error || 'Could not read the setup status'); break; }
        W.setup = j;
        set(1, j.ssh && j.ssh.found ? 'ok' : 'bad', j.ssh && j.ssh.found ? '' : 'ssh was not found.');
        if (j.key && j.key.exists) { W.key = j.key; set(4, 'ok'); } else if (W.st[4] !== 'ok') set(4, 'idle');
        if (!W.host && j.host) W.host = j.host;
        break;
      }
      case 'discover': {
        begin(2); await doDiscover(); W.st[2] = W.st[2] === 'ok' ? 'ok' : 'idle';
        const best = (S.cands || []).find(c => c.reachable); if (best && !W.host.trim()) W.host = best.host;
        break;
      }
      case 'deep': {
        begin(2); const j = await doDeepDiscover(); W.st[2] = W.st[2] === 'ok' ? 'ok' : 'idle';
        const mine = j && j.ok && (S.cands || []).find(c => c.identity === 'confirmed'); if (mine) W.host = mine.host;
        break;
      }
      case 'cand': { W.host = S.cands[+el.dataset.i].host; return wizAct('useaddr'); }
      case 'useaddr': {
        const h = W.host.trim();
        if (!h || /\s/.test(h)) { set(2, 'bad', 'Type an address without spaces, for example an IP address.'); break; }
        if (h !== W.hostUsed) { W.hostUsed = h; wizReset(3); }
        set(2, 'ok'); $('#hostInput').value = h;
        await call('/api/settings', { last_host: h }, { quiet: true });
        S.settings.last_host = h;
        break;
      }
      case 'scan': {
        begin(3);
        const j = await call('/api/scan_host_key', { host: W.host.trim() }, { quiet: true });
        if (!j.ok) { W.scan = null; set(3, 'bad', (j.error || 'The robot did not answer.') + ' Is the address right and the robot on?'); break; }
        W.scan = j; W.sure = false;
        if (j.trusted) set(3, 'ok'); else set(3, 'wait', 'Not trusted yet. Compare the fingerprint, then trust it.');
        break;
      }
      case 'trust': {
        if (!W.scan || !W.sure) break;
        begin(3);
        const label = W.label.trim() || 'My robot';
        const j = await call('/api/trust_host_key', { key: W.scan.key, label, confirm: true }, { quiet: true });
        if (!j.ok) { set(3, 'bad', j.error || 'Could not save the trusted key'); break; }
        W.scan.trusted = true; W.scan.label = label; set(3, 'ok');
        loadSettings();
        break;
      }
      case 'mkkey': {
        begin(4);
        const j = await call('/api/create_key', {}, { quiet: true });
        if (!j.ok) { set(4, 'bad', j.error || 'Could not create the key'); break; }
        W.key = { path: j.path, fingerprint: j.fingerprint }; set(4, 'ok', j.created ? 'Key created.' : 'This computer already had a key.');
        break;
      }
      case 'term': {
        begin(5);
        const j = await call('/api/setup_key', { host: W.host.trim() }, { quiet: true });
        if (!j.ok) { set(5, 'bad', j.error || 'Could not open the terminal'); break; }
        set(5, 'wait', j.note || 'Terminal opened. Type the robot password there. When it says it is done, go on with step 6.');
        break;
      }
      case 'test': {
        begin(6);
        const j = await call('/api/test_login', { host: W.host.trim() }, { quiet: true });
        if (!j.ok) {
          const help = WIZ_KIND_HELP[j.kind] || '';
          set(6, 'bad', [j.error, help].filter(Boolean).join(' ') || 'Login failed');
          if (j.kind === 'key_not_set_up') W.st[5] = 'idle';
          if (j.kind === 'host_key') W.st[3] = 'idle';
          if (j.kind === 'no_ssh') W.st[1] = 'idle';
          break;
        }
        W.hostname = j.hostname || null; set(6, 'ok'); set(5, 'ok');
        const r = await call('/api/settings', { setup_done: true }, { quiet: true });
        if (r.ok) S.settings.setup_done = true;
        break;
      }
      case 'connect': {
        W.busy = true; W.render();
        const j = await doConnect(W.host.trim());
        W.busy = false;
        if (j.ok) { const ov = $('#wizBody') && $('#wizBody').closest('.overlay'); if (ov) $$('.actions button', ov)[1].click(); }
        break;
      }
      default: break;
    }
  } finally { W.busy = false; if (W.open && W.render) W.render(); }
}
async function openWizard() {
  if (W.open) return;
  Object.assign(W, { open: true, busy: false, st: { 1: 'idle', 2: 'idle', 3: 'idle', 4: 'idle', 5: 'idle', 6: 'idle' }, msg: {}, setup: null, hostUsed: null, scan: null, key: null, sure: false, label: '', hostname: null });
  W.host = $('#hostInput').value.trim() || S.settings.last_host || '';
  let ovRef = null;
  W.render = () => {
    if (!ovRef || !ovRef.isConnected) return;
    const a = document.activeElement, id = a && ovRef.contains(a) ? a.id : '', pos = a && a.selectionStart != null ? a.selectionStart : null;
    $('#wizBody', ovRef).innerHTML = wizHtml();
    if (id) { const e = document.getElementById(id); if (e) { e.focus(); if (pos != null && e.setSelectionRange && e.type === 'text') { try { e.setSelectionRange(pos, pos); } catch (x) { /* ignore */ } } } }
  };
  const p = modal({
    title: 'Set up TurtleBot Studio', body: '<div id="wizBody" aria-live="polite"></div>',
    buttons: [{ label: 'Skip setup', value: 'skip' }, { label: 'Close', value: 'close', kind: 'primary' }],
    onOpen: ov => {
      ovRef = ov; W.render();
      ov.addEventListener('click', e => { const b = e.target.closest('[data-wact]'); if (b && !b.disabled) wizAct(b.dataset.wact, b); });
      ov.addEventListener('input', e => { if (e.target.id === 'wzHost') W.host = e.target.value; else if (e.target.id === 'wzLabel') W.label = e.target.value; });
      ov.addEventListener('change', e => { if (e.target.id === 'wzSure') { W.sure = e.target.checked; const t = $('[data-wact=trust]', ov); if (t) t.disabled = !W.sure; } });
    },
  });
  wizAct('check');
  const r = await p;
  W.open = false; W.render = null;
  if (r === 'skip') { const j = await call('/api/settings', { setup_done: true }, { quiet: true }); if (j.ok) { S.settings.setup_done = true; notify('info', 'Setup skipped. You can open the wizard again from the Dashboard or the Tools tab.'); } }
}

/* ---------- SSE ---------- */
let es = null, retry = 0, retryTimer = null, countdown = null;
function setSse(ok) { S.sse = ok; $('#bannerLost').classList.toggle('hidden', ok); if (ok) { $('#retryIn').textContent = ''; clearInterval(countdown); } }
function connectSse() {
  clearTimeout(retryTimer);
  try { es && es.close(); } catch (e) { /* ignore */ }
  es = new EventSource('/api/events?token=' + encodeURIComponent(TOKEN));
  es.onopen = () => { retry = 0; setSse(true); };
  es.onmessage = m => { let ev; try { ev = JSON.parse(m.data); } catch (e) { return; } onEvent(ev); };
  es.onerror = () => {
    try { es.close(); } catch (e) { /* ignore */ }
    if (S.stopped) return;
    setSse(false); renderConn();
    const wait = Math.min(10, 1 << Math.min(retry++, 4)); let left = wait;
    clearInterval(countdown); $('#retryIn').textContent = ` in ${left} s`;
    countdown = setInterval(() => { left = Math.max(0, left - 1); $('#retryIn').textContent = left ? ` in ${left} s` : ' now'; }, 1000);
    retryTimer = setTimeout(connectSse, wait * 1000);
  };
}
let lastConnState = null;
function onEvent(ev) {
  switch (ev.ev) {
    case 'conn': {
      const prev = lastConnState; S.conn = ev; lastConnState = ev.state;
      if (ev.state === 'reconnecting') S.reconn = { since: ev.since, attempt: ev.attempt, nextAt: performance.now() + (ev.next_in || 0) * 1000 }; else S.reconn = null;
      renderConn();
      if (ev.state === 'error' && ev.error) notify('error', 'Connection: ' + ev.error);
      if (ev.state === 'disconnected' && ev.kind === 'gave_up') notify('error', 'Connection: ' + ev.error);
      if (ev.state === 'connected' && prev !== 'connected') onConnected(prev === 'reconnecting');
      if (ev.state !== 'connected') { S.hello = ev.state === 'disconnected' ? null : S.hello; renderAbout(); tickStale(); }
      break;
    }
    case 'hello': S.hello = ev; renderAbout(); break;
    case 'status':
      S.status = ev; S.statusAt = performance.now();
      if (ev.estop && ev.estop.on !== null && ev.estop.on !== undefined) S.estopLocal = false;
      mergeRuns(ev.runs); renderEstop(); renderDash(); tickStale(); break;
    case 'discover': S.cands = ev.candidates || []; renderCands(); break;
    case 'deep_progress': S.deep.done = ev.done; S.deep.total = ev.total; S.deep.running = true; renderDeep(); break;
    case 'update': S.update = ev; renderUpdate(); break;
    case 'quit': showStopped(); break;
    case 'sync': showSync(ev); if (ev.state === 'done') { compareFiles(); loadPrograms(); } break;
    case 'log': addLog(ev.level || 'info', ev.text || ''); break;
    case 'run_output': onRunOutput(ev); break;
    case 'run_exit': { const r = ensureRun(ev.run_id); r.alive = false; r.code = ev.code; raf(renderRuns); break; }
    case 'msg': {
      const w = S.watches[ev.watch_id] || (S.watches[ev.watch_id] = { id: ev.watch_id, topic: ev.topic });
      w.topic = ev.topic || w.topic; w.data = ev.data; w.rate = ev.rate_hz; raf(renderWatches); break;
    }
    case 'action': {
      S.action = ev; const el = $('#actionState');
      const icon = { succeeded: '&#10003;', aborted: '&#10007;', rejected: '&#10007;', canceled: '&#9888;' }[ev.state] || '&#8987;';
      el.innerHTML = `${icon} ${esc(ev.name)}: ${esc(ev.state)}${ev.detail ? ' (' + esc(typeof ev.detail === 'string' ? ev.detail : JSON.stringify(ev.detail)) + ')' : ''}`;
      break;
    }
    default: break;
  }
}
async function onConnected(wasReconnecting) {
  // a new bridge process knows nothing about earlier watches: ask for the same topics again (reading only)
  const old = Object.values(S.watches).map(w => w.topic).filter(Boolean);
  if (old.length) { S.watches = {}; renderWatches(); }
  if (wasReconnecting) notify('ok', 'Reconnected');
  await bridge('status_on', { period: 1.0 }, { quiet: true });
  for (const t of old) await watchTopic(t);
  loadPrograms(); loadTopics(); renderPrograms();
  if ($('#p-wifi').classList.contains('active')) loadWifi();
  checkPendingWifiJob();
  if (LOCAL_DIR() && $("#p-files").classList.contains("active")) compareFiles();
}

/* ---------- wiring ---------- */
function selectTab(name) {
  $$('.tab').forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id === 'p-' + name));
  if (name === 'prog' || name === 'code') loadPrograms();
  if (name === 'wifi') loadWifi();
  if (name === 'topics' && connected() && !S.topics.length) loadTopics();
  if (name === 'files' && LOCAL_DIR() && !S.local) compareFiles();
}
function wire() {
  window.addEventListener('beforeunload', e => { if (C.dirty) { e.preventDefault(); e.returnValue = ''; } });
  $$('.tab').forEach(t => { t.onclick = () => selectTab(t.dataset.tab); });
  $('.tabs').addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const tabs = $$('.tab'), i = tabs.indexOf(document.activeElement); if (i < 0) return;
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); n.click();
  });
  $('#btnEstop').onclick = doEstop; $('#btnRelease').onclick = releaseEstop;
  $('#btnDiscover').onclick = doDiscover; $('#btnConnect').onclick = () => doConnect();
  $('#btnDeep').onclick = doDeepDiscover; $('#btnDiag').onclick = showDiagnostics; $('#btnDiagErr').onclick = showDiagnostics;
  $('#btnReconnStop').onclick = () => call('/api/reconnect_cancel', {}, { what: 'Stop reconnecting' });
  $('#btnUpdCheck').onclick = checkUpdates; $('#btnQuit').onclick = quitStudio;
  $('#btnUpdDismiss').onclick = async () => { if (S.update && S.update.latest) { await saveSettingsPatch({ update_dismissed: S.update.latest }); renderUpdate(); } };
  $('#btnDisconnect').onclick = () => call('/api/disconnect', {}, { what: 'Disconnect' });
  $('#btnUndock').onclick = () => doAction('undock', 'Undock'); $('#btnDock').onclick = () => doAction('dock', 'Dock');
  $('#btnHealth').onclick = doHealth; $('#btnKeyHint').onclick = () => $('#btnKey').click();
  $('#candBody').onclick = e => { const b = e.target.closest('[data-cand]'); if (b) { const c = S.cands[+b.dataset.cand]; $('#hostInput').value = c.host; doConnect(c.host); } };
  $('#cardScan').addEventListener('click', e => { if (e.target.id === 'btnLidar') bridge('lidar', { on: true }).then(j => j.ok && notify('ok', 'Lidar motor start sent')); });
  // programs
  $('#btnProgRefresh').onclick = loadPrograms;
  $('#btnStopAll').onclick = async () => { const j = await bridge('stop', { run_id: 'all' }); if (j.ok) notify('info', 'Stop sent to all programs'); };
  $('#progBody').addEventListener('input', e => { const i = e.target.dataset.args; if (i !== undefined) S.args[S.files[+i].name] = e.target.value; });
  $('#progBody').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.args !== undefined) { const f = S.files[+e.target.dataset.args]; runProgram(f.name, e.target.value); } });
  $('#progBody').addEventListener('toggle', e => { const n = e.target.dataset && e.target.dataset.det; if (n) S.open[n] = e.target.open; }, true);
  $('#progBody').addEventListener('click', e => {
    const x = e.target.closest('[data-ex]');
    if (x) { const [i, j] = x.dataset.ex.split(':').map(Number), f = S.files[i], ex = S.catalog.programs[f.name].examples[j]; S.args[f.name] = ex.args; const inp = $('[data-args="' + i + '"]'); if (inp) inp.value = ex.args; return; }
    const b = e.target.closest('[data-run]'); if (b) { const f = S.files[+b.dataset.run]; runProgram(f.name, S.args[f.name] || ''); }
  });
  $('#progBody').addEventListener('change', async e => {
    const i = e.target.dataset.mark; if (i === undefined) return;
    const name = S.files[+i].name, set = new Set(S.settings.motion_files || []);
    e.target.checked ? set.add(name) : set.delete(name);
    await saveSettingsPatch({ motion_files: [...set] }); renderPrograms();
  });
  $('#runBody').onclick = e => {
    const v = e.target.closest('[data-viewrun]'), s = e.target.closest('[data-stoprun]');
    if (v) { S.selRun = v.dataset.viewrun; renderRuns(); renderLog(); } if (s) stopRun(s.dataset.stoprun);
  };
  $('#btnLogClear').onclick = () => { const r = S.runs[S.selRun]; if (r) { r.lines = []; renderLog(); } };
  $('#autoScroll').onchange = renderLog;
  // files
  $('#btnUseDir').onclick = async () => { const j = await saveSettingsPatch({ local_dir: LOCAL_DIR(), remote_dir: $('#remoteDir').value.trim() || '~/robot_code' }); if (j.ok) { fillSettings(); compareFiles(); } };
  $('#btnCompare').onclick = compareFiles;
  $('#btnPreview').onclick = () => doSync('up', true); $('#btnUpload').onclick = () => doSync('up', false);
  $('#btnDownload').onclick = () => doSync('down', false); $('#btnSyncRun').onclick = syncAndRun;
  $('#cmpBody').onchange = e => { const i = e.target.dataset.sel; if (i !== undefined) { S.selFile = compareRows()[+i].name; renderCompare(); } };
  // topics
  $('#btnTopics').onclick = loadTopics; $('#topicFilter').oninput = renderTopics;
  $('#topicBody').onclick = e => { const b = e.target.closest('[data-watch]'); if (b) watchTopic(b.dataset.watch); };
  $('#watchList').onclick = e => { const b = e.target.closest('[data-unwatch]'); if (b) unwatch(b.dataset.unwatch); };
  // tools
  $('#btnTerm').onclick = async () => { const j = await call('/api/open_terminal', {}, { what: 'Terminal' }); if (j.ok) notify('ok', 'Terminal opened'); };
  $('#btnKey').onclick = async () => {
    const ok = await confirmDialog('Set up key login', '<p>A terminal window will open and ask for the <strong>robot password</strong>. Type it <strong>in that terminal window</strong>. This app never sees or stores it.</p>', 'Open terminal window');
    if (!ok) return; const j = await call('/api/setup_key', {}, { what: 'Key setup' }); if (j.ok) notify('ok', 'Terminal opened: finish the key setup there, then press Connect');
  };
  $('#btnCode').onclick = openVscode;
  $('#btnWizard').onclick = openWizard; $('#btnWizardTools').onclick = openWizard; $('#btnKeyWizard').onclick = openWizard;
  $('#btnTrustPaste').onclick = trustPasted;
  $('#trustedBody').onclick = e => { const b = e.target.closest('[data-untrust]'); if (b) untrustRobot(+b.dataset.untrust); };
  $('#settingsForm').onsubmit = saveSettingsForm;
  wireCode(); wireWifi();
  $('#btnLogCopy').onclick = () => { S.applog = []; renderAppLog(); };
}

async function init() {
  wire(); renderConn(); renderCands(); renderPrograms(); renderRuns(); renderAbout(); renderWatches();
  loadCatalog();
  await loadSettings();
  $('#progDir').textContent = remoteDir();
  connectSse();
  setInterval(tickStale, 500);
  setInterval(renderReconn, 500);
  api('/api/update_status').then(j => { if (j && j.ok && j.newer) { S.update = j; renderUpdate(); } });
  const tab = qs.get('tab'); if (tab) selectTab(tab);
  if ((S.settings.setup_done === false && !qs.has('nowizard')) || qs.get('wizard') === '1') openWizard();
}
init();
