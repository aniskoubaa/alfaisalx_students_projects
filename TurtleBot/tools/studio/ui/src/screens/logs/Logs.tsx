import { Copy, Download, FileDown } from 'lucide-react';
import { useMemo, useState } from 'react';
import { JOURNAL_LINES, JOURNAL_SINCE, JOURNAL_UNITS, fetchJournal } from '../../api/live';
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Panel,
  Select,
} from '../../components/ui';
import { useAsyncAction } from '../../lib/useAsync';
import { notify } from '../../state/feedback';
import { useStudio } from '../../state/store';
import { VirtualLines } from './VirtualLines';
import { countLevels, filterLogLines, linesToText, logFileName, toLogLines } from './logFilter';
import type { LogLine } from './logFilter';

interface Fetched {
  unit: string;
  at: Date;
  lines: LogLine[];
  fake: boolean;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function saveText(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function Logs() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const [unit, setUnit] = useState<string>(JOURNAL_UNITS[0].id);
  const [count, setCount] = useState<number>(300);
  const [since, setSince] = useState<string>('');
  const [text, setText] = useState('');
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [data, setData] = useState<Fetched | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchNo, setFetchNo] = useState(0);

  const fetchLogs = useAsyncAction(async () => {
    setError(null);
    const r = await fetchJournal({ unit, lines: count, since });
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setData({ unit, at: new Date(), lines: toLogLines(r.lines ?? []), fake: r.fake === true });
    setFetchNo((n) => n + 1);
  });

  const shown = useMemo(
    () => (data ? filterLogLines(data.lines, { text, problemsOnly }) : []),
    [data, text, problemsOnly],
  );
  const levels = useMemo(() => (data ? countLevels(data.lines) : { error: 0, warn: 0 }), [data]);

  const copy = async () => {
    const ok = await copyText(linesToText(shown));
    notify(
      ok ? 'ok' : 'error',
      ok ? `Copied ${shown.length} lines.` : 'Could not copy. Use Save as file instead.',
    );
  };
  const save = () => {
    if (!data) return;
    saveText(logFileName(data.unit, data.at), linesToText(shown));
    notify('ok', `Saved ${shown.length} lines.`);
  };

  return (
    <div className="page logs">
      <h1 className="page-title">Logs</h1>
      <Panel title="Robot log">
        <form
          className="log-form"
          onSubmit={(e) => {
            e.preventDefault();
            void fetchLogs.run();
          }}
        >
          <Field label="Service" className="grow">
            {(p) => (
              <Select {...p} value={unit} onChange={(e) => setUnit(e.target.value)}>
                {JOURNAL_UNITS.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Lines">
            {(p) => (
              <Select {...p} value={count} onChange={(e) => setCount(Number(e.target.value))}>
                {JOURNAL_LINES.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Since">
            {(p) => (
              <Select {...p} value={since} onChange={(e) => setSince(e.target.value)}>
                {JOURNAL_SINCE.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Button
            type="submit"
            variant="primary"
            icon={<Download size={16} aria-hidden="true" />}
            loading={fetchLogs.pending}
            disabled={!connected}
          >
            Fetch log
          </Button>
        </form>
        {!connected ? <p className="small dim">Connect to the robot to read its log.</p> : null}
        {error ? (
          <div className="note note-bad" role="alert">
            <strong>Could not read the log.</strong> {error}
          </div>
        ) : null}
      </Panel>

      <Panel
        title={data ? `${data.unit}` : 'Log lines'}
        actions={
          data ? (
            <div className="row">
              <Button
                size="sm"
                icon={<Copy size={14} aria-hidden="true" />}
                onClick={() => void copy()}
                disabled={!shown.length}
              >
                Copy
              </Button>
              <Button
                size="sm"
                icon={<FileDown size={14} aria-hidden="true" />}
                onClick={save}
                disabled={!shown.length}
              >
                Save as file
              </Button>
            </div>
          ) : null
        }
      >
        {data ? (
          <div className="stack">
            <div className="log-filter">
              <Field label="Filter lines" className="grow">
                {(p) => (
                  <Input
                    {...p}
                    type="search"
                    value={text}
                    placeholder="Text to find"
                    onChange={(e) => setText(e.target.value)}
                  />
                )}
              </Field>
              <Checkbox
                label="Only warnings and errors"
                checked={problemsOnly}
                onChange={(e) => setProblemsOnly(e.target.checked)}
              />
            </div>
            <p className="log-summary small" role="status">
              {shown.length} of {data.lines.length} lines
              {levels.error ? <Badge tone="bad">{levels.error} errors</Badge> : null}
              {levels.warn ? <Badge tone="warn">{levels.warn} warnings</Badge> : null}
              <span className="dim">
                Fetched at {data.at.toTimeString().slice(0, 8)}
                {data.fake ? ' (sample lines from the demo robot)' : ''}
              </span>
            </p>
            {shown.length ? (
              <VirtualLines lines={shown} scrollKey={fetchNo} label={`Log lines of ${data.unit}`} />
            ) : (
              <EmptyState compact title="No lines match">
                {data.lines.length
                  ? 'Change the filter to see more of the fetched lines.'
                  : 'The robot returned no lines for this service and time. Try a longer time range.'}
              </EmptyState>
            )}
          </div>
        ) : (
          <EmptyState compact title="Nothing fetched yet">
            Choose a service and press Fetch log. Studio reads the robot&apos;s journal without
            changing anything on it.
          </EmptyState>
        )}
      </Panel>
    </div>
  );
}
