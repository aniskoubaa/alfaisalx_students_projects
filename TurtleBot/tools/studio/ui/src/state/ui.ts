import { create } from 'zustand';

export type ThemeChoice = 'system' | 'light' | 'dark';
export const THEME_KEY = 'studio_theme';
export const NAV_KEY = 'studio_nav_collapsed';

function readStore(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeStore(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice lasts until the page closes */
  }
}

export function readTheme(): ThemeChoice {
  const v = readStore(THEME_KEY);
  return v === 'light' || v === 'dark' ? v : 'system';
}

/** Put the choice on <html>. 'system' removes the attribute so prefers-color-scheme decides. */
export function applyTheme(
  choice: ThemeChoice,
  root: HTMLElement = document.documentElement,
): void {
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);
}

interface UiState {
  theme: ThemeChoice;
  navCollapsed: boolean;
  navOpen: boolean;
  eventsOpen: boolean;
  setTheme(t: ThemeChoice): void;
  toggleNav(): void;
  setNavOpen(v: boolean): void;
  toggleEvents(): void;
}

export const useUi = create<UiState>()((set, get) => ({
  theme: readTheme(),
  navCollapsed: readStore(NAV_KEY) === '1',
  navOpen: false,
  eventsOpen: false,
  setTheme: (theme) => {
    writeStore(THEME_KEY, theme);
    applyTheme(theme);
    set({ theme });
  },
  toggleNav: () => {
    const navCollapsed = !get().navCollapsed;
    writeStore(NAV_KEY, navCollapsed ? '1' : '0');
    set({ navCollapsed });
  },
  setNavOpen: (navOpen) => set({ navOpen }),
  toggleEvents: () => set({ eventsOpen: !get().eventsOpen }),
}));
