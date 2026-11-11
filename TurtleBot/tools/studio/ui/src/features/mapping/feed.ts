import { useEffect } from 'react';
import { notify } from '../../state/feedback';
import { onStudioEvent } from '../../state/runtime';
import { useStudio } from '../../state/store';
import { usePageVisible } from '../../screens/live/useStreams';
import { fetchMappingInfo, mapOff, mapOn, mappingStatus } from './api';
import { useMapping } from './store';

/** The words for a finished operation, shown as a toast. */
export function resultText(r: {
  op: 'start' | 'save' | 'stop';
  ok: boolean;
  name?: string;
  error?: string;
}): { kind: 'ok' | 'error'; text: string } {
  const what =
    r.op === 'start' ? 'Starting mapping' : r.op === 'save' ? 'Saving the map' : 'Stopping';
  if (r.ok) {
    if (r.op === 'save') return { kind: 'ok', text: `Map saved${r.name ? ' as ' + r.name : ''}.` };
    if (r.op === 'start') return { kind: 'ok', text: 'Mapping has started.' };
    return { kind: 'ok', text: 'Mapping has stopped.' };
  }
  return { kind: 'error', text: `${what} failed. ${r.error ?? 'The robot gave no reason.'}` };
}

/**
 * Listen for mapping, map, pose and scan events while the Maps screen is open, and load the
 * first mapping state (Studio's last copy first, then the robot's own answer).
 */
export function useMappingFeed(): void {
  const connected = useStudio((s) => s.conn.state === 'connected');

  useEffect(() => {
    const off = [
      onStudioEvent('mapping', (ev) => {
        useMapping.getState().onMappingEvent(ev);
        if (ev.result) {
          const t = resultText(ev.result);
          notify(t.kind, t.text);
        }
      }),
      onStudioEvent('map', (ev) => useMapping.getState().onMapEvent(ev)),
      onStudioEvent('pose', (ev) => useMapping.getState().onPose(ev)),
      onStudioEvent('scan', (ev) => useMapping.getState().onScan(ev)),
    ];
    return () => off.forEach((f) => f());
  }, []);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const first = await fetchMappingInfo();
      if (alive && first.ok) {
        const { ok: _ok, ...info } = first;
        void _ok;
        useMapping.getState().setInfo(info);
      }
      if (!connected) return;
      const r = await mappingStatus();
      if (alive && r.ok) {
        const { ok: _ok, ...info } = r;
        void _ok;
        useMapping.getState().setInfo(info);
      }
    })();
    return () => {
      alive = false;
    };
  }, [connected]);
}

/**
 * Ask for the live map while the screen is open, the tab is visible and the robot is connected.
 * The scan and pose streams come from useLiveStreams.
 */
export function useMapStream(): void {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const visible = usePageVisible();
  useEffect(() => {
    if (!connected || !visible) return;
    void mapOn(0.5, 1_000_000);
    return () => {
      void mapOff();
    };
  }, [connected, visible]);
}
