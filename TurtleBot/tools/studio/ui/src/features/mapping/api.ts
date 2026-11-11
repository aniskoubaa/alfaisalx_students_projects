/**
 * Typed calls for the mapping feature. Bridge commands go through POST /api/bridge; the picture
 * and download endpoints are plain GETs that need the token header, so they return blobs.
 */
import { api } from '../../api';
import type { ApiResult, BridgeAnswers, MapMeta, MappingInfo } from '../../api';
import { parseMapMeta } from './model';

const T = { timeoutMs: 15_000 };

export const mappingStatus = (): Promise<ApiResult<BridgeAnswers['mapping_status']>> =>
  api().bridge('mapping_status', {}, T);

export const startMapping = (): Promise<ApiResult<BridgeAnswers['mapping_start']>> =>
  api().bridge('mapping_start', {}, T);

export const saveMap = (
  name: string,
  overwrite = false,
): Promise<ApiResult<BridgeAnswers['mapping_save']>> =>
  api().bridge('mapping_save', overwrite ? { name, overwrite: true } : { name }, T);

export const stopMapping = (): Promise<ApiResult<BridgeAnswers['mapping_stop']>> =>
  api().bridge('mapping_stop', {}, T);

export const resetMapping = (): Promise<ApiResult<BridgeAnswers['mapping_reset']>> =>
  api().bridge('mapping_reset', {}, T);

export const mapOn = (
  hz = 0.5,
  maxCells = 1_000_000,
): Promise<ApiResult<BridgeAnswers['map_on']>> =>
  api().bridge('map_on', { hz, max_cells: maxCells }, { timeoutMs: 8000 });

export const mapOff = (): Promise<ApiResult<BridgeAnswers['map_off']>> =>
  api().bridge('map_off', {}, { timeoutMs: 8000 });

export const listMaps = (): Promise<ApiResult<BridgeAnswers['maps_list']>> =>
  api().bridge('maps_list', {}, T);

export const renameMap = (
  name: string,
  newName: string,
): Promise<ApiResult<BridgeAnswers['map_rename']>> =>
  api().bridge('map_rename', { name, new_name: newName }, T);

/** Deleting always sends confirm:true; the dialog in the interface is the confirmation. */
export const deleteMap = (name: string): Promise<ApiResult<BridgeAnswers['map_delete']>> =>
  api().bridge('map_delete', { name, confirm: true }, T);

/** The current mapping state Studio last saw (replayed to pages opened later). */
export const fetchMappingInfo = (): Promise<ApiResult<MappingInfo>> =>
  api().get<MappingInfo>('/api/mapping');

/* ---------- pictures ---------- */

export const LIVE_MAP_PATH = '/api/map/live.png';

/** The latest live map as a PNG, with its description from the X-Map-Meta header. */
export async function fetchLiveMap(): Promise<ApiResult<{ blob: Blob; meta: MapMeta | null }>> {
  const r = await api().getBlob(LIVE_MAP_PATH, { timeoutMs: 20_000 });
  if (!r.ok) return r;
  return { ok: true, blob: r.blob, meta: parseMapMeta(r.headers['x-map-meta']) };
}

export function previewUrl(name: string, maxPx = 512): string {
  return `/api/maps/preview.png?name=${encodeURIComponent(name)}&max=${maxPx}`;
}

export const fetchPreview = (
  name: string,
  maxPx = 512,
): Promise<ApiResult<{ blob: Blob; headers: Record<string, string> }>> =>
  api().getBlob(previewUrl(name, maxPx), { timeoutMs: 30_000 });

export function downloadUrl(name: string): string {
  return `/api/maps/download?name=${encodeURIComponent(name)}`;
}

/** Fetch the zip of a map and hand it to the browser as a file download. */
export async function downloadMap(name: string): Promise<ApiResult<{ file: string }>> {
  const r = await api().getBlob(downloadUrl(name), { timeoutMs: 120_000 });
  if (!r.ok) return r;
  if (typeof URL.createObjectURL !== 'function') {
    return { ok: false, error: 'This browser cannot save files from here.' };
  }
  const url = URL.createObjectURL(r.blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.zip`;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return { ok: true, file: `${name}.zip` };
}
