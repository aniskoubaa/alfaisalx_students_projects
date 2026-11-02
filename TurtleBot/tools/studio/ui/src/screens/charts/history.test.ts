import { describe, expect, it } from 'vitest';
import {
  CHARTS,
  appendSample,
  emptyBuffer,
  fmtValue,
  fromAnswer,
  lastValue,
  mergeBuffers,
  rangeFor,
  sampleFromStatus,
  windowData,
} from './history';
import type { HistoryAnswer } from '../../api';

const status = {
  ev: 'status' as const,
  battery: { percent: 76, voltage: 15.8, current_a: -0.4 },
  odom: { vx: -0.12, rate_hz: 19.5 },
  scan: { rate_hz: 7.5 },
  system: { cpu_pct: 12, temp_c: 55.5 },
  net: { signal_dbm: -57 },
};

describe('sampleFromStatus', () => {
  it('maps every field and uses the size of the forward speed', () => {
    const s = sampleFromStatus(status);
    expect(s).toEqual({
      battery_pct: 76,
      voltage: 15.8,
      current_a: -0.4,
      speed: 0.12,
      odom_hz: 19.5,
      scan_hz: 7.5,
      cpu_pct: 12,
      temp_c: 55.5,
      wifi_dbm: -57,
    });
  });

  it('gives null for missing or non-finite values', () => {
    const s = sampleFromStatus({ ev: 'status', battery: { percent: Number.NaN } });
    expect(Object.values(s).every((v) => v === null)).toBe(true);
  });
});

describe('appendSample', () => {
  it('appends in order, ignores a sample too close to the last, and caps the age', () => {
    const b = emptyBuffer();
    const s = sampleFromStatus(status);
    expect(appendSample(b, 1000, s, 10)).toBe(true);
    expect(appendSample(b, 1000.2, s, 10)).toBe(false);
    expect(appendSample(b, 1001, s, 10)).toBe(true);
    expect(appendSample(b, 1012, s, 10)).toBe(true);
    // 1000 and 1001 are older than 1012 - 10 = 1002 and are dropped.
    expect(b.t).toEqual([1012]);
    expect(b.series.battery_pct).toEqual([76]);
  });
});

describe('windowData', () => {
  it('returns only the samples inside the window, aligned across columns', () => {
    const b = emptyBuffer();
    for (let t = 0; t <= 600; t += 60) {
      appendSample(b, t, { ...sampleFromStatus(status), battery_pct: t / 6 });
    }
    const d = windowData(b, ['battery_pct', 'voltage'], 600, 5);
    expect(d[0]).toEqual([300, 360, 420, 480, 540, 600]);
    expect(d[1]).toEqual([50, 60, 70, 80, 90, 100]);
    expect(d[2]?.length).toBe(6);
  });
});

describe('merge and load', () => {
  const answer: HistoryAnswer = {
    t: [100, 101, 102],
    series: {
      battery_pct: [80, 80, null],
      voltage: [15, 15, 15],
      current_a: [0, 0, 0],
      speed: [0, 0, 0],
      odom_hz: [20, 20, 20],
      scan_hz: [7, 7, 7],
      cpu_pct: [1, 2, 3],
      temp_c: [50, 50, 50],
      wifi_dbm: [-55, -55, -55],
    },
  };

  it('fromAnswer keeps nulls', () => {
    const b = fromAnswer(answer);
    expect(b.t).toEqual([100, 101, 102]);
    expect(b.series.battery_pct).toEqual([80, 80, null]);
  });

  it('mergeBuffers unions by second and prefers the second buffer', () => {
    const live = emptyBuffer();
    appendSample(live, 102.4, { ...sampleFromStatus(status), cpu_pct: 99 });
    appendSample(live, 103.4, { ...sampleFromStatus(status), cpu_pct: 98 });
    const merged = mergeBuffers(live, fromAnswer(answer));
    expect(merged.t).toEqual([100, 101, 102, 103]);
    expect(merged.series.cpu_pct).toEqual([1, 2, 3, 98]);
  });

  it('lastValue skips the last few nulls', () => {
    const b = fromAnswer(answer);
    expect(lastValue(b, 'battery_pct')).toBe(80);
    expect(lastValue(emptyBuffer(), 'voltage')).toBeNull();
  });
});

describe('ranges and text', () => {
  it('rangeFor widens the default to fit the data unless fixed', () => {
    expect(rangeFor([0, 100], 10, 20, true)).toEqual([0, 100]);
    expect(rangeFor([0, 0.3], 0, 0.1)).toEqual([0, 0.3]);
    const [lo, hi] = rangeFor([0, 25], 0, 40);
    expect(lo).toBe(0);
    expect(hi).toBeGreaterThan(40);
    expect(rangeFor([0, 25], null, null)).toEqual([0, 25]);
  });

  it('fmtValue writes a real minus, a thin space and the unit', () => {
    expect(fmtValue(-57, { digits: 0, unit: 'dBm' })).toBe('−57 dBm');
    expect(fmtValue(null, { digits: 0, unit: 'dBm' })).toBe('–');
  });

  it('defines the six charts with the TB-25 note on message rates', () => {
    expect(CHARTS.map((c) => c.id)).toEqual([
      'battery',
      'power',
      'speed',
      'rates',
      'system',
      'wifi',
    ]);
    expect(CHARTS.find((c) => c.id === 'rates')?.hint).toContain('TB-25');
  });
});
