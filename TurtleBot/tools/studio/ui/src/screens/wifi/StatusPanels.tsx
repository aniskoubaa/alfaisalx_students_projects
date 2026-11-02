import { RefreshCw } from 'lucide-react';
import { Badge, Button, Dash, KV, KeyValue, Panel, Spinner } from '../../components/ui';
import { routeWords } from '../../lib/connView';
import { robotMode } from '../../lib/wifi';
import { loadLaptop, loadRobot } from '../../state/wifiActions';
import { useStudio } from '../../state/store';
import { useWifi } from '../../state/wifiStore';

export function ThisComputerPanel() {
  const laptop = useWifi((s) => s.laptop);
  const err = useWifi((s) => s.laptopErr);
  const loading = useWifi((s) => s.laptopLoading);
  const w = laptop?.wifi ?? null;
  const wired = laptop?.wired ?? [];

  return (
    <Panel
      title="This computer"
      actions={
        <Button
          size="sm"
          icon={<RefreshCw size={14} aria-hidden="true" />}
          loading={loading}
          aria-label="Refresh this computer's network info"
          onClick={() => void loadLaptop()}
        >
          Refresh
        </Button>
      }
    >
      {!laptop && !err ? (
        <p className="dim small">
          <Spinner size={14} label="Reading the network info" /> Reading the network info…
        </p>
      ) : (
        <>
          <KeyValue label="This computer's Wi-Fi">
            <KV label="Wi-Fi network">
              {w?.ssid ? (
                <strong>{w.ssid}</strong>
              ) : laptop ? (
                <Badge tone="neutral">Not on Wi-Fi</Badge>
              ) : (
                <Badge tone="warn">Cannot tell</Badge>
              )}
            </KV>
            <KV label="Signal">
              {w?.signal_pct != null ? <span className="num">{w.signal_pct} %</span> : <Dash />}
            </KV>
            <KV label="State">{w?.state || <Dash />}</KV>
            <KV label="System">{laptop?.os || <Dash />}</KV>
          </KeyValue>
          <div className="wired">
            <p className="small">
              <strong>Cables (Ethernet)</strong>
            </p>
            {wired.length ? (
              <ul className="wired-list">
                {wired.map((x) => (
                  <li key={x.name}>
                    <span>{x.name}</span>{' '}
                    {x.up ? <Badge tone="ok">Up</Badge> : <Badge tone="neutral">Down</Badge>}
                    {x.ipv4 && x.ipv4.length ? (
                      <span className="mono small"> {x.ipv4.join(', ')}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="dim small">None found.</p>
            )}
          </div>
        </>
      )}
      {err ? (
        <div className="note note-warn" role="alert">
          Could not read this computer&apos;s network info: {err}
        </div>
      ) : null}
    </Panel>
  );
}

export function RobotPanel() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const via = useStudio((s) => s.conn.via);
  const net = useStudio((s) => s.status?.net);
  const info = useWifi((s) => s.robot);
  const err = useWifi((s) => s.robotErr);
  const loading = useWifi((s) => s.robotLoading);
  const wl = info?.wlan0 ?? {};
  const mode = robotMode(info, net?.wifi_mode);
  const ip = wl.ip || net?.addresses?.wlan0;
  const dbm = wl.signal_dbm ?? net?.signal_dbm;

  return (
    <Panel
      title="The robot"
      actions={
        <Button
          size="sm"
          icon={<RefreshCw size={14} aria-hidden="true" />}
          loading={loading}
          disabled={!connected}
          aria-label="Refresh the robot's Wi-Fi info"
          onClick={() => void loadRobot()}
        >
          Refresh
        </Button>
      }
    >
      {!connected ? (
        <>
          <KeyValue label="The robot's Wi-Fi">
            <KV label="Status">
              <Badge tone="neutral">Not connected</Badge>
            </KV>
          </KeyValue>
          <p className="dim small">
            Not connected yet. Connect by cable (C) or join its hotspot (A) first.
          </p>
        </>
      ) : (
        <>
          <KeyValue label="The robot's Wi-Fi">
            <KV label="Wi-Fi mode">
              {mode === 'ap' ? (
                <Badge tone="warn">Hotspot (its own Wi-Fi)</Badge>
              ) : mode === 'client' ? (
                <Badge tone="ok">Joined a network</Badge>
              ) : (
                <Dash />
              )}
            </KV>
            <KV label="Network">{wl.ssid || net?.ssid || <Dash />}</KV>
            <KV label="Wi-Fi address">{ip ? <span className="mono">{ip}</span> : <Dash />}</KV>
            <KV label="Signal">
              {dbm != null ? <span className="num">{dbm} dBm</span> : <Dash />}
            </KV>
            <KV label="Power save">
              {wl.powersave || net?.powersave || net?.powersave_students || <Dash />}
            </KV>
            <KV label="Studio talks to it via">{routeWords(via) || <Dash />}</KV>
          </KeyValue>
          {mode === 'ap' ? (
            <p className="dim small">
              The robot found no saved network, so it made its own hotspot.
            </p>
          ) : null}
          {err ? (
            <div className="note note-warn" role="alert">
              Could not read the robot&apos;s Wi-Fi info: {err}
            </div>
          ) : null}
        </>
      )}
    </Panel>
  );
}
