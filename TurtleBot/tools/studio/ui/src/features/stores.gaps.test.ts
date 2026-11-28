/**
 * Failure scenarios of the three feature stores (mapping, routes, menu): what the screen keeps when the robot or Studio
 * answers with an error, and what a late or out of order answer must not do. Written to close the gaps found by
 * `npm run coverage` (see docs/TESTING.md).
 */
import { waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioClient, setApi } from '../api';
import type { MapEvent, MenuCheck, MenuGetAnswer, RoutesList, TripStatusAnswer } from '../api';
import { installApi, resetStores } from '../test/helpers';
import { setMapDecoder, useMapping } from './mapping/store';
import { toYaml } from './menu/model';
import { currentCheck, useMenu } from './menu/store';
import { useRoutes } from './routes/store';

type Body = Record<string, unknown>;
const bridgeCalls = (cs: Array<{ body: Body }>, cmd: string) =>
  cs.filter((c) => c.body.cmd === cmd);

beforeEach(() => {
  resetStores();
  useMapping.getState().reset();
  useRoutes.getState().reset();
  useMenu.getState().reset();
  setMapDecoder(null);
});
afterEach(() => {
  setApi(null);
  setMapDecoder(null);
  useMapping.getState().reset();
  useRoutes.getState().reset();
  useMenu.getState().reset();
});

describe('routes store: errors keep what the screen already shows', () => {
  const list = (): RoutesList =>
    ({ ok: true, routes: [{ name: 'home' }], current: 'home' }) as unknown as RoutesList;
  const trip = (): TripStatusAnswer =>
    ({ ok: true, menu_running: true, lines: ['one'] }) as unknown as TripStatusAnswer;

  it('a failed refresh keeps the old list and shows the error; the next good answer clears it', async () => {
    let fail = false;
    installApi((c) => {
      if (c.body.cmd !== 'routes_list') return { ok: true };
      return fail ? { ok: false, error: 'robot busy' } : list();
    });
    await useRoutes.getState().loadRoutes();
    expect(useRoutes.getState().list?.current).toBe('home');
    fail = true;
    await useRoutes.getState().loadRoutes();
    expect(useRoutes.getState().listError).toBe('robot busy');
    expect(useRoutes.getState().list?.current).toBe('home');
    fail = false;
    await useRoutes.getState().loadRoutes();
    expect(useRoutes.getState().listError).toBeNull();
  });

  it('a failed trip status keeps the old status, and asks for 40 lines', async () => {
    let fail = false;
    const m = installApi((c) => {
      if (c.body.cmd !== 'trip_status') return { ok: true };
      return fail ? { ok: false, error: 'no log' } : trip();
    });
    await useRoutes.getState().loadTrip();
    fail = true;
    await useRoutes.getState().loadTrip();
    expect(useRoutes.getState().tripError).toBe('no log');
    expect(useRoutes.getState().trip).not.toBeNull();
    expect(bridgeCalls(m.calls, 'trip_status')[0]?.body.lines).toBe(40);
  });

  it('a network failure is reported, not thrown', async () => {
    setApi(
      new StudioClient({
        token: 't',
        fetchImpl: (async () => {
          throw new Error('down');
        }) as typeof fetch,
      }),
    );
    await useRoutes.getState().loadRoutes();
    expect(useRoutes.getState().listError).toMatch(/Cannot reach Studio/);
    expect(useRoutes.getState().list).toBeNull();
  });
});

describe('mapping store: picture failures', () => {
  const ev = (seq: number): MapEvent => ({
    ev: 'map',
    seq,
    t: seq,
    width: 4,
    height: 4,
    resolution: 0.05,
    origin: { x: 0, y: 0, yaw: 0 },
  });
  const src = { width: 4, height: 4 } as CanvasImageSource & { width: number; height: number };
  const arm = (status: number, metaSeq = 1) => {
    const fetchImpl = (async () =>
      new Response(status === 200 ? 'png' : '{"ok":false,"error":"no map yet"}', {
        status,
        headers: { 'X-Map-Meta': JSON.stringify({ ...ev(metaSeq), ev: undefined }) },
      })) as typeof fetch;
    setApi(new StudioClient({ token: 't', fetchImpl }));
  };

  it('a picture the browser cannot decode is an error, with no image and the fetch released', async () => {
    arm(200);
    setMapDecoder(async () => null);
    useMapping.getState().onMapEvent(ev(1));
    await waitFor(() =>
      expect(useMapping.getState().fetchError).toMatch(/could not read the map picture/),
    );
    expect(useMapping.getState().image).toBeNull();
    expect(useMapping.getState().fetching).toBe(false);
  });

  it('a failed fetch after a good picture keeps the good picture on screen', async () => {
    arm(200, 1);
    setMapDecoder(async () => ({ source: src, known: 3, close: vi.fn() }));
    useMapping.getState().onMapEvent(ev(1));
    await waitFor(() => expect(useMapping.getState().image?.seq).toBe(1));
    arm(404);
    useMapping.getState().onMapEvent(ev(2));
    await waitFor(() => expect(useMapping.getState().fetchError).toBe('no map yet'));
    expect(useMapping.getState().image?.seq).toBe(1);
  });

  it('a decoded picture older than the one on screen is dropped and closed', async () => {
    arm(200, 5);
    const closeNew = vi.fn();
    setMapDecoder(async () => ({ source: src, known: 1, close: vi.fn() }));
    useMapping.getState().onMapEvent(ev(5));
    await waitFor(() => expect(useMapping.getState().image?.seq).toBe(5));
    // The server answers with an older picture (seq 3) for the next event.
    arm(200, 3);
    setMapDecoder(async () => ({ source: src, known: 1, close: closeNew }));
    useMapping.getState().onMapEvent(ev(6));
    await waitFor(() => expect(closeNew).toHaveBeenCalled());
    expect(useMapping.getState().image?.seq).toBe(5);
    expect(useMapping.getState().fetching).toBe(false);
  });

  it('clearing while a picture is being decoded discards that picture and releases it', async () => {
    arm(200);
    const close = vi.fn();
    let release: () => void = () => {};
    setMapDecoder(
      () =>
        new Promise((r) => {
          release = () => r({ source: src, known: 1, close });
        }),
    );
    useMapping.getState().onMapEvent(ev(1));
    await waitFor(() => expect(useMapping.getState().fetching).toBe(true));
    await new Promise((r) => setTimeout(r, 0));
    useMapping.getState().clearMap();
    release();
    await waitFor(() => expect(close).toHaveBeenCalled());
    expect(useMapping.getState().image).toBeNull();
    expect(useMapping.getState().latestSeq).toBe(-1);
  });

  it('a pose with a non finite map position falls back to the odometry pose and drops the source', () => {
    const s = useMapping.getState();
    s.onPose({
      ev: 'pose',
      x: 1,
      y: 2,
      yaw: 0.5,
      map: { x: Number.NaN, y: 0, yaw: 0, source: 'tf' },
    } as never);
    expect(useMapping.getState().pose).toEqual({ x: 1, y: 2, yaw: 0.5 });
    expect(useMapping.getState().poseSource).toBeNull();
  });
});

describe('menu store: failures never lose the document or fake a save', () => {
  const okCheck: MenuCheck = {
    ok: true,
    errors: [],
    warnings: [],
    hide: [],
    layout: ['trip', 'dock', 'estop', 'power', 'help'],
    labels: { trip: 'Trip', dock: 'Dock', estop: 'EStop', power: 'Power', help: 'Help' },
    custom: {},
  };
  const robot = (over: Partial<MenuGetAnswer> = {}): MenuGetAnswer => ({
    path: '/home/ubuntu/robot_code/menu/menu.yaml',
    exists: true,
    text: 'version: 1\n',
    check: okCheck,
    checker_ok: true,
    ...over,
  });

  it('a failed load leaves the screen state alone and reports the error', async () => {
    installApi(() => ({ ok: false, error: 'ssh down' }));
    await useMenu.getState().load();
    expect(useMenu.getState().robotError).toBe('ssh down');
    expect(useMenu.getState().robot).toBeNull();
    expect(useMenu.getState().blocked).toBe(false);
  });

  it('a file that exists but fails its check blocks editing until the standard menu is chosen', async () => {
    installApi(() => robot({ check: { ...okCheck, ok: false, errors: ['bad'] } }));
    await useMenu.getState().load();
    expect(useMenu.getState().blocked).toBe(true);
    expect(useMenu.getState().lastCheck).toBeNull();
    useMenu.getState().startStandard();
    expect(useMenu.getState().blocked).toBe(false);
  });

  it('no file on the robot is not blocked and starts from the standard menu', async () => {
    installApi(() => robot({ exists: false, check: null }));
    await useMenu.getState().load();
    expect(useMenu.getState().blocked).toBe(false);
    expect(useMenu.getState().doc.entries).toHaveLength(0);
  });

  it('a refused save returns false, keeps the error and does not reload from the robot', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'menu_put' ? { ok: false, error: 'checker said no' } : robot(),
    );
    await useMenu.getState().load();
    const loads = bridgeCalls(m.calls, 'menu_get').length;
    const ok = await useMenu.getState().save();
    expect(ok).toBe(false);
    expect(useMenu.getState().saveError).toBe('checker said no');
    expect(useMenu.getState().saving).toBe(false);
    expect(bridgeCalls(m.calls, 'menu_get')).toHaveLength(loads);
    expect(bridgeCalls(m.calls, 'menu_put')[0]?.body.confirm).toBe(true);
  });

  it('a good save reloads from the robot and clears an old save error', async () => {
    let put = 0;
    const m = installApi((c) => {
      if (c.body.cmd === 'menu_put')
        return put++ === 0 ? { ok: false, error: 'first try' } : { path: 'p', check: okCheck };
      return robot();
    });
    await useMenu.getState().load();
    await useMenu.getState().save();
    expect(useMenu.getState().saveError).toBe('first try');
    const loads = bridgeCalls(m.calls, 'menu_get').length;
    expect(await useMenu.getState().save()).toBe(true);
    expect(useMenu.getState().saveError).toBeNull();
    expect(bridgeCalls(m.calls, 'menu_get')).toHaveLength(loads + 1);
  });

  it('a failed check keeps the previous check, and a check goes stale when the document changes', async () => {
    let fail = false;
    installApi((c) => {
      if (c.body.cmd === 'menu_check')
        return fail ? { ok: false, error: 'checker offline' } : { check: okCheck };
      return robot();
    });
    await useMenu.getState().load();
    await useMenu.getState().runCheck();
    expect(currentCheck(useMenu.getState())).not.toBeNull();
    fail = true;
    await useMenu.getState().runCheck();
    expect(useMenu.getState().checkError).toBe('checker offline');
    expect(useMenu.getState().checking).toBe(false);
    // Hiding an entry changes the generated text: the old check no longer describes the document.
    const doc = { ...useMenu.getState().doc, hide: ['wall_left'] };
    useMenu.getState().setDoc(doc);
    expect(toYaml(doc)).not.toBe(useMenu.getState().lastCheck?.text);
    expect(currentCheck(useMenu.getState())).toBeNull();
  });
});
