import { HeartPulse } from 'lucide-react';
import { useState } from 'react';
import type { HealthCheck } from '../../api';
import { api } from '../../api';
import { useAsyncAction } from '../../lib/useAsync';
import { report } from '../../state/actions';
import { useStudio } from '../../state/store';
import { Badge, Button, Panel, Table } from '../../components/ui';

export function HealthPanel() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const [checks, setChecks] = useState<HealthCheck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useAsyncAction(async () => {
    setError(null);
    const r = report(await api().bridge('health'), 'Health check', true);
    if (r.ok) setChecks(r.checks ?? []);
    else setError(r.error);
  });
  return (
    <Panel
      wide
      title="Health check"
      actions={
        <Button
          icon={<HeartPulse size={16} aria-hidden="true" />}
          disabled={!connected}
          loading={run.pending}
          onClick={() => void run.run()}
        >
          Run health check
        </Button>
      }
    >
      {error ? (
        <div className="note note-bad" role="alert">
          <strong>The health check failed.</strong> {error}
        </div>
      ) : checks ? (
        <Table label="Health check results">
          <thead>
            <tr>
              <th>Check</th>
              <th>Result</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>
                  {c.ok === true ? (
                    <Badge tone="ok">OK</Badge>
                  ) : c.ok === false ? (
                    <Badge tone="bad">Problem</Badge>
                  ) : (
                    <Badge tone="neutral">Unknown</Badge>
                  )}
                </td>
                <td>{c.detail ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <p className="dim small">
          Read-only checks of ROS, topics, the clock and the sensors. Nothing moves.
        </p>
      )}
    </Panel>
  );
}
