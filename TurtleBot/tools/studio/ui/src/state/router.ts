import type { LucideIcon } from 'lucide-react';
import {
  Cable,
  ChartLine,
  Code,
  FolderSync,
  LayoutDashboard,
  Play,
  Radar,
  ScrollText,
  Settings,
  Terminal,
  Wifi,
} from 'lucide-react';
import { useSyncExternalStore } from 'react';

export interface RouteDef {
  path: string;
  label: string;
  icon: LucideIcon;
  /** False for screens that arrive in a later build. */
  ready: boolean;
  /** False for a screen that is reached from another screen or the command list, not from the menu. */
  nav?: boolean;
  /** Shown on the "Coming in this build" screen. */
  blurb?: string;
  /** Where the same feature lives in the classic interface today. */
  classic?: string;
}

/** Sections in sidebar order. A gap in `GROUP_BREAKS` starts a new group. */
export const ROUTES: RouteDef[] = [
  { path: '/overview', label: 'Overview', icon: LayoutDashboard, ready: true },
  {
    path: '/live',
    label: 'Live',
    icon: Radar,
    ready: true,
    blurb: 'A live lidar map with the robot and its path, plus joystick and keyboard driving.',
  },
  { path: '/programs', label: 'Programs', icon: Play, ready: true },
  { path: '/code', label: 'Code', icon: Code, ready: true },
  { path: '/files', label: 'Files', icon: FolderSync, ready: true },
  {
    path: '/charts',
    label: 'Charts',
    icon: ChartLine,
    ready: true,
    blurb: 'Battery, speed, Wi-Fi signal and temperature over time, with a timeline of alerts.',
  },
  {
    path: '/logs',
    label: 'Logs',
    icon: ScrollText,
    ready: true,
    blurb: "Read the robot's own log with search and time filters.",
  },
  {
    path: '/wifi',
    label: 'Wi-Fi',
    icon: Wifi,
    ready: true,
    blurb: 'Teach the robot a Wi-Fi network and see which networks it can reach.',
    classic: '/classic/?tab=wifi',
  },
  {
    path: '/topics',
    label: 'Topics',
    icon: Cable,
    ready: true,
    blurb: 'Browse ROS topics and watch their messages live.',
    classic: '/classic/?tab=topics',
  },
  {
    path: '/tools',
    label: 'Tools',
    icon: Terminal,
    ready: true,
    blurb: 'Terminal, VS Code, diagnostics, settings and trusted robots.',
    classic: '/classic/?tab=tools',
  },
  { path: '/settings', label: 'Settings', icon: Settings, ready: true, nav: false },
];

/** Index in ROUTES where a visual gap goes before the item. */
export const GROUP_BREAKS: ReadonlySet<string> = new Set(['/programs', '/charts', '/wifi']);

export const DEFAULT_PATH = '/overview';

export function parseHash(hash: string): string {
  const p = hash.replace(/^#/, '').split('?')[0] ?? '';
  return ROUTES.some((r) => r.path === p) ? p : DEFAULT_PATH;
}

export function routeFor(path: string): RouteDef {
  return ROUTES.find((r) => r.path === path) ?? (ROUTES[0] as RouteDef);
}

function subscribe(cb: () => void): () => void {
  window.addEventListener('hashchange', cb);
  return () => window.removeEventListener('hashchange', cb);
}

export function useRoute(): RouteDef {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return routeFor(parseHash(hash));
}

export function navigate(path: string): void {
  if (window.location.hash !== '#' + path) window.location.hash = path;
}
