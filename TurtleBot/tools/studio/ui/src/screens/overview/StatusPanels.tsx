import { Anchor, Power } from 'lucide-react';
import type { ReactNode } from 'react';
import type { BatteryStatus } from '../../api';
import { fmtNum, fmtUptime, MINUS } from '../../lib/format';
import { useAsyncAction } from '../../lib/useAsync';
import { useNow } from '../../lib/useNow';
import { dockAction, startLidar } from '../../state/actions';
import { isStale } from '../../state/selectors';
import { useStudio } from '../../state/store';
import { Badge, Button, Dash, KV, KeyValue, Panel } from '../../components/ui';

const NB = ' ';

/** A number with a unit, or a dash while unknown. */
function Val({
  v,
  digits = 1,
  unit,
}: {
  v: number | null | undefined;
  digits?: number;
  unit?: string;
}) {
  if (v === null || v === undefined || Number.isNaN(v)) return <Dash />;
  return (
    <span className="num">
      {fmtNum(v, digits)}
      {unit ? NB + unit : ''}
    </span>
  );
}

function YesNo({
  v,
  yes = 'Yes',
  no = 'No',
}: {
  v: boolean | null | undefined;
  yes?: string;
  no?: string;
}) {
  if (v === null || v === undefined) return <Badge tone="neutral">Unknown</Badge>;
  return v ? <Badge tone="ok">{yes}</Badge> : <Badge tone="neutral">{no}</Badge>;
}

function powerState(b: BatteryStatus): ReactNode {
  const cur = b.current_a;
  const amps = cur == null ? '' : ` (${cur < 0 ? MINUS : ''}${Math.abs(cur).toFixed(2)} A)`;
  if (b.full) return <Badge tone="ok">Full</Badge>;
  if (b.charging === true) return <Badge tone="ok">{'Charging' + amps}</Badge>;
  if (cur != null && cur < 0) return <Badge tone="neutral">{'On battery' + amps}</Badge>;
  if (b.charging === false) return <Badge tone="neutral">{'Not charging' + amps}</Badge>;
  return <Badge tone="neutral">Unknown</Badge>;
}

function useStale(): boolean {
  const now = useNow(500);
  return useStudio((s) => isStale(s, now));
}

export function BatteryPanel() {
  const b = useStudio((s) => s.status?.battery) ?? {};
  const stale = useStale();
  const pct = b.percent ?? null;
  const low = pct !== null && pct < 20;
  return (
    <Panel title="Battery" stale={stale}>
      <div className="big-number">
        <span className="num big">{pct === null ? '–' : Math.round(pct)}</span>
        <span className="big-unit">%</span>
        {low ? <Badge tone="warn">Low</Badge> : null}
      </div>
      <div
        className={'meter' + (low ? ' meter-low' : '')}
        role="progressbar"
        aria-label="Battery charge"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct === null ? undefined : Math.round(pct)}
      >
        <i style={{ width: (pct === null ? 0 : Math.max(0, Math.min(100, pct))) + '%' }} />
      </div>
      <KeyValue label="Battery details">
        <KV label="Voltage">
          <Val v={b.voltage} digits={2} unit="V" />
        </KV>
        <KV label="Power">{powerState(b)}</KV>
        <KV label="Current">
          <Val v={b.current_a} digits={2} unit="A" />
        </KV>
      </KeyValue>
    </Panel>
  );
}

export function DockPanel() {
  const status = useStudio((s) => s.status);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const action = useStudio((s) => s.action);
  const stale = useStale();
  const d = status?.dock ?? {};
  const e = status?.estop;
  const undock = useAsyncAction(() => dockAction('undock'));
  const dock = useAsyncAction(() => dockAction('dock'));
  return (
    <Panel title="Dock" stale={stale}>
      <KeyValue label="Dock details">
        <KV label="Docked">
          <YesNo v={d.is_docked} yes="Docked" no="Undocked" />
        </KV>
        <KV label="Dock visible">
          <YesNo v={d.dock_visible} />
        </KV>
        <KV label="E-stop">
          {e?.on ? (
            <Badge tone="bad">On</Badge>
          ) : e?.on === false ? (
            <Badge tone="ok">Off</Badge>
          ) : (
            <Badge tone="neutral">Unknown</Badge>
          )}
        </KV>
      </KeyValue>
      <div className="row">
        <Button
          icon={<Power size={16} aria-hidden="true" />}
          disabled={!connected || d.is_docked === false}
          loading={undock.pending}
          onClick={() => void undock.run()}
        >
          Undock
        </Button>
        <Button
          icon={<Anchor size={16} aria-hidden="true" />}
          disabled={!connected || d.is_docked === true}
          loading={dock.pending}
          onClick={() => void dock.run()}
        >
          Dock
        </Button>
        {action ? (
          <span className="dim small" role="status">
            {action.name}: {action.state}
            {action.detail
              ? ` (${typeof action.detail === 'string' ? action.detail : JSON.stringify(action.detail)})`
              : ''}
          </span>
        ) : null}
      </div>
    </Panel>
  );
}

export function PosePanel() {
  const o = useStudio((s) => s.status?.odom) ?? {};
  const stale = useStale();
  const age = o.age_s;
  return (
    <Panel title="Motion and odometry" stale={stale}>
      <KeyValue label="Motion details">
        <KV label="Position x / y">
          <span className="num">
            {fmtNum(o.x, 2)} / {fmtNum(o.y, 2)}
            {NB}m
          </span>
        </KV>
        <KV label="Heading">
          <Val v={o.yaw_deg} digits={0} unit={'°'} />
        </KV>
        <KV label="Speed">
          <span className="num">
            {fmtNum(o.vx, 2)}
            {NB}m/s, {fmtNum(o.wz, 2)}
            {NB}rad/s
          </span>
        </KV>
        <KV label="Odometry rate">
          <Val v={o.rate_hz} digits={1} unit="Hz" />
        </KV>
        <KV label="Odometry age">
          {age == null ? (
            <Dash />
          ) : age > 0.5 ? (
            <Badge tone="bad">{age.toFixed(2)} s old</Badge>
          ) : (
            <Badge tone="ok">{age.toFixed(2) + ' s'}</Badge>
          )}
        </KV>
      </KeyValue>
    </Panel>
  );
}

export function ScanPanel() {
  const status = useStudio((s) => s.status);
  const sc = status?.scan ?? {};
  const docked = status?.dock?.is_docked;
  const hazards = status?.hazards ?? [];
  const stale = useStale();
  const lidar = useAsyncAction(startLidar);
  const lidarOff = docked === false && sc.rate_hz == null;
  return (
    <Panel title="Lidar and hazards" stale={stale}>
      <KeyValue label="Lidar details">
        <KV label="Nearest ahead">
          <Val v={sc.front_m} digits={2} unit="m" />
        </KV>
        <KV label="Nearest any">
          <Val v={sc.min_m} digits={2} unit="m" />
        </KV>
        <KV label="Lidar rate">
          {!status ? (
            <Dash />
          ) : sc.rate_hz == null ? (
            <Badge tone="warn">Off</Badge>
          ) : (
            <Val v={sc.rate_hz} digits={1} unit="Hz" />
          )}
        </KV>
        <KV label="Hazards">
          {hazards.length ? (
            <span className="badge-list">
              {hazards.map((h) => (
                <Badge key={h} tone="bad">
                  {h}
                </Badge>
              ))}
            </span>
          ) : (
            <Badge tone="ok">None</Badge>
          )}
        </KV>
      </KeyValue>
      {lidarOff ? (
        <div className="note note-warn">
          <strong>The lidar is off.</strong> There is no scan data while the robot is undocked.
          <div className="row">
            <Button size="sm" loading={lidar.pending} onClick={() => void lidar.run()}>
              Start lidar motor
            </Button>
          </div>
        </div>
      ) : docked === true && sc.rate_hz == null ? (
        <p className="dim small">The lidar is off while the robot is docked. This is normal.</p>
      ) : null}
    </Panel>
  );
}

export function NetworkPanel() {
  const n = useStudio((s) => s.status?.net) ?? {};
  const stale = useStale();
  const addresses = Object.entries(n.addresses ?? {});
  return (
    <Panel title="Network" stale={stale}>
      <KeyValue label="Network details">
        <KV label="Mode">
          {n.wifi_mode ? (
            <Badge tone={n.wifi_mode === 'down' ? 'bad' : 'ok'}>{n.wifi_mode}</Badge>
          ) : (
            <Dash />
          )}
        </KV>
        <KV label="Network name">{n.ssid ? n.ssid : <Dash />}</KV>
        <KV label="Signal">
          {n.signal_dbm == null ? (
            <Dash />
          ) : (
            <span className="num">
              {n.signal_dbm}
              {NB}dBm{n.link_quality != null ? ` (${n.link_quality})` : ''}
            </span>
          )}
        </KV>
        <KV label="Addresses">
          {addresses.length ? (
            <span className="addr-list">
              {addresses.map(([k, v]) => (
                <span key={k} className="mono">
                  {k} {v}
                </span>
              ))}
            </span>
          ) : (
            <Dash />
          )}
        </KV>
        <KV label="Wi-Fi power save">{n.powersave ?? n.powersave_students ?? <Dash />}</KV>
      </KeyValue>
    </Panel>
  );
}

export function SystemPanel() {
  const status = useStudio((s) => s.status);
  const sy = status?.system ?? {};
  const cl = status?.clock ?? {};
  const stale = useStale();
  const temp = sy.temp_c;
  const clockBad = cl.synced === false || (cl.year != null && cl.year < 2026);
  return (
    <Panel title="Robot system" stale={stale}>
      <KeyValue label="System details">
        <KV label="CPU">
          <span className="num">
            {fmtNum(sy.cpu_pct, 0)}
            {NB}% (load {fmtNum(sy.load1, 2)})
          </span>
        </KV>
        <KV label="Temperature">
          {temp == null ? (
            <Dash />
          ) : temp > 75 ? (
            <Badge tone="bad">{temp.toFixed(1)} &deg;C</Badge>
          ) : temp > 65 ? (
            <Badge tone="warn">{temp.toFixed(1)} &deg;C</Badge>
          ) : (
            <span className="num">
              {temp.toFixed(1)}
              {NB}&deg;C
            </span>
          )}
        </KV>
        <KV label="Throttled">
          {sy.throttled == null ? (
            <Dash />
          ) : sy.throttled === '0x0' ? (
            <Badge tone="ok">No</Badge>
          ) : (
            <Badge tone="warn">{sy.throttled}</Badge>
          )}
        </KV>
        <KV label="Memory">
          {sy.mem_total_mb ? (
            <span className="num">
              {Math.round(sy.mem_used_mb ?? 0)} / {Math.round(sy.mem_total_mb)}
              {NB}MB
            </span>
          ) : (
            <Dash />
          )}
        </KV>
        <KV label="Disk free">
          <Val v={sy.disk_free_gb} digits={1} unit="GB" />
        </KV>
        <KV label="Uptime">
          <span className="num">{fmtUptime(sy.uptime_s)}</span>
        </KV>
        <KV label="ROS service">
          {status?.ros_service ? (
            <Badge tone={status.ros_service === 'active' ? 'ok' : 'bad'}>
              {status.ros_service}
            </Badge>
          ) : (
            <Dash />
          )}
        </KV>
      </KeyValue>
      {clockBad ? (
        <div className="note note-warn">
          <strong>The robot clock looks wrong</strong> (
          {cl.synced === false ? 'not synced' : 'synced'}, year {cl.year ?? 'unknown'}). Log times
          and file times will be off.
        </div>
      ) : null}
    </Panel>
  );
}
