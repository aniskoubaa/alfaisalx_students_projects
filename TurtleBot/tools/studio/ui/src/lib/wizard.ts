import type { CreateKeyAnswer, HostKeyScan, KeyInfo, SetupStatus } from '../api/setup-types';
import type { ApiResult } from '../api/types';

export type StepId = 1 | 2 | 3 | 4 | 5 | 6;
export const STEP_IDS: readonly StepId[] = [1, 2, 3, 4, 5, 6];
export type StepState = 'idle' | 'run' | 'ok' | 'bad' | 'wait';

export interface WizardState {
  st: Record<StepId, StepState>;
  /** A short message under each step (what happened, or what to do next). */
  msg: Record<StepId, string>;
  setup: SetupStatus | null;
  /** The address typed in step 2. */
  host: string;
  /** The address steps 3 to 6 were last run for. */
  hostUsed: string | null;
  scan: HostKeyScan | null;
  key: KeyInfo | null;
  /** "I compared the fingerprints and they are the same." */
  sure: boolean;
  label: string;
  hostname: string | null;
  busy: boolean;
}

export function initialWizard(host = ''): WizardState {
  const idle = (): Record<StepId, StepState> => ({
    1: 'idle',
    2: 'idle',
    3: 'idle',
    4: 'idle',
    5: 'idle',
    6: 'idle',
  });
  return {
    st: idle(),
    msg: { 1: '', 2: '', 3: '', 4: '', 5: '', 6: '' },
    setup: null,
    host,
    hostUsed: null,
    scan: null,
    key: null,
    sure: false,
    label: '',
    hostname: null,
    busy: false,
  };
}

/** A step can be used once the one before it is done. Step 6 may also run while step 5 waits for you. */
export function stepEnabled(w: WizardState, n: StepId): boolean {
  if (n === 1) return true;
  const prev = w.st[(n - 1) as StepId];
  return prev === 'ok' || (n === 6 && w.st[5] === 'wait');
}

export type OsName = 'win' | 'mac' | 'linux';
export function osOf(setup: SetupStatus | null, platform: string): OsName {
  const o = String(setup?.os || platform || '').toLowerCase();
  return /mac|darwin/.test(o) ? 'mac' : /win/.test(o) ? 'win' : 'linux';
}

export const KIND_HELP: Record<string, string> = {
  key_not_set_up:
    'The robot did not accept the key yet. Do step 5 (type the robot password in the terminal window), then test again.',
  host_key:
    "The robot's identity does not match the one you trusted. Redo step 3 and compare the fingerprints.",
  no_ssh: 'ssh was not found. Redo step 1.',
};

/** Whether an address can be used: not empty and without spaces. */
export function validWizardHost(h: string): boolean {
  const t = h.trim();
  return t.length > 0 && !/\s/.test(t);
}

export type WizardAction =
  | { type: 'begin'; n: StepId }
  | { type: 'end' }
  | { type: 'busy' }
  | { type: 'set_host'; host: string }
  | { type: 'set_label'; label: string }
  | { type: 'set_sure'; sure: boolean }
  | { type: 'check_done'; result: ApiResult<SetupStatus> }
  | { type: 'discover_done'; best: string | null }
  | { type: 'deep_done'; mine: string | null }
  | { type: 'use_addr' }
  | { type: 'scan_done'; result: ApiResult<HostKeyScan> }
  | { type: 'trust_done'; ok: boolean; error?: string; label: string }
  | { type: 'mkkey_done'; result: ApiResult<CreateKeyAnswer> }
  | { type: 'term_done'; result: ApiResult<{ note?: string }> }
  | {
      type: 'test_done';
      result: ApiResult<{ hostname?: string | null }>;
    };

function setStep(w: WizardState, n: StepId, state: StepState, msg = ''): WizardState {
  return { ...w, st: { ...w.st, [n]: state }, msg: { ...w.msg, [n]: msg } };
}

/** Forget the results that depend on the robot address (from step 3 on). */
export function resetFrom(w: WizardState): WizardState {
  return {
    ...w,
    scan: null,
    sure: false,
    hostname: null,
    st: { ...w.st, 3: 'idle', 5: w.st[5] === 'ok' ? 'idle' : w.st[5], 6: 'idle' },
    msg: { ...w.msg, 3: '', 6: '' },
  };
}

export function wizardReducer(w: WizardState, a: WizardAction): WizardState {
  switch (a.type) {
    case 'begin':
      return { ...setStep(w, a.n, 'run'), busy: true };
    case 'busy':
      return { ...w, busy: true };
    case 'end':
      return { ...w, busy: false };
    case 'set_host':
      return { ...w, host: a.host };
    case 'set_label':
      return { ...w, label: a.label };
    case 'set_sure':
      return { ...w, sure: a.sure };
    case 'check_done': {
      if (!a.result.ok) {
        return setStep(w, 1, 'bad', a.result.error || 'Could not read the setup status.');
      }
      const j = a.result;
      let next = setStep(
        { ...w, setup: j },
        1,
        j.ssh?.found ? 'ok' : 'bad',
        j.ssh?.found ? '' : 'ssh was not found.',
      );
      if (j.key?.exists) {
        next = setStep({ ...next, key: j.key }, 4, 'ok');
      } else if (next.st[4] !== 'ok') {
        next = setStep(next, 4, 'idle');
      }
      if (!next.host && j.host) next = { ...next, host: j.host };
      return next;
    }
    case 'discover_done': {
      let next = setStep(w, 2, 'idle');
      if (a.best && !next.host.trim()) next = { ...next, host: a.best };
      return next;
    }
    case 'deep_done': {
      let next = setStep(w, 2, 'idle');
      if (a.mine) next = { ...next, host: a.mine };
      return next;
    }
    case 'use_addr': {
      const h = w.host.trim();
      if (!validWizardHost(h)) {
        return setStep(w, 2, 'bad', 'Type an address without spaces, for example an IP address.');
      }
      let next = w;
      if (h !== w.hostUsed) next = resetFrom({ ...w, hostUsed: h });
      return setStep(next, 2, 'ok');
    }
    case 'scan_done': {
      if (!a.result.ok) {
        return {
          ...setStep(
            w,
            3,
            'bad',
            `${a.result.error || 'The robot did not answer.'} Is the address right and the robot on?`,
          ),
          scan: null,
        };
      }
      const scan = a.result;
      const base = { ...w, scan, sure: false };
      return scan.trusted
        ? setStep(base, 3, 'ok')
        : setStep(base, 3, 'wait', 'Not trusted yet. Compare the fingerprint, then trust it.');
    }
    case 'trust_done': {
      if (!a.ok || !w.scan) {
        return setStep(w, 3, 'bad', a.error || 'Could not save the trusted key.');
      }
      return setStep({ ...w, scan: { ...w.scan, trusted: true, label: a.label } }, 3, 'ok');
    }
    case 'mkkey_done': {
      if (!a.result.ok) {
        return setStep(w, 4, 'bad', a.result.error || 'Could not create the key.');
      }
      const r = a.result;
      return setStep(
        { ...w, key: { path: r.path, fingerprint: r.fingerprint, exists: true } },
        4,
        'ok',
        r.created ? 'Key created.' : 'This computer already had a key.',
      );
    }
    case 'term_done': {
      if (!a.result.ok) {
        return setStep(w, 5, 'bad', a.result.error || 'Could not open the terminal.');
      }
      return setStep(
        w,
        5,
        'wait',
        a.result.note ||
          'Terminal opened. Type the robot password there. When it says it is done, go on with step 6.',
      );
    }
    case 'test_done': {
      if (!a.result.ok) {
        const help = KIND_HELP[a.result.kind ?? ''] ?? '';
        let next = setStep(
          w,
          6,
          'bad',
          [a.result.error, help].filter(Boolean).join(' ') || 'The login failed.',
        );
        if (a.result.kind === 'key_not_set_up') next = { ...next, st: { ...next.st, 5: 'idle' } };
        if (a.result.kind === 'host_key') next = { ...next, st: { ...next.st, 3: 'idle' } };
        if (a.result.kind === 'no_ssh') next = { ...next, st: { ...next.st, 1: 'idle' } };
        return next;
      }
      const hostname = a.result.hostname || null;
      return setStep(setStep({ ...w, hostname }, 6, 'ok'), 5, 'ok');
    }
    default:
      return w;
  }
}
