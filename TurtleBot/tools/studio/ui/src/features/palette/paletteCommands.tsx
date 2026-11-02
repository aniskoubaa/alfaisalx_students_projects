import { create } from 'zustand';
import { api } from '../../api';
import type { HealthCheck } from '../../api';
import { Badge } from '../../components/ui';
import { connect, disconnect, discover, report } from '../../state/actions';
import { inform, notify } from '../../state/feedback';
import { ROUTES, navigate } from '../../state/router';
import { useStudio } from '../../state/store';
import type { StudioState } from '../../state/store';
import { useUi } from '../../state/ui';
import { buildDiagnostics } from './commands';
import type { Command } from './commands';

interface PaletteState {
  open: boolean;
  shortcuts: boolean;
  setOpen(v: boolean): void;
  setShortcuts(v: boolean): void;
}

export const usePalette = create<PaletteState>()((set) => ({
  open: false,
  shortcuts: false,
  setOpen: (open) => set({ open }),
  setShortcuts: (shortcuts) => set({ shortcuts }),
}));

async function runHealthCheck(): Promise<void> {
  const r = report(await api().bridge('health'), 'Health check');
  if (!r.ok) return;
  const checks: HealthCheck[] = r.checks ?? [];
  const bad = checks.filter((c) => c.ok === false).length;
  void inform({
    title: bad ? `Health check: ${bad} problem${bad > 1 ? 's' : ''}` : 'Health check: all good',
    body: (
      <ul className="plain">
        {checks.map((c) => (
          <li key={c.name}>
            <Badge tone={c.ok === true ? 'ok' : c.ok === false ? 'bad' : 'neutral'}>
              {c.ok === true ? 'OK' : c.ok === false ? 'Problem' : 'Unknown'}
            </Badge>{' '}
            <strong>{c.name}</strong>
            {c.detail ? <span className="dim"> {c.detail}</span> : null}
          </li>
        ))}
      </ul>
    ),
  });
}

async function copyDiagnostics(): Promise<void> {
  const text = buildDiagnostics(useStudio.getState());
  try {
    await navigator.clipboard.writeText(text);
    notify('ok', 'Diagnostics copied. Paste them into your message.');
  } catch {
    void inform({
      title: 'Copy diagnostics',
      body: <pre className="pre-block">{text}</pre>,
    });
  }
}

function toggleTheme(): void {
  const ui = useUi.getState();
  const dark =
    ui.theme === 'dark' ||
    (ui.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  ui.setTheme(dark ? 'light' : 'dark');
}

/** The commands for the current state. Motion is never in this list. */
export function paletteCommands(s: StudioState): Command[] {
  const connected = s.conn.state === 'connected';
  const settingsPath = ROUTES.some((r) => r.path === '/settings') ? '/settings' : '/tools';
  const go: Command[] = ROUTES.map((r) => ({
    id: 'go:' + r.path,
    label: 'Go to ' + r.label,
    group: 'Go to',
    keywords: r.path.slice(1),
    disabled: null,
    run: () => navigate(r.path),
  }));
  const actions: Command[] = [
    {
      id: 'discover',
      label: 'Discover robots',
      group: 'Actions',
      keywords: 'find search network scan',
      disabled: null,
      run: () => discover(),
    },
    {
      id: 'connect',
      label: 'Connect to the robot',
      group: 'Actions',
      keywords: 'link ssh',
      disabled: connected ? 'Already connected' : null,
      run: async () => {
        await connect();
      },
    },
    {
      id: 'disconnect',
      label: 'Disconnect from the robot',
      group: 'Actions',
      keywords: 'unlink',
      disabled: connected ? null : 'Not connected',
      run: () => disconnect(),
    },
    {
      id: 'health',
      label: 'Run health check',
      group: 'Actions',
      keywords: 'test diagnose',
      disabled: connected ? null : 'Connect first',
      run: runHealthCheck,
    },
    {
      id: 'diagnostics',
      label: 'Copy diagnostics',
      group: 'Actions',
      keywords: 'support report clipboard',
      disabled: null,
      run: copyDiagnostics,
    },
    {
      id: 'theme',
      label: 'Toggle theme',
      group: 'Actions',
      keywords: 'dark light colour mode',
      disabled: null,
      run: toggleTheme,
    },
    {
      id: 'settings',
      label: 'Open settings',
      group: 'Actions',
      keywords: 'preferences options',
      disabled: null,
      run: () => navigate(settingsPath),
    },
    {
      id: 'shortcuts',
      label: 'Show keyboard shortcuts',
      group: 'Actions',
      keywords: 'keys help',
      disabled: null,
      run: () => usePalette.getState().setShortcuts(true),
    },
  ];
  return [...go, ...actions];
}
