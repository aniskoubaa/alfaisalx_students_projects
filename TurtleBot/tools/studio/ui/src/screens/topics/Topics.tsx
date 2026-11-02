import { Eye, EyeOff, RefreshCw } from 'lucide-react';
import { useEffect } from 'react';
import { Button, EmptyState, Input, Panel, Table } from '../../components/ui';
import { MAX_WATCHES, filterTopics, messageText, rateText } from '../../lib/topics';
import { useAsyncAction } from '../../lib/useAsync';
import { useStudio } from '../../state/store';
import { loadTopics, unwatch, watchTopic } from '../../state/topicsActions';
import { useTopics } from '../../state/topicsStore';
import type { Watch } from '../../state/topicsStore';

function WatchRow({ topic, disabled }: { topic: string; disabled: boolean }) {
  const watching = useTopics((s) => Object.values(s.watches).some((w) => w.topic === topic));
  const pending = useTopics((s) => s.pending.includes(topic));
  return (
    <Button
      size="sm"
      icon={watching ? <Eye size={14} aria-hidden="true" /> : undefined}
      loading={pending}
      disabled={watching || disabled}
      aria-label={watching ? `Watching ${topic}` : `Watch ${topic}`}
      onClick={() => void watchTopic(topic)}
    >
      {watching ? 'Watching' : 'Watch'}
    </Button>
  );
}

function WatchCard({ w }: { w: Watch }) {
  const stop = useAsyncAction(() => unwatch(w.id));
  return (
    <article className="watch" aria-label={`Watching ${w.topic}`}>
      <header className="watch-head">
        <strong className="mono watch-topic">{w.topic}</strong>
        <span className="dim small num">{rateText(w.rate)}</span>
        <span className="watch-gap" />
        <Button
          size="sm"
          icon={<EyeOff size={14} aria-hidden="true" />}
          loading={stop.pending}
          aria-label={`Stop watching ${w.topic}`}
          onClick={() => void stop.run()}
        >
          Unwatch
        </Button>
      </header>
      <pre className="output watch-data" tabIndex={0} aria-label={`Latest message of ${w.topic}`}>
        {messageText(w.data)}
      </pre>
    </article>
  );
}

export function Topics() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const topics = useTopics((s) => s.topics);
  const loaded = useTopics((s) => s.loaded);
  const loading = useTopics((s) => s.loading);
  const error = useTopics((s) => s.error);
  const filter = useTopics((s) => s.filter);
  const watches = useTopics((s) => s.watches);
  const list = filterTopics(topics, filter);
  const ids = Object.keys(watches);
  const full = ids.length >= MAX_WATCHES;

  useEffect(() => {
    if (connected && !useTopics.getState().loaded) void loadTopics();
  }, [connected]);

  return (
    <div className="page">
      <h1 className="page-title">Topics</h1>
      <div className="split">
        <Panel
          title="Topics"
          actions={
            <Button
              size="sm"
              icon={<RefreshCw size={14} aria-hidden="true" />}
              loading={loading}
              disabled={!connected}
              aria-label="Refresh topics"
              onClick={() => void loadTopics()}
            >
              Refresh
            </Button>
          }
        >
          <Input
            type="search"
            placeholder="Filter by name or type"
            aria-label="Filter topics"
            value={filter}
            onChange={(e) => useTopics.setState({ filter: e.target.value })}
          />
          {error ? (
            <div className="note note-bad" role="alert">
              Could not list the topics: {error}
            </div>
          ) : null}
          {list.length ? (
            <Table label="Topics" maxHeight={560}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th className="num">Publishers</th>
                  <th>
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((t) => (
                  <tr key={t.name}>
                    <td className="mono wrap-any">{t.name}</td>
                    <td className="mono small dim type-cell">
                      {(t.types ?? [])
                        .join(', ')
                        .split('/')
                        .map((part, i) => (
                          <span key={i}>
                            {i > 0 ? (
                              <>
                                /<wbr />
                              </>
                            ) : null}
                            {part}
                          </span>
                        ))}
                    </td>
                    <td className="num">{t.publishers ?? ''}</td>
                    <td className="cell-action">
                      <WatchRow topic={t.name} disabled={full} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="dim small">
              {!connected
                ? 'Connect to the robot to list its topics.'
                : loaded && topics.length
                  ? 'No topic matches the filter.'
                  : loaded
                    ? 'The robot reports no topics.'
                    : 'Press Refresh to list the topics.'}
            </p>
          )}
        </Panel>

        <Panel
          title="Watching"
          actions={
            <span className="dim small num">
              {ids.length} / {MAX_WATCHES}
            </span>
          }
        >
          {ids.length ? (
            <div className="watch-list">
              {ids.map((id) => (
                <WatchCard key={id} w={watches[id] as Watch} />
              ))}
            </div>
          ) : (
            <EmptyState compact icon={<Eye size={28} />} title="Nothing watched yet">
              Pick a topic to watch its messages live (up to {MAX_WATCHES}).
            </EmptyState>
          )}
          {full ? (
            <p className="dim small">
              {MAX_WATCHES} topics are being watched. Stop one to watch another.
            </p>
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
