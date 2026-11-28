import type { LucideIcon } from 'lucide-react';
import {
  Cable,
  ChartLine,
  Code,
  FolderSync,
  LayoutDashboard,
  ListOrdered,
  Map as MapIcon,
  Play,
  Radar,
  Route as RouteIcon,
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
  /** The sidebar group this screen sits in. */
  group?: NavGroup;
}

export type NavGroup = 'use' | 'make' | 'check' | 'setup';

/** Sidebar group headings, in order. */
export const NAV_GROUPS: ReadonlyArray<{ id: NavGroup; label: string }> = [
  { id: 'use', label: 'Use the robot' },
  { id: 'make', label: 'Make your own' },
  { id: 'check', label: 'Check on it' },
  { id: 'setup', label: 'Set up' },
];

/** Screens in sidebar order, grouped by `group`. Paths never change; only labels do. */
export const ROUTES: RouteDef[] = [
  { path: '/overview', label: 'Home', icon: LayoutDashboard, ready: true, group: 'use' },
  {
    path: '/live',
    label: 'Drive',
    icon: Radar,
    ready: true,
    group: 'use',
    blurb: 'A live lidar map with the robot and its path, plus joystick and keyboard driving.',
  },
  { path: '/programs', label: 'Programs', icon: Play, ready: true, group: 'use' },
  {
    path: '/maps',
    label: 'Maps',
    icon: MapIcon,
    ready: true,
    group: 'use',
    blurb: 'Build a map of a place, save it under a name and manage the saved maps.',
  },
  {
    path: '/routes',
    label: 'Routes',
    icon: RouteIcon,
    ready: true,
    group: 'use',
    blurb:
      'See the delivery routes on the robot, choose the current one and upload a planned route.',
  },
  { path: '/code', label: 'Code', icon: Code, ready: true, group: 'make' },
  {
    path: '/menu',
    label: 'Robot menu',
    icon: ListOrdered,
    ready: true,
    group: 'make',
    blurb:
      "Hide some of the robot's built-in menu entries and add your own programs to its screen.",
  },
  { path: '/files', label: 'Files', icon: FolderSync, ready: true, group: 'make' },
  {
    path: '/charts',
    label: 'Charts',
    icon: ChartLine,
    ready: true,
    group: 'check',
    blurb: 'Battery, speed, Wi-Fi signal and temperature over time, with a timeline of alerts.',
  },
  {
    path: '/logs',
    label: 'Logs',
    icon: ScrollText,
    ready: true,
    group: 'check',
    blurb: "Read the robot's own log with search and time filters.",
  },
  {
    path: '/topics',
    label: 'Topics',
    icon: Cable,
    ready: true,
    group: 'check',
    blurb: 'Browse ROS topics and watch their messages live.',
    classic: '/classic/?tab=topics',
  },
  {
    path: '/wifi',
    label: 'Wi-Fi',
    icon: Wifi,
    ready: true,
    group: 'setup',
    blurb: 'Teach the robot a Wi-Fi network and see which networks it can reach.',
    classic: '/classic/?tab=wifi',
  },
  {
    path: '/tools',
    label: 'Settings and help',
    icon: Terminal,
    ready: true,
    group: 'setup',
    blurb: 'Terminal, VS Code, diagnostics, settings and trusted robots.',
    classic: '/classic/?tab=tools',
  },
  { path: '/settings', label: 'Settings', icon: Settings, ready: true, nav: false },
];

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
