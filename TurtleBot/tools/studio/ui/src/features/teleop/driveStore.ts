import { create } from 'zustand';
import { DEFAULT_LIMITS, HARD_LIMITS } from './controller';
import type { Limits } from './controller';

export type DrivePhase = 'off' | 'arming' | 'armed';

export interface DriveEcho {
  vx: number;
  wz: number;
  seq: number;
  /** Epoch milliseconds when the answer arrived. */
  at: number;
}

export interface DriveState {
  phase: DrivePhase;
  /** Why driving is off, or why arming was refused. Shown to the person as written. */
  reason: string | null;
  reasonTone: 'info' | 'warn' | 'error';
  /** The user's speed limits (what the sliders show). */
  limits: Limits;
  /** The ceilings the sliders may reach. */
  caps: Limits;
  limitsLoaded: boolean;
  echo: DriveEcho | null;
  armedAt: number;
  /** True while a non-zero command is being sent (drives the "moving" readout). */
  moving: boolean;
}

export interface DriveActions {
  patch(p: Partial<DriveState>): void;
  reset(): void;
}

export const initialDrive = (): DriveState => ({
  phase: 'off',
  reason: null,
  reasonTone: 'info',
  limits: DEFAULT_LIMITS,
  caps: HARD_LIMITS,
  limitsLoaded: false,
  echo: null,
  armedAt: 0,
  moving: false,
});

export const useDrive = create<DriveState & DriveActions>()((set) => ({
  ...initialDrive(),
  patch: (p) => set(p),
  reset: () => set(initialDrive()),
}));
