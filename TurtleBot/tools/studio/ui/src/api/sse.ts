import type { EventName, StudioEvent } from './types';

const KNOWN: ReadonlySet<string> = new Set<EventName>([
  'conn',
  'hello',
  'status',
  'discover',
  'deep_progress',
  'update',
  'quit',
  'sync',
  'log',
  'run_output',
  'run_exit',
  'msg',
  'action',
  'scan',
  'pose',
  'mapping',
  'map',
  'teleop',
  'alert',
]);

/** Parse one SSE message. Anything that is not a known event object is dropped. */
export function parseEvent(data: string): StudioEvent | null {
  let raw: unknown;
  try {
    raw = JSON.parse(data);
  } catch {
    return null;
  }
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const ev = (raw as { ev?: unknown }).ev;
  if (typeof ev !== 'string' || !KNOWN.has(ev)) return null;
  if (
    (ev === 'run_output' || ev === 'run_exit') &&
    typeof (raw as { run_id?: unknown }).run_id !== 'string'
  ) {
    return null;
  }
  return raw as StudioEvent;
}

export type SseState = 'connecting' | 'open' | 'down';

export interface SseStatus {
  state: SseState;
  /** Failed attempts since the last good connection. */
  attempt: number;
  /** Wall-clock time (ms) of the next retry while down, otherwise null. */
  retryAt: number | null;
}

interface EventSourceLike {
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  close(): void;
}
type EventSourceCtor = new (url: string) => EventSourceLike;

export interface SseOptions {
  url: () => string;
  onEvent: (ev: StudioEvent) => void;
  onStatus: (s: SseStatus) => void;
  eventSource?: EventSourceCtor;
  now?: () => number;
}

/** 1, 2, 4, 8, then 10 seconds (the same pacing as Studio 1.3). */
export function backoffSeconds(attempt: number): number {
  return Math.min(10, 1 << Math.min(attempt, 4));
}

export interface SseClient {
  start(): void;
  stop(): void;
  /** Skip the wait and try again now. */
  retryNow(): void;
}

export function createSseClient(opts: SseOptions): SseClient {
  const ES: EventSourceCtor = opts.eventSource ?? (EventSource as unknown as EventSourceCtor);
  const now = opts.now ?? (() => Date.now());
  let es: EventSourceLike | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let stopped = true;

  const emit = (state: SseState, retryAt: number | null) =>
    opts.onStatus({ state, attempt, retryAt });

  const closeSource = () => {
    if (!es) return;
    es.onopen = es.onmessage = es.onerror = null;
    try {
      es.close();
    } catch {
      /* already closed */
    }
    es = null;
  };

  const connect = () => {
    if (stopped) return;
    if (timer) clearTimeout(timer);
    timer = null;
    closeSource();
    emit('connecting', null);
    let source: EventSourceLike;
    try {
      source = new ES(opts.url());
    } catch {
      scheduleRetry();
      return;
    }
    es = source;
    source.onopen = () => {
      attempt = 0;
      emit('open', null);
    };
    source.onmessage = (m) => {
      const ev = parseEvent(String(m.data));
      if (ev) opts.onEvent(ev);
    };
    source.onerror = () => {
      closeSource();
      scheduleRetry();
    };
  };

  const scheduleRetry = () => {
    if (stopped) return;
    const wait = backoffSeconds(attempt) * 1000;
    attempt += 1;
    emit('down', now() + wait);
    timer = setTimeout(connect, wait);
  };

  return {
    start() {
      stopped = false;
      attempt = 0;
      connect();
    },
    stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
      timer = null;
      closeSource();
    },
    retryNow() {
      if (!stopped) connect();
    },
  };
}
