import { parseUrlOptions, shouldAutoOpenWizard } from '../lib/urlOptions';
import { navigate } from './router';
import { useStudio } from './store';
import { loadTopics, rewatchAll, startTopicsListener } from './topicsActions';
import { applyTheme } from './ui';
import { checkPendingWifiJob } from './wifiActions';
import { openWizard } from './wizardActions';

/**
 * Start-up work for the Wi-Fi, topics and setup screens (Frontend F2):
 * the address options (?theme, ?tab, ?wizard, ?nowizard), the watch listener, what to do each
 * time the robot connects, and the first-run setup wizard. Returns a function that undoes it all.
 */
export function startF2Runtime(): () => void {
  const opts = parseUrlOptions(window.location.search, window.location.hash);
  if (opts.theme) applyTheme(opts.theme);
  if (opts.path) navigate(opts.path);

  const stopMsg = startTopicsListener();

  let prev = useStudio.getState().conn.state;
  let wizardChecked = false;
  const unsub = useStudio.subscribe((s) => {
    const now = s.conn.state;
    if (now !== prev) {
      prev = now;
      if (now === 'connected') {
        // A new bridge process knows nothing about earlier watches.
        void rewatchAll().then(() => loadTopics());
        void checkPendingWifiJob();
      }
    }
    if (!wizardChecked && s.settingsLoaded) {
      wizardChecked = true;
      if (shouldAutoOpenWizard(opts, s.settings.setup_done)) openWizard();
    }
  });
  // Settings may already be loaded.
  const s0 = useStudio.getState();
  if (s0.settingsLoaded) {
    wizardChecked = true;
    if (shouldAutoOpenWizard(opts, s0.settings.setup_done)) openWizard();
  }

  return () => {
    unsub();
    stopMsg();
  };
}
