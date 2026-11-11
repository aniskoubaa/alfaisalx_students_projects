import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApi } from '../../api';
import type { RoutesList, TripStatusAnswer } from '../../api';
import { DialogHost, TooltipProvider } from '../../components/ui';
import { Routes } from '../../screens/routes/Routes';
import { ROUTES, parseHash, routeFor } from '../../state/router';
import { connectedStatus, installApi, resetStores } from '../../test/helpers';
import { toBase64, uploadPath } from './api';
import {
  UPLOAD_LIMIT_BYTES,
  canSetCurrent,
  checkUploadFiles,
  confirmText,
  currentSummary,
  routeStatus,
  suggestRouteName,
  tripWords,
  validRouteName,
  waypointsText,
} from './model';
import type { PickedFile } from './model';
import { RouteList } from './RouteList';
import { useRoutes } from './store';
import { TripStatus } from './TripStatus';
import { UploadRoute } from './UploadRoute';

type Body = Record<string, unknown>;

const list = (extra: Partial<RoutesList> = {}): RoutesList => ({
  routes: [
    {
      name: 'home',
      valid: true,
      missing: [],
      mtime: 1_700_000_000,
      waypoints: { outbound: 3, inbound: 2 },
    },
    {
      name: 'route1',
      valid: true,
      missing: [],
      mtime: 1_700_000_100,
      waypoints: { outbound: 5, inbound: 4 },
    },
    { name: 'half', valid: false, missing: ['map.yaml', 'speed_mask.yaml'], mtime: 1_700_000_200 },
  ],
  current: 'home',
  current_ok: true,
  dir: '/home/ubuntu/robot_code/routes',
  ...extra,
});

const trip = (extra: Partial<TripStatusAnswer> = {}): TripStatusAnswer => ({
  menu_running: true,
  mission_running: false,
  stack_running: false,
  log_path: '/tmp/menu.log',
  lines: ['menu started', 'waiting for a button'],
  ...extra,
});

const withUi = (ui: React.ReactNode) =>
  render(
    <TooltipProvider>
      {ui}
      <DialogHost />
    </TooltipProvider>,
  );

const calls = (cs: Array<{ body: Body }>, cmd: string) => cs.filter((c) => c.body.cmd === cmd);

/** A file the way the browser gives it for a chosen folder. */
function pick(rel: string, content = 'x'): File {
  const f = new File([content], rel.split('/').pop() as string);
  Object.defineProperty(f, 'webkitRelativePath', { value: rel });
  if (typeof f.arrayBuffer !== 'function') {
    Object.defineProperty(f, 'arrayBuffer', {
      value: () => Promise.resolve(new TextEncoder().encode(content).buffer),
    });
  }
  return f;
}

const folder = (name: string, skip: string[] = []) =>
  ['route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml']
    .filter((n) => !skip.includes(n))
    .map((n) => pick(`${name}/${n}`));

beforeEach(() => {
  resetStores();
  useRoutes.getState().reset();
});
afterEach(() => {
  setApi(null);
  useRoutes.getState().reset();
  vi.useRealTimers();
});

/* ---------- model ---------- */

describe('route model', () => {
  it('status words', () => {
    expect(routeStatus({ valid: true, missing: [] })).toBe('Ready');
    expect(routeStatus({ valid: false, missing: ['map.yaml', 'route.yaml'] })).toBe(
      'Incomplete: missing map.yaml, route.yaml',
    );
    expect(routeStatus({ valid: false, missing: [] })).toBe('Incomplete');
  });

  it('waypoints and the current summary', () => {
    expect(waypointsText({ waypoints: { outbound: 3, inbound: 2 } })).toBe('3 out, 2 in');
    expect(waypointsText({})).toBe('Not known');
    const l = list();
    expect(currentSummary('home', true, l.routes)).toBe(
      'The front-panel menu and the next trip use this route.',
    );
    expect(currentSummary(null, undefined, l.routes)).toBe('No current route is set.');
    expect(currentSummary('gone', false, l.routes)).toContain('missing or incomplete');
  });

  it('canSetCurrent gives a reason for every refusal', () => {
    const [home, route1, half] = list().routes as [
      RoutesList['routes'][0],
      RoutesList['routes'][0],
      RoutesList['routes'][0],
    ];
    expect(canSetCurrent(route1, 'home', null)).toEqual({ ok: true, reason: '' });
    expect(canSetCurrent(route1, 'home', { mission_running: false, stack_running: false }).ok).toBe(
      true,
    );
    expect(canSetCurrent(half, 'home', null).reason).toContain('missing map.yaml');
    expect(canSetCurrent(home, 'home', null).reason).toBe('Already the current route.');
    expect(
      canSetCurrent(route1, 'home', { mission_running: true, stack_running: false }).reason,
    ).toMatch(/trip/);
    expect(
      canSetCurrent(route1, 'home', { mission_running: false, stack_running: true }).reason,
    ).toMatch(/navigation/i);
  });

  it('confirm text names both routes', () => {
    const t = confirmText('home', 'route1');
    expect(t).toContain('route1 instead of home');
    expect(t).toContain('Nothing moves now');
  });

  it('name rule matches the bridge', () => {
    expect(validRouteName('route-1_a').ok).toBe(true);
    expect(validRouteName('a'.repeat(48)).ok).toBe(true);
    expect(validRouteName('a'.repeat(49)).ok).toBe(false);
    expect(validRouteName('').ok).toBe(false);
    expect(validRouteName('-bad').ok).toBe(false);
    expect(validRouteName('has space').ok).toBe(false);
    expect(validRouteName('../x').ok).toBe(false);
  });

  it('suggests a valid name from a folder name', () => {
    expect(suggestRouteName('My route (v2)')).toBe('My-route-v2');
    expect(suggestRouteName('..hidden')).toBe('hidden');
    expect(suggestRouteName('???')).toBe('route');
    expect(suggestRouteName('x'.repeat(80))).toHaveLength(48);
    for (const f of ['My route (v2)', '..hidden', '???', 'é', 'a'.repeat(80)]) {
      expect(validRouteName(suggestRouteName(f)).ok).toBe(true);
    }
  });

  it('checks a chosen folder: complete, missing, nested, too big', () => {
    const ok = checkUploadFiles(folder('plan') as PickedFile[]);
    expect(ok.ok).toBe(true);
    expect(ok.folder).toBe('plan');
    expect(ok.missing).toEqual([]);

    const miss = checkUploadFiles(folder('plan', ['map.yaml', 'route.yaml']) as PickedFile[]);
    expect(miss.ok).toBe(false);
    expect(miss.missing).toEqual(['route.yaml', 'map.yaml']);

    const nested = checkUploadFiles([
      ...folder('plan'),
      pick('plan/sub/map.yaml'),
      pick('plan/sub/deep/x.png'),
    ]);
    expect(nested.ok).toBe(true);
    expect(nested.nested).toEqual(['sub/map.yaml', 'sub/deep/x.png']);
    expect(nested.found).toHaveLength(4);

    // A required file only inside a subfolder does not count.
    const onlyNested = checkUploadFiles([
      ...folder('plan', ['route.yaml']),
      pick('plan/sub/route.yaml'),
    ]);
    expect(onlyNested.missing).toEqual(['route.yaml']);

    const big = checkUploadFiles([
      { webkitRelativePath: 'plan/route.yaml', name: 'route.yaml', size: UPLOAD_LIMIT_BYTES },
      { webkitRelativePath: 'plan/map.yaml', name: 'map.yaml', size: 1 },
      { webkitRelativePath: 'plan/keepout_mask.yaml', name: 'keepout_mask.yaml', size: 1 },
      { webkitRelativePath: 'plan/speed_mask.yaml', name: 'speed_mask.yaml', size: 1 },
    ]);
    expect(big.tooBig).toBe(true);
    expect(big.ok).toBe(false);
    expect(checkUploadFiles([]).ok).toBe(false);
  });

  it('trip words', () => {
    expect(tripWords(trip())).toEqual({
      menu: 'Menu running: yes',
      trip: 'Trip running: no',
      stack: 'Navigation running: no',
    });
    expect(
      tripWords(trip({ mission_running: true, stack_running: true, menu_running: false })),
    ).toEqual({
      menu: 'Menu running: no',
      trip: 'Trip running: yes',
      stack: 'Navigation running: yes',
    });
  });

  it('base64 works on big input and the upload path is flat', () => {
    const big = new Uint8Array(300_000).fill(65);
    const b = toBase64(big);
    expect(atob(b)).toHaveLength(300_000);
    expect(uploadPath(pick('plan/route.yaml'))).toBe('route.yaml');
  });
});

/* ---------- RouteList ---------- */

describe('RouteList', () => {
  const seed = (l: RoutesList, t: TripStatusAnswer | null = null) =>
    useRoutes.setState({ list: l, trip: t });

  it('shows the current badge, statuses and waypoints', () => {
    seed(list(), trip());
    withUi(<RouteList />);
    expect(screen.getByTestId('route-current')).toHaveTextContent('home');
    const home = screen.getByTestId('route-row-home');
    expect(within(home).getByText('Current')).toBeInTheDocument();
    expect(within(home).getByText('3 out, 2 in')).toBeInTheDocument();
    expect(within(screen.getByTestId('route-row-route1')).queryByText('Current')).toBeNull();
    expect(
      within(screen.getByTestId('route-row-half')).getByText(
        'Incomplete: missing map.yaml, speed_mask.yaml',
      ),
    ).toBeInTheDocument();
  });

  it('button rules: current, incomplete, trip and stack', () => {
    seed(list(), trip());
    const { unmount } = withUi(<RouteList />);
    const btn = (n: string) => within(screen.getByTestId(`route-row-${n}`)).getByRole('button');
    expect(btn('home')).toBeDisabled();
    expect(btn('half')).toBeDisabled();
    expect(btn('route1')).toBeEnabled();
    unmount();

    act(() => seed(list(), trip({ mission_running: true })));
    const r2 = withUi(<RouteList />);
    expect(within(screen.getByTestId('route-row-route1')).getByRole('button')).toBeDisabled();
    expect(screen.getByText(/A trip is running/)).toBeInTheDocument();
    r2.unmount();

    act(() => seed(list(), trip({ stack_running: true })));
    withUi(<RouteList />);
    expect(within(screen.getByTestId('route-row-route1')).getByRole('button')).toBeDisabled();
    expect(screen.getByText(/navigation stack is running/i)).toBeInTheDocument();
  });

  it('confirm dialog names both routes and confirming calls setCurrentRoute', async () => {
    const { calls: cs } = installApi((c) => {
      if (c.body.cmd === 'route_set_current') return { ok: true, current: 'route1' };
      if (c.body.cmd === 'routes_list') return { ok: true, ...list({ current: 'route1' }) };
      return { ok: true };
    });
    seed(list(), trip());
    withUi(<RouteList />);
    const u = userEvent.setup();
    await u.click(within(screen.getByTestId('route-row-route1')).getByRole('button'));
    const dlg = await screen.findByRole('dialog');
    expect(within(dlg).getByText('Use route route1?')).toBeInTheDocument();
    expect(dlg).toHaveTextContent(
      'The front-panel menu and the next trip will use route1 instead of home. Nothing moves now.',
    );
    expect(calls(cs, 'route_set_current')).toHaveLength(0);
    await u.click(within(dlg).getByRole('button', { name: 'Use this route' }));
    await waitFor(() => expect(calls(cs, 'route_set_current')).toHaveLength(1));
    expect(calls(cs, 'route_set_current')[0]?.body).toMatchObject({
      name: 'route1',
      confirm: true,
    });
    await waitFor(() => expect(screen.getByTestId('route-current')).toHaveTextContent('route1'));
  });

  it('cancel changes nothing', async () => {
    const { calls: cs } = installApi(() => ({ ok: true }));
    seed(list(), trip());
    withUi(<RouteList />);
    const u = userEvent.setup();
    await u.click(within(screen.getByTestId('route-row-route1')).getByRole('button'));
    await u.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }),
    );
    expect(calls(cs, 'route_set_current')).toHaveLength(0);
  });

  it('says so when not connected, and when the robot refuses', async () => {
    withUi(<RouteList connected={false} />);
    expect(screen.getByText(/Not connected to the robot/)).toBeInTheDocument();
  });
});

/* ---------- UploadRoute ---------- */

describe('UploadRoute', () => {
  const choose = async (files: File[]) => {
    const u = userEvent.setup();
    await u.upload(screen.getByLabelText('Choose a route folder'), files);
    return u;
  };

  it('has a labelled folder input and explains plan_route.py', () => {
    withUi(<UploadRoute />);
    const input = screen.getByLabelText('Choose a route folder');
    expect(input).toHaveAttribute('webkitdirectory');
    expect(input).toHaveAttribute('multiple');
    expect(screen.getByText(/delivery\/tools\/plan_route\.py/)).toBeInTheDocument();
  });

  it('prefills a valid name and enables Upload for a complete folder', async () => {
    withUi(<UploadRoute />);
    await choose(folder('My route'));
    expect(screen.getByLabelText('Name on the robot')).toHaveValue('My-route');
    expect(screen.getByText('All four route files are there.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled();
  });

  it('lists what is missing and keeps Upload off', async () => {
    withUi(<UploadRoute />);
    await choose(folder('plan', ['keepout_mask.yaml']));
    expect(screen.getByText('Missing: keepout_mask.yaml.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('reports nested files as ignored', async () => {
    withUi(<UploadRoute />);
    await choose([...folder('plan'), pick('plan/old/route.yaml')]);
    expect(
      screen.getByText(/Ignored, because they are inside subfolders: old\/route\.yaml/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled();
  });

  it('validates the name', async () => {
    withUi(<UploadRoute />);
    const u = await choose(folder('plan'));
    const name = screen.getByLabelText('Name on the robot');
    await u.clear(name);
    await u.type(name, 'bad name');
    expect(screen.getByRole('alert')).toHaveTextContent('No spaces');
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('refuses a name already in the list before sending', async () => {
    useRoutes.setState({ list: list() });
    withUi(<UploadRoute />);
    await choose(folder('home'));
    expect(
      screen.getByText('A route named home already exists on the robot. Choose another name.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('uploads only the top-level files and then reloads the list', async () => {
    const { calls: cs } = installApi((c) => {
      if (c.path === '/api/routes/upload') return { ok: true, name: 'plan' };
      if (c.body.cmd === 'routes_list') return { ok: true, ...list() };
      return { ok: true };
    });
    withUi(<UploadRoute />);
    const u = await choose([...folder('plan'), pick('plan/sub/x.png')]);
    await u.click(screen.getByRole('button', { name: 'Upload' }));
    await waitFor(() => expect(cs.some((c) => c.path === '/api/routes/upload')).toBe(true));
    const up = cs.find((c) => c.path === '/api/routes/upload');
    const body = up?.body as { name: string; files: Array<{ path: string; data_b64: string }> };
    expect(body.name).toBe('plan');
    expect(body.files.map((f) => f.path)).toEqual([
      'route.yaml',
      'map.yaml',
      'keepout_mask.yaml',
      'speed_mask.yaml',
    ]);
    expect(body.files[0]?.data_b64).toBe(btoa('x'));
    await waitFor(() => expect(calls(cs, 'routes_list').length).toBeGreaterThan(0));
  });

  it('shows the exists error when the robot says the name is taken', async () => {
    installApi((c) =>
      c.path === '/api/routes/upload'
        ? { ok: false, error: 'route exists', exists: true }
        : { ok: true },
    );
    withUi(<UploadRoute />);
    const u = await choose(folder('plan'));
    await u.click(screen.getByRole('button', { name: 'Upload' }));
    expect(
      await screen.findByText(
        'A route named plan already exists on the robot. Choose another name.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('shows other upload errors in words', async () => {
    installApi((c) =>
      c.path === '/api/routes/upload' ? { ok: false, error: 'missing route.yaml' } : { ok: true },
    );
    withUi(<UploadRoute />);
    const u = await choose(folder('plan'));
    await u.click(screen.getByRole('button', { name: 'Upload' }));
    expect(
      await screen.findByText(/Could not upload the route. missing route.yaml/),
    ).toBeInTheDocument();
  });
});

/* ---------- TripStatus ---------- */

describe('TripStatus', () => {
  it('shows the words, the note and the log lines', async () => {
    installApi((c) =>
      c.body.cmd === 'trip_status'
        ? { ok: true, ...trip({ mission_running: true }) }
        : { ok: true },
    );
    withUi(<TripStatus />);
    expect(await screen.findByText('Trip running: yes')).toBeInTheDocument();
    expect(screen.getByText('Menu running: yes')).toBeInTheDocument();
    expect(screen.getByText('Navigation running: no')).toBeInTheDocument();
    expect(screen.getByTestId('trip-log')).toHaveTextContent('waiting for a button');
    expect(
      screen.getByText(
        "Starting trips from Studio is not part of this version; use the robot's front-panel menu.",
      ),
    ).toBeInTheDocument();
  });

  it('refreshes by button and every 5 s, and not when disconnected', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { calls: cs } = installApi((c) =>
      c.body.cmd === 'trip_status' ? { ok: true, ...trip() } : { ok: true },
    );
    const { unmount } = withUi(<TripStatus />);
    await waitFor(() => expect(calls(cs, 'trip_status')).toHaveLength(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(calls(cs, 'trip_status').length).toBeGreaterThanOrEqual(2);
    const before = calls(cs, 'trip_status').length;
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole('button', { name: /Refresh/ }));
    await waitFor(() => expect(calls(cs, 'trip_status').length).toBeGreaterThan(before));
    unmount();

    const n = calls(cs, 'trip_status').length;
    withUi(<TripStatus connected={false} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(11_000);
    });
    expect(calls(cs, 'trip_status')).toHaveLength(n);
  });
});

/* ---------- screen and router ---------- */

describe('Routes screen', () => {
  it('shows a note when not connected', () => {
    installApi(() => ({ ok: true }));
    withUi(<Routes />);
    expect(screen.getByRole('heading', { name: 'Routes', level: 1 })).toBeInTheDocument();
    expect(screen.getAllByText(/Not connected to the robot/).length).toBeGreaterThan(0);
  });

  it('loads the routes when connected', async () => {
    installApi((c) => {
      if (c.body.cmd === 'routes_list') return { ok: true, ...list() };
      if (c.body.cmd === 'trip_status') return { ok: true, ...trip() };
      return { ok: true };
    });
    connectedStatus();
    withUi(<Routes />);
    expect(await screen.findByTestId('route-row-route1')).toBeInTheDocument();
    expect(screen.getByTestId('route-current')).toHaveTextContent('home');
  });
});

describe('router', () => {
  it('has /routes right after /maps', () => {
    const paths = ROUTES.map((r) => r.path);
    expect(paths.indexOf('/routes')).toBe(paths.indexOf('/maps') + 1);
    expect(routeFor('/routes').label).toBe('Routes');
    expect(parseHash('#/routes')).toBe('/routes');
    expect(ROUTES.find((r) => r.path === '/routes')?.ready).toBe(true);
  });
});
