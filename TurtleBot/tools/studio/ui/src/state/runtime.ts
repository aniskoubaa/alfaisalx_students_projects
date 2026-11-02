import { api, createSseClient } from '../api';
import type { EventName, EventOf, SseClient, StudioEvent } from '../api';
import { loadCatalog, loadSettings, loadUpdateStatus, onConnected } from './actions';
import { notify } from './feedback';
import { useStudio } from './store';

type Listener<K extends EventName> = (ev: EventOf<K>) => void;
const listeners = new Map<EventName, Set<(ev: StudioEvent) => void>>();

/** Subscribe to one kind of event, for high-rate data that does not belong in the store. */
export function onStudioEvent<K extends EventName>(name: K, fn: Listener<K>): () => void {
  const set = listeners.get(name) ?? new Set();
  set.add(fn as (ev: StudioEvent) => void);
  listeners.set(name, set);
  return () => {
    set.delete(fn as (ev: StudioEvent) => void);
  };
}

let sse: SseClient | null = null;
let unsubscribe: (() => void) | null = null;

/** Called for every event from the stream: stores it, lets listeners see it, runs side effects. */
export function handleEvent(ev: StudioEvent): void {
  const s = useStudio.getState();
  s.dispatch(ev);
  listeners.get(ev.ev)?.forEach((fn) => fn(ev));
  if (ev.ev === 'conn') {
    if (ev.state === 'error' && ev.error) notify('error', 'Connection: ' + ev.error);
    if (ev.state === 'disconnected' && ev.kind === 'gave_up' && ev.error) {
      notify('error', 'Connection: ' + ev.error);
    }
  }
  if (ev.ev === 'quit') sse?.stop();
}

/** Start loading data and listening to Studio. Returns a function that stops everything. */
export function startRuntime(): () => void {
  const client = api();
  const store = useStudio;

  let prev = store.getState().conn.state;
  unsubscribe = store.subscribe((s) => {
    const now = s.conn.state;
    if (now === prev) return;
    const was = prev;
    prev = now;
    if (now === 'connected') void onConnected(was === 'reconnecting');
  });

  sse = createSseClient({
    url: () => client.eventsUrl(),
    onEvent: handleEvent,
    onStatus: (st) => store.getState().setSse(st),
  });
  sse.start();

  void loadSettings();
  void loadCatalog();
  void loadUpdateStatus();

  return () => {
    sse?.stop();
    sse = null;
    unsubscribe?.();
    unsubscribe = null;
  };
}

export function retryEventStream(): void {
  sse?.retryNow();
}
