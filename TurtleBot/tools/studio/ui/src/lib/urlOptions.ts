import { ROUTES } from '../state/router';

/** The old tab names of the classic interface and the screens they became. */
const TAB_TO_PATH: Record<string, string> = {
  dash: '/overview',
  overview: '/overview',
  prog: '/programs',
  programs: '/programs',
  code: '/code',
  files: '/files',
  wifi: '/wifi',
  topics: '/topics',
  tools: '/tools',
  settings: '/settings',
};

export interface UrlOptions {
  /** ?theme=dark or ?theme=light: used for this page only, not saved. */
  theme: 'dark' | 'light' | null;
  /** ?tab=wifi and the like: the screen to open when the address has no screen yet. */
  path: string | null;
  /** ?wizard=1 opens the setup wizard. */
  wizard: boolean;
  /** ?nowizard stops the wizard from opening by itself. */
  noWizard: boolean;
}

export function parseUrlOptions(search: string, hash: string): UrlOptions {
  const qs = new URLSearchParams(search);
  const theme = qs.get('theme');
  const tab = (qs.get('tab') ?? '').toLowerCase();
  const mapped = TAB_TO_PATH[tab];
  const known = mapped && ROUTES.some((r) => r.path === mapped) ? mapped : null;
  return {
    theme: theme === 'dark' || theme === 'light' ? theme : null,
    path: hash.replace(/^#/, '') ? null : known,
    wizard: qs.get('wizard') === '1',
    noWizard: qs.has('nowizard'),
  };
}

/** Should the first-run wizard open by itself? */
export function shouldAutoOpenWizard(opts: UrlOptions, setupDone: boolean | undefined): boolean {
  if (opts.wizard) return true;
  return setupDone === false && !opts.noWizard;
}
