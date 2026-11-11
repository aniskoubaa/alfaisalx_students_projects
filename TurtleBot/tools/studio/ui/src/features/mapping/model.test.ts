import { describe, expect, it } from 'vitest';
import type { MapEntry, MappingInfo } from '../../api';
import {
  STATE_WORDS,
  allowedActions,
  cellToPixel,
  cellToWorld,
  filesSummary,
  fitMap,
  formatAge,
  formatBytes,
  formatSaved,
  imageToWorld,
  isBusy,
  knownCellsSummary,
  mapBounds,
  mapSizeText,
  parseMapMeta,
  stateTone,
  stateWord,
  suggestName,
  toMapMeta,
  validMapName,
  worldToImage,
} from './model';
import { MapViewState, imageRect } from './view';

const info = (state: MappingInfo['state'], extra: Partial<MappingInfo> = {}): MappingInfo => ({
  state,
  scripts_ok: true,
  other_stack: null,
  ...extra,
});

describe('state words and tones', () => {
  it('uses the agreed words', () => {
    expect(STATE_WORDS).toMatchObject({
      idle: 'Not mapping',
      starting: 'Starting mapping…',
      mapping: 'Mapping',
      saving: 'Saving the map…',
      stopping: 'Stopping…',
      error: 'Error',
    });
    expect(stateWord(info('mapping'))).toBe('Mapping');
    expect(stateWord(null)).toBe('Checking the mapping state…');
    expect(stateWord({ state: 'nonsense' as never })).toBe('Checking the mapping state…');
  });

  it('gives each state a tone', () => {
    expect(stateTone(info('mapping'))).toBe('ok');
    expect(stateTone(info('error'))).toBe('bad');
    expect(stateTone(info('idle'))).toBe('neutral');
    expect(stateTone(info('saving'))).toBe('info');
    expect(stateTone(null)).toBe('neutral');
  });

  it('knows which states are busy', () => {
    expect(['starting', 'saving', 'stopping'].map((s) => isBusy(info(s as never)))).toEqual([
      true,
      true,
      true,
    ]);
    expect(['idle', 'mapping', 'error'].map((s) => isBusy(info(s as never)))).toEqual([
      false,
      false,
      false,
    ]);
  });
});

describe('allowedActions', () => {
  const flags = (i: MappingInfo | null, connected = true) => {
    const a = allowedActions(i, connected);
    return [a.start, a.save, a.stop, a.reset, a.drive].map((x) => x.enabled);
  };

  it('idle: only start (and driving)', () => {
    expect(flags(info('idle'))).toEqual([true, false, false, false, true]);
  });
  it('mapping: save, stop, drive', () => {
    expect(flags(info('mapping'))).toEqual([false, true, true, false, true]);
  });
  it('error: stop and clear', () => {
    expect(flags(info('error'))).toEqual([false, false, true, true, true]);
  });
  it('starting, saving, stopping: nothing, and no driving', () => {
    for (const s of ['starting', 'saving', 'stopping'] as const) {
      expect(flags(info(s))).toEqual([false, false, false, false, false]);
      expect(allowedActions(info(s)).drive.reason).toMatch(/Driving is off/);
    }
  });
  it('not connected: everything off with a reason', () => {
    const a = allowedActions(info('idle'), false);
    expect([a.start, a.save, a.stop, a.reset, a.drive].every((x) => !x.enabled)).toBe(true);
    expect(a.start.reason).toBe('Not connected to the robot.');
  });
  it('unknown or missing state: waits', () => {
    expect(allowedActions(null).start.reason).toMatch(/Waiting/);
    expect(allowedActions(info('unknown')).start.enabled).toBe(false);
  });
  it('start explains missing scripts and a running navigation program', () => {
    expect(allowedActions(info('idle', { scripts_ok: false })).start.reason).toMatch(/missing/);
    const a = allowedActions(info('idle', { other_stack: 'nav2' })).start;
    expect(a.enabled).toBe(false);
    expect(a.reason).toContain('nav2');
  });
  it('every disabled action has a reason and every enabled one has none', () => {
    for (const s of ['idle', 'starting', 'mapping', 'saving', 'stopping', 'error'] as const) {
      const a = allowedActions(info(s));
      for (const x of [a.start, a.save, a.stop, a.reset, a.drive])
        expect(x.reason === '').toBe(x.enabled);
    }
  });
});

describe('validMapName', () => {
  it.each(['a', 'map1', 'Lab_floor-2', 'A'.repeat(48), '9lives'])('accepts %s', (n) => {
    expect(validMapName(n)).toEqual({ ok: true });
  });
  it.each([
    ['', /Type a name/],
    ['A'.repeat(49), /48 characters/],
    ['-start', /Start the name/],
    ['_start', /Start the name/],
    ['has space', /letters, digits/],
    ['dot.name', /letters, digits/],
    ['../x', /Start the name/],
    ['a/b', /letters, digits/],
    ['é', /Start the name/],
  ])('refuses %j', (n, msg) => {
    const r = validMapName(n);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(msg);
  });
});

describe('suggestName', () => {
  it('builds a name from the local date and time, and it is valid', () => {
    const n = suggestName(new Date(2026, 10, 12, 9, 5));
    expect(n).toBe('map-2026-11-12-0905');
    expect(validMapName(n).ok).toBe(true);
  });
});

describe('image and world transform', () => {
  const g = { width: 100, height: 50, resolution: 0.05, origin: { x: -1, y: -2 } };

  it('cell centre in world metres', () => {
    expect(cellToWorld(g, 0, 0)).toEqual([-1 + 0.025, -2 + 0.025]);
    const [x, y] = cellToWorld(g, 10, 20);
    expect(x).toBeCloseTo(-1 + 10.5 * 0.05);
    expect(y).toBeCloseTo(-2 + 20.5 * 0.05);
  });

  it('image row 0 is the top row, the highest y', () => {
    expect(cellToPixel(g, 3, 49)).toEqual([3, 0]);
    expect(cellToPixel(g, 3, 0)).toEqual([3, 49]);
    const [, topY] = imageToWorld(g, 0, 0);
    const [, bottomY] = imageToWorld(g, 0, 50);
    expect(topY).toBeCloseTo(-2 + 50 * 0.05);
    expect(bottomY).toBeCloseTo(-2);
  });

  it('world to image and back', () => {
    const [px, py] = worldToImage(g, 0.5, -1);
    expect(px).toBeCloseTo(30);
    expect(py).toBeCloseTo(50 - 20);
    const [x, y] = imageToWorld(g, px, py);
    expect(x).toBeCloseTo(0.5);
    expect(y).toBeCloseTo(-1);
  });

  it('the centre of cell (i, j) lands in the middle of its pixel', () => {
    const [wx, wy] = cellToWorld(g, 7, 12);
    const [px, py] = worldToImage(g, wx, wy);
    const [col, row] = cellToPixel(g, 7, 12);
    expect(px).toBeCloseTo(col + 0.5);
    expect(py).toBeCloseTo(row + 0.5);
  });

  it('bounds and fit', () => {
    expect(mapBounds(g)).toEqual({ minX: -1, maxX: 4, minY: -2, maxY: 0.5 });
    const f = fitMap(g, 524, 324, 12);
    expect(f.cx).toBeCloseTo(1.5);
    expect(f.cy).toBeCloseTo(-0.75);
    // 500 px for 5 m, 300 px for 2.5 m: width limits at 100, height at 120.
    expect(f.scale).toBeCloseTo(100);
  });
});

describe('map view', () => {
  const g = { width: 100, height: 100, resolution: 0.05, origin: { x: 0, y: 0 } };

  it('fit centres the map and leaves follow mode', () => {
    const v = new MapViewState();
    v.follow = true;
    v.fit(g, 400, 400);
    expect(v.follow).toBe(false);
    expect(v.centre[0]).toBeCloseTo(2.5);
    const r = imageRect(v.view(400, 400, null), g);
    expect(r.w).toBeCloseTo(r.h);
    expect(r.x + r.w / 2).toBeCloseTo(200);
    expect(r.y + r.h / 2).toBeCloseTo(200);
  });

  it('follows the robot, and freezes the view when follow is turned off', () => {
    const v = new MapViewState();
    const robot = { x: 1, y: 2, yaw: 0 };
    v.setFollow(true, 400, 400, robot);
    expect(v.view(400, 400, robot)).toMatchObject({ cx: 1, cy: 2 });
    v.setFollow(false, 400, 400, robot);
    expect(v.view(400, 400, { x: 9, y: 9, yaw: 0 })).toMatchObject({ cx: 1, cy: 2 });
  });

  it('panning turns follow off and zoom keeps the scale in range', () => {
    const v = new MapViewState();
    v.follow = true;
    expect(v.pan(10, 0, 400, 400, { x: 0, y: 0, yaw: 0 })).toBe(true);
    expect(v.follow).toBe(false);
    for (let i = 0; i < 50; i++) v.zoom(1.5, 400, 400, null);
    expect(v.scale).toBeLessThanOrEqual(600);
    for (let i = 0; i < 80; i++) v.zoom(0.5, 400, 400, null);
    expect(v.scale).toBeGreaterThanOrEqual(15);
  });
});

describe('parseMapMeta', () => {
  const good = {
    seq: 4,
    t: 12.5,
    width: 10,
    height: 8,
    resolution: 0.05,
    origin: { x: -0.5, y: -0.4, yaw: 0 },
    stride: 2,
  };
  it('reads a header', () => {
    expect(parseMapMeta(JSON.stringify(good))).toEqual(good);
  });
  it('accepts an origin as a list', () => {
    const m = parseMapMeta(JSON.stringify({ ...good, origin: [1, 2, 0.5] }));
    expect(m?.origin).toEqual({ x: 1, y: 2, yaw: 0.5 });
  });
  it.each([
    null,
    undefined,
    '',
    'not json',
    '[]',
    '"x"',
    JSON.stringify({ ...good, width: 0 }),
    JSON.stringify({ ...good, resolution: -1 }),
    JSON.stringify({ ...good, seq: 'a' }),
    JSON.stringify({ ...good, origin: null }),
    JSON.stringify({ ...good, origin: { x: 'a', y: 1 } }),
  ])('returns null for %j', (h) => {
    expect(parseMapMeta(h as string | null | undefined)).toBeNull();
  });
  it('toMapMeta ignores extra fields like ev', () => {
    expect(toMapMeta({ ev: 'map', ...good })?.seq).toBe(4);
  });
});

describe('formatting', () => {
  it('sizes in metres', () => {
    expect(mapSizeText({ width: 248, height: 160, resolution: 0.05 })).toBe('12.4 m by 8.0 m');
    expect(mapSizeText({ width: 4000, height: 2000, resolution: 0.05 })).toBe('200 m by 100 m');
  });
  it('known cells summary', () => {
    const s = knownCellsSummary(400, 800, 0.05, { width: 40, height: 20 });
    expect(s).toBe('Map size 2.0 m by 1.0 m. Known area 1.0 m² of 2.0 m² (50%).');
    expect(knownCellsSummary(0, 0, 0.05)).toBe('Known area 0.0 m² of 0.0 m² (0%).');
  });
  it('bytes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(3 * 1048576)).toBe('3.0 MB');
    expect(formatBytes(null)).toBe('–');
  });
  it('age', () => {
    expect(formatAge(100, 102)).toBe('just now');
    expect(formatAge(100, 130)).toBe('30 s ago');
    expect(formatAge(100, 100 + 300)).toBe('5 min ago');
    expect(formatAge(100, 100 + 7200)).toBe('2 h ago');
    expect(formatAge(100, 100 + 86400)).toBe('1 day ago');
    expect(formatAge(100, 100 + 3 * 86400)).toBe('3 days ago');
    expect(formatAge(200, 100)).toBe('just now');
  });
  it('saved time', () => {
    const t = new Date(2026, 10, 12, 14, 7).getTime() / 1000;
    expect(formatSaved(t)).toBe('2026-11-12 14:07');
  });
  it('files', () => {
    const f: MapEntry['files'] = { pgm: 1, yaml: 1, posegraph: 1, data: 1 };
    expect(filesSummary(f)).toBe('image, settings, graph, data');
    expect(filesSummary({ ...f, data: null })).toBe('image, settings, graph (missing: data)');
  });
});
