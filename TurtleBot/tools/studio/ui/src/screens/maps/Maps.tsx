import { useEffect } from 'react';
import { Panel } from '../../components/ui';
import { MapCanvas } from '../../features/mapping/MapCanvas';
import { MapLibrary } from '../../features/mapping/MapLibrary';
import { MappingControls } from '../../features/mapping/MappingControls';
import { useMapStream, useMappingFeed } from '../../features/mapping/feed';
import { allowedActions } from '../../features/mapping/model';
import { useMapping } from '../../features/mapping/store';
import { DrivePanel } from '../../features/teleop/DrivePanel';
import { disarm } from '../../features/teleop/driver';
import { useDriveKeys } from '../../features/teleop/useDriveKeys';
import { useStudio } from '../../state/store';
import { useLiveStreams } from '../live/useStreams';

export function Maps() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const info = useMapping((s) => s.info);
  const drive = allowedActions(info, connected).drive;

  useMappingFeed();
  useLiveStreams();
  useMapStream();
  useDriveKeys();

  // Leaving this screen ends driving, whatever else happens.
  useEffect(() => {
    return () => disarm('You left the Maps screen.');
  }, []);

  // New robot processes can stall the base, so driving is off while the robot changes state.
  const blocked = connected && !drive.enabled;
  useEffect(() => {
    if (blocked) disarm(drive.reason);
  }, [blocked, drive.reason]);

  return (
    <div className="page live maps">
      <h1 className="page-title">Maps</h1>
      {!connected ? (
        <p className="live-note maps-note" role="status">
          Not connected to the robot. Connect to build or manage maps.
        </p>
      ) : null}
      <div className="live-grid">
        <Panel className="live-stage" aria-label="Map">
          <MappingControls />
          <MapCanvas />
        </Panel>
        <div className="live-side">
          <fieldset className="maps-drive" disabled={blocked}>
            <legend className="sr-only">Driving</legend>
            <DrivePanel />
          </fieldset>
          {blocked ? (
            <p className="dim small" role="status">
              {drive.reason}
            </p>
          ) : null}
          <p className="phone-only dim small">
            Driving by stick or keys needs a wider screen. On a phone you can watch the map and use
            the E-STOP.
          </p>
        </div>
      </div>
      <div className="maps-library">
        <MapLibrary connected={connected} />
      </div>
    </div>
  );
}
