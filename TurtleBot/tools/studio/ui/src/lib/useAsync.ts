import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Wrap an async action so a button can show it is working.
 * `run` never throws; it ignores a second call while the first is still running.
 */
export function useAsyncAction<A extends unknown[]>(fn: (...args: A) => Promise<unknown>) {
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const alive = useRef(true);
  const latest = useRef(fn);
  useEffect(() => {
    latest.current = fn;
  });
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const run = useCallback(async (...args: A) => {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    try {
      await latest.current(...args);
    } catch (e) {
      console.error(e);
    } finally {
      busy.current = false;
      if (alive.current) setPending(false);
    }
  }, []);
  return { run, pending };
}
