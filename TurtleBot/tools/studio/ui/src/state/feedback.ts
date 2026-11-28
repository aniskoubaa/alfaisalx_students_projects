import type { ReactNode } from 'react';
import { create } from 'zustand';
import { useStudio } from './store';

/* ---------- toasts ---------- */

export type ToastKind = 'ok' | 'info' | 'warn' | 'error';
export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastState {
  items: ToastItem[];
  push(kind: ToastKind, text: string): void;
  dismiss(id: number): void;
}

let toastSeq = 0;
export const useToasts = create<ToastState>()((set, get) => ({
  items: [],
  push: (kind, text) => {
    const next = get().items.concat({ id: ++toastSeq, kind, text });
    set({ items: next.length > 5 ? next.slice(next.length - 5) : next });
  },
  dismiss: (id) => set({ items: get().items.filter((t) => t.id !== id) }),
}));

/** Show a toast and keep a line in the activity log. */
export function notify(kind: ToastKind, text: string): void {
  useToasts.getState().push(kind, text);
  useStudio
    .getState()
    .addLog(kind === 'error' ? 'error' : kind === 'warn' ? 'warn' : 'info', text, true);
}

/* ---------- dialogs ---------- */

export type DialogTone = 'primary' | 'danger' | 'caution';

export interface ConfirmRequest {
  kind: 'confirm';
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone: DialogTone;
  /** When set, the confirm button stays disabled until this box is ticked. */
  requireCheck?: string;
  /** Show "The robot is on its dock. Undock it first." while the dock status says docked. */
  dockWarning?: boolean;
  resolve: (ok: boolean) => void;
}
export interface InfoRequest {
  kind: 'info';
  key?: string;
  title: string;
  body: ReactNode;
  closeLabel?: string;
  tone?: DialogTone;
  resolve: () => void;
}
export type DialogRequest = (ConfirmRequest | InfoRequest) & {
  /** Set when the dialog opens. Each dialog gets its own number, so a new dialog never reuses an old one's
   * ticked box, even when it has the same title (for example undock right after a movement question). */
  uid?: number;
};

let dialogSeq = 0;

interface DialogState {
  stack: DialogRequest[];
  open(d: DialogRequest): void;
  close(d: DialogRequest): void;
}

export const useDialogs = create<DialogState>()((set, get) => ({
  stack: [],
  open: (d) => {
    // An info dialog with a key replaces an earlier one with the same key.
    const rest = get().stack.filter(
      (x) => !(d.kind === 'info' && x.kind === 'info' && d.key && x.key === d.key),
    );
    d.uid = ++dialogSeq;
    set({ stack: rest.concat(d) });
  },
  close: (d) => set({ stack: get().stack.filter((x) => x !== d) }),
}));

export function confirm(opts: {
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: DialogTone;
  requireCheck?: string;
  dockWarning?: boolean;
}): Promise<boolean> {
  return new Promise((resolve) => {
    useDialogs.getState().open({
      kind: 'confirm',
      title: opts.title,
      body: opts.body,
      confirmLabel: opts.confirmLabel ?? 'Confirm',
      cancelLabel: opts.cancelLabel,
      tone: opts.tone ?? 'primary',
      requireCheck: opts.requireCheck,
      dockWarning: opts.dockWarning,
      resolve,
    });
  });
}

export function inform(opts: {
  title: string;
  body: ReactNode;
  key?: string;
  closeLabel?: string;
  tone?: DialogTone;
}): Promise<void> {
  return new Promise((resolve) => {
    useDialogs.getState().open({ kind: 'info', ...opts, resolve });
  });
}

/** The question every program that moves the robot must pass first. */
export function confirmMotion(
  what: ReactNode,
  opts: { dockWarning?: boolean } = {},
): Promise<boolean> {
  return confirm({
    title: 'Confirm robot movement',
    body: what,
    confirmLabel: 'Start moving',
    tone: 'caution',
    requireCheck: 'I am next to the robot and about 1 m around it is clear',
    dockWarning: opts.dockWarning ?? true,
  });
}

/**
 * Cancel every question that is waiting for an answer (each one resolves as "no").
 * The E-STOP calls this so a pending "start moving?" can never be answered afterwards.
 */
export function cancelPendingConfirms(): void {
  const { stack } = useDialogs.getState();
  for (const d of stack) if (d.kind === 'confirm') d.resolve(false);
  useDialogs.setState({ stack: stack.filter((d) => d.kind !== 'confirm') });
}
