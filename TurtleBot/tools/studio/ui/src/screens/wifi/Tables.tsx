import { Badge, Button, Dash, Panel, Table } from '../../components/ui';
import type { SavedWifi, ScannedWifi } from '../../api/setup-types';
import { isProtectedWifi, wifiSecurity } from '../../lib/wifi';
import { useAsyncAction } from '../../lib/useAsync';
import { nameOf } from '../../state/names';
import { useStudio } from '../../state/store';
import { removeWifi } from '../../state/wifiActions';
import { useWifi } from '../../state/wifiStore';

function RemoveButton({ x }: { x: SavedWifi }) {
  const doRemove = useAsyncAction(() => removeWifi(x));
  return (
    <Button
      size="sm"
      variant="danger"
      loading={doRemove.pending}
      aria-label={`Remove ${x.name} from the robot`}
      onClick={() => void doRemove.run()}
    >
      Remove
    </Button>
  );
}

export function SavedPanel() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const hotspot = useStudio((s) => nameOf(s, 'hotspot_ssid'));
  const saved = useWifi((s) => s.robot?.saved) ?? [];
  const loaded = useWifi((s) => s.robot !== null);
  return (
    <Panel title="Saved networks on the robot" wide>
      <p className="small dim">
        The robot joins the saved network with the highest priority that it can see. The
        robot&apos;s own hotspot and cable entries cannot be removed here.
      </p>
      {saved.length ? (
        <Table label="Saved networks on the robot" maxHeight={260}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Network (SSID)</th>
              <th className="num">Priority</th>
              <th>Auto-join</th>
              <th>Power save</th>
              <th>Active</th>
              <th>
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {saved.map((x) => (
              <tr key={x.name}>
                <td className="mono">{x.name}</td>
                <td>{x.ssid || <Dash />}</td>
                <td className="num">{x.priority ?? <Dash />}</td>
                <td>
                  {x.autoconnect == null ? (
                    <Badge tone="neutral">Unknown</Badge>
                  ) : x.autoconnect ? (
                    <Badge tone="ok">Yes</Badge>
                  ) : (
                    <Badge tone="neutral">No</Badge>
                  )}
                </td>
                <td>{x.powersave || <Dash />}</td>
                <td>
                  {x.active ? <Badge tone="ok">Active</Badge> : <Badge tone="neutral">No</Badge>}
                </td>
                <td className="cell-action">
                  {isProtectedWifi(x.name, hotspot) ? (
                    <span className="dim small">Protected</span>
                  ) : (
                    <RemoveButton x={x} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <p className="dim small">
          {connected && loaded
            ? 'The robot has no saved networks.'
            : 'Connect to the robot to see its saved networks.'}
        </p>
      )}
    </Panel>
  );
}

export function SeenPanel({ onUse }: { onUse: (ssid: string) => void }) {
  const info = useWifi((s) => s.robot);
  const scan: ScannedWifi[] = info?.scan ?? [];
  const note =
    info?.scan_note ||
    (!info
      ? 'Connect to the robot to see what it can see.'
      : scan.length
        ? ''
        : 'No networks found.');
  return (
    <Panel title="Networks the robot can see" wide>
      {note ? <p className="dim small">{note}</p> : null}
      {scan.length ? (
        <Table label="Networks the robot can see" maxHeight={240}>
          <thead>
            <tr>
              <th>Network (SSID)</th>
              <th className="num">Signal</th>
              <th>Security</th>
              <th className="num">Channel</th>
              <th>
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {scan.map((x, i) => {
              const sec = wifiSecurity(x.security);
              return (
                <tr key={`${x.ssid ?? ''}-${i}`}>
                  <td>{x.ssid || <Dash />}</td>
                  <td className="num">{x.signal ?? <Dash />}</td>
                  <td>
                    {sec.ok ? (
                      <Badge tone="ok">{sec.label}</Badge>
                    ) : (
                      <Badge tone="warn">{sec.label}: not supported</Badge>
                    )}
                  </td>
                  <td className="num">{x.chan ?? <Dash />}</td>
                  <td className="cell-action">
                    {x.ssid ? (
                      <Button
                        size="sm"
                        disabled={!sec.ok}
                        title={sec.ok ? undefined : sec.why}
                        aria-label={`Use ${x.ssid} as the network to join`}
                        onClick={() => onUse(x.ssid as string)}
                      >
                        Use
                      </Button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      ) : null}
    </Panel>
  );
}
