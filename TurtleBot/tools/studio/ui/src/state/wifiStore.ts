import { create } from 'zustand';
import type { LaptopNet, WifiInfo } from '../api/setup-types';
import type { JobFlag, JobView, WifiJob } from '../lib/wifi';

export const JOB_KEY = 'studio_wifi_job';

/** Remember the job across a reload or a reconnect. Holds the nonce and the network name, never a password. */
export function saveJob(job: WifiJob | null): void {
  try {
    if (job) {
      sessionStorage.setItem(
        JOB_KEY,
        JSON.stringify({
          nonce: job.nonce,
          ssid: job.ssid,
          now: job.now,
          t: job.t,
          base: job.base ?? null,
          fake: job.fake ?? false,
        }),
      );
    } else sessionStorage.removeItem(JOB_KEY);
  } catch {
    /* storage blocked: the job is only remembered while this page stays open */
  }
}

export function loadJob(): WifiJob | null {
  try {
    const raw: unknown = JSON.parse(sessionStorage.getItem(JOB_KEY) ?? 'null');
    if (typeof raw !== 'object' || raw === null) return null;
    const j = raw as Record<string, unknown>;
    if (typeof j.nonce !== 'string' || typeof j.ssid !== 'string') return null;
    const job: WifiJob = {
      nonce: j.nonce,
      ssid: j.ssid,
      now: j.now === true,
      t: typeof j.t === 'number' ? j.t : Date.now(),
      fake: j.fake === true,
    };
    if (typeof j.base === 'number') job.base = j.base;
    return job;
  } catch {
    return null;
  }
}

export interface WifiState {
  laptop: LaptopNet | null;
  laptopErr: string | null;
  laptopLoading: boolean;
  robot: WifiInfo | null;
  robotErr: string | null;
  robotLoading: boolean;
  /** The network being added, while a result is still expected. */
  job: WifiJob | null;
  /** The network the progress dialog is about. */
  shown: WifiJob | null;
  jobView: JobView | null;
  jobFlag: JobFlag;
  jobErr: string | null;
  /** True while the progress dialog is open. */
  jobOpen: boolean;
  /** Set when the job was asked about once after a reconnect. */
  jobAsked: boolean;
}

export const initialWifi = (): WifiState => ({
  laptop: null,
  laptopErr: null,
  laptopLoading: false,
  robot: null,
  robotErr: null,
  robotLoading: false,
  job: null,
  shown: null,
  jobView: null,
  jobFlag: null,
  jobErr: null,
  jobOpen: false,
  jobAsked: false,
});

export const useWifi = create<WifiState>()(() => initialWifi());
