export interface EstopLine {
  label: string;
  ok: boolean | null;
}

const LABELS: Record<string, string> = {
  e_stop_service: 'Drive motors switched off',
  cancel_goals: 'Running robot actions cancelled',
  programs: 'Programs started by Studio stopped',
  stop_file: 'STOP file written',
  zero_cmd_vel: 'Zero velocity sent',
};

function pick(v: unknown): boolean | null {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'object' && v !== null) {
    const o = v as { success?: unknown; ok?: unknown };
    if (typeof o.success === 'boolean') return o.success;
    if (typeof o.ok === 'boolean') return o.ok;
  }
  return null;
}

/** Where the steps are in the answer: Studio wraps the bridge's answer (`bridge.steps`). */
export function findSteps(answer: unknown): Record<string, unknown> | null {
  if (typeof answer !== 'object' || answer === null) return null;
  const a = answer as { steps?: unknown; bridge?: unknown };
  if (typeof a.steps === 'object' && a.steps !== null) return a.steps as Record<string, unknown>;
  if (typeof a.bridge === 'object' && a.bridge !== null) return findSteps(a.bridge);
  return null;
}

/** One short line per e-stop step, so the answer reads as a checklist and not as raw data. */
export function estopLines(answer: unknown): EstopLine[] {
  const steps = findSteps(answer);
  if (!steps) return [];
  return Object.entries(steps).map(([k, v]) => ({
    label: LABELS[k] ?? k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()),
    ok: pick(v),
  }));
}
