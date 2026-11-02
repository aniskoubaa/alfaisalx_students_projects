import { useEffect, useState } from 'react';
import { poseOff, poseOn, scanOff, scanOn } from '../../api/live';
import { useStudio } from '../../state/store';

/** True while the browser tab is visible. */
export function usePageVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');
  useEffect(() => {
    const on = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', on);
    return () => document.removeEventListener('visibilitychange', on);
  }, []);
  return visible;
}

/**
 * Ask the robot for the scan and pose streams while the Live screen is open, the tab is visible
 * and the robot is connected. Turns them off when any of that stops being true. A reconnect
 * starts a new bridge process, so the streams are asked for again.
 */
export function useLiveStreams(): void {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const visible = usePageVisible();
  useEffect(() => {
    if (!connected || !visible) return;
    void scanOn(4, 360);
    void poseOn(10);
    return () => {
      void scanOff();
      void poseOff();
    };
  }, [connected, visible]);
}
