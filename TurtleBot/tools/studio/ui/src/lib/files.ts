import type { RemoteFile } from '../api';

export type CompareStatus = 'same' | 'changed' | 'new' | 'robot only';

export interface CompareRow {
  name: string;
  status: CompareStatus;
  local?: RemoteFile;
  robot?: RemoteFile;
}

/** Match local and robot files by name and say how they differ. */
export function compareFiles(local: RemoteFile[] | null, robot: RemoteFile[] | null): CompareRow[] {
  const L = new Map((local ?? []).map((f) => [f.name, f]));
  const R = new Map((robot ?? []).map((f) => [f.name, f]));
  const names = [...new Set([...L.keys(), ...R.keys()])].sort();
  return names.map((name) => {
    const a = L.get(name);
    const b = R.get(name);
    let status: CompareStatus;
    if (a && !b) status = 'new';
    else if (!a && b) status = 'robot only';
    else if (a && b && a.sha1 && b.sha1) status = a.sha1 === b.sha1 ? 'same' : 'changed';
    else status = a?.size === b?.size ? 'same' : 'changed';
    return { name, status, local: a, robot: b };
  });
}

export function countByStatus(rows: CompareRow[]): Record<CompareStatus, number> {
  const out: Record<CompareStatus, number> = { same: 0, changed: 0, new: 0, 'robot only': 0 };
  for (const r of rows) out[r.status] += 1;
  return out;
}

/** Only .py and .sh files can be run. */
export const isRunnable = (name: string): boolean => /\.(py|sh)$/.test(name);

export const NEW_NAME_RE = /^[A-Za-z0-9_-]+\.py$/;
