import { create } from 'zustand';
import { initialWizard, wizardReducer } from '../lib/wizard';
import type { WizardAction, WizardState } from '../lib/wizard';

export interface WizardStore {
  open: boolean;
  w: WizardState;
}

export const useWizard = create<WizardStore>()(() => ({ open: false, w: initialWizard() }));

/** Apply one step of the wizard's logic to the stored state. */
export function wizDispatch(a: WizardAction): void {
  useWizard.setState((s) => ({ w: wizardReducer(s.w, a) }));
}
