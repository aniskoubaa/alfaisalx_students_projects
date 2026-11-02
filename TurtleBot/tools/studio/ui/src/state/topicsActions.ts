import { api } from '../api';
import { MAX_WATCHES, WATCH_MAX_HZ, sortTopics } from '../lib/topics';
import { notify } from './feedback';
import { onStudioEvent } from './runtime';
import { useStudio } from './store';
import { useTopics } from './topicsStore';

const isConnected = () => useStudio.getState().conn.state === 'connected';

export async function loadTopics(): Promise<void> {
  if (!isConnected()) return;
  useTopics.setState({ loading: true });
  const r = await api().bridge('topics');
  if (r.ok) {
    useTopics.setState({
      topics: sortTopics(r.topics ?? []),
      loaded: true,
      loading: false,
      error: null,
    });
  } else {
    useTopics.setState({ loading: false, error: r.error });
  }
}

export async function watchTopic(topic: string): Promise<void> {
  const s = useTopics.getState();
  if (Object.keys(s.watches).length >= MAX_WATCHES) {
    notify('warn', `At most ${MAX_WATCHES} topics can be watched at once.`);
    return;
  }
  if (s.pending.includes(topic)) return;
  useTopics.setState({ pending: [...s.pending, topic] });
  try {
    const r = await api().bridge('watch', { topic, max_hz: WATCH_MAX_HZ });
    if (!r.ok) {
      notify('error', `Watch ${topic}: ${r.error}`);
      return;
    }
    if (r.watch_id != null) {
      const id = String(r.watch_id);
      const cur = useTopics.getState().watches;
      useTopics.setState({
        watches: {
          ...cur,
          [id]: { id, topic, data: cur[id]?.data ?? null, rate: cur[id]?.rate ?? null },
        },
      });
    }
  } finally {
    useTopics.setState({ pending: useTopics.getState().pending.filter((t) => t !== topic) });
  }
}

export async function unwatch(id: string): Promise<void> {
  const r = await api().bridge('unwatch', { watch_id: Number(id) });
  if (r.ok || /unknown|not found/i.test(r.ok ? '' : r.error)) {
    const { [id]: _gone, ...rest } = useTopics.getState().watches;
    void _gone;
    useTopics.setState({ watches: rest });
  } else {
    notify('error', `Stop watching: ${r.error}`);
  }
}

/** A new bridge process knows nothing about earlier watches: ask for the same topics again (reading only). */
export async function rewatchAll(): Promise<void> {
  const old = Object.values(useTopics.getState().watches)
    .map((w) => w.topic)
    .filter(Boolean);
  if (!old.length) return;
  useTopics.setState({ watches: {} });
  for (const t of old) await watchTopic(t);
}

/** Keep the latest message and rate of every watch. Returns a function that stops listening. */
export function startTopicsListener(): () => void {
  return onStudioEvent('msg', (ev) => {
    const id = String(ev.watch_id);
    const cur = useTopics.getState().watches;
    const w = cur[id] ?? { id, topic: ev.topic ?? '', data: null, rate: null };
    useTopics.setState({
      watches: {
        ...cur,
        [id]: { ...w, topic: ev.topic || w.topic, data: ev.data, rate: ev.rate_hz ?? null },
      },
    });
  });
}
