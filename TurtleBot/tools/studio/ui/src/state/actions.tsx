import { api } from '../api';
import type { ApiResult, Settings } from '../api';
import { EstopSteps } from '../components/EstopSteps';
import { splitArgs } from '../lib/args';
import { isMotionProgram } from '../lib/motion';
import { cancelPendingConfirms, confirm, confirmMotion, inform, notify } from './feedback';
import { remoteDir } from './selectors';
import { useStudio } from './store';

const st = () => useStudio.getState();

/**
 * Report a failed call as a toast (unless quiet) and pass the result on.
 * `what` names the action in plain words, for example "Connect".
 */
export function report<T>(r: ApiResult<T>, what: string, quiet = false): ApiResult<T> {
  if (!r.ok && !quiet) notify('error', `${what}: ${r.error}`);
  return r;
}

/* ---------- settings, catalog ---------- */

export async function loadSettings(): Promise<boolean> {
  const r = await api().settings();
  if (!r.ok) {
    notify('error', 'Could not load settings: ' + r.error);
    return false;
  }
  st().setSettings(r);
  return true;
}

export async function saveSettings(patch: Settings, quiet = false): Promise<boolean> {
  const r = report(await api().saveSettings(patch), 'Save settings', quiet);
  if (!r.ok) return false;
  if (r.settings && Object.keys(r.settings).length) st().setSettings(r);
  else st().patchSettings(patch);
  return true;
}

export async function loadCatalog(): Promise<void> {
  const r = await api().catalog();
  if (r.ok) st().setCatalog(r.programs, r.templates);
}

export async function loadUpdateStatus(): Promise<void> {
  const r = await api().updateStatus();
  if (r.ok && r.newer) {
    const { ok: _ok, ...info } = r;
    void _ok;
    st().setUpdate(info);
  }
}

export async function dismissUpdate(): Promise<void> {
  const latest = st().update?.latest;
  if (latest) await saveSettings({ update_dismissed: latest });
}

/* ---------- connection ---------- */

export async function discover(): Promise<void> {
  const r = report(await api().discover(), 'Discover');
  if (r.ok && r.candidates) st().setCandidates(r.candidates);
}

export async function deepDiscover(): Promise<void> {
  if (st().deep.running) return;
  st().setDeep({ running: true, done: 0, total: 0 });
  const r = report(await api().deepDiscover(), 'Search the whole network');
  st().setDeep({ running: false, done: 0, total: 0 });
  if (!r.ok) return;
  st().setCandidates(r.candidates);
  const mine = r.candidates.find((c) => c.identity === 'confirmed');
  if (mine) notify('ok', `Found your robot at ${mine.host} (identity confirmed).`);
  else if (r.candidates.length) {
    notify(
      'info',
      `Found ${r.candidates.length} device(s) with ssh, but none is confirmed as your robot. Check the address on the robot's screen.`,
    );
  } else notify('info', 'No device with ssh answered on this network.');
}

export async function connect(host?: string): Promise<boolean> {
  const h = host?.trim();
  return report(await api().connect(h || undefined), 'Connect').ok;
}

export async function disconnect(): Promise<void> {
  report(await api().disconnect(), 'Disconnect');
}

export async function stopReconnecting(): Promise<void> {
  report(await api().reconnectCancel(), 'Stop reconnecting');
}

export async function setupKeyLogin(): Promise<void> {
  const ok = await confirm({
    title: 'Set up key login',
    body: (
      <p>
        A terminal window opens and asks for the <strong>robot password</strong>. Type it{' '}
        <strong>in that terminal window</strong>. This app never sees or stores it.
      </p>
    ),
    confirmLabel: 'Open terminal window',
  });
  if (!ok) return;
  const r = report(await api().setupKey(), 'Key setup');
  if (r.ok) notify('ok', 'Terminal opened. Finish the key setup there, then press Connect.');
}

export async function quitStudio(): Promise<void> {
  const ok = await confirm({
    title: 'Quit Studio?',
    body: (
      <p>
        Studio closes its connection to the robot and stops. Stop any robot program that is running
        first.
      </p>
    ),
    confirmLabel: 'Quit Studio',
    tone: 'danger',
  });
  if (!ok) return;
  const r = report(await api().quit(), 'Quit');
  if (r.ok) st().dispatch({ ev: 'quit' });
}

/** What to do the moment the robot connects (also after an automatic reconnect). */
export async function onConnected(wasReconnecting: boolean): Promise<void> {
  if (wasReconnecting) notify('ok', 'Reconnected.');
  await api().bridge('status_on', { period: 1.0 });
  await loadPrograms();
}

/* ---------- e-stop ---------- */

let estopBusy = false;

export async function triggerEstop(): Promise<void> {
  if (estopBusy) return;
  estopBusy = true;
  cancelPendingConfirms();
  st().setEstopLocal(true);
  try {
    const r = await api().estop();
    st().addLog(r.ok ? 'warn' : 'error', 'E-stop sent' + (r.ok ? '' : ': ' + r.error), true);
    void inform({
      key: 'estop-result',
      title: r.ok ? 'E-stop sent' : 'The e-stop may have failed',
      tone: r.ok ? 'primary' : 'danger',
      body: r.ok ? (
        <>
          <p>Drive motors should be off. Check that the robot has stopped.</p>
          <EstopSteps steps={r} />
        </>
      ) : (
        <p>{r.error} Hold the robot or switch off its power if it still moves.</p>
      ),
    });
  } finally {
    estopBusy = false;
  }
}

export async function releaseEstop(): Promise<void> {
  const ok = await confirm({
    title: 'Release the e-stop?',
    body: (
      <p>
        This turns drive power back on. Release only when the area around the robot is clear and the
        cause is fixed.
      </p>
    ),
    confirmLabel: 'Release e-stop',
    tone: 'danger',
  });
  if (!ok) return;
  const r = report(await api().bridge('estop_release'), 'Release e-stop');
  if (r.ok) {
    st().setEstopLocal(false);
    notify('ok', 'E-stop released.');
  }
}

/* ---------- dock, lidar ---------- */

export async function dockAction(cmd: 'undock' | 'dock'): Promise<void> {
  const label = cmd === 'undock' ? 'Undock' : 'Dock';
  const ok = await confirmMotion(
    <p>
      <strong>{label}</strong>. The robot will move by itself. Is the area clear?
    </p>,
  );
  if (!ok) return;
  const r = report(await api().bridge(cmd, { confirmed: true }), label);
  if (r.ok) notify('info', `${label} started.`);
}

export async function startLidar(): Promise<void> {
  const r = report(await api().bridge('lidar', { on: true }), 'Start lidar motor');
  if (r.ok) notify('ok', 'Lidar motor start sent.');
}

/* ---------- programs ---------- */

export async function loadPrograms(): Promise<void> {
  if (st().conn.state !== 'connected') return;
  const r = report(await api().bridge('ls', { dir: remoteDir(st()) }), 'List programs');
  if (r.ok) {
    const files = (r.files ?? [])
      .filter((f) => !f.is_dir && /\.(py|sh)$/.test(f.name))
      .sort((a, b) => a.name.localeCompare(b.name));
    st().setFiles(files);
  }
  await loadDescribe();
}

export async function loadDescribe(): Promise<void> {
  if (st().conn.state !== 'connected') return;
  const r = await api().bridge('describe', { dir: remoteDir(st()) });
  if (r.ok) st().setDesc(r.programs ?? []);
}

export function motionOf(name: string): boolean {
  const s = st();
  return isMotionProgram(name, s.catalog, s.desc, s.settings.motion_files ?? []);
}

/** Returns true when the program started. */
export async function runProgram(name: string, argStr: string): Promise<boolean> {
  let args: string[];
  try {
    args = splitArgs(argStr);
  } catch (e) {
    notify('error', e instanceof Error ? e.message : 'The arguments could not be read.');
    return false;
  }
  if (!st().catalog[name] && !st().desc[name]) await loadDescribe();
  const motion = motionOf(name);
  if (motion) {
    const ok = await confirmMotion(
      <p>
        <strong>{name}</strong> moves the robot
        {args.length ? (
          <>
            {' '}
            with arguments <code>{args.join(' ')}</code>
          </>
        ) : null}
        .
      </p>,
    );
    if (!ok) return false;
  }
  const r = report(
    await api().bridge('run', {
      path: name,
      dir: remoteDir(st()),
      args,
      motion,
      confirmed: motion,
    }),
    'Run ' + name,
  );
  if (!r.ok || !r.run_id) return false;
  st().addRun({ id: r.run_id, name, pid: r.pid ?? null, motion });
  notify('ok', `Started ${name}.`);
  return true;
}

export async function stopRun(id: string): Promise<void> {
  const r = report(await api().bridge('stop', { run_id: id }), 'Stop');
  if (r.ok) {
    const n = r.stopped?.length ?? 0;
    notify('info', 'Stop sent' + (n ? ` (${n} run${n > 1 ? 's' : ''})` : '') + '.');
  }
}

export async function stopAllRuns(): Promise<void> {
  const r = report(await api().bridge('stop', { run_id: 'all' }), 'Stop all');
  if (r.ok) notify('info', 'Stop sent to all programs.');
}

/* ---------- VS Code ---------- */

export async function openVscode(): Promise<void> {
  let r = await api().openVscode();
  if (!r.ok && r.needs_confirm) {
    const ok = await confirm({
      title: 'Add a block to your ssh config?',
      body: (
        <>
          <p>
            VS Code needs this block in your ssh config file. It is only added; nothing existing is
            changed.
          </p>
          <pre className="pre-block">{r.preview ?? ''}</pre>
        </>
      ),
      confirmLabel: 'Add and open',
    });
    if (!ok) return;
    r = await api().openVscode(true);
  }
  if (!r.ok) {
    notify('error', 'VS Code: ' + r.error);
    return;
  }
  notify('ok', 'Opening VS Code.');
}
