import { useDialogs } from './feedback';

/** Close the information dialog that was opened with this key (its promise then resolves). */
export function closeInfoDialog(key: string): void {
  const { stack, close } = useDialogs.getState();
  const d = stack.find((x) => x.kind === 'info' && x.key === key);
  if (!d || d.kind !== 'info') return;
  close(d);
  d.resolve();
}
