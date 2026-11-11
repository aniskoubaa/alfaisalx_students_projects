import { RefreshCw } from 'lucide-react';
import { useState } from 'react';
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Panel,
  Spinner,
  Table,
} from '../../components/ui';
import { notify } from '../../state/feedback';
import { setCurrentRoute } from './api';
import {
  canSetCurrent,
  confirmText,
  currentSummary,
  formatSaved,
  routeStatus,
  waypointsText,
} from './model';
import { useRoutes } from './store';

/** The routes saved on the robot, with the current one marked and a way to change it. */
export function RouteList({ connected = true }: { connected?: boolean }) {
  const list = useRoutes((s) => s.list);
  const error = useRoutes((s) => s.listError);
  const trip = useRoutes((s) => s.trip);
  const loadRoutes = useRoutes((s) => s.loadRoutes);
  const [loading, setLoading] = useState(false);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const refresh = async () => {
    setLoading(true);
    await loadRoutes();
    setLoading(false);
  };

  const current = list?.current ?? null;

  const confirm = async () => {
    const name = choosing;
    if (!name) return;
    setPending(true);
    const r = await setCurrentRoute(name);
    setPending(false);
    setChoosing(null);
    if (r.ok) notify('ok', `The current route is now ${name}.`);
    else notify('error', `Could not change the current route. ${r.error}`);
    void loadRoutes();
  };

  return (
    <Panel
      title="Routes on the robot"
      actions={
        <Button
          size="sm"
          icon={<RefreshCw size={14} aria-hidden="true" />}
          loading={loading}
          disabled={!connected}
          onClick={() => void refresh()}
        >
          Refresh
        </Button>
      }
    >
      {!connected ? (
        <p className="dim small">Not connected to the robot. Connect to see its routes.</p>
      ) : error ? (
        <p className="mapping-error" role="alert">
          Could not read the routes. {error}
        </p>
      ) : list === null ? (
        <p className="dim small" role="status">
          <Spinner size={14} /> Loading the routes
        </p>
      ) : (
        <>
          <p className="route-current-line">
            Current route: <strong data-testid="route-current">{current ?? 'none'}</strong>
            <span className="dim small route-current-note">
              {' '}
              {currentSummary(current, list.current_ok, list.routes)}
            </span>
          </p>
          {list.routes.length === 0 ? (
            <EmptyState compact title="No routes on the robot yet">
              Upload a planned route folder below.
            </EmptyState>
          ) : (
            <Table label="Routes" className="route-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Status</th>
                  <th scope="col">Waypoints</th>
                  <th scope="col">Saved</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {list.routes.map((r) => {
                  const can = canSetCurrent(r, current, trip);
                  return (
                    <tr
                      key={r.name}
                      data-testid={`route-row-${r.name}`}
                      className={r.name === current ? 'is-selected' : ''}
                    >
                      <th scope="row">
                        {r.name} {r.name === current ? <Badge tone="info">Current</Badge> : null}
                      </th>
                      <td>
                        <Badge tone={r.valid ? 'ok' : 'warn'}>{routeStatus(r)}</Badge>
                      </td>
                      <td>{waypointsText(r)}</td>
                      <td>{formatSaved(r.mtime)}</td>
                      <td>
                        <Button
                          size="sm"
                          aria-label={`Use the route ${r.name}`}
                          disabled={!can.ok}
                          title={can.ok ? undefined : can.reason}
                          onClick={() => setChoosing(r.name)}
                        >
                          Use this route
                        </Button>
                        {!can.ok && r.name !== current ? (
                          <span className="dim small route-why"> {can.reason}</span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </>
      )}
      <ConfirmDialog
        open={choosing !== null}
        title={`Use route ${choosing ?? ''}?`}
        body={confirmText(current, choosing ?? '')}
        confirmLabel="Use this route"
        pending={pending}
        onConfirm={() => void confirm()}
        onCancel={() => setChoosing(null)}
      />
    </Panel>
  );
}
