import { OctagonX, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { OutputLog } from '../components/OutputLog';
import { Badge, Button, Checkbox, EmptyState, Panel, Table } from '../components/ui';
import { useAsyncAction } from '../lib/useAsync';
import { loadPrograms, stopAllRuns, stopRun } from '../state/actions';
import { anyRunAlive, remoteDir } from '../state/selectors';
import { useStudio } from '../state/store';
import { ProgramCard } from './programs/ProgramCard';

function RunsPanel() {
  const runsMap = useStudio((s) => s.runs);
  const runs = useMemo(
    () => Object.values(runsMap).sort((a, b) => b.started - a.started),
    [runsMap],
  );
  const selected = useStudio((s) => s.selectedRun);
  const select = useStudio((s) => s.selectRun);
  const anyAlive = useStudio(anyRunAlive);
  const stopAll = useAsyncAction(stopAllRuns);
  const stopOne = useAsyncAction(stopRun);
  return (
    <Panel
      title="Running"
      actions={
        <Button
          variant="danger"
          size="sm"
          icon={<OctagonX size={14} aria-hidden="true" />}
          disabled={!anyAlive}
          loading={stopAll.pending}
          onClick={() => void stopAll.run()}
        >
          Stop all
        </Button>
      }
    >
      {runs.length === 0 ? (
        <p className="dim small">Nothing started yet. Run a program and it shows up here.</p>
      ) : (
        <Table label="Runs" maxHeight={240}>
          <thead>
            <tr>
              <th>Program and state</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className={r.id === selected ? 'is-selected' : undefined}>
                <td>
                  <div className="run-name mono">{r.name}</div>
                  <div className="run-meta">
                    {r.alive ? (
                      <Badge tone="ok">Running</Badge>
                    ) : (
                      <Badge tone="neutral">
                        {'Finished' + (r.code != null ? ` (exit ${r.code})` : '')}
                      </Badge>
                    )}
                    {r.motion ? <Badge tone="warn">Moves</Badge> : null}
                    {r.pid != null ? <span className="dim small num">PID {r.pid}</span> : null}
                  </div>
                </td>
                <td className="cell-action">
                  <div className="run-actions">
                    <Button
                      size="sm"
                      aria-label={`Show output of ${r.name}`}
                      aria-pressed={r.id === selected}
                      onClick={() => select(r.id)}
                    >
                      Output
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      aria-label={`Stop ${r.name}`}
                      disabled={!r.alive}
                      onClick={() => void stopOne.run(r.id)}
                    >
                      Stop
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}

function LogPanel() {
  const run = useStudio((s) => (s.selectedRun ? s.runs[s.selectedRun] : undefined));
  const clear = useStudio((s) => s.clearRunLines);
  const [follow, setFollow] = useState(true);
  return (
    <Panel
      id="run-output"
      title="Output"
      actions={
        <>
          {run ? <span className="dim small mono">{run.name}</span> : null}
          <Checkbox
            label="Follow new lines"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
          />
          <Button size="sm" disabled={!run} onClick={() => run && clear(run.id)}>
            Clear view
          </Button>
        </>
      }
    >
      <OutputLog
        lines={run?.lines ?? null}
        label="Program output"
        follow={follow}
        tall
        empty={
          run
            ? run.alive
              ? 'Waiting for output.'
              : 'This run printed nothing.'
            : 'Select a run to see its output.'
        }
      />
      <p className="dim small">Studio keeps the last 2000 lines of each run.</p>
    </Panel>
  );
}

export function Programs() {
  const files = useStudio((s) => s.files);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const dir = useStudio(remoteDir);
  const refresh = useAsyncAction(loadPrograms);

  useEffect(() => {
    if (connected) void loadPrograms();
  }, [connected]);

  return (
    <div className="page">
      <h1 className="page-title">Programs</h1>
      <div className="split">
        <div className="split-main">
          <Panel
            title="Programs on the robot"
            actions={
              <>
                <span className="dim small mono">{dir}</span>
                <Button
                  size="sm"
                  icon={<RefreshCw size={14} aria-hidden="true" />}
                  disabled={!connected}
                  loading={refresh.pending}
                  onClick={() => void refresh.run()}
                >
                  Refresh
                </Button>
              </>
            }
          >
            {files.length === 0 ? (
              <EmptyState
                compact
                title={connected ? 'No programs in this folder' : 'Not connected'}
              >
                {connected
                  ? 'Add a .py or .sh file to the robot folder, or make one in the Code screen.'
                  : 'Connect to the robot on the Overview screen to list its programs.'}
              </EmptyState>
            ) : (
              <div className="prog-list">
                {files.map((f) => (
                  <ProgramCard key={f.name} file={f} />
                ))}
              </div>
            )}
            <p className="dim small">
              Programs that move the robot ask you to confirm first. Many also need{' '}
              <code>--yes</code> in the arguments box: open &ldquo;What does it do?&rdquo; to see
              what to type.
            </p>
          </Panel>
        </div>
        <div className="split-side">
          <RunsPanel />
          <LogPanel />
        </div>
      </div>
    </div>
  );
}
