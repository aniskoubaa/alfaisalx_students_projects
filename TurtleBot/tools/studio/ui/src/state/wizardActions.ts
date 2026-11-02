import { setupApi } from '../api/setup';
import { initialWizard } from '../lib/wizard';
import type { StepId } from '../lib/wizard';
import { connect, deepDiscover, discover, loadSettings, saveSettings } from './actions';
import { notify } from './feedback';
import { useStudio } from './store';
import { useWizard, wizDispatch } from './wizardStore';

const wiz = () => useWizard.getState().w;

export function openWizard(): void {
  if (useWizard.getState().open) return;
  const host = useStudio.getState().settings.last_host ?? '';
  useWizard.setState({ open: true, w: initialWizard(host) });
  void wizAct('check');
}

export function closeWizard(): void {
  useWizard.setState({ open: false });
}

/** "Skip setup": remember that setup is done so the wizard does not open by itself again. */
export async function skipWizard(): Promise<void> {
  const ok = await saveSettings({ setup_done: true }, true);
  closeWizard();
  if (ok) {
    notify(
      'info',
      'Setup skipped. You can open the wizard again from the Overview or Tools screen.',
    );
  }
}

export type WizardCommand =
  | 'check'
  | 'discover'
  | 'deep'
  | 'useaddr'
  | 'scan'
  | 'trust'
  | 'mkkey'
  | 'term'
  | 'test'
  | 'connect';

async function runStep(n: StepId, fn: () => Promise<void>): Promise<void> {
  if (wiz().busy) return;
  wizDispatch({ type: 'begin', n });
  try {
    await fn();
  } finally {
    wizDispatch({ type: 'end' });
  }
}

/** Use the address typed in step 2 and remember it as the last robot address. */
export function applyWizardAddress(): void {
  wizDispatch({ type: 'use_addr' });
  const w = wiz();
  if (w.st[2] !== 'ok') return;
  const h = w.host.trim();
  void saveSettings({ last_host: h }, true).then((ok) => {
    if (!ok) useStudio.getState().patchSettings({ last_host: h });
  });
}

export async function wizAct(cmd: WizardCommand): Promise<void> {
  switch (cmd) {
    case 'check':
      return runStep(1, async () => {
        wizDispatch({ type: 'check_done', result: await setupApi.setupStatus() });
      });
    case 'discover':
      return runStep(2, async () => {
        await discover();
        const best = useStudio.getState().candidates.find((c) => c.reachable)?.host ?? null;
        wizDispatch({ type: 'discover_done', best });
      });
    case 'deep':
      return runStep(2, async () => {
        await deepDiscover();
        const mine =
          useStudio.getState().candidates.find((c) => c.identity === 'confirmed')?.host ?? null;
        wizDispatch({ type: 'deep_done', mine });
      });
    case 'useaddr':
      if (wiz().busy) return;
      applyWizardAddress();
      return;
    case 'scan':
      return runStep(3, async () => {
        wizDispatch({ type: 'scan_done', result: await setupApi.scanHostKey(wiz().host.trim()) });
      });
    case 'trust': {
      const { scan, sure, label } = wiz();
      if (!scan || !sure) return;
      return runStep(3, async () => {
        const name = label.trim() || 'My robot';
        const r = await setupApi.trustHostKey(scan.key, name);
        wizDispatch({
          type: 'trust_done',
          ok: r.ok,
          error: r.ok ? undefined : r.error,
          label: name,
        });
        if (r.ok) void loadSettings();
      });
    }
    case 'mkkey':
      return runStep(4, async () => {
        wizDispatch({ type: 'mkkey_done', result: await setupApi.createKey() });
      });
    case 'term':
      return runStep(5, async () => {
        wizDispatch({ type: 'term_done', result: await setupApi.setupKey(wiz().host.trim()) });
      });
    case 'test':
      return runStep(6, async () => {
        const r = await setupApi.testLogin(wiz().host.trim());
        wizDispatch({ type: 'test_done', result: r });
        if (r.ok) await saveSettings({ setup_done: true }, true);
      });
    case 'connect': {
      if (wiz().busy) return;
      wizDispatch({ type: 'busy' });
      try {
        const ok = await connect(wiz().host.trim());
        if (ok) closeWizard();
      } finally {
        wizDispatch({ type: 'end' });
      }
      return;
    }
    default:
      return;
  }
}
