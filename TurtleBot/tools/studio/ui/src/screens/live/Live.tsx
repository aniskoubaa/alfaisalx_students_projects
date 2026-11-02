import { Compass, Crosshair, Eraser, ZoomIn, ZoomOut } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, IconButton, KV, KeyValue, Panel } from '../../components/ui';
import { DrivePanel } from '../../features/teleop/DrivePanel';
import { disarm } from '../../features/teleop/driver';
import { useDriveKeys } from '../../features/teleop/useDriveKeys';
import { isDocked } from '../../state/selectors';
import { useStudio } from '../../state/store';
import { LiveCanvas } from './LiveCanvas';
import { LiveModel } from './model';
import type { ModelSnapshot } from './model';
import { fmtNearest, noScanNote } from './scan';
import { useLiveStreams } from './useStreams';

type Listener = (s: ModelSnapshot, stale: boolean) => void;

/** Numbers beside the map. They update 5 times a second through a small listener list. */
function useSnapshot(bus: React.MutableRefObject<Set<Listener>>): {
  snap: ModelSnapshot | null;
  stale: boolean;
} {
  const [state, setState] = useState<{ snap: ModelSnapshot | null; stale: boolean }>({
    snap: null,
    stale: true,
  });
  useEffect(() => {
    const set = bus.current;
    const fn: Listener = (snap, stale) => setState({ snap, stale });
    set.add(fn);
    return () => {
      set.delete(fn);
    };
  }, [bus]);
  return state;
}

function MapNote({ bus }: { bus: React.MutableRefObject<Set<Listener>> }) {
  const { snap, stale } = useSnapshot(bus);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const docked = useStudio(isDocked);
  if (!stale && connected) return null;
  return (
    <p className="live-note" role="status">
      {noScanNote({ connected, docked, everScan: (snap?.lastScanAt ?? 0) > 0 })}
    </p>
  );
}

function Readouts({
  bus,
  onClear,
}: {
  bus: React.MutableRefObject<Set<Listener>>;
  onClear: () => void;
}) {
  const { snap, stale } = useSnapshot(bus);
  const p = snap?.pose ?? null;
  const dash = '–';
  const deg = p ? ((p.yaw * 180) / Math.PI + 360) % 360 : null;
  return (
    <Panel title="Readouts" actions={null}>
      <KeyValue label="Live readouts">
        <KV label="Nearest obstacle">
          <span className={stale ? 'dim' : 'strong'}>
            {stale ? dash : fmtNearest(snap?.nearest ?? null)}
          </span>
        </KV>
        <KV label="Lidar">
          {stale
            ? 'No data'
            : `${snap?.points ?? 0} points, ${(snap?.scanHz ?? 0).toFixed(1)} scans/s`}
        </KV>
        <KV label="Position">
          <span className="num">{p ? `${p.x.toFixed(2)} m, ${p.y.toFixed(2)} m` : dash}</span>
        </KV>
        <KV label="Heading">
          <span className="num">{deg === null ? dash : `${deg.toFixed(0)}°`}</span>
        </KV>
        <KV label="Speed">
          <span className="num">
            {p ? `${(snap?.vx ?? 0).toFixed(2)} m/s, ${(snap?.wz ?? 0).toFixed(2)} rad/s` : dash}
          </span>
        </KV>
        <KV label="Path">
          <span className="num">{snap?.trailPoints ?? 0} points</span>{' '}
          <Button size="sm" icon={<Eraser size={14} aria-hidden="true" />} onClick={onClear}>
            Clear trail
          </Button>
        </KV>
      </KeyValue>
    </Panel>
  );
}

export function Live() {
  const [m] = useState(() => new LiveModel());
  const bus = useRef(new Set<Listener>());
  const size = useRef({ width: 800, height: 600 });
  const [follow, setFollow] = useState(true);
  const [headingUp, setHeadingUp] = useState(true);

  useLiveStreams();
  useDriveKeys();

  // Leaving this screen ends driving, whatever else happens.
  useEffect(() => {
    return () => disarm('You left the Live screen.');
  }, []);

  const onSnapshot = useCallback((s: ModelSnapshot, stale: boolean) => {
    bus.current.forEach((fn) => fn(s, stale));
  }, []);

  const zoom = (f: number) => m.zoom(f, size.current.width, size.current.height);

  return (
    <div className="page live">
      <h1 className="page-title">Live</h1>
      <div className="live-grid">
        <Panel className="live-stage" aria-label="Live map">
          <div className="live-toolbar" role="toolbar" aria-label="Map controls">
            <IconButton
              label="Zoom out"
              icon={<ZoomOut size={18} aria-hidden="true" />}
              variant="secondary"
              onClick={() => zoom(0.8)}
            />
            <IconButton
              label="Zoom in"
              icon={<ZoomIn size={18} aria-hidden="true" />}
              variant="secondary"
              onClick={() => zoom(1.25)}
            />
            <Button
              icon={<Crosshair size={16} aria-hidden="true" />}
              aria-pressed={follow}
              onClick={() => {
                const v = !follow;
                m.setFollow(v, size.current.width, size.current.height);
                setFollow(v);
              }}
            >
              {follow ? 'Following robot' : 'Free view'}
            </Button>
            <Button
              icon={<Compass size={16} aria-hidden="true" />}
              aria-label={
                headingUp
                  ? 'Map orientation: robot up. Switch to north up.'
                  : 'Map orientation: north up. Switch to robot up.'
              }
              onClick={() => {
                m.setHeadingUp(!headingUp);
                setHeadingUp(!headingUp);
              }}
            >
              {headingUp ? 'Robot up' : 'North up'}
            </Button>
          </div>
          <LiveCanvas
            model={m}
            onSnapshot={onSnapshot}
            onFreePan={() => setFollow(false)}
            sizeRef={size}
          />
          <MapNote bus={bus} />
        </Panel>
        <div className="live-side">
          <DrivePanel />
          <p className="phone-only dim small">
            Driving by stick or keys needs a wider screen. On a phone you can watch the map and use
            the E-STOP.
          </p>
          <Readouts bus={bus} onClear={() => m.clearTrail()} />
        </div>
      </div>
    </div>
  );
}
