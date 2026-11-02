import { beforeEach, describe, expect, it } from 'vitest';
import { isEstopOn, isStale, remoteDir } from './selectors';
import { MAX_LOGS, MAX_RUN_LINES, initialState, reduceEvent, useStudio } from './store';
import type { StudioState } from './store';
import { resetStores } from '../test/helpers';

const fresh = (): StudioState => initialState();
const apply = (s: StudioState, ev: Parameters<typeof reduceEvent>[1], now = 1000) => ({
  ...s,
  ...reduceEvent(s, ev, now),
});

describe('reduceEvent', () => {
  it('tracks the connection and the reconnect countdown', () => {
    let s = apply(fresh(), {
      ev: 'conn',
      state: 'reconnecting',
      attempt: 2,
      next_in: 4,
      since: 500,
    });
    expect(s.conn.state).toBe('reconnecting');
    expect(s.reconn).toEqual({ since: 500, attempt: 2, nextAt: 1000 + 4000 });
    s = apply(s, { ev: 'conn', state: 'connected', host: 'h' });
    expect(s.reconn).toBeNull();
  });

  it('forgets the hello when the robot disconnects', () => {
    let s = apply(fresh(), { ev: 'hello', hostname: 'tb4' });
    expect(s.hello?.hostname).toBe('tb4');
    s = apply(s, { ev: 'conn', state: 'disconnected' });
    expect(s.hello).toBeNull();
  });

  it('stores the status snapshot and its time', () => {
    const s = apply(fresh(), { ev: 'status', battery: { percent: 50 } }, 4242);
    expect(s.status?.battery?.percent).toBe(50);
    expect(s.statusAt).toBe(4242);
  });

  it('lets Studio override the local e-stop flag once it reports a state', () => {
    let s = { ...fresh(), estopLocal: true };
    s = apply(s, { ev: 'status', estop: { on: null } });
    expect(s.estopLocal).toBe(true);
    s = apply(s, { ev: 'status', estop: { on: false } });
    expect(s.estopLocal).toBe(false);
  });

  it('merges runs from the status and keeps their output', () => {
    let s = apply(fresh(), { ev: 'run_output', run_id: 'r1', lines: ['a'] });
    s = apply(s, {
      ev: 'status',
      runs: [{ run_id: 'r1', name: 'x.py', pid: 7, alive: true, started_wall: 10, motion: true }],
    });
    expect(s.runs.r1).toMatchObject({
      name: 'x.py',
      pid: 7,
      alive: true,
      motion: true,
      lines: ['a'],
    });
    const before = s.runs;
    s = apply(s, {
      ev: 'status',
      runs: [{ run_id: 'r1', name: 'x.py', pid: 7, alive: true, started_wall: 10, motion: true }],
    });
    expect(s.runs).toBe(before);
  });

  it('appends output, caps it, and selects the first run', () => {
    let s = fresh();
    const lines = Array.from({ length: MAX_RUN_LINES + 50 }, (_, i) => 'l' + i);
    s = apply(s, { ev: 'run_output', run_id: 'r1', lines });
    expect(s.runs.r1?.lines).toHaveLength(MAX_RUN_LINES);
    expect(s.runs.r1?.lines.at(-1)).toBe('l' + (MAX_RUN_LINES + 49));
    expect(s.selectedRun).toBe('r1');
    s = apply(s, { ev: 'run_output', run_id: 'r2', lines: ['z'] });
    expect(s.selectedRun).toBe('r1');
  });

  it('marks a run finished with its exit code', () => {
    let s = apply(fresh(), { ev: 'run_output', run_id: 'r1', lines: ['a'] });
    s = apply(s, { ev: 'run_exit', run_id: 'r1', code: 2 });
    expect(s.runs.r1).toMatchObject({ alive: false, code: 2 });
  });

  it('keeps the newest logs only', () => {
    let s = fresh();
    for (let i = 0; i < MAX_LOGS + 5; i++)
      s = apply(s, { ev: 'log', level: 'warn', text: 'm' + i }, i);
    expect(s.logs).toHaveLength(MAX_LOGS);
    expect(s.logs.at(-1)?.text).toBe('m' + (MAX_LOGS + 4));
    expect(s.logs[0]?.level).toBe('warn');
  });

  it('marks the app as stopped on quit', () => {
    expect(apply(fresh(), { ev: 'quit' }).stopped).toBe(true);
  });

  it('keeps update info, discovery results and deep search progress', () => {
    let s = apply(fresh(), { ev: 'update', latest: '2.1', newer: true });
    expect(s.update).toMatchObject({ latest: '2.1', newer: true });
    s = apply(s, { ev: 'discover', candidates: [{ host: 'h', reachable: true }] });
    expect(s.candidates).toHaveLength(1);
    s = apply(s, { ev: 'deep_progress', done: 5, total: 10 });
    expect(s.deep).toEqual({ running: true, done: 5, total: 10 });
  });

  it('collects alerts without duplicates and follows teleop state', () => {
    const alert = {
      ev: 'alert' as const,
      id: 1,
      t: 1,
      severity: 'warn' as const,
      code: 'c',
      text: 't',
    };
    let s = apply(fresh(), alert);
    s = apply(s, alert);
    expect(s.alerts).toHaveLength(1);
    s = apply(s, { ev: 'teleop', armed: true });
    expect(s.teleopArmed).toBe(true);
  });

  it('ignores high-rate events (they go to listeners, not the store)', () => {
    const s = fresh();
    expect(
      reduceEvent(
        s,
        { ev: 'scan', t: 1, frame: 'base', angle_min: 0, angle_inc: 1, range_max: 5, ranges: [] },
        1,
      ),
    ).toEqual({});
    expect(reduceEvent(s, { ev: 'pose', t: 1, x: 0, y: 0, yaw: 0, vx: 0, wz: 0 }, 1)).toEqual({});
  });
});

describe('selectors', () => {
  beforeEach(resetStores);

  it('says the e-stop is on from the local flag or from Studio', () => {
    expect(isEstopOn(fresh())).toBe(false);
    expect(isEstopOn({ ...fresh(), estopLocal: true })).toBe(true);
    expect(isEstopOn(apply(fresh(), { ev: 'status', estop: { on: true } }))).toBe(true);
  });

  it('calls values old after 3 seconds, or when not connected', () => {
    const connected = apply(
      apply(fresh(), { ev: 'conn', state: 'connected' }),
      { ev: 'status' },
      1000,
    );
    expect(isStale(connected, 2000)).toBe(false);
    expect(isStale(connected, 4500)).toBe(true);
    expect(isStale(apply(connected, { ev: 'conn', state: 'disconnected' }), 1500)).toBe(true);
    expect(isStale(fresh(), 1)).toBe(true);
  });

  it('uses the saved robot folder or the default', () => {
    expect(remoteDir(fresh())).toBe('~/robot_code');
    useStudio.getState().setSettings({ settings: { remote_dir: '~/x' } });
    expect(remoteDir(useStudio.getState())).toBe('~/x');
  });
});

describe('store actions', () => {
  beforeEach(resetStores);

  it('adds a run the UI started and selects it', () => {
    useStudio.getState().addRun({ id: 'r9', name: 'a.py', pid: 3, motion: false });
    const s = useStudio.getState();
    expect(s.runs.r9).toMatchObject({ name: 'a.py', alive: true });
    expect(s.selectedRun).toBe('r9');
  });

  it('clears only the view of one run', () => {
    const s = useStudio.getState();
    s.dispatch({ ev: 'run_output', run_id: 'r1', lines: ['a', 'b'] });
    s.clearRunLines('r1');
    expect(useStudio.getState().runs.r1?.lines).toEqual([]);
  });

  it('records local log lines', () => {
    useStudio.getState().addLog('error', 'boom');
    expect(useStudio.getState().logs.at(-1)).toMatchObject({
      level: 'error',
      text: 'boom',
      local: true,
    });
  });
});
