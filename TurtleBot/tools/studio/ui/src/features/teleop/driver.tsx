/**
 * Connects the pure TeleopController to Studio: arming, the 10 Hz send loop, disarming.
 * One instance for the whole page. Every way out of driving ends in `disarm`.
 */
import { getTeleopLimits, putTeleopLimits, teleopArm, teleopSend } from '../../api/live';
import { confirm, notify } from '../../state/feedback';
import { useStudio } from '../../state/store';
import {
  DEFAULT_LIMITS,
  HARD_LIMITS,
  TeleopController,
  axesFromKeys,
  clampLimits,
} from './controller';
import type { DriveDir, Limits, TeleopCommand } from './controller';
import { useDrive } from './driveStore';

const TICK_MS = 50;
/** Three failed sends in a row (no answer from Studio) end driving. */
const MAX_FAILS = 3;

export const controller = new TeleopController(DEFAULT_LIMITS);

let timer: ReturnType<typeof setInterval> | null = null;
let inflight = false;
let fails = 0;
const keys = new Set<DriveDir>();
let stick = { forward: 0, turn: 0 };
let limitsTimer: ReturnType<typeof setTimeout> | null = null;

const drive = () => useDrive.getState();

export function isArmed(): boolean {
  return drive().phase === 'armed';
}

/** The keys and the stick together: the stick wins while it is away from the centre. */
function apply(): void {
  if (!controller.armed) return;
  const k = axesFromKeys(keys);
  const forward = stick.forward !== 0 || stick.turn !== 0 ? stick.forward : k.forward;
  const turn = stick.forward !== 0 || stick.turn !== 0 ? stick.turn : k.turn;
  const zero = controller.setInput(forward, turn, performance.now());
  if (zero) void send(zero);
  else pump();
}

function pump(): void {
  const cmd = controller.tick(performance.now());
  if (cmd) void send(cmd);
}

async function send(cmd: TeleopCommand): Promise<void> {
  const isZero = cmd.vx === 0 && cmd.wz === 0;
  // A zero always goes out. A moving command is dropped when the last one has not been answered.
  if (inflight && !isZero) return;
  inflight = true;
  try {
    const r = await teleopSend(cmd.vx, cmd.wz, cmd.seq);
    if (!controller.armed) return;
    if (r.ok) {
      fails = 0;
      if (!r.ignored) {
        drive().patch({
          echo: { vx: r.vx ?? cmd.vx, wz: r.wz ?? cmd.wz, seq: r.seq ?? cmd.seq, at: Date.now() },
          moving: (r.vx ?? cmd.vx) !== 0 || (r.wz ?? cmd.wz) !== 0,
        });
      }
    } else if (r.network) {
      if (++fails >= MAX_FAILS) disarm('Lost contact with Studio while driving.', 'error');
    } else {
      // The bridge refused: it is not armed any more. Show its words.
      disarm(r.error, 'warn', false);
    }
  } finally {
    inflight = false;
  }
}

function startLoop(): void {
  if (timer) return;
  timer = setInterval(pump, TICK_MS);
}
function stopLoop(): void {
  if (timer) clearInterval(timer);
  timer = null;
}

/** Ask for permission, then arm. Returns true when driving is armed. */
export async function requestArm(): Promise<boolean> {
  if (drive().phase !== 'off') return drive().phase === 'armed';
  const ok = await confirm({
    title: 'Arm driving?',
    body: (
      <>
        <p>
          <strong>Stand next to the robot with about 1 m of clear floor around it.</strong>
        </p>
        <p>
          While driving is armed, the keys W, A, S, D and the arrow keys, and the on-screen stick,
          move the robot. Releasing them stops it. Esc or Space is the E-STOP.
        </p>
      </>
    ),
    confirmLabel: 'Arm driving',
    tone: 'caution',
    requireCheck: 'I am next to the robot and about 1 m around it is clear',
  });
  if (!ok) return false;
  drive().patch({ phase: 'arming', reason: null, echo: null });
  const r = await teleopArm(true);
  if (!r.ok) {
    drive().patch({ phase: 'off', reason: r.error, reasonTone: 'error' });
    return false;
  }
  if (drive().phase !== 'arming') {
    // Something ended the request while it was in flight (E-STOP, blur). Make sure it is off.
    void teleopArm(false, 'cancelled');
    return false;
  }
  if (typeof r.max_linear === 'number' && typeof r.max_angular === 'number') {
    const l = clampLimits({ linear: r.max_linear, angular: r.max_angular });
    controller.setLimits(l);
    drive().patch({ limits: l });
  } else {
    controller.setLimits(drive().limits);
  }
  controller.arm();
  keys.clear();
  stick = { forward: 0, turn: 0 };
  fails = 0;
  drive().patch({ phase: 'armed', reason: null, armedAt: Date.now(), moving: false });
  startLoop();
  return true;
}

/**
 * Stop driving. Sends `teleop_arm {on:false}` (the bridge publishes zero) unless the bridge
 * already told us it is off (`remote` false).
 */
export function disarm(
  reason: string,
  tone: 'info' | 'warn' | 'error' = 'info',
  remote = true,
): void {
  const was = drive().phase;
  if (was === 'off') return;
  controller.disarm();
  keys.clear();
  stick = { forward: 0, turn: 0 };
  stopLoop();
  drive().patch({ phase: 'off', reason, reasonTone: tone, moving: false });
  if (remote) void teleopArm(false, reason.slice(0, 60));
  if (was === 'armed') notify(tone === 'info' ? 'info' : 'warn', 'Driving stopped. ' + reason);
}

/** The bridge reported a change in its arm state (event `teleop`). */
export function onBridgeTeleop(armed: boolean, reason: string | undefined): void {
  if (armed) return;
  if (drive().phase === 'off') return;
  disarm(reason ? reasonText(reason) : 'Driving was switched off.', 'warn', false);
}

/** Plain-English wording for the short reasons the bridge uses. Unknown text passes through. */
export function reasonText(reason: string): string {
  switch (reason) {
    case 'e-stop':
      return 'The E-STOP was pressed.';
    case 'disarmed':
      return 'Driving was switched off.';
    case 'bridge shutting down':
    case 'bridge ended':
      return 'The robot link ended.';
    default:
      return reason;
  }
}

/* ---------- inputs ---------- */

export function keyDown(dir: DriveDir): void {
  if (keys.has(dir)) return;
  keys.add(dir);
  apply();
}
export function keyUp(dir: DriveDir): void {
  if (!keys.delete(dir)) return;
  apply();
}
/** Every key and the stick let go at once: zero now. */
export function releaseAll(): void {
  keys.clear();
  stick = { forward: 0, turn: 0 };
  if (!controller.armed) return;
  const z = controller.release(performance.now());
  if (z) void send(z);
}
export function setStick(forward: number, turn: number): void {
  stick = { forward, turn };
  apply();
}

/* ---------- speed limits ---------- */

export async function loadLimits(): Promise<void> {
  const r = await getTeleopLimits();
  if (!r.ok) return;
  const caps = clampLimits({ linear: r.max_linear, angular: r.max_angular });
  const limits = clampLimits({ linear: r.linear, angular: r.angular }, caps);
  drive().patch({
    limits,
    caps: { linear: caps.linear, angular: caps.angular },
    limitsLoaded: true,
  });
  controller.setLimits(limits);
}

/** The sliders moved. The page uses the value at once and tells Studio shortly after. */
export function changeLimits(next: Limits): void {
  const l = clampLimits(next, drive().caps);
  drive().patch({ limits: l });
  controller.setLimits(l);
  if (limitsTimer) clearTimeout(limitsTimer);
  limitsTimer = setTimeout(() => {
    void putTeleopLimits(l.linear, l.angular).then((r) => {
      if (!r.ok) {
        notify('error', 'Could not save the speed limits: ' + r.error);
        return;
      }
      const saved = clampLimits({ linear: r.linear, angular: r.angular }, HARD_LIMITS);
      controller.setLimits(saved);
      drive().patch({ limits: saved });
    });
  }, 400);
}

/* ---------- safety watchers ---------- */

/**
 * End driving whenever the page cannot be trusted to see key releases: the window loses focus,
 * the tab is hidden, the stream to Studio is lost, the robot link drops, or the e-stop is on.
 * Returns the function that removes the watchers.
 */
export function watchSafety(): () => void {
  const onBlur = () => disarm('The window lost focus.');
  const onHidden = () => {
    if (document.visibilityState === 'hidden') disarm('The tab was hidden.');
  };
  window.addEventListener('blur', onBlur);
  document.addEventListener('visibilitychange', onHidden);
  const unsub = useStudio.subscribe((s, prev) => {
    if (s.sse.state === 'down' && prev.sse.state !== 'down')
      disarm('The link to Studio was lost.', 'warn');
    if (s.conn.state !== 'connected' && prev.conn.state === 'connected')
      disarm('The robot connection was lost.', 'warn');
    const estop = s.estopLocal || s.status?.estop?.on === true;
    const wasEstop = prev.estopLocal || prev.status?.estop?.on === true;
    if (estop && !wasEstop) disarm('The E-STOP was pressed.', 'warn');
    // Studio says driving is off while this page thinks it is on (and the snapshot is newer than the arm).
    if (
      drive().phase === 'armed' &&
      s.status?.teleop &&
      s.status.teleop.armed === false &&
      s.statusAt > drive().armedAt + 1500
    ) {
      disarm('Studio reports that driving is off.', 'warn', false);
    }
  });
  return () => {
    window.removeEventListener('blur', onBlur);
    document.removeEventListener('visibilitychange', onHidden);
    unsub();
  };
}

/** Test hook: put the module back to a clean start. */
export function resetDriver(): void {
  stopLoop();
  controller.disarm();
  keys.clear();
  stick = { forward: 0, turn: 0 };
  inflight = false;
  fails = 0;
  if (limitsTimer) clearTimeout(limitsTimer);
  limitsTimer = null;
  useDrive.getState().reset();
}
