import { create } from 'zustand';
import type {
  Alert,
  Candidate,
  CatalogEntry,
  CatalogTemplate,
  ConnEvent,
  HelloEvent,
  LogLevel,
  ProgramDescription,
  RemoteFile,
  RunSummary,
  Settings,
  SseStatus,
  StatusEvent,
  StudioEvent,
  SyncEvent,
  UpdateInfo,
  ActionEvent,
  TrustedKey,
} from '../api';

export const MAX_RUN_LINES = 2000;
export const MAX_LOGS = 500;
export const MAX_ALERTS = 200;

export interface LogEntry {
  id: number;
  level: LogLevel;
  text: string;
  /** Epoch milliseconds. */
  at: number;
  /** True when the UI wrote it (not Studio). */
  local: boolean;
}

export interface Run {
  id: string;
  name: string;
  pid: number | null;
  alive: boolean;
  code: number | null;
  started: number;
  motion: boolean;
  lines: string[];
}

export interface ReconnectInfo {
  since: number;
  attempt: number;
  /** Epoch milliseconds of the next try. */
  nextAt: number;
}

export interface StudioState {
  /** The live event stream between this page and Studio. */
  sse: SseStatus;
  /** True after Studio said it is quitting. */
  stopped: boolean;
  /** Connection between Studio and the robot. */
  conn: ConnEvent;
  reconn: ReconnectInfo | null;
  /** Epoch milliseconds when the robot connection last came up (0 = not connected). */
  connectedAt: number;
  hello: HelloEvent | null;
  status: StatusEvent | null;
  /** Epoch milliseconds of the last status snapshot (0 = none yet). */
  statusAt: number;
  /** Set the moment the E-STOP was pressed here, until Studio reports its state. */
  estopLocal: boolean;
  logs: LogEntry[];
  runs: Record<string, Run>;
  selectedRun: string | null;
  candidates: Candidate[];
  deep: { running: boolean; done: number; total: number };
  update: UpdateInfo | null;
  action: ActionEvent | null;
  sync: SyncEvent | null;
  alerts: Alert[];
  teleopArmed: boolean;

  settings: Settings;
  defaults: Record<string, string>;
  labKey: string | null;
  trusted: TrustedKey[];
  settingsLoaded: boolean;
  catalog: Record<string, CatalogEntry>;
  templates: CatalogTemplate[];
  /** Python and shell files in the robot's program folder. */
  files: RemoteFile[];
  filesLoaded: boolean;
  desc: Record<string, ProgramDescription>;
}

export interface StudioActions {
  dispatch(ev: StudioEvent, now?: number): void;
  setSse(s: SseStatus): void;
  setEstopLocal(v: boolean): void;
  addLog(level: LogLevel, text: string, local?: boolean, now?: number): void;
  clearRunLines(id: string): void;
  selectRun(id: string | null): void;
  setCandidates(c: Candidate[]): void;
  setDeep(d: StudioState['deep']): void;
  setUpdate(u: UpdateInfo | null): void;
  setSync(s: SyncEvent | null): void;
  setSettings(s: {
    settings?: Settings;
    defaults?: Record<string, string>;
    lab_host_key?: string | null;
    trusted?: TrustedKey[];
  }): void;
  patchSettings(p: Settings): void;
  setCatalog(programs: Record<string, CatalogEntry>, templates: CatalogTemplate[]): void;
  setFiles(files: RemoteFile[]): void;
  setDesc(list: ProgramDescription[]): void;
  /** Add a run the UI started, before Studio mentions it. */
  addRun(r: { id: string; name: string; pid?: number | null; motion: boolean }): void;
  reset(): void;
}

let logSeq = 0;

export const initialState = (): StudioState => ({
  sse: { state: 'connecting', attempt: 0, retryAt: null },
  stopped: false,
  conn: { ev: 'conn', state: 'disconnected' },
  reconn: null,
  connectedAt: 0,
  hello: null,
  status: null,
  statusAt: 0,
  estopLocal: false,
  logs: [],
  runs: {},
  selectedRun: null,
  candidates: [],
  deep: { running: false, done: 0, total: 0 },
  update: null,
  action: null,
  sync: null,
  alerts: [],
  teleopArmed: false,
  settings: {},
  defaults: {},
  labKey: null,
  trusted: [],
  settingsLoaded: false,
  catalog: {},
  templates: [],
  files: [],
  filesLoaded: false,
  desc: {},
});

function pushLog(
  logs: LogEntry[],
  level: LogLevel,
  text: string,
  local: boolean,
  now: number,
): LogEntry[] {
  const next = logs.concat({ id: ++logSeq, level, text, at: now, local });
  return next.length > MAX_LOGS ? next.slice(next.length - MAX_LOGS) : next;
}

function blankRun(id: string): Run {
  return { id, name: id, pid: null, alive: true, code: null, started: 0, motion: false, lines: [] };
}

function mergeRuns(runs: Record<string, Run>, list: RunSummary[]): Record<string, Run> {
  let out = runs;
  for (const x of list) {
    const r = out[x.run_id] ?? blankRun(x.run_id);
    const next: Run = {
      ...r,
      name: x.name ?? r.name,
      pid: x.pid ?? null,
      alive: !!x.alive,
      started: x.started_wall ?? r.started,
      motion: !!x.motion,
    };
    const same =
      out[x.run_id] &&
      r.name === next.name &&
      r.pid === next.pid &&
      r.alive === next.alive &&
      r.started === next.started &&
      r.motion === next.motion;
    if (same) continue;
    if (out === runs) out = { ...runs };
    out[x.run_id] = next;
  }
  return out;
}

/**
 * The reducer for one SSE event: returns the part of the state that changes.
 * Pure (time comes from `now`), so it is easy to test.
 */
export function reduceEvent(s: StudioState, ev: StudioEvent, now: number): Partial<StudioState> {
  switch (ev.ev) {
    case 'conn': {
      const patch: Partial<StudioState> = { conn: ev };
      patch.reconn =
        ev.state === 'reconnecting'
          ? {
              since: ev.since ?? now / 1000,
              attempt: ev.attempt ?? 1,
              nextAt: now + (ev.next_in ?? 0) * 1000,
            }
          : null;
      if (ev.state === 'disconnected') patch.hello = null;
      if (ev.state === 'connected') {
        if (s.conn.state !== 'connected' || !s.connectedAt) patch.connectedAt = now;
      } else if (ev.state !== 'reconnecting') {
        patch.connectedAt = 0;
      }
      return patch;
    }
    case 'hello':
      return { hello: ev };
    case 'status': {
      const patch: Partial<StudioState> = { status: ev, statusAt: now };
      if (ev.estop && ev.estop.on !== null && ev.estop.on !== undefined) patch.estopLocal = false;
      if (ev.runs) patch.runs = mergeRuns(s.runs, ev.runs);
      if (ev.teleop) patch.teleopArmed = ev.teleop.armed;
      return patch;
    }
    case 'discover':
      return { candidates: ev.candidates ?? [] };
    case 'deep_progress':
      return { deep: { running: true, done: ev.done, total: ev.total } };
    case 'update': {
      const { ev: _e, ...info } = ev;
      void _e;
      return { update: info };
    }
    case 'quit':
      return { stopped: true };
    case 'sync':
      return { sync: ev };
    case 'log':
      return { logs: pushLog(s.logs, ev.level ?? 'info', ev.text ?? '', false, now) };
    case 'run_output': {
      const r = s.runs[ev.run_id] ?? blankRun(ev.run_id);
      let lines = r.lines.concat(ev.lines ?? []);
      if (lines.length > MAX_RUN_LINES) lines = lines.slice(lines.length - MAX_RUN_LINES);
      return {
        runs: { ...s.runs, [ev.run_id]: { ...r, lines } },
        selectedRun: s.selectedRun ?? ev.run_id,
      };
    }
    case 'run_exit': {
      const r = s.runs[ev.run_id] ?? blankRun(ev.run_id);
      return { runs: { ...s.runs, [ev.run_id]: { ...r, alive: false, code: ev.code ?? null } } };
    }
    case 'action':
      return { action: ev };
    case 'alert': {
      const { ev: _e, ...alert } = ev;
      void _e;
      if (s.alerts.some((a) => a.id === alert.id)) return {};
      const alerts = s.alerts.concat(alert);
      return {
        alerts: alerts.length > MAX_ALERTS ? alerts.slice(alerts.length - MAX_ALERTS) : alerts,
      };
    }
    case 'teleop':
      return { teleopArmed: ev.armed };
    default:
      // msg, scan, pose: high-rate data. Screens subscribe to them directly.
      return {};
  }
}

export const useStudio = create<StudioState & StudioActions>()((set, get) => ({
  ...initialState(),
  dispatch: (ev, now = Date.now()) => set(reduceEvent(get(), ev, now)),
  setSse: (sse) => set({ sse }),
  setEstopLocal: (estopLocal) => set({ estopLocal }),
  addLog: (level, text, local = true, now = Date.now()) =>
    set({ logs: pushLog(get().logs, level, text, local, now) }),
  clearRunLines: (id) => {
    const r = get().runs[id];
    if (r) set({ runs: { ...get().runs, [id]: { ...r, lines: [] } } });
  },
  selectRun: (selectedRun) => set({ selectedRun }),
  setCandidates: (candidates) => set({ candidates }),
  setDeep: (deep) => set({ deep }),
  setUpdate: (update) => set({ update }),
  setSync: (sync) => set({ sync }),
  setSettings: (a) => {
    const patch: Partial<StudioState> = { settingsLoaded: true };
    if (a.settings) patch.settings = a.settings;
    if (a.defaults) patch.defaults = a.defaults;
    if (a.lab_host_key !== undefined) patch.labKey = a.lab_host_key;
    if (a.trusted) patch.trusted = a.trusted;
    set(patch);
  },
  patchSettings: (p) => set({ settings: { ...get().settings, ...p } }),
  setCatalog: (catalog, templates) => set({ catalog, templates }),
  setFiles: (files) => set({ files, filesLoaded: true }),
  setDesc: (list) => set({ desc: Object.fromEntries(list.map((p) => [p.name, p])) }),
  addRun: ({ id, name, pid = null, motion }) => {
    const r = get().runs[id] ?? blankRun(id);
    set({
      runs: {
        ...get().runs,
        [id]: { ...r, name, pid, motion, alive: true, started: Date.now() / 1000 },
      },
      selectedRun: id,
    });
  },
  reset: () => set(initialState()),
}));
