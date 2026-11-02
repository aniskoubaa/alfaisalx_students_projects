import { ChevronDown, ChevronRight, Search, Unplug } from 'lucide-react';
import { useState } from 'react';
import type { Candidate } from '../../api';
import { connHint, connView, routeWords } from '../../lib/connView';
import { fmtClock } from '../../lib/format';
import { useAsyncAction } from '../../lib/useAsync';
import { connect, deepDiscover, disconnect, discover, setupKeyLogin } from '../../state/actions';
import { showDiagnostics } from '../../state/toolsActions';
import { useStudio } from '../../state/store';
import { openWizard } from '../../state/wizardActions';
import { Badge, Button, Field, Input, Panel, Table } from '../../components/ui';

function CandidateRow({
  c,
  onConnect,
  busy,
}: {
  c: Candidate;
  onConnect: (host: string) => void;
  busy: boolean;
}) {
  return (
    <tr>
      <td>
        <span className="mono">{c.host}</span>
        {c.identity === 'confirmed' ? (
          <>
            {' '}
            <Badge tone="ok">Your robot (identity confirmed)</Badge>
          </>
        ) : c.label ? (
          <span className="dim"> {c.label}</span>
        ) : null}
      </td>
      <td>{routeWords(c.via) ?? '–'}</td>
      <td>
        {c.reachable ? <Badge tone="ok">Reachable</Badge> : <Badge tone="bad">No answer</Badge>}
      </td>
      <td className="num">{c.ms == null ? '–' : Math.round(c.ms)}</td>
      <td className="cell-action">
        <Button
          size="sm"
          variant={c.identity === 'confirmed' ? 'primary' : 'secondary'}
          disabled={busy}
          aria-label={`Connect to ${c.host}`}
          title={c.reachable ? undefined : 'This address did not answer on port 22'}
          onClick={() => onConnect(c.host)}
        >
          Connect
        </Button>
      </td>
    </tr>
  );
}

export function ConnectionPanel() {
  const conn = useStudio((s) => s.conn);
  const hello = useStudio((s) => s.hello);
  const sse = useStudio((s) => s.sse);
  const candidates = useStudio((s) => s.candidates);
  const deep = useStudio((s) => s.deep);
  const lastHost = useStudio((s) => s.settings.last_host);
  const hotspot = useStudio(
    (s) => s.settings.hotspot_addr ?? s.defaults.hotspot_addr ?? '10.42.0.1',
  );
  const hostname = useStudio(
    (s) => s.settings.robot_hostname ?? s.defaults.robot_hostname ?? 'turtlebot4',
  );

  const connectedAt = useStudio((s) => s.connectedAt);
  const [typed, setTyped] = useState<string | null>(null);
  const [changeOpen, setChangeOpen] = useState(false);
  const address = typed ?? lastHost ?? '';

  const view = connView(conn, hello, sse);
  const hint = conn.state === 'error' ? connHint(conn) : null;
  const linkBusy = ['connecting', 'discovering', 'connected', 'reconnecting'].includes(conn.state);

  const doConnect = useAsyncAction((host?: string) => connect(host ?? address));
  const doDiscover = useAsyncAction(discover);
  const doDeep = useAsyncAction(deepDiscover);
  const doDisconnect = useAsyncAction(disconnect);
  const doKey = useAsyncAction(setupKeyLogin);
  const doDiag = useAsyncAction(showDiagnostics);

  // Connected: a short summary; the address field and the search tools sit behind "Change robot".
  const compact = conn.state === 'connected';
  const showTools = !compact || changeOpen;
  const found = candidates.find((c) => c.host === conn.host);
  const latency = found?.ms != null && found.reachable ? Math.round(found.ms) : null;

  const pct = deep.total ? Math.min(100, Math.round((100 * deep.done) / deep.total)) : 0;

  return (
    <Panel
      wide
      title="Connection"
      actions={
        <Button
          size="sm"
          icon={<Unplug size={14} aria-hidden="true" />}
          disabled={conn.state === 'disconnected' || conn.state === 'error'}
          loading={doDisconnect.pending}
          onClick={() => void doDisconnect.run()}
        >
          Disconnect
        </Button>
      }
    >
      <div className="conn-head">
        <p className="conn-state" data-tone={view.tone}>
          {compact && view.host ? (
            <>
              Connected to <span className="mono">{view.host}</span>
            </>
          ) : (
            view.label
          )}
        </p>
        {conn.error ? <p className="conn-detail">{conn.error}</p> : null}
        {conn.state === 'error' || (conn.state === 'disconnected' && conn.error) ? (
          <div className="row">
            <Button
              size="sm"
              loading={doDiag.pending}
              aria-label="Show diagnostics to send with a problem report"
              onClick={() => void doDiag.run()}
            >
              Show diagnostics
            </Button>
          </div>
        ) : null}
        {compact ? (
          <dl className="conn-summary">
            <div>
              <dt>Robot</dt>
              <dd className="mono">{view.host ?? 'unknown'}</dd>
            </div>
            <div>
              <dt>Reached over</dt>
              <dd>{view.route ?? 'unknown'}</dd>
            </div>
            <div>
              <dt>Connected since</dt>
              <dd>{connectedAt ? fmtClock(connectedAt / 1000) : 'unknown'}</dd>
            </div>
            {latency != null ? (
              <div>
                <dt>Answer time</dt>
                <dd>{latency} ms</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        {conn.state === 'connected' && hello ? (
          <p className="conn-detail">
            {hello.fake
              ? 'Simulated robot: nothing real moves'
              : hello.ros
                ? `ROS 2 ${hello.ros_distro ?? ''}`.trim()
                : 'ROS is not available on the robot'}
          </p>
        ) : null}
      </div>

      {hint ? (
        <div className="note note-warn" role="alert">
          <strong>{hint.title}.</strong> {hint.text}
          <div className="row">
            {hint.kind === 'key_not_set_up' ? (
              <Button
                variant="primary"
                size="sm"
                loading={doKey.pending}
                onClick={() => void doKey.run()}
              >
                Set up key login
              </Button>
            ) : null}
            <Button size="sm" onClick={() => openWizard()}>
              Open the setup wizard
            </Button>
          </div>
        </div>
      ) : null}

      {compact ? (
        <div className="row">
          <Button
            size="sm"
            icon={
              changeOpen ? (
                <ChevronDown size={14} aria-hidden="true" />
              ) : (
                <ChevronRight size={14} aria-hidden="true" />
              )
            }
            aria-expanded={changeOpen}
            aria-controls="conn-tools"
            onClick={() => {
              setChangeOpen((o) => !o);
            }}
          >
            Change robot
          </Button>
        </div>
      ) : null}

      {showTools ? (
        <div id="conn-tools" className="conn-tools">
          <form
            className="conn-form"
            onSubmit={(e) => {
              e.preventDefault();
              void doConnect.run();
            }}
          >
            <Field label="Robot address (optional)" className="grow">
              {(p) => (
                <Input
                  {...p}
                  className="mono"
                  value={address}
                  placeholder={`for example ${hotspot} or ${hostname}.local`}
                  onChange={(e) => {
                    setTyped(e.target.value);
                  }}
                />
              )}
            </Field>
            <div className="row row-end">
              <Button
                type="submit"
                variant="primary"
                loading={doConnect.pending}
                disabled={linkBusy}
              >
                Connect
              </Button>
              <Button loading={doDiscover.pending} onClick={() => void doDiscover.run()}>
                Discover
              </Button>
              <Button onClick={() => openWizard()}>Setup wizard</Button>
            </div>
          </form>

          <div className="row deep-row">
            <Button
              icon={<Search size={16} aria-hidden="true" />}
              loading={deep.running || doDeep.pending}
              onClick={() => void doDeep.run()}
            >
              Search the whole network
            </Button>
            <span className="dim small grow">
              Checks every address on this computer&apos;s network for your robot, about 15 seconds.
              Or read the address on the robot&apos;s screen and type it.
            </span>
          </div>

          {deep.running ? (
            <div className="progress-wrap" role="status" aria-live="polite">
              <div
                className="progress"
                role="progressbar"
                aria-label="Search progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
              >
                <i style={{ width: pct + '%' }} />
              </div>
              <span className="dim small">
                {deep.total ? `Checking addresses: ${deep.done} of ${deep.total}` : 'Starting…'}
              </span>
            </div>
          ) : null}

          {candidates.length ? (
            <Table label="Robots found" maxHeight={220}>
              <thead>
                <tr>
                  <th>Address</th>
                  <th>Found via</th>
                  <th>Reachable</th>
                  <th className="num">ms</th>
                  <th>
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <CandidateRow
                    key={c.host}
                    c={c}
                    busy={doConnect.pending}
                    onConnect={(h) => {
                      setTyped(h);
                      void doConnect.run(h);
                    }}
                  />
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="dim small cand-empty">
              No robots listed yet. Press Discover to look on the cable and Wi-Fi.
            </p>
          )}
        </div>
      ) : null}
    </Panel>
  );
}
