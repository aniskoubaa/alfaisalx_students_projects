import { api } from '../api';
import { setupApi } from '../api/setup';
import { DiagnosticsBody } from '../screens/tools/DiagnosticsBody';
import { inform, notify } from './feedback';
import { saveSettings } from './actions';
import { useStudio } from './store';

export async function openTerminal(): Promise<void> {
  const r = await setupApi.openTerminal();
  if (r.ok) notify('ok', 'Terminal opened.');
  else notify('error', `Terminal: ${r.error}`);
}

/** Collect the diagnostics text and show it with Copy and Save as file. */
export async function showDiagnostics(): Promise<void> {
  const r = await setupApi.diagnostics();
  if (!r.ok) {
    notify('error', `Diagnostics: ${r.error}`);
    return;
  }
  void inform({
    key: 'diagnostics',
    title: 'Diagnostics',
    body: <DiagnosticsBody text={r.text} />,
  });
}

export type UpdateCheck =
  | { result: 'latest' }
  | { result: 'failed'; error: string }
  | { result: 'newer'; latest: string; page?: string };

/** Ask GitHub for the newest version. A newer one also brings the update banner back. */
export async function checkForUpdates(): Promise<UpdateCheck> {
  const r = await api().checkUpdates();
  if (!r.ok) return { result: 'failed', error: r.error };
  if (r.result === 'failed')
    return { result: 'failed', error: r.error || 'No answer from GitHub.' };
  if (r.result === 'latest' || !r.latest || r.newer === false) return { result: 'latest' };
  const { ok: _ok, result: _result, ...info } = r;
  void _ok;
  void _result;
  const s = useStudio.getState();
  s.setUpdate(info);
  if (s.settings.update_dismissed) await saveSettings({ update_dismissed: '' }, true);
  return { result: 'newer', latest: r.latest, page: r.page };
}
