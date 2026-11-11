import { RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button, Panel } from '../../components/ui';
import { TRIP_NOTE, tripWords } from './model';
import { useRoutes } from './store';

export const TRIP_REFRESH_MS = 5000;

/** Read-only view of the front-panel menu, the running trip and the navigation stack. */
export function TripStatus({ connected = true }: { connected?: boolean }) {
  const trip = useRoutes((s) => s.trip);
  const error = useRoutes((s) => s.tripError);
  const loadTrip = useRoutes((s) => s.loadTrip);
  const [loading, setLoading] = useState(false);

  // Read now, then every 5 s while connected and the page is visible.
  useEffect(() => {
    if (!connected) return;
    void loadTrip();
    const id = setInterval(() => {
      if (document.visibilityState !== 'hidden') void loadTrip();
    }, TRIP_REFRESH_MS);
    return () => clearInterval(id);
  }, [connected, loadTrip]);

  const refresh = async () => {
    setLoading(true);
    await loadTrip();
    setLoading(false);
  };

  const words = trip ? tripWords(trip) : null;
  return (
    <Panel
      title="Trip status"
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
      <p className="dim small">{TRIP_NOTE}</p>
      {!connected ? (
        <p className="dim small">Not connected to the robot.</p>
      ) : error ? (
        <p className="mapping-error" role="alert">
          Could not read the trip status. {error}
        </p>
      ) : words ? (
        <ul className="trip-words" data-testid="trip-words">
          <li>{words.menu}</li>
          <li>{words.trip}</li>
          <li>{words.stack}</li>
        </ul>
      ) : (
        <p className="dim small" role="status">
          Reading the trip status
        </p>
      )}
      {trip ? (
        <pre
          className="trip-log"
          tabIndex={0}
          aria-label="Last lines of menu.log"
          data-testid="trip-log"
        >
          {trip.lines.length > 0 ? trip.lines.join('\n') : 'The menu log is empty.'}
        </pre>
      ) : null}
    </Panel>
  );
}
