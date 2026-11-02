import { useEffect } from 'react';
import { startHistoryFeed } from '../screens/charts/feed';
import { startAlertFeed } from '../screens/events/state';
import { onStudioEvent } from '../state/runtime';
import { CommandPalette } from './palette/CommandPalette';
import { usePalette } from './palette/paletteCommands';
import { ShortcutsDialog } from './palette/ShortcutsDialog';
import { onBridgeTeleop, releaseAll, watchSafety } from './teleop/driver';

const TYPING = 'input,textarea,select,[contenteditable="true"],[contenteditable=""],.cm-editor';

/**
 * Everything the 2.0 features need for the whole session, mounted once in the app:
 * the alert feed, the chart history feed, the driving safety watchers, the bridge's driving
 * events, and the palette and shortcut keys.
 */
export function FeatureHost() {
  useEffect(() => {
    const offAlerts = startAlertFeed();
    const offHistory = startHistoryFeed();
    const offSafety = watchSafety();
    const offTeleop = onStudioEvent('teleop', (ev) => onBridgeTeleop(ev.armed, ev.reason));
    return () => {
      offAlerts();
      offHistory();
      offSafety();
      offTeleop();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const p = usePalette.getState();
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        // Typing in the palette can hide a key release: drop any held drive key first.
        releaseAll();
        p.setOpen(!p.open);
        return;
      }
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const t = e.target instanceof Element ? e.target : null;
        if (t?.closest(TYPING)) return;
        e.preventDefault();
        p.setShortcuts(true);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <CommandPalette />
      <ShortcutsDialog />
    </>
  );
}
