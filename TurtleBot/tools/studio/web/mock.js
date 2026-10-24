/* Standalone mock of the Studio HTTP API and SSE stream, for developing and screenshotting the UI
 * without a server or robot. Load BEFORE app.js (see mock.html). Query options:
 *   ?theme=dark|light  ?tab=dash|wifi|prog|files|topics|tools  ?scenario=normal|nokey|estop|disconnected|stale|lidaroff|badclock|hotspot|firstrun
 *   scenario=update shows the "new version" banner. Mock controls: "Drop connection" shows the reconnect banner for about 6 s.
 *   ?wizard=1 opens the setup wizard; ?nowizard=1 keeps it closed in the firstrun scenario.
 *   ?shot=1 hides the mock controls (for documentation screenshots).
 *   Wi-Fi join: pick any network but FailNet (fails) in tab=wifi. The password 'wrongpass1' also fails.
 */
(function () {
  'use strict';
  try { sessionStorage.setItem('studio_token', 'mock-token'); } catch (e) { /* ignore */ }
  const q = new URLSearchParams(location.search);
  const sc = q.get('scenario') || 'normal';
  if (q.get('shot') === '1') document.addEventListener('DOMContentLoaded', () => { const m = document.getElementById('mockbar'); if (m) m.style.display = 'none'; });
  const M = window.__mock = {
    conn: sc === 'disconnected' || sc === 'nokey' || sc === 'firstrun' ? 'disconnected' : 'connected',
    nokey: sc === 'nokey', keyLogin: sc !== 'firstrun' && sc !== 'nokey', keyExists: sc !== 'firstrun', setupDone: sc !== 'firstrun', wifiAdded: [], jobs: {}, joinN: 0, estop: sc === 'estop', stale: sc === 'stale', lidarOff: sc === 'lidaroff', badClock: sc === 'badclock',
    docked: false, update: sc === 'update', t0: Date.now(), ap: sc === 'hotspot', laptopSsid: sc === 'hotspot' ? 'Turtlebot4' : 'PhoneHotspot',
  };
  const sources = new Set();
  const emit = ev => sources.forEach(s => s.onmessage && s.onmessage({ data: JSON.stringify(ev) }));
  const logEv = (level, text) => emit({ ev: 'log', level, text });
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const rnd = (a, b) => a + Math.random() * (b - a);

  /* ---- fake robot state ---- */
  const runs = {};      // run_id -> {run_id,name,pid,alive,started_wall,motion}
  let nextRun = 1, watchSeq = 1;
  const watches = {};
  const REMOTE = [
    ['motion_shapes.py', 14210, 'a1'], ['clearance_check.py', 6120, 'b2'], ['health_check.py', 5310, 'c3'], ['drive_test.py', 3340, 'd4'],
    ['motion_common.py', 4410, 'e5'], ['topic_rates.py', 2210, 'f6'], ['motion_test.sh', 1210, 'g7'], ['old_notes.py', 800, 'h8'], ['my_spin.py', 1900, 'm1'],
  ];
  const LOCAL = [
    ['motion_shapes.py', 14210, 'a1'], ['clearance_check.py', 6544, 'b2x'], ['health_check.py', 5310, 'c3'], ['drive_test.py', 3340, 'd4'],
    ['motion_common.py', 4410, 'e5'], ['topic_rates.py', 2210, 'f6'], ['motion_test.sh', 1210, 'g7'], ['wall_approach.py', 5902, 'n9'], ['keep_distance.py', 5120, 'n10'],
  ];
  const TOPICS = [
    ['/battery_state', 'sensor_msgs/msg/BatteryState', 1], ['/cmd_vel', 'geometry_msgs/msg/TwistStamped', 0], ['/dock_status', 'irobot_create_msgs/msg/DockStatus', 1],
    ['/hazard_detection', 'irobot_create_msgs/msg/HazardDetectionVector', 1], ['/imu', 'sensor_msgs/msg/Imu', 1], ['/ip', 'std_msgs/msg/String', 1],
    ['/odom', 'nav_msgs/msg/Odometry', 1], ['/scan', 'sensor_msgs/msg/LaserScan', 1], ['/tf', 'tf2_msgs/msg/TFMessage', 4], ['/wheel_status', 'irobot_create_msgs/msg/WheelStatus', 1],
    ['/diagnostics_toplevel_state', 'diagnostic_msgs/msg/DiagnosticStatus', 1], ['/hmi/display', 'irobot_create_msgs/msg/HmiDisplay', 1],
  ].map(([name, type, p]) => ({ name, types: [type], publishers: p, subscribers: 2 }));


  /* ---- v1.1 data: catalog, file contents, Wi-Fi ---- */
  const CATALOG = { version: 1, programs: {
    'motion_shapes.py': { title: 'Drive shapes (square, triangle, circle...)', summary: 'Drives the robot along a shape using its odometry. You will see it move, turn and stop where it started.', moves: true, needs_undock: true, safe_on_dock: false, category: 'motion',
      args: [{ name: 'shape', help: 'square, triangle, rotate, back_and_forth or figure_eight' }, { name: '--side', help: 'side length in metres (default 0.40, max 1.0)' }, { name: '--yes', help: 'skip the "area clear?" question (needed when run from Studio)' }],
      examples: [{ args: 'square --side 0.3 --yes', what: 'drives a 30 cm square' }, { args: 'rotate --yes', what: 'turns on the spot' }],
      stop: 'Press E-STOP, Ctrl+C, or create the ~/STOP file. It also stops by itself after a time limit.', notes: ['Undock first.', 'Lidar must be on to see obstacles.'], doc: '../../examples/README.md#motion_shapespy-drive-a-square-triangle-circle-and-more' },
    'clearance_check.py': { title: 'Check the space around the robot', summary: 'Reads the lidar and tells you how much free space there is ahead, left, right and behind. It never moves the robot.', moves: false, needs_undock: true, safe_on_dock: false, category: 'sensors', args: [], examples: [{ args: '', what: 'prints the distances once' }], stop: 'Ends by itself.', notes: ['The lidar is off while docked, so undock first.'], doc: 'https://example.org/docs' },
    'health_check.py': { title: 'Robot health check', summary: 'Checks ROS, the sensors and the clock. Safe to run any time.', moves: false, needs_undock: false, safe_on_dock: true, category: 'diagnostics', args: [], examples: [], stop: 'Ends by itself.', notes: [] },
    'drive_test.py': { title: 'Drive test', summary: 'A short straight drive to check that the wheels work.', moves: true, needs_undock: true, safe_on_dock: false, category: 'motion', args: [{ name: '--yes', help: 'skip the question' }], examples: [{ args: '--yes', what: 'drives about 20 cm forward' }], stop: 'E-STOP, Ctrl+C or ~/STOP.', notes: [] },
    'motion_common.py': { title: 'Shared helper code', summary: 'Code used by the other motion programs. It is not run directly.', moves: false, needs_undock: false, safe_on_dock: true, category: 'helper', args: [], examples: [], stop: 'Not run directly.', notes: [] },
  }, templates: ['my_first_program.py', 'spin_in_place.py'] };
  CATALOG.programs['spin_in_place.py'] = { title: 'Template: spin in place', summary: 'Turns the robot on the spot by a number of turns, then stops. Start here for your own motion code.', moves: true, needs_undock: true, safe_on_dock: false, category: 'template', args: [{ name: '--turns', help: 'number of turns (default 1.0)' }, { name: '--speed', help: 'rad/s, max 1.0' }], examples: [{ args: '--turns 1 --speed 0.5', what: 'one slow turn' }], stop: 'E-STOP, Ctrl+C, ~/STOP, or when the turns are done.', notes: [] };
  CATALOG.programs['my_first_program.py'] = { title: 'Template: my first program', summary: 'Prints the battery, dock state and position for 10 seconds. It does not move.', moves: false, needs_undock: false, safe_on_dock: true, category: 'template', args: [], examples: [], stop: 'Ends by itself after 10 s.', notes: [] };
  const FILES = {
    'my_spin.py': '#!/usr/bin/env python3\n"""My own spin test."""\nimport rclpy\nfrom geometry_msgs.msg import TwistStamped\n\n\ndef main():\n    rclpy.init()\n    node = rclpy.create_node("my_spin")\n    pub = node.create_publisher(TwistStamped, "/cmd_vel", 10)\n    msg = TwistStamped()\n    msg.twist.angular.z = 0.5  # rad/s, left\n    for _ in range(20):\n        pub.publish(msg)\n    msg.twist.angular.z = 0.0\n    pub.publish(msg)\n\n\nmain()\n',
  };
  const sha = {};
  let shaN = 0;
  const textOf = n => FILES[n] !== undefined ? FILES[n] : '#!/usr/bin/env python3\n"""' + n + ' (mock file)"""\nprint("hello")\n';
  const shaOf = n => sha[n] || (sha[n] = 'sha' + (++shaN));
  const DESCRIBE = () => REMOTE.filter(r => /\.(py|sh)$/.test(r[0])).map(([name, size]) => ({ name, size, mtime: 1790000000,
    docstring: name === 'my_spin.py' ? 'My own spin test.' : (CATALOG.programs[name] ? CATALOG.programs[name].summary : ''), usage: name === 'my_spin.py' ? [] : [],
    moves_detected: name === 'my_spin.py' || (CATALOG.programs[name] ? CATALOG.programs[name].moves : false), moves_reasons: name === 'my_spin.py' ? ['cmd_vel', 'TwistStamped'] : [] }));
  const SCAN = [{ ssid: 'HomeNet', signal: 70, security: 'WPA2', chan: 6 }, { ssid: 'Students', signal: 55, security: 'WPA2', chan: 36 }, { ssid: 'eduroam', signal: 48, security: 'WPA2 802.1X', chan: 11 },
    { ssid: 'CafeFree', signal: 40, security: '--', chan: 1 }, { ssid: 'FailNet', signal: 30, security: 'WPA2', chan: 3 }, { ssid: 'PhoneHotspot', signal: 62, security: 'WPA2 WPA3', chan: 44 }, { ssid: 'OnlyWpa3', signal: 35, security: 'WPA3', chan: 52 }];
  const curSsid = () => M.joined || 'HomeNet';
  const WIFI = () => ({ ok: true,
    wlan0: M.ap ? { state: 'connected', connection: 'netplan-wlan0-Turtlebot4', mode: 'ap', ssid: 'Turtlebot4', ip: '10.42.0.1', signal_dbm: null, powersave: null }
      : { state: 'connected', connection: curSsid(), mode: 'infrastructure', ssid: curSsid(), ip: M.joined ? M.joinedIp : '192.168.50.12', signal_dbm: -57, powersave: 'disable' },
    saved: [{ name: 'netplan-wlan0-Turtlebot4', ssid: 'Turtlebot4', mode: 'ap', autoconnect: true, priority: 0, powersave: null, active: !!M.ap },
      { name: 'HomeNet', ssid: 'HomeNet', mode: 'infrastructure', autoconnect: true, priority: 10, powersave: 'disable', active: !M.ap && curSsid() === 'HomeNet' },
      { name: 'netplan-eth0', ssid: null, mode: null, autoconnect: true, priority: 0, powersave: null, active: true }]
      .concat(M.wifiAdded.map(n => ({ name: n, ssid: n, mode: 'infrastructure', autoconnect: true, priority: 10, powersave: 'disable', active: !M.ap && curSsid() === n }))),
    scan: M.ap ? [] : SCAN,
    scan_note: M.ap ? 'the robot cannot scan while it runs its hotspot' : undefined });

  function startRun(name, args, motion) {
    const id = 'r' + nextRun++;
    const r = runs[id] = { run_id: id, name, pid: 4000 + nextRun * 7, alive: true, started_wall: Date.now() / 1000, motion };
    emit({ ev: 'run_output', run_id: id, lines: [`$ python3 -u ${name} ${args.join(' ')}`, 'ROS 2 Jazzy, domain 0', 'odometry ok (rate 19.8 Hz), scan ok (7.7 Hz)', 'clearance ahead 1.84 m, left 0.92 m, right 1.10 m'] });
    let step = 0;
    const iv = setInterval(() => {
      step++;
      emit({ ev: 'run_output', run_id: id, lines: [`step ${step}: moving 0.30 m at 0.10 m/s, odom age ${(rnd(0.02, 0.2)).toFixed(2)} s`, `  pose x=${(step * 0.3).toFixed(2)} y=0.00 yaw=0.0 deg`] });
      if (step >= (name === 'motion_shapes.py' ? 400 : 6)) { clearInterval(iv); r.alive = false; emit({ ev: 'run_output', run_id: id, lines: ['done.'] }); emit({ ev: 'run_exit', run_id: id, code: 0 }); }
      if (!r.alive) clearInterval(iv);
    }, 700);
    r.timer = iv;
    return r;
  }
  function stopRuns(which) {
    const out = [];
    Object.values(runs).forEach(r => { if (r.alive && (which === 'all' || which === r.run_id)) { r.alive = false; clearInterval(r.timer); out.push(r.run_id); emit({ ev: 'run_output', run_id: r.run_id, lines: ['^C received, stopping (zero velocity sent)'] }); emit({ ev: 'run_exit', run_id: r.run_id, code: -2 }); } });
    return out;
  }

  function status() {
    const up = (Date.now() - M.t0) / 1000;
    const docked = M.docked, lidar = !docked && !M.lidarOff;
    return {
      ev: 'status', t: up, wall: Date.now() / 1000,
      battery: { percent: 76.4 - up / 600, voltage: 15.12, current_a: docked ? 0.5 : -0.8, charging: docked, full: false },
      dock: { is_docked: docked, dock_visible: docked },
      odom: { x: 1.23, y: -0.42, yaw_deg: 87.5, vx: 0.0, wz: 0.0, age_s: sc === 'odomold' ? 0.9 : rnd(0.02, 0.09), rate_hz: 19.8 },
      scan: { rate_hz: lidar ? 7.7 : null, front_m: lidar ? 1.84 : null, min_m: lidar ? 0.62 : null, age_s: lidar ? 0.05 : null },
      hazards: [],
      estop: { on: M.estop, source: M.estop ? 'app' : null },
      system: { cpu_pct: rnd(18, 34), load1: 0.82, temp_c: 58.2, throttled: '0x0', mem_used_mb: 1210, mem_total_mb: 3800, disk_free_gb: 21.4, uptime_s: 86400 * 2 + 3600 * 5 + up },
      net: { wifi_mode: 'client', ssid: 'HomeNet', signal_dbm: -57, link_quality: 70, addresses: { eth0: '192.168.185.3', wlan0: '192.168.50.12' }, powersave: 'disable', powersave_students: 'disable' },
      clock: M.badClock ? { synced: false, year: 1970 } : { synced: true, year: 2026 },
      ros_service: 'active',
      runs: Object.values(runs).map(r => ({ run_id: r.run_id, name: r.name, pid: r.pid, alive: r.alive, started_wall: r.started_wall, motion: r.motion })),
    };
  }
  function emitConn(state, extra) { emit({ ev: 'conn', state, host: '192.168.185.3', via: 'cable', ...extra }); }
  const CANDS = [
    { host: '192.168.185.3', label: 'cable', via: 'cable', reachable: true, ms: 3 },
    { host: 'turtlebot4.local', label: '', via: 'wifi', reachable: true, ms: 14 },
    { host: '10.42.0.1', label: 'robot hotspot', via: 'hotspot', reachable: false, ms: null },
    { host: 'fe80::da3a:ddff:fe12:3456%12', label: 'link-local', via: 'cable', reachable: true, ms: 5 },
  ];

  /* ---- bridge commands ---- */
  async function bridgeCmd(b) {
    switch (b.cmd) {
      case 'ping': return { ok: true, pong: true };
      case 'describe': return { ok: true, programs: DESCRIBE() };
      case 'read_file': { const t = textOf(b.path); return { ok: true, path: b.path, text: t, size: t.length, mtime: 1790000000, sha1: shaOf(b.path) }; }
      case 'write_file': {
        if (!b.overwrite && REMOTE.some(r => r[0] === b.path)) return { ok: false, error: 'file exists' };
        if (b.expect_sha1 && b.expect_sha1 !== shaOf(b.path)) return { ok: false, error: 'changed on the robot since you opened it' };
        if (b.overwrite && textOf(b.path) === b.text) return { ok: true, path: b.path, size: b.text.length, sha1: shaOf(b.path), backup: null, unchanged: true };
        FILES[b.path] = b.text; sha[b.path] = 'sha' + (++shaN);
        if (!REMOTE.some(r => r[0] === b.path)) REMOTE.push([b.path, b.text.length, sha[b.path]]);
        return { ok: true, path: b.path, size: b.text.length, sha1: sha[b.path], backup: b.overwrite ? b.path + '.bak' : null };
      }
      case 'wifi_info': return WIFI();
      case 'status_on': case 'status_off': return { ok: true };
      case 'ls': return { ok: true, dir: '/home/ubuntu/robot_code', files: REMOTE.map(([name, size, sha1]) => ({ name, size, mtime: 1790000000, is_dir: false, sha1 })).concat(b.recursive ? [{ name: 'lib/util.py', size: 900, mtime: 1790000000, is_dir: false, sha1: 'zz' }] : [{ name: 'logs', size: 0, mtime: 0, is_dir: true, sha1: null }]) };
      case 'topics': return { ok: true, topics: TOPICS };
      case 'watch': {
        if (Object.keys(watches).length >= 4) return { ok: false, error: 'max 4 watches' };
        const id = watchSeq++; let n = 0;
        watches[id] = setInterval(() => emit({ ev: 'msg', watch_id: id, topic: b.topic, t: n, rate_hz: 5.0, data: { header: { stamp: { sec: 1790000000 + n, nanosec: 120000000 }, frame_id: 'odom' }, pose: { pose: { position: { x: 1.23 + n * 0.001, y: -0.42, z: 0 }, orientation: { x: 0, y: 0, z: 0.69, w: 0.72 } } }, twist: { twist: { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } } } , ranges: [0.62, 0.63, '…(+688)'] } }) || n++, 400);
        return { ok: true, watch_id: id };
      }
      case 'unwatch': clearInterval(watches[b.watch_id]); delete watches[b.watch_id]; return { ok: true };
      case 'run': {
        if (b.motion && !b.confirmed) return { ok: false, error: 'motion needs confirmation' };
        if (M.estop) return { ok: false, error: 'e-stop/STOP file present: release first' };
        const r = startRun(b.path, b.args || [], !!b.motion);
        return { ok: true, run_id: r.run_id, pid: r.pid, log: '~/robot_code/logs/20261024_' + b.path + '.log' };
      }
      case 'stop': return { ok: true, stopped: stopRuns(b.run_id), how: {} };
      case 'estop': M.estop = true; stopRuns('all'); return { ok: true, steps: { zero_cmd_vel: 'sent', stop_file: 'created', programs: 'stopped', e_stop_service: { success: true, message: 'ok' }, cancel_goals: 'none' } };
      case 'estop_release': M.estop = false; return { ok: true };
      case 'undock': case 'dock': {
        if (!b.confirmed) return { ok: false, error: 'motion needs confirmation' };
        setTimeout(() => emit({ ev: 'action', name: b.cmd, state: 'accepted' }), 100);
        setTimeout(() => { M.docked = b.cmd === 'dock'; emit({ ev: 'action', name: b.cmd, state: 'succeeded' }); }, 2500);
        return { ok: true };
      }
      case 'lidar': M.lidarOff = !b.on; return { ok: true };
      case 'health': return { ok: true, checks: [
        { name: 'ROS 2 daemon', ok: true, detail: 'Jazzy, rmw_fastrtps_cpp, domain 0' }, { name: '/odom publishing', ok: true, detail: '19.8 Hz' },
        { name: '/scan publishing', ok: !M.lidarOff, detail: M.lidarOff ? 'no messages: lidar motor off' : '7.7 Hz' },
        { name: 'Robot clock', ok: !M.badClock, detail: M.badClock ? 'not synced, year 1970' : 'synced' }, { name: 'Disk space', ok: true, detail: '21.4 GB free' },
        { name: 'Wi-Fi power save', ok: null, detail: 'not measurable over cable' }] };
      default: return { ok: false, error: 'unknown command ' + b.cmd };
    }
  }

  /* ---- fetch stub ---- */
  const DEFAULTS = { robot_hostname: 'turtlebot4', robot_user: 'ubuntu', hotspot_ssid: 'Turtlebot4', hotspot_addr: '10.42.0.1', cable_addr: '192.168.185.3' };
  const settings = { last_host: sc === 'firstrun' ? '' : '192.168.185.3', key_path: '', local_dir: 'C:\\Users\\student\\robot_code', remote_dir: '~/robot_code', motion_files: ['my_dance.py'], ...DEFAULTS, setup_done: sc !== 'firstrun',
    auto_reconnect: true, update_check: true, update_last: {}, update_dismissed: null };
  const UPD = () => ({ ok: true, current: '1.3', latest: M.update ? '1.4' : '1.3', newer: !!M.update, page: 'https://github.com/aniskoubaa/alfaisalx_students_projects/blob/main/TurtleBot/tools/studio/INSTALL.md',
    notes: M.update ? 'Mock: a newer version of Studio is available.' : '', checked: Date.now() / 1000, error: null, dismissed: settings.update_dismissed });
  let rcTimer = null;
  function stopMockReconnect() { clearTimeout(rcTimer); rcTimer = null; }
  M.toggleUpdate = () => { M.update = !M.update; if (M.update) emit({ ev: 'update', ...UPD() }); else emit({ ev: 'log', level: 'info', text: 'Mock: no newer version' }); };
  M.dropConn = () => { // like the real thing: reconnecting (attempt 1 in 2 s, attempt 2 in 4 s), then connected again
    if (M.conn !== 'connected') return;
    M.conn = 'reconnecting'; const since = Date.now() / 1000, delays = [2, 4]; let attempt = 0;
    const step = () => {
      const d = delays[Math.min(attempt, 1)]; attempt++;
      emit({ ev: 'conn', state: 'reconnecting', host: '192.168.185.3', via: 'cable', error: 'connection lost (connection ended)', attempt, next_in: d, since });
      rcTimer = setTimeout(() => { if (attempt < 2) step(); else { M.conn = 'connected'; emitConn('connected'); emit(hello()); emit(status()); } }, d * 1000);
    };
    step();
  };
  const BUILTIN = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBUILTINMOCKKEY00000000000000000000000';
  const FAKEKEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEMOCKROBOTKEY0000000000000000000000';
  const fp = key => 'SHA256:' + btoa(key.slice(-24)).replace(/=+$/, '');
  const trusted = [{ key: BUILTIN, label: 'Built-in key', builtin: true, fingerprint: fp(BUILTIN) }];
  const settingsAnswer = () => ({ ok: true, settings: { ...settings }, defaults: DEFAULTS, lab_host_key: BUILTIN, trusted: trusted.map(t => ({ ...t })) });
  const isTrusted = key => trusted.some(t => t.key === key);
  let vscodeOk = false;
  async function route(path, method, body) {
    if (path.startsWith('/api/templates/')) {
      const n = decodeURIComponent(path.slice(15));
      return '#!/usr/bin/env python3\n"""Template ' + n + ' (mock).\n\nMoves: see the catalog. Stop: E-STOP or Ctrl+C.\n"""\nSPEED = 0.5  # try changing this first\nprint("template", SPEED)\n';
    }
    switch (path) {
      case '/api/catalog': return { ok: true, ...CATALOG };
      case '/api/deep_discover': {
        if (M.searching) return { ok: false, error: 'already searching' };
        M.searching = true;
        for (let i = 1; i <= 10; i++) { await wait(200); emit({ ev: 'deep_progress', done: 254 * i / 10 | 0, total: 254 }); }
        const found = [{ host: '192.168.1.57', label: 'Your robot (identity confirmed)', via: 'wifi', reachable: true, ms: 4, identity: 'confirmed', pi: true },
          { host: '192.168.1.60', label: 'Raspberry Pi with ssh', via: 'wifi', reachable: true, ms: 6, identity: 'unknown', pi: true },
          { host: '192.168.1.1', label: 'Other device with ssh', via: 'wifi', reachable: true, ms: 2, identity: 'unknown', pi: false }];
        M.searching = false; emit({ ev: 'discover', candidates: found, deep: true }); return { ok: true, candidates: found };
      }
      case '/api/quit': return { ok: true };
      case '/api/reconnect_cancel': { const was = M.conn === 'reconnecting'; stopMockReconnect(); if (was) { M.conn = 'disconnected'; emit({ ev: 'conn', state: 'disconnected', host: '192.168.185.3', via: 'cable', error: null }); } return { ok: true, was_reconnecting: was }; }
      case '/api/diagnostics': return { ok: true, text: ['TurtleBot Studio diagnostics (mock)', '', '== Studio ==', 'Version: 1.3', 'Running as: built app', '', '== This computer ==',
        'Operating system: Windows-11-10.0.26200-SP0', 'Python: 3.13.3', 'ssh -V: OpenSSH_for_Windows_9.5p2', 'Wi-Fi name: PhoneHotspot', 'Wired connection up: yes', '', '== Connection ==',
        'State: ' + M.conn, 'Host: 192.168.185.3', '', '== Last 60 log lines ==', '12:00:01 info Studio started (mock)', '12:00:02 info psk=[redacted]'].join('\n') + '\n' };
      case '/api/update_status': return UPD();
      case '/api/check_updates': { await wait(400); return { ...UPD(), result: M.update ? 'newer' : 'latest' }; }
      case '/api/laptop_net': return { ok: true, os: 'Windows', wifi: M.laptopSsid ? { ssid: M.laptopSsid, signal_pct: 82, state: 'connected', interface: 'Wi-Fi' } : null, wired: [{ name: 'Ethernet', up: M.conn === 'connected', ipv4: M.conn === 'connected' ? ['192.168.185.10'] : [] }] };
      case '/api/robot_wifi_add': {
        if (!body.confirm) return { ok: false, error: 'confirmation required' };
        if (!/^[\x20-\x7e]{8,63}$/.test(body.psk || '')) return { ok: false, error: 'the Wi-Fi password must be 8 to 63 characters' };
        if (!body.ssid || body.ssid === 'Turtlebot4') return { ok: false, error: 'bad network name' };
        const nonce = Math.random().toString(16).slice(2).padEnd(32, '0');
        M.jobs[nonce] = { ssid: body.ssid, now: !!body.connect_now, fail: body.ssid === 'FailNet' || body.psk === 'wrongpass1', t: Date.now() };
        logEv('info', 'Wi-Fi add requested for ' + body.ssid + ' (mock, password not logged)');
        return { ok: true, nonce, fake: true };
      }
      case '/api/robot_wifi_status': {
        if (M.conn !== 'connected') return { ok: false, error: 'not connected' };
        const jb = M.jobs[body.nonce]; if (!jb) return { ok: true, secret: 'none', join: null };
        const age = Date.now() - jb.t;
        if (age < 1000) return { ok: true, secret: 'waiting', join: null };
        if (!jb.saved) { jb.saved = true; if (!jb.fail && !M.wifiAdded.includes(jb.ssid)) M.wifiAdded.push(jb.ssid); }
        if (!jb.now) return { ok: true, secret: 'fetched', join: null };
        if (age < 4000) return { ok: true, secret: 'fetched', join: { state: 'joining', ssid: jb.ssid, prev: 'HomeNet', t: jb.t } };
        if (jb.fail) { M.wifiAdded = M.wifiAdded.filter(n => n !== jb.ssid); return { ok: true, secret: 'fetched', join: { state: 'failed', ssid: jb.ssid, reason: 'could not join (wrong password or out of range)', fallback: 'HomeNet', fallback_ok: true, removed: true, t: jb.t + 4 } }; }
        if (!jb.ip) { jb.ip = '192.168.50.' + (20 + (++M.joinN)); M.joined = jb.ssid; M.joinedIp = jb.ip; }
        return { ok: true, secret: 'fetched', join: { state: 'joined', ssid: jb.ssid, ip: jb.ip, prev: 'HomeNet', t: jb.t + 4 } };
      }
      case '/api/setup_status': return { ok: true, ssh: { found: true, path: 'C:\\Windows\\System32\\OpenSSH\\ssh.exe', version: 'OpenSSH_for_Windows_9.5p1' }, keygen: { found: true }, keyscan: { found: true },
        key: { path: 'C:\\Users\\student\\.ssh\\turtlebot_studio_ed25519', exists: M.keyExists, fingerprint: M.keyExists ? 'SHA256:MockUserKeyFingerprint0000000000000000000000' : null },
        host: settings.last_host || null, setup_done: settings.setup_done, fake: true, os: 'Windows' };
      case '/api/create_key': { const created = !M.keyExists; M.keyExists = true; return { ok: true, path: 'C:\\Users\\student\\.ssh\\turtlebot_studio_ed25519', fingerprint: 'SHA256:MockUserKeyFingerprint0000000000000000000000', created }; }
      case '/api/scan_host_key': {
        if (!body.host) return { ok: false, error: 'no address' };
        if (/nope|bad/.test(body.host)) return { ok: false, error: 'no answer from ' + body.host + ' on port 22' };
        const t = trusted.find(x => x.key === FAKEKEY);
        return { ok: true, key: FAKEKEY, fingerprint: fp(FAKEKEY), trusted: !!t, label: t ? t.label : null };
      }
      case '/api/trust_host_key': {
        if (!body.confirm || !body.key) return { ok: false, error: 'confirmation required' };
        if (!isTrusted(body.key)) trusted.push({ key: body.key, label: body.label || 'Robot', added: Date.now() / 1000, fingerprint: fp(body.key) });
        return { ok: true };
      }
      case '/api/untrust_host_key': {
        if (!body.confirm) return { ok: false, error: 'confirmation required' };
        const i = trusted.findIndex(t => t.key === body.key); if (i < 0) return { ok: false, error: 'not trusted' };
        trusted.splice(i, 1); return { ok: true };
      }
      case '/api/test_login':
        await wait(500);
        if (!M.keyLogin) return { ok: false, kind: 'key_not_set_up', error: 'Permission denied (publickey)' };
        return { ok: true, hostname: 'fake-turtlebot4' };
      case '/api/robot_wifi_remove': logEv('info', 'Wi-Fi remove requested for ' + body.name); return { ok: true };
      case '/api/laptop_wifi_settings': return { ok: true };
      case '/api/join_hotspot': return { ok: false, needs_settings: true };
      case '/api/settings': if (method === 'POST') Object.keys(body).forEach(k => { if (k !== 'trusted_host_keys') settings[k] = body[k]; }); return settingsAnswer();
      case '/api/discover': emit({ ev: 'conn', state: 'discovering', host: null }); await wait(500); emit({ ev: 'discover', candidates: CANDS }); emitConn(M.conn === 'connected' ? 'connected' : 'disconnected', M.conn === 'connected' ? {} : { host: null, via: null }); return { ok: true, candidates: CANDS };
      case '/api/connect':
        emit({ ev: 'conn', state: 'connecting', host: body.host || '192.168.185.3', via: 'cable' }); await wait(700);
        if (M.nokey || !M.keyLogin) { emit({ ev: 'conn', state: 'error', host: '192.168.185.3', via: 'cable', error: 'key not set up (Permission denied (publickey))', kind: 'key_not_set_up' }); return { ok: false, error: 'key not set up' }; }
        M.conn = 'connected'; emitConn('connected'); emit(hello()); emit(status()); return { ok: true };
      case '/api/disconnect': stopMockReconnect(); M.conn = 'disconnected'; emit({ ev: 'conn', state: 'disconnected', host: null }); return { ok: true };
      case '/api/bridge': return M.conn !== 'connected' ? { ok: false, error: 'not connected' } : bridgeCmd(body);
      case '/api/estop': { const r = await bridgeCmd({ cmd: 'estop' }); emit(status()); return r; }
      case '/api/local_files': return { ok: true, files: LOCAL.map(([name, size, sha1]) => ({ name, size, sha1, mtime: 1790000000, is_dir: false })) };
      case '/api/sync': {
        if (body.dry_run) return { ok: true, uploaded: ['clearance_check.py', 'wall_approach.py', 'keep_distance.py'], skipped: 6, deleted: [] };
        emit({ ev: 'sync', state: 'running', uploaded: [], skipped: 0, deleted: [] }); await wait(900);
        const up = ['clearance_check.py', 'wall_approach.py', 'keep_distance.py'];
        emit({ ev: 'sync', state: 'done', uploaded: up, skipped: 6, deleted: [] }); return { ok: true, uploaded: up, skipped: 6, deleted: [] };
      }
      case '/api/open_terminal': logEv('info', 'Opened system terminal (mock)'); return { ok: true };
      case '/api/setup_key': logEv('info', 'Opened key-setup terminal (mock); on success the next Connect works'); setTimeout(() => { M.nokey = false; M.keyLogin = true; }, 3000); return { ok: true, note: 'Mock: no terminal. The key login works about 3 seconds after you press Open terminal.' };
      case '/api/open_vscode':
        if (!body.confirm_write_ssh_config && !vscodeOk) return { ok: false, needs_confirm: true, preview: '# >>> TurtleBot Studio >>>\nHost turtlebot-studio\n  HostName 192.168.185.3\n  User ubuntu\n  IdentityFile ~/.ssh/turtlebot4_ed25519\n  HostKeyAlias turtlebot4-lab\n  UserKnownHostsFile ~/.config/turtlebot-studio/known_hosts\n# <<< TurtleBot Studio <<<' };
        vscodeOk = true; return { ok: true };
      default: return { ok: false, error: 'mock: unknown endpoint ' + path };
    }
  }
  const realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = async function (url, opt = {}) {
    const path = String(url).split('?')[0];
    if (!path.startsWith('/api/')) return realFetch ? realFetch(url, opt) : Promise.reject(new Error('no network'));
    if (!opt.headers || opt.headers['X-Studio-Token'] !== 'mock-token') return new Response(JSON.stringify({ ok: false, error: 'bad token' }), { status: 403 });
    await wait(60);
    const body = opt.body ? JSON.parse(opt.body) : {};
    const j = await route(path, opt.method || 'GET', body);
    if (typeof j === 'string') return new Response(j, { status: 200, headers: { 'Content-Type': 'text/plain' } });
    return new Response(JSON.stringify(j), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };

  /* ---- EventSource stub ---- */
  function hello() { return { ev: 'hello', version: '1', bridge: 'robot_bridge', hostname: 'turtlebot4', ros: true, ros_distro: 'jazzy', rmw: 'rmw_fastrtps_cpp', domain: 0, python: '3.12.3', pid: 2311, fake: false }; }
  window.EventSource = function (url) {
    const s = { url, onmessage: null, onerror: null, onopen: null, close() { sources.delete(s); clearInterval(s.iv); } };
    sources.add(s);
    setTimeout(() => {
      if (M.sseDown) { s.onerror && s.onerror(); return; }
      s.onopen && s.onopen();
      emit({ ev: 'log', level: 'info', text: 'Studio started (mock)' });
      emit({ ev: 'log', level: 'warn', text: 'Robot clock is not synced' });
      if (M.nokey) { emit({ ev: 'conn', state: 'error', host: '192.168.185.3', via: 'cable', error: 'key not set up (Permission denied (publickey))', kind: 'key_not_set_up' }); return; }
      if (M.conn === 'connected') {
        emitConn('connected'); emit(hello()); emit(status());
        if (sc !== 'estop' && !Object.keys(runs).length && q.get('tab') !== 'dash') startRun('motion_shapes.py', ['square', '--yes'], true);
      } else emit({ ev: 'conn', state: 'disconnected', host: null });
      if (M.stale) return;
      s.iv = setInterval(() => { if (!M.stale && M.conn === 'connected') emit(status()); }, 1000);
    }, 120);
    return s;
  };

  M.toggleAp = () => { M.ap = !M.ap; };
  M.setStale = v => { M.stale = v; };
  M.toggleEstop = () => { M.estop = !M.estop; emit(status()); };
  M.toggleNokey = () => { M.nokey = !M.nokey; if (M.nokey) { M.conn = 'disconnected'; emit({ ev: 'conn', state: 'error', host: '192.168.185.3', via: 'cable', error: 'key not set up (Permission denied (publickey))', kind: 'key_not_set_up' }); } else { emit({ ev: 'conn', state: 'disconnected', host: null }); } };
  M.toggleLidar = () => { M.lidarOff = !M.lidarOff; emit(status()); };
  M.toggleClock = () => { M.badClock = !M.badClock; emit(status()); };
  M.toggleDock = () => { M.docked = !M.docked; emit(status()); };
  M.hostKeyError = () => { M.conn = 'disconnected'; emit({ ev: 'conn', state: 'error', host: '192.168.185.3', via: 'cable', error: 'robot host key is not trusted', kind: 'host_key' }); };
  M.dropSse = () => { M.sseDown = true; sources.forEach(s => { s.onerror && s.onerror(); }); setTimeout(() => { M.sseDown = false; }, 6000); };
  M.syncDemo = () => route('/api/sync', 'POST', { dry_run: false });
})();
