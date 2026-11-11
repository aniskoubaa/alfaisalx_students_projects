/** Typed calls for the Routes screen. */
import { api } from '../../api';
import type { ApiResult, BridgeAnswers, RouteUploadAnswer } from '../../api';

const T = { timeoutMs: 15_000 };

export const listRoutes = (): Promise<ApiResult<BridgeAnswers['routes_list']>> =>
  api().bridge('routes_list', {}, T);

/** Always sends confirm:true; the dialog in the interface is the confirmation. */
export const setCurrentRoute = (
  name: string,
): Promise<ApiResult<BridgeAnswers['route_set_current']>> =>
  api().bridge('route_set_current', { name, confirm: true }, T);

export const tripStatus = (lines = 40): Promise<ApiResult<BridgeAnswers['trip_status']>> =>
  api().bridge('trip_status', { lines }, T);

/** Base64 of bytes, in chunks so big files do not overflow the call stack. */
export function toBase64(bytes: Uint8Array): string {
  const CHUNK = 0x8000;
  let bin = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

/** The path a file gets on the robot: its place inside the chosen folder (a flat folder). */
export const uploadPath = (f: Pick<File, 'name' | 'webkitRelativePath'>): string => {
  const rel = f.webkitRelativePath || f.name;
  return rel.split('/').slice(1).join('/') || f.name;
};

export async function uploadRoute(
  name: string,
  files: File[],
): Promise<ApiResult<RouteUploadAnswer>> {
  const out: Array<{ path: string; data_b64: string }> = [];
  for (const f of files) {
    out.push({ path: uploadPath(f), data_b64: toBase64(new Uint8Array(await f.arrayBuffer())) });
  }
  return api().post<RouteUploadAnswer>(
    '/api/routes/upload',
    { name, files: out },
    { timeoutMs: 120_000 },
  );
}
