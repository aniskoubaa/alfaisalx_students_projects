import { StudioClient, browserToken } from './client';

export * from './types';
export { StudioClient, resolveToken, toResult, BAD_TOKEN } from './client';
export type { CallOptions } from './client';
export { createSseClient, parseEvent, backoffSeconds } from './sse';
export type { SseStatus, SseState, SseClient } from './sse';

let shared: StudioClient | null = null;

/** The one client used by the running app. Tests build their own with `new StudioClient`. */
export function api(): StudioClient {
  if (!shared) shared = new StudioClient({ token: browserToken() });
  return shared;
}

/** Replace the shared client (tests). */
export function setApi(client: StudioClient | null): void {
  shared = client;
}
