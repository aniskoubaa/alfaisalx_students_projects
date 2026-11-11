/**
 * What the Maps screen knows: the mapping state, the latest map picture, the robot pose in the
 * map frame and the last lidar scan. Fed by the `mapping`, `map`, `pose` and `scan` events.
 * The canvas reads this store inside its own animation loop, so high-rate events never re-render
 * the buttons.
 */
import { create } from 'zustand';
import type {
  MapEvent,
  MapMeta,
  MapPose,
  MappingEvent,
  MappingInfo,
  MappingResult,
  PoseEvent,
  ScanEvent,
} from '../../api';
import { scanToPoints } from '../../screens/live/scan';
import type { Pose, ScanPoints } from '../../screens/live/scan';
import { fetchLiveMap } from './api';
import { toMapMeta } from './model';

/** A decoded picture the canvas can draw. */
export interface MapImage {
  seq: number;
  meta: MapMeta;
  source: CanvasImageSource & { width: number; height: number };
  /** Cells that are known (free or occupied), when it could be counted. */
  known: number | null;
  close: () => void;
}

export type MapDecoder = (blob: Blob) => Promise<{
  source: CanvasImageSource & { width: number; height: number };
  known: number | null;
  close: () => void;
} | null>;

/** Turn the PNG into something drawable. Replaceable in tests (jsdom has no image decoding). */
export const browserDecoder: MapDecoder = async (blob) => {
  if (typeof createImageBitmap !== 'function') return null;
  try {
    const bmp = await createImageBitmap(blob);
    let known: number | null = null;
    try {
      const c = document.createElement('canvas');
      c.width = bmp.width;
      c.height = bmp.height;
      const ctx = c.getContext('2d', { willReadFrequently: true });
      if (ctx) {
        ctx.drawImage(bmp, 0, 0);
        known = countKnown(ctx.getImageData(0, 0, bmp.width, bmp.height).data);
      }
    } catch {
      known = null;
    }
    return { source: bmp, known, close: () => bmp.close() };
  } catch {
    return null;
  }
};

/** The unknown grey in the PNG is 205 (see the design). Count pixels that are not that. */
export function countKnown(rgba: ArrayLike<number>): number {
  let n = 0;
  for (let i = 0; i + 3 < rgba.length; i += 4) if (rgba[i] !== 205) n++;
  return n;
}

let decoder: MapDecoder = browserDecoder;
export function setMapDecoder(d: MapDecoder | null): void {
  decoder = d ?? browserDecoder;
}

interface MappingStore {
  /** null until the first answer. */
  info: MappingInfo | null;
  /** The newest finished operation (start, save or stop). */
  result: MappingResult | null;
  meta: MapMeta | null;
  image: MapImage | null;
  /** Seq of the newest map event seen, drawn or not. */
  latestSeq: number;
  fetching: boolean;
  fetchError: string | null;
  /** Robot pose in the map frame (or the odometry frame until a map pose is known). */
  pose: Pose | null;
  poseSource: MapPose['source'] | null;
  scan: ScanPoints | null;
  scanPose: Pose | null;
  scanAt: number;

  setInfo(info: MappingInfo): void;
  onMappingEvent(ev: MappingEvent): void;
  onMapEvent(ev: MapEvent): void;
  onPose(ev: PoseEvent): void;
  onScan(ev: ScanEvent, now?: number): void;
  clearMap(): void;
  reset(): void;
}

const blank = () => ({
  info: null as MappingInfo | null,
  result: null as MappingResult | null,
  meta: null as MapMeta | null,
  image: null as MapImage | null,
  latestSeq: -1,
  fetching: false,
  fetchError: null as string | null,
  pose: null as Pose | null,
  poseSource: null as MapPose['source'] | null,
  scan: null as ScanPoints | null,
  scanPose: null as Pose | null,
  scanAt: 0,
});

/** Only one picture is fetched at a time; this is the newest one asked for meanwhile. */
let pending: MapMeta | null = null;
let generation = 0;

export const useMapping = create<MappingStore>()((set, get) => ({
  ...blank(),

  setInfo: (info) => set({ info }),

  onMappingEvent: (ev) => {
    const { ev: _e, result, ...info } = ev;
    void _e;
    const prev = get().info;
    const patch: Partial<MappingStore> = { info: info as MappingInfo };
    if (result) patch.result = result;
    // A new mapping run starts a new picture; the sequence numbers may start again.
    if (info.state === 'starting' && prev?.state !== 'starting') {
      get().clearMap();
    }
    set(patch);
  },

  onMapEvent: (ev) => {
    const meta = toMapMeta(ev);
    if (!meta) return;
    if (meta.seq <= get().latestSeq) return;
    set({ latestSeq: meta.seq, meta });
    void requestFetch(meta);
  },

  onPose: (ev) => {
    const m = ev.map;
    if (m && Number.isFinite(m.x) && Number.isFinite(m.y)) {
      set({ pose: { x: m.x, y: m.y, yaw: m.yaw }, poseSource: m.source });
    } else {
      set({ pose: { x: ev.x, y: ev.y, yaw: ev.yaw }, poseSource: null });
    }
  },

  onScan: (ev, now = Date.now()) => {
    set({
      scan: scanToPoints(ev),
      scanPose: get().pose ?? { x: 0, y: 0, yaw: 0 },
      scanAt: now,
    });
  },

  clearMap: () => {
    generation++;
    pending = null;
    get().image?.close();
    set({ meta: null, image: null, latestSeq: -1, fetching: false, fetchError: null });
  },

  reset: () => {
    generation++;
    pending = null;
    get().image?.close();
    set(blank());
  },
}));

async function requestFetch(meta: MapMeta): Promise<void> {
  const s = useMapping.getState();
  if (s.fetching) {
    // Keep only the newest request.
    if (!pending || meta.seq > pending.seq) pending = meta;
    return;
  }
  const gen = generation;
  useMapping.setState({ fetching: true });
  try {
    const r = await fetchLiveMap();
    if (gen !== generation) return;
    if (!r.ok) {
      useMapping.setState({ fetchError: r.error });
      return;
    }
    const m = r.meta ?? meta;
    const dec = await decoder(r.blob);
    if (gen !== generation) {
      dec?.close();
      return;
    }
    if (!dec) {
      useMapping.setState({ fetchError: 'This browser could not read the map picture.' });
      return;
    }
    const old = useMapping.getState().image;
    // Never go back to an older picture than the one on screen.
    if (old && old.seq > m.seq) {
      dec.close();
      return;
    }
    useMapping.setState({
      image: { seq: m.seq, meta: m, source: dec.source, known: dec.known, close: dec.close },
      meta: m,
      fetchError: null,
    });
    old?.close();
  } finally {
    if (gen === generation) {
      useMapping.setState({ fetching: false });
      const next = pending;
      pending = null;
      const shown = useMapping.getState().image?.seq ?? -1;
      if (next && next.seq > shown) void requestFetch(next);
    }
  }
}
