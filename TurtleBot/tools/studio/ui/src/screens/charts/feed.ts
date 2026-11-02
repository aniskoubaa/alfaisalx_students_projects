import { api } from '../../api';
import { useStudio } from '../../state/store';
import { appendSample, emptyBuffer, fromAnswer, mergeBuffers, sampleFromStatus } from './history';
import type { HistoryBuffer } from './history';

/**
 * The history shown on the Charts screen: what Studio kept (loaded when the screen opens) plus
 * every status snapshot that arrived since. The feed runs for the whole session so the lines are
 * continuous when you come back to the screen.
 */
let buffer: HistoryBuffer = emptyBuffer();
let version = 0;
const listeners = new Set<() => void>();
let stop: (() => void) | null = null;

const bump = () => {
  version++;
  listeners.forEach((fn) => fn());
};

export const getBuffer = (): HistoryBuffer => buffer;
export const getVersion = (): number => version;
export function subscribeHistory(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Start appending a sample for every status snapshot. Safe to call twice. */
export function startHistoryFeed(): () => void {
  if (stop) return stop;
  const unsub = useStudio.subscribe((s, prev) => {
    if (s.status === prev.status || !s.status || s.conn.state !== 'connected') return;
    if (appendSample(buffer, s.statusAt / 1000, sampleFromStatus(s.status))) bump();
  });
  stop = () => {
    unsub();
    stop = null;
  };
  return stop;
}

export type LoadResult = { ok: true } | { ok: false; error: string };

/** Fetch the last 30 minutes from Studio and merge them with what was collected here. */
export async function loadHistory(): Promise<LoadResult> {
  const r = await api().history(30);
  if (!r.ok) return { ok: false, error: r.error };
  buffer = mergeBuffers(buffer, fromAnswer(r));
  bump();
  return { ok: true };
}

export function resetHistory(): void {
  buffer = emptyBuffer();
  bump();
}
