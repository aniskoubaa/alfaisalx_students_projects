import { setupApi } from '../api/setup';
import type { SavedWifi } from '../api/setup-types';
import { WifiJobBody } from '../screens/wifi/WifiJobBody';
import { POLL_EVERY_MS, pollStep, wifiView } from '../lib/wifi';
import type { JobView, PollState, WifiJob } from '../lib/wifi';
import { confirm, inform, notify } from './feedback';
import { nameOf } from './names';
import { parseHash } from './router';
import { useStudio } from './store';
import { loadJob, saveJob, useWifi } from './wifiStore';

const isConnected = () => useStudio.getState().conn.state === 'connected';
const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/* ---------- reading ---------- */

export async function loadLaptop(): Promise<void> {
  useWifi.setState({ laptopLoading: true });
  const r = await setupApi.laptopNet();
  if (r.ok) {
    const { ok: _ok, ...net } = r;
    void _ok;
    useWifi.setState({ laptop: net, laptopErr: null, laptopLoading: false });
  } else {
    useWifi.setState({ laptop: null, laptopErr: r.error, laptopLoading: false });
  }
}

export async function loadRobot(): Promise<void> {
  if (!isConnected()) {
    useWifi.setState({ robot: null, robotErr: null, robotLoading: false });
    return;
  }
  useWifi.setState({ robotLoading: true });
  const r = await setupApi.wifiInfo();
  if (r.ok) {
    const { ok: _ok, ...info } = r;
    void _ok;
    useWifi.setState({ robot: info, robotErr: null, robotLoading: false });
  } else {
    useWifi.setState({ robot: null, robotErr: r.error, robotLoading: false });
  }
}

export async function loadWifi(): Promise<void> {
  await Promise.all([loadLaptop(), loadRobot()]);
}

/* ---------- hotspot and settings ---------- */

export async function joinHotspot(): Promise<void> {
  const hs = nameOf(useStudio.getState(), 'hotspot_ssid');
  const r = await setupApi.joinHotspot();
  if (!r.ok && r.needs_settings) {
    const ok = await confirm({
      title: `Join ${hs} yourself`,
      body: (
        <>
          <p>
            Studio cannot join the network for you on this computer. Open the Wi-Fi settings, pick{' '}
            <strong>{hs}</strong> and enter its password (in the TurtleBot 4 manual, or ask whoever
            set up the robot).
          </p>
          <p className="dim">While you are on the hotspot this computer has no internet.</p>
        </>
      ),
      confirmLabel: 'Open Wi-Fi settings',
    });
    if (ok) await openWifiSettings();
    return;
  }
  if (!r.ok) {
    notify('error', `Join hotspot: ${r.error}`);
    return;
  }
  notify(
    'info',
    r.warning ||
      r.message ||
      `Joining ${hs}. This computer has no internet while it is on the hotspot.`,
  );
  setTimeout(() => void loadWifi(), 4000);
}

export async function openWifiSettings(): Promise<void> {
  const r = await setupApi.laptopWifiSettings();
  if (!r.ok) notify('error', `Wi-Fi settings: ${r.error}`);
}

/* ---------- removing a saved network ---------- */

export async function removeWifi(x: SavedWifi): Promise<void> {
  const ok = await confirm({
    title: `Remove “${x.name}” from the robot?`,
    body: (
      <p>
        A terminal window opens and asks for the robot&apos;s password to delete this saved network.
        The robot will no longer join it by itself.
      </p>
    ),
    confirmLabel: 'Open terminal',
    tone: 'danger',
  });
  if (!ok) return;
  const r = await setupApi.wifiRemove(x.name);
  if (!r.ok) notify('error', `Remove Wi-Fi: ${r.error}`);
  else notify('ok', 'Terminal opened. Finish there, then press Refresh.');
}

/* ---------- adding a network ---------- */

/**
 * The add flow: ask first, then send the name and password once, then follow the result.
 * `takePsk` reads the password box and clears it, so the password leaves the page whether or not
 * the question was confirmed.
 */
export async function addWifi(opts: {
  ssid: string;
  now: boolean;
  takePsk: () => string;
}): Promise<void> {
  const { ssid, now } = opts;
  const ok = await confirm({
    title: `Add “${ssid}” to the robot?`,
    body: (
      <>
        <p>
          A terminal window opens. In it you type <strong>one password</strong>: the robot&apos;s
          own password (sudo asks for it before it changes system settings). Type it only in that
          window.
        </p>
        <p>
          The Wi-Fi password was typed here in Studio. Studio sends it once, through the secure
          link, to the robot&apos;s memory for at most 3 minutes. It is used to save the network and
          is never stored by Studio.
        </p>
        <p>
          Check the network name: it must match the Wi-Fi exactly, including capitals. The robot
          keeps its own hotspot as a backup. To undo it later, use Remove in the saved networks
          table.
        </p>
        {now ? (
          <div className="note note-warn">
            <p>
              <strong>The robot will switch to this network now and test it.</strong> If it fails,
              it removes the entry and goes back to its current network. You may lose the connection
              for a moment. Join <strong>{ssid}</strong> on this computer too, then press Discover.
            </p>
          </div>
        ) : (
          <p className="dim">
            The robot will use it the next time it starts, or when its current network is out of
            range.
          </p>
        )}
      </>
    ),
    confirmLabel: 'Open terminal',
  });
  const typed = opts.takePsk();
  if (!ok) return;
  const r = await setupApi.wifiAdd(ssid, typed, now);
  if (!r.ok) {
    notify('error', `Add Wi-Fi: ${r.error}`);
    return;
  }
  if (!r.nonce) {
    notify('ok', 'Terminal opened. Finish there, then press Refresh.');
    return;
  }
  const job: WifiJob = { nonce: r.nonce, ssid, now, t: Date.now(), fake: !!r.fake };
  useWifi.setState({ job, jobAsked: false });
  saveJob(job);
  showJobDialog(job, wifiView(job, null, false), true);
}

/* ---------- following the result ---------- */

export function showJobDialog(job: WifiJob, view: JobView, poll: boolean, sleep = defaultSleep) {
  useWifi.setState({ shown: job, jobView: view, jobFlag: null, jobErr: null, jobOpen: true });
  void inform({
    key: 'wifi-job',
    title: `Adding “${job.ssid}” to the robot`,
    body: <WifiJobBody />,
  }).then(() => useWifi.setState({ jobOpen: false }));
  if (poll) void pollJob(job, sleep);
}

let pollGen = 0;

/** Ask for the result every 2 s until it is known, the robot is lost, or 150 s pass. */
export async function pollJob(first: WifiJob, sleep = defaultSleep): Promise<void> {
  const gen = ++pollGen;
  const t0 = Date.now();
  let job = first;
  let state: PollState = { last: null, fails: 0 };
  for (;;) {
    const r = await setupApi.wifiStatus(job.nonce);
    if (gen !== pollGen || !useWifi.getState().jobOpen) return;
    const answer = r.ok
      ? ({ ok: true, data: r } as const)
      : ({ ok: false, error: r.error } as const);
    const step = pollStep(job, state, answer, {
      connected: isConnected(),
      elapsedMs: Date.now() - t0,
    });
    state = step.state;
    if (step.base !== undefined) {
      job = { ...job, base: step.base };
      useWifi.setState({ job });
      saveJob(job);
    }
    useWifi.setState({ jobView: step.view, jobFlag: step.flag, jobErr: step.error ?? null });
    if (step.view.done) {
      useWifi.setState({ job: null });
      saveJob(null);
      if (isConnected()) void loadWifi();
      return;
    }
    if (step.stop) return;
    await sleep(POLL_EVERY_MS);
  }
}

/** After a reconnect: ask once for the stored result of the last add. */
export async function checkPendingWifiJob(): Promise<void> {
  const s = useWifi.getState();
  const job = s.job ?? loadJob();
  if (!job || s.jobAsked || s.jobOpen) return;
  if (Date.now() - job.t > 3600e3) {
    useWifi.setState({ job: null });
    saveJob(null);
    return;
  }
  useWifi.setState({ job, jobAsked: true });
  const r = await setupApi.wifiStatus(job.nonce);
  if (!r.ok) {
    useWifi.setState({ jobAsked: false });
    return;
  }
  const v = wifiView(job, r, false);
  if (v.done) {
    useWifi.setState({ job: null });
    saveJob(null);
    showJobDialog(job, v, false);
    if (parseHash(window.location.hash) === '/wifi') void loadWifi();
  } else if (r.secret === 'none' && !r.join) {
    useWifi.setState({ job: null });
    saveJob(null);
  } else {
    // Still joining: ask again at the next reconnect.
    useWifi.setState({ jobAsked: false });
  }
}
