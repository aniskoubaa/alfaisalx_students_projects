import { create } from 'zustand';
import { api } from '../../api';
import type { AlertSeverity } from '../../api';
import { notify } from '../../state/feedback';
import { onStudioEvent } from '../../state/runtime';
import { useStudio } from '../../state/store';
import { latestId, mergeAlerts, needsToast } from './alerts';

const SEEN_KEY = 'studio_alerts_seen';

function readSeen(): number | null {
  try {
    const v = window.localStorage.getItem(SEEN_KEY);
    const n = v === null ? NaN : Number(v);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}
function writeSeen(n: number): void {
  try {
    window.localStorage.setItem(SEEN_KEY, String(n));
  } catch {
    /* storage blocked: unread counts restart on reload */
  }
}

interface AlertsUi {
  /** Highest alert id the person has looked at. */
  seenId: number;
  /** False until the first load decides what counts as already seen. */
  ready: boolean;
  show: AlertSeverity[];
  markSeen(id: number): void;
  toggle(sev: AlertSeverity): void;
  setReady(seen: number): void;
}

export const useAlertsUi = create<AlertsUi>()((set, get) => ({
  seenId: readSeen() ?? 0,
  ready: false,
  show: ['critical', 'warn', 'info'],
  markSeen: (id) => {
    if (id <= get().seenId) return;
    writeSeen(id);
    set({ seenId: id });
  },
  toggle: (sev) => {
    const cur = get().show;
    set({ show: cur.includes(sev) ? cur.filter((s) => s !== sev) : [...cur, sev] });
  },
  setReady: (seen) => set({ ready: true, seenId: seen }),
}));

/** Load alerts newer than the ones we have and merge them into the store. */
export async function loadAlerts(): Promise<void> {
  const have = latestId(useStudio.getState().alerts);
  const r = await api().alerts(have || undefined);
  if (!r.ok) return;
  const merged = mergeAlerts(useStudio.getState().alerts, r.alerts ?? []);
  useStudio.setState({ alerts: merged });
  const ui = useAlertsUi.getState();
  if (!ui.ready) {
    // The very first time on this computer, the history counts as read.
    const stored = readSeen();
    ui.setReady(stored ?? latestId(merged));
    if (stored === null) writeSeen(latestId(merged));
  }
}

/** Toast critical alerts as they arrive and reload missed alerts after the stream comes back. */
export function startAlertFeed(): () => void {
  void loadAlerts();
  const off = onStudioEvent('alert', (ev) => {
    if (needsToast(ev)) notify('error', 'Critical: ' + ev.text);
  });
  const unsub = useStudio.subscribe((s, prev) => {
    if (s.sse.state === 'open' && prev.sse.state === 'down') void loadAlerts();
  });
  return () => {
    off();
    unsub();
  };
}
