import { useEffect } from 'react';
import { RouteList } from '../../features/routes/RouteList';
import { useRoutes } from '../../features/routes/store';
import { TripStatus } from '../../features/routes/TripStatus';
import { UploadRoute } from '../../features/routes/UploadRoute';
import { useStudio } from '../../state/store';

export function Routes() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const loadRoutes = useRoutes((s) => s.loadRoutes);

  useEffect(() => {
    if (connected) void loadRoutes();
  }, [connected, loadRoutes]);

  return (
    <div className="page routes">
      <h1 className="page-title">Routes</h1>
      {!connected ? (
        <p className="live-note maps-note" role="status">
          Not connected to the robot. Connect to see and manage its routes.
        </p>
      ) : null}
      <RouteList connected={connected} />
      <div className="routes-grid">
        <UploadRoute connected={connected} />
        <TripStatus connected={connected} />
      </div>
    </div>
  );
}
