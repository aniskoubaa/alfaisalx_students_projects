import { setupApi } from '../api/setup';
import type { TrustedEntry } from '../api/setup-types';
import { loadSettings } from './actions';
import { confirm, notify } from './feedback';
import { useStudio } from './store';

export const trustedLabel = (t: TrustedEntry): string =>
  t.label || (t.builtin ? 'Built-in key' : 'Unnamed robot');

/** Stop trusting a robot after a warning. Returns true when it was removed. */
export async function untrustRobot(t: TrustedEntry): Promise<boolean> {
  const key = t.key || (t.builtin ? useStudio.getState().labKey : null);
  const label = trustedLabel(t);
  if (!key) {
    notify('error', 'This entry has no key to remove.');
    return false;
  }
  const ok = await confirm({
    title: 'Stop trusting this robot?',
    body: (
      <>
        <p>
          Studio will refuse to connect to <strong>{label}</strong> until you trust it again.
        </p>
        {t.fingerprint ? <p className="mono small">{t.fingerprint}</p> : null}
      </>
    ),
    confirmLabel: 'Remove',
    tone: 'danger',
  });
  if (!ok) return false;
  const r = await setupApi.untrustHostKey(key);
  if (!r.ok) {
    notify('error', `Remove trusted robot: ${r.error}`);
    return false;
  }
  notify('ok', `Removed ${label}.`);
  await loadSettings();
  return true;
}

/** Trust a pasted host key after a warning. Returns true when it was added. */
export async function trustPasted(key: string, label: string): Promise<boolean> {
  const k = key.trim();
  const name = label.trim() || 'My robot';
  if (!k) {
    notify('warn', 'Paste the robot key first (a line starting with ssh-ed25519).');
    return false;
  }
  const ok = await confirm({
    title: 'Trust this robot key?',
    body: (
      <div className="note note-warn">
        <p>
          Only do this for a TurtleBot that you own. If the key is wrong, someone else could pose as
          the robot and see everything you send. Compare its fingerprint with the one shown on the
          robot first.
        </p>
      </div>
    ),
    confirmLabel: 'Trust this key',
    tone: 'danger',
  });
  if (!ok) return false;
  const r = await setupApi.trustHostKey(k, name);
  if (!r.ok) {
    notify('error', `Trust key: ${r.error}`);
    return false;
  }
  notify('ok', `Trusted ${name}.`);
  await loadSettings();
  return true;
}
