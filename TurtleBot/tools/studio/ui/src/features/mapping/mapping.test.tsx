import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioClient, setApi } from '../../api';
import type { MapEntry, MappingInfo, PoseEvent, ScanEvent } from '../../api';
import { DialogHost, TooltipProvider } from '../../components/ui';
import { useDialogs, useToasts } from '../../state/feedback';
import { ROUTES, parseHash, routeFor } from '../../state/router';
import { useStudio } from '../../state/store';
import { Maps } from '../../screens/maps/Maps';
import { connectedStatus, installApi, resetStores } from '../../test/helpers';
import { resultText } from './feed';
import { MapCanvas } from './MapCanvas';
import { MapLibrary } from './MapLibrary';
import { MappingControls } from './MappingControls';
import { SaveMapDialog } from './SaveMapDialog';
import { countKnown, setMapDecoder, useMapping } from './store';
import type { MapImage } from './store';

type Body = Record<string, unknown>;

const fakeSource = () => ({ width: 4, height: 4 }) as unknown as MapImage['source'];

const info = (state: MappingInfo['state'], extra: Partial<MappingInfo> = {}): MappingInfo => ({
  state,
  since: 1000,
  last_error: null,
  last_saved: null,
  unsaved: false,
  scripts_ok: true,
  other_stack: null,
  ...extra,
});

const withUi = (ui: React.ReactNode) =>
  render(
    <TooltipProvider>
      {ui}
      <DialogHost />
    </TooltipProvider>,
  );

const bridgeCalls = (calls: Array<{ body: Body }>, cmd: string) =>
  calls.filter((c) => c.body.cmd === cmd);

beforeEach(() => {
  resetStores();
  useMapping.getState().reset();
  setMapDecoder(null);
  // jsdom has no canvas; the screen must still work without one.
  HTMLCanvasElement.prototype.getContext = (() => null) as never;
});
afterEach(() => {
  setApi(null);
  setMapDecoder(null);
  useMapping.getState().reset();
});

/* ---------- store ---------- */

const mapEv = (seq: number) => ({
  ev: 'map' as const,
  seq,
  t: seq,
  width: 4,
  height: 4,
  resolution: 0.05,
  origin: { x: 0, y: 0, yaw: 0 },
});

describe('mapping store', () => {
  it('takes the state and result from mapping events', () => {
    useMapping.getState().onMappingEvent({
      ev: 'mapping',
      ...info('mapping', { unsaved: true }),
      result: { op: 'start', ok: true },
    });
    const s = useMapping.getState();
    expect(s.info?.state).toBe('mapping');
    expect(s.info?.unsaved).toBe(true);
    expect(s.info).not.toHaveProperty('result');
    expect(s.info).not.toHaveProperty('ev');
    expect(s.result).toEqual({ op: 'start', ok: true });
  });

  it('keeps the old result when an event has none', () => {
    const s = useMapping.getState();
    s.onMappingEvent({ ev: 'mapping', ...info('idle'), result: { op: 'stop', ok: true } });
    s.onMappingEvent({ ev: 'mapping', ...info('starting') });
    expect(useMapping.getState().result?.op).toBe('stop');
  });

  it('uses the map pose when present, else the odometry pose', () => {
    const base: PoseEvent = { ev: 'pose', t: 1, x: 1, y: 2, yaw: 0.1, vx: 0, wz: 0 };
    useMapping.getState().onPose(base);
    expect(useMapping.getState().pose).toEqual({ x: 1, y: 2, yaw: 0.1 });
    expect(useMapping.getState().poseSource).toBeNull();
    useMapping.getState().onPose({ ...base, map: { x: 5, y: 6, yaw: 1, source: 'slam' } });
    expect(useMapping.getState().pose).toEqual({ x: 5, y: 6, yaw: 1 });
    expect(useMapping.getState().poseSource).toBe('slam');
  });

  it('remembers the pose a scan was taken at', () => {
    const s = useMapping.getState();
    s.onPose({ ev: 'pose', t: 1, x: 1, y: 1, yaw: 0, vx: 0, wz: 0 });
    const scan: ScanEvent = {
      ev: 'scan',
      t: 1,
      frame: 'laser',
      angle_min: 0,
      angle_inc: 0.1,
      range_max: 10,
      ranges: [1, 2, null],
    };
    s.onScan(scan, 500);
    const after = useMapping.getState();
    expect(after.scan?.n).toBe(2);
    expect(after.scanPose).toEqual({ x: 1, y: 1, yaw: 0 });
    expect(after.scanAt).toBe(500);
  });

  describe('picture fetching', () => {
    function setup() {
      const gates: Array<() => void> = [];
      const seen: string[] = [];
      const fetchImpl = (async (url: RequestInfo | URL, init?: RequestInit) => {
        const path = String(url);
        seen.push(path);
        expect((init?.headers as Record<string, string>)['X-Studio-Token']).toBe('tok');
        await new Promise<void>((r) => gates.push(r));
        const n = seen.length;
        return new Response('png', {
          status: 200,
          headers: {
            'X-Map-Meta': JSON.stringify({ ...mapEv(n === 1 ? 1 : 3), ev: undefined }),
          },
        });
      }) as typeof fetch;
      setApi(new StudioClient({ token: 'tok', fetchImpl }));
      const close = vi.fn();
      setMapDecoder(async () => ({ source: fakeSource(), known: 7, close }));
      return { gates, seen, close };
    }
    const release = async (gates: Array<() => void>, i: number) => {
      await waitFor(() => expect(gates.length).toBeGreaterThan(i));
      gates[i]?.();
    };

    it('never has more than one fetch in flight and keeps the newest', async () => {
      const { gates, seen } = setup();
      const s = useMapping.getState();
      s.onMapEvent(mapEv(1));
      s.onMapEvent(mapEv(2));
      s.onMapEvent(mapEv(3));
      await waitFor(() => expect(seen).toHaveLength(1));
      expect(useMapping.getState().fetching).toBe(true);
      await release(gates, 0);
      // The second fetch is for the newest request only.
      await waitFor(() => expect(seen).toHaveLength(2));
      await release(gates, 1);
      await waitFor(() => expect(useMapping.getState().fetching).toBe(false));
      expect(seen).toHaveLength(2);
      expect(seen[0]).toBe('/api/map/live.png');
      // The newest picture is the one kept.
      expect(useMapping.getState().image?.seq).toBe(3);
      expect(useMapping.getState().image?.known).toBe(7);
    });

    it('ignores events that are not newer', async () => {
      const { gates, seen } = setup();
      const s = useMapping.getState();
      s.onMapEvent(mapEv(5));
      await release(gates, 0);
      await waitFor(() => expect(useMapping.getState().image).not.toBeNull());
      s.onMapEvent(mapEv(5));
      s.onMapEvent(mapEv(4));
      expect(seen).toHaveLength(1);
    });

    it('drops a bad event and shows a fetch failure in words', async () => {
      const fetchImpl = (async () =>
        new Response(JSON.stringify({ ok: false, error: 'no map yet' }), {
          status: 404,
        })) as typeof fetch;
      setApi(new StudioClient({ token: 'tok', fetchImpl }));
      useMapping.getState().onMapEvent({ ...mapEv(1), width: 0 });
      expect(useMapping.getState().latestSeq).toBe(-1);
      useMapping.getState().onMapEvent(mapEv(1));
      await waitFor(() => expect(useMapping.getState().fetchError).toBe('no map yet'));
      expect(useMapping.getState().fetching).toBe(false);
    });

    it('a new mapping run clears the old picture and its sequence numbers', async () => {
      const { gates, close } = setup();
      useMapping.getState().onMapEvent(mapEv(5));
      await release(gates, 0);
      await waitFor(() => expect(useMapping.getState().image).not.toBeNull());
      useMapping.getState().onMappingEvent({ ev: 'mapping', ...info('starting') });
      expect(useMapping.getState().image).toBeNull();
      expect(useMapping.getState().latestSeq).toBe(-1);
      expect(close).toHaveBeenCalled();
    });
  });

  it('counts known pixels', () => {
    // two pixels: one unknown grey (205), one free (254)
    expect(countKnown([205, 205, 205, 255, 254, 254, 254, 255])).toBe(1);
  });
});

/* ---------- MappingControls ---------- */

describe('MappingControls', () => {
  const enabled = () =>
    (['Start mapping', 'Save map', 'Stop mapping', 'Clear error'] as const).map(
      (n) => !(screen.getByRole('button', { name: n }) as HTMLButtonElement).disabled,
    );

  beforeEach(() => connectedStatus());

  it.each([
    ['idle', 'Not mapping', [true, false, false, false]],
    ['starting', 'Starting mapping…', [false, false, false, false]],
    ['mapping', 'Mapping', [false, true, true, false]],
    ['saving', 'Saving the map…', [false, false, false, false]],
    ['stopping', 'Stopping…', [false, false, false, false]],
    ['error', 'Error', [false, false, true, true]],
  ] as const)('%s: shows the words and the right buttons', (state, words, want) => {
    installApi(() => ({ ok: true }));
    useMapping.getState().setInfo(info(state));
    withUi(<MappingControls />);
    expect(screen.getByTestId('mapping-state')).toHaveTextContent(words);
    expect(enabled()).toEqual([...want]);
  });

  it('is all off before the state is known and when not connected', () => {
    installApi(() => ({ ok: true }));
    const { unmount } = withUi(<MappingControls />);
    expect(enabled()).toEqual([false, false, false, false]);
    expect(screen.getByTestId('mapping-state')).toHaveTextContent('Checking');
    unmount();
    useStudio.getState().dispatch({ ev: 'conn', state: 'disconnected' } as never);
    useMapping.getState().setInfo(info('idle'));
    withUi(<MappingControls />);
    expect(enabled()).toEqual([false, false, false, false]);
  });

  it('start sends mapping_start and shows the new state from the reply', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_start' ? { ok: true, ...info('starting') } : { ok: true },
    );
    useMapping.getState().setInfo(info('idle'));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Start mapping' }));
    await waitFor(() =>
      expect(screen.getByTestId('mapping-state')).toHaveTextContent('Starting mapping…'),
    );
    expect(bridgeCalls(m.calls, 'mapping_start')).toHaveLength(1);
  });

  it('explains why start is off', () => {
    installApi(() => ({ ok: true }));
    useMapping.getState().setInfo(info('idle', { other_stack: 'nav2' }));
    withUi(<MappingControls />);
    expect(screen.getByTestId('start-reason')).toHaveTextContent('navigation program');
  });

  it('shows the last error and the last saved map in words', () => {
    installApi(() => ({ ok: true }));
    useMapping.getState().setInfo(
      info('error', {
        last_error: 'SLAM did not start',
        last_saved: { name: 'lab', t: Date.now() / 1000 - 120 },
      }),
    );
    withUi(<MappingControls />);
    expect(screen.getByTestId('mapping-error')).toHaveTextContent('Last error: SLAM did not start');
    expect(screen.getByTestId('mapping-saved')).toHaveTextContent(
      'Last saved map: lab (2 min ago)',
    );
  });

  it('clear error sends mapping_reset', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_reset' ? { ok: true, ...info('idle') } : { ok: true },
    );
    useMapping.getState().setInfo(info('error', { last_error: 'x' }));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Clear error' }));
    await waitFor(() => expect(bridgeCalls(m.calls, 'mapping_reset')).toHaveLength(1));
    await waitFor(() => expect(useMapping.getState().info?.state).toBe('idle'));
  });

  it('stops at once when the map is saved', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_stop' ? { ok: true, ...info('stopping') } : { ok: true },
    );
    useMapping.getState().setInfo(info('mapping', { unsaved: false }));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Stop mapping' }));
    await waitFor(() => expect(bridgeCalls(m.calls, 'mapping_stop')).toHaveLength(1));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks first when the map is not saved, and does nothing on Keep mapping', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_stop' ? { ok: true, ...info('stopping') } : { ok: true },
    );
    useMapping.getState().setInfo(info('mapping', { unsaved: true }));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Stop mapping' }));
    const dlg = await screen.findByRole('dialog');
    expect(within(dlg).getByText('This map is not saved. Stop and lose it?')).toBeInTheDocument();
    expect(bridgeCalls(m.calls, 'mapping_stop')).toHaveLength(0);
    await userEvent.click(within(dlg).getByRole('button', { name: 'Keep mapping' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(bridgeCalls(m.calls, 'mapping_stop')).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: 'Stop mapping' }));
    const dlg2 = await screen.findByRole('dialog');
    await userEvent.click(within(dlg2).getByRole('button', { name: 'Stop and lose the map' }));
    await waitFor(() => expect(bridgeCalls(m.calls, 'mapping_stop')).toHaveLength(1));
  });

  it('tells the person when the robot refuses', async () => {
    installApi((c) =>
      c.body.cmd === 'mapping_start' ? { ok: false, error: 'scripts_missing' } : { ok: true },
    );
    useMapping.getState().setInfo(info('idle'));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Start mapping' }));
    await waitFor(() =>
      expect(useToasts.getState().items.some((t) => t.text.includes('scripts_missing'))).toBe(true),
    );
  });

  it('Save map opens the save dialog', async () => {
    installApi(() => ({ ok: true }));
    useMapping.getState().setInfo(info('mapping'));
    withUi(<MappingControls />);
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    expect(await screen.findByRole('textbox', { name: 'Map name' })).toBeInTheDocument();
  });
});

/* ---------- SaveMapDialog ---------- */

describe('SaveMapDialog', () => {
  const now = new Date(2026, 10, 12, 9, 5);
  const open = (onClose = vi.fn()) => {
    withUi(<SaveMapDialog open onClose={onClose} now={now} />);
    return onClose;
  };

  it('suggests a name and saves it', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_save' ? { ok: true, ...info('saving') } : { ok: true },
    );
    const onClose = open();
    const box = await screen.findByRole('textbox', { name: 'Map name' });
    expect(box).toHaveValue('map-2026-11-12-0905');
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const calls = bridgeCalls(m.calls, 'mapping_save');
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ cmd: 'mapping_save', name: 'map-2026-11-12-0905' });
    expect(useMapping.getState().info?.state).toBe('saving');
  });

  it('refuses a bad name in words and sends nothing', async () => {
    const m = installApi(() => ({ ok: true }));
    open();
    const box = await screen.findByRole('textbox', { name: 'Map name' });
    await userEvent.clear(box);
    await userEvent.type(box, 'my map');
    expect(await screen.findByText(/letters, digits, hyphens/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    expect(bridgeCalls(m.calls, 'mapping_save')).toHaveLength(0);
    await userEvent.clear(box);
    expect(await screen.findByText('Type a name for the map.')).toBeInTheDocument();
  });

  it('asks a second question when the name exists, then resends with overwrite', async () => {
    const m = installApi((c) => {
      if (c.body.cmd !== 'mapping_save') return { ok: true };
      return c.body.overwrite
        ? { ok: true, ...info('saving') }
        : { ok: false, error: 'exists', exists: true };
    });
    const onClose = open();
    const box = await screen.findByRole('textbox', { name: 'Map name' });
    await userEvent.clear(box);
    await userEvent.type(box, 'lab');
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    expect(
      await screen.findByText('A map named lab already exists on the robot. Replace it?'),
    ).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(bridgeCalls(m.calls, 'mapping_save')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Replace map' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const calls = bridgeCalls(m.calls, 'mapping_save');
    expect(calls).toHaveLength(2);
    expect(calls[1]?.body).toEqual({ cmd: 'mapping_save', name: 'lab', overwrite: true });
  });

  it('declining the replace question sends nothing more', async () => {
    const m = installApi((c) =>
      c.body.cmd === 'mapping_save' ? { ok: false, error: 'exists', exists: true } : { ok: true },
    );
    open();
    await screen.findByRole('textbox', { name: 'Map name' });
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    await screen.findByText(/already exists on the robot/);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(bridgeCalls(m.calls, 'mapping_save')).toHaveLength(1);
    expect(await screen.findByRole('textbox', { name: 'Map name' })).toBeInTheDocument();
  });

  it('shows another refusal in the dialog', async () => {
    installApi((c) =>
      c.body.cmd === 'mapping_save' ? { ok: false, error: 'Not mapping.' } : { ok: true },
    );
    const onClose = open();
    await screen.findByRole('textbox', { name: 'Map name' });
    await userEvent.click(screen.getByRole('button', { name: 'Save map' }));
    expect(await screen.findByText('Not mapping.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});

/* ---------- MapLibrary ---------- */

const entry = (name: string, extra: Partial<MapEntry> = {}): MapEntry => ({
  name,
  width: 200,
  height: 100,
  resolution: 0.05,
  origin: [0, 0, 0],
  mtime: new Date(2026, 10, 12, 14, 7).getTime() / 1000,
  bytes: 4096,
  files: { pgm: 20000, yaml: 200, posegraph: 900, data: 800 },
  ...extra,
});

describe('MapLibrary', () => {
  let maps: MapEntry[];
  beforeEach(() => {
    connectedStatus();
    maps = [
      entry('lab'),
      entry('hall', { files: { pgm: 1, yaml: 1, posegraph: null, data: null } }),
    ];
  });

  const setup = () =>
    installApi((c) => {
      switch (c.body.cmd) {
        case 'maps_list':
          return { ok: true, maps, dir: '/maps' };
        case 'map_rename': {
          if (maps.some((m) => m.name === c.body.new_name))
            return { ok: false, error: 'That name is taken.' };
          maps = maps.map((m) =>
            m.name === c.body.name ? { ...m, name: String(c.body.new_name) } : m,
          );
          return { ok: true, name: c.body.new_name };
        }
        case 'map_delete':
          maps = maps.filter((m) => m.name !== c.body.name);
          return { ok: true, deleted: [`${String(c.body.name)}.yaml`] };
        default:
          return { ok: true };
      }
    });

  it('lists the maps with size, detail, saved time and files', async () => {
    setup();
    withUi(<MapLibrary />);
    const row = await screen.findByTestId('map-row-lab');
    expect(row).toHaveTextContent('10.0 m by 5.0 m');
    expect(row).toHaveTextContent('5 cm per cell');
    expect(row).toHaveTextContent('2026-11-12 14:07');
    expect(row).toHaveTextContent('image, settings, graph, data');
    expect(screen.getByTestId('map-row-hall')).toHaveTextContent('missing: graph, data');
  });

  it('says so when there are no maps, and when the list fails', async () => {
    maps = [];
    setup();
    const { unmount } = withUi(<MapLibrary />);
    expect(await screen.findByText('No saved maps yet')).toBeInTheDocument();
    unmount();
    installApi(() => ({ ok: false, error: 'bridge is down' }));
    withUi(<MapLibrary />);
    expect(await screen.findByRole('alert')).toHaveTextContent('bridge is down');
  });

  it('refresh asks the robot again', async () => {
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(bridgeCalls(m.calls, 'maps_list')).toHaveLength(2));
  });

  it('lists again after a new map is saved', async () => {
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    act(() => useMapping.getState().setInfo(info('mapping', { last_saved: { name: 'x', t: 5 } })));
    await waitFor(() => expect(bridgeCalls(m.calls, 'maps_list')).toHaveLength(2));
  });

  it('shows a preview of the selected row', async () => {
    const created = vi.fn(() => 'blob:preview');
    URL.createObjectURL = created as never;
    URL.revokeObjectURL = (() => {}) as never;
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Show the preview of lab' }));
    const img = await screen.findByRole('img', { name: 'Preview of the map lab' });
    expect(img).toHaveAttribute('src', 'blob:preview');
    expect(m.calls.some((c) => c.path.startsWith('/api/maps/preview.png?name=lab'))).toBe(true);
    delete (URL as { createObjectURL?: unknown }).createObjectURL;
  });

  it('rename checks the name, refuses an existing one, then renames', async () => {
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Rename lab' }));
    const dlg = await screen.findByRole('dialog');
    const box = within(dlg).getByRole('textbox', { name: 'New name' });
    const go = within(dlg).getByRole('button', { name: 'Rename map' });
    expect(go).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, 'bad name');
    expect(await within(dlg).findByText(/letters, digits, hyphens/)).toBeInTheDocument();
    expect(go).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, 'hall');
    expect(await within(dlg).findByText('A map named hall already exists.')).toBeInTheDocument();
    expect(go).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, 'lab-2');
    expect(go).toBeEnabled();
    await userEvent.click(go);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const calls = bridgeCalls(m.calls, 'map_rename');
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ cmd: 'map_rename', name: 'lab', new_name: 'lab-2' });
    expect(await screen.findByTestId('map-row-lab-2')).toBeInTheDocument();
  });

  it('delete asks in a danger dialog and sends confirm:true', async () => {
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Delete lab' }));
    const dlg = await screen.findByRole('dialog');
    expect(dlg.className).toContain('dialog-danger');
    expect(dlg).toHaveTextContent('removed from the robot');
    expect(dlg).toHaveTextContent('cannot be undone');
    expect(bridgeCalls(m.calls, 'map_delete')).toHaveLength(0);
    await userEvent.click(within(dlg).getByRole('button', { name: 'Delete map' }));
    await waitFor(() => expect(bridgeCalls(m.calls, 'map_delete')).toHaveLength(1));
    expect(bridgeCalls(m.calls, 'map_delete')[0]?.body).toEqual({
      cmd: 'map_delete',
      name: 'lab',
      confirm: true,
    });
    await waitFor(() => expect(screen.queryByTestId('map-row-lab')).toBeNull());
    expect(screen.getByTestId('map-row-hall')).toBeInTheDocument();
  });

  it('cancel on the delete dialog deletes nothing', async () => {
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Delete lab' }));
    const dlg = await screen.findByRole('dialog');
    await userEvent.click(within(dlg).getByRole('button', { name: 'Cancel' }));
    expect(bridgeCalls(m.calls, 'map_delete')).toHaveLength(0);
    expect(useDialogs.getState().stack).toHaveLength(0);
  });

  it('download fetches the zip with the token and saves it', async () => {
    const created = vi.fn(() => 'blob:zip');
    URL.createObjectURL = created as never;
    URL.revokeObjectURL = (() => {}) as never;
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const m = setup();
    withUi(<MapLibrary />);
    await screen.findByTestId('map-row-lab');
    await userEvent.click(screen.getByRole('button', { name: 'Download lab' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(m.calls.some((c) => c.path === '/api/maps/download?name=lab')).toBe(true);
    expect(m.calls.find((c) => c.path.startsWith('/api/maps/download'))?.headers).toMatchObject({
      'X-Studio-Token': 'tok',
    });
    click.mockRestore();
    delete (URL as { createObjectURL?: unknown }).createObjectURL;
  });

  it('says it needs a connection', () => {
    setup();
    withUi(<MapLibrary connected={false} />);
    expect(screen.getByText(/Not connected to the robot/)).toBeInTheDocument();
  });
});

/* ---------- canvas, screen, router, words ---------- */

describe('MapCanvas', () => {
  it('shows the empty state, then the sequence number of the drawn map', async () => {
    withUi(<MapCanvas />);
    expect(screen.getByText('No map yet. Start mapping to build one.')).toBeInTheDocument();
    const canvas = screen.getByTestId('map-canvas');
    expect(canvas).toHaveAttribute('data-map-seq', '');
    act(() => {
      useMapping.setState({
        image: {
          seq: 12,
          meta: { ...mapEv(12), ev: undefined } as never,
          source: fakeSource(),
          known: 8,
          close: () => {},
        },
      });
    });
    expect(canvas).toHaveAttribute('data-map-seq', '12');
    expect(screen.queryByText('No map yet. Start mapping to build one.')).toBeNull();
    expect(screen.getByTestId('map-info')).toHaveTextContent('Known area');
  });

  it('has labelled view controls', () => {
    withUi(<MapCanvas />);
    for (const n of ['Zoom out', 'Zoom in', 'Free view', 'Fit map'])
      expect(screen.getByRole('button', { name: n })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit map' })).toBeDisabled();
  });
});

describe('Maps screen', () => {
  it('starts the streams, shows the state, and turns the streams off on leave', async () => {
    const m = installApi((c) => {
      if (c.path === '/api/mapping') return { ok: true, state: 'unknown' };
      if (c.body.cmd === 'mapping_status') return { ok: true, ...info('idle') };
      if (c.body.cmd === 'maps_list') return { ok: true, maps: [], dir: '/maps' };
      if (c.path.startsWith('/api/teleop_limits'))
        return { ok: true, linear: 0.1, angular: 0.5, max_linear: 0.15, max_angular: 1 };
      return { ok: true };
    });
    connectedStatus();
    const { unmount } = withUi(<Maps />);
    expect(screen.getByRole('heading', { name: 'Maps' })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('mapping-state')).toHaveTextContent('Not mapping'),
    );
    await waitFor(() => expect(bridgeCalls(m.calls, 'map_on')).toHaveLength(1));
    expect(bridgeCalls(m.calls, 'map_on')[0]?.body).toEqual({
      cmd: 'map_on',
      hz: 0.5,
      max_cells: 1_000_000,
    });
    expect(bridgeCalls(m.calls, 'scan_on')).toHaveLength(1);
    expect(bridgeCalls(m.calls, 'pose_on')).toHaveLength(1);
    expect(screen.getByTestId('map-canvas')).toBeInTheDocument();
    unmount();
    await waitFor(() => expect(bridgeCalls(m.calls, 'map_off')).toHaveLength(1));
    expect(bridgeCalls(m.calls, 'scan_off')).toHaveLength(1);
  });

  it('says when it is not connected and asks the robot for nothing', () => {
    const m = installApi(() => ({ ok: true }));
    withUi(<Maps />);
    expect(screen.getByText(/Not connected to the robot. Connect to build/)).toBeInTheDocument();
    expect(bridgeCalls(m.calls, 'map_on')).toHaveLength(0);
  });
});

describe('router and words', () => {
  it('has a Maps route right after Live', () => {
    const paths = ROUTES.map((r) => r.path);
    expect(paths.indexOf('/maps')).toBe(paths.indexOf('/live') + 1);
    expect(routeFor('/maps').label).toBe('Maps');
    expect(parseHash('#/maps')).toBe('/maps');
    expect(ROUTES.find((r) => r.path === '/maps')?.ready).toBe(true);
  });

  it('words for finished operations', () => {
    expect(resultText({ op: 'save', ok: true, name: 'lab' }).text).toBe('Map saved as lab.');
    expect(resultText({ op: 'start', ok: true }).text).toBe('Mapping has started.');
    expect(resultText({ op: 'stop', ok: true }).text).toBe('Mapping has stopped.');
    const bad = resultText({ op: 'save', ok: false, error: 'disk full' });
    expect(bad.kind).toBe('error');
    expect(bad.text).toBe('Saving the map failed. disk full');
    expect(resultText({ op: 'start', ok: false }).text).toContain('The robot gave no reason.');
  });
});
