import { useEffect, useRef } from 'react';
import { Button, Panel } from '../../components/ui';
import { fmtTime } from '../../lib/format';
import { useStudio } from '../../state/store';
import type { LogEntry } from '../../state/store';

const WORD: Record<LogEntry['level'], string> = { info: 'Info', warn: 'Warning', error: 'Error' };

/** What Studio and this page have reported, newest at the bottom. */
export function AppLog() {
  const logs = useStudio((s) => s.logs);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <Panel
      title="App log"
      wide
      actions={
        <Button size="sm" disabled={!logs.length} onClick={() => useStudio.setState({ logs: [] })}>
          Clear
        </Button>
      }
    >
      <div
        ref={ref}
        className="output output-tall applog"
        role="log"
        tabIndex={0}
        aria-label="Application log"
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
        }}
      >
        {logs.length ? (
          logs.map((l) => (
            <div key={l.id} className={`applog-line applog-${l.level}`}>
              <span className="applog-time">{fmtTime(new Date(l.at))}</span>
              <span className="applog-level">{WORD[l.level]}</span>
              <span className="applog-text">{l.text}</span>
            </div>
          ))
        ) : (
          <span className="output-empty">Nothing has been reported yet.</span>
        )}
      </div>
    </Panel>
  );
}
