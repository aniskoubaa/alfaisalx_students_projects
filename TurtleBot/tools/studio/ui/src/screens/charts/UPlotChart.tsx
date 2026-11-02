import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { useEffect, useRef } from 'react';
import { fmtValue, rangeFor, windowData } from './history';
import type { ChartDef, HistoryBuffer, SeriesDef } from './history';

/** Read the colour tokens from the page so the chart follows the light and dark themes. */
export interface ChartColors {
  signal: string;
  green: string;
  amber: string;
  ink: string;
  muted: string;
  line: string;
  surface: string;
}

export function readChartColors(): ChartColors {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string, f: string) => cs.getPropertyValue(n).trim() || f;
  return {
    signal: v('--signal', '#1d5bd6'),
    green: v('--green', '#1d8a3a'),
    amber: v('--amber', '#d99a00'),
    ink: v('--ink', '#18212b'),
    muted: v('--muted', '#5a6676'),
    line: v('--line', '#d3d9e1'),
    surface: v('--surface', '#ffffff'),
  };
}

const FONT = '12px "IBM Plex Sans", system-ui, sans-serif';

function tooltipPlugin(def: ChartDef, colors: ChartColors): uPlot.Plugin {
  let tip: HTMLDivElement | null = null;
  return {
    hooks: {
      init: (u) => {
        tip = document.createElement('div');
        tip.className = 'chart-tip';
        tip.style.display = 'none';
        u.over.appendChild(tip);
      },
      setCursor: (u) => {
        if (!tip) return;
        const { idx, left, top } = u.cursor;
        if (idx === null || idx === undefined || left === undefined || left < 0) {
          tip.style.display = 'none';
          return;
        }
        const time = u.data[0][idx];
        if (time === undefined) {
          tip.style.display = 'none';
          return;
        }
        tip.replaceChildren();
        const head = document.createElement('div');
        head.className = 'chart-tip-time';
        head.textContent = new Date(time * 1000).toTimeString().slice(0, 8);
        tip.appendChild(head);
        def.series.forEach((s, i) => {
          const row = document.createElement('div');
          row.className = 'chart-tip-row';
          const sw = document.createElement('span');
          sw.className = 'chart-swatch' + (s.dashed ? ' is-dashed' : '');
          sw.style.setProperty('--sw', colors[s.color]);
          const name = document.createElement('span');
          name.textContent = s.label;
          const val = document.createElement('span');
          val.className = 'chart-tip-val';
          val.textContent = fmtValue(u.data[i + 1]?.[idx] ?? null, s);
          row.append(sw, name, val);
          tip?.appendChild(row);
        });
        tip.style.display = 'block';
        const w = u.over.clientWidth;
        const flip = left > w - 190;
        tip.style.left = (flip ? left - 12 : left + 12) + 'px';
        tip.style.transform = flip ? 'translateX(-100%)' : 'none';
        tip.style.top = Math.max(0, Math.min((top ?? 0) - 10, u.over.clientHeight - 80)) + 'px';
      },
    },
  };
}

function seriesOpts(s: SeriesDef, colors: ChartColors): uPlot.Series {
  return {
    label: s.label,
    scale: s.scale,
    stroke: colors[s.color],
    width: 2,
    dash: s.dashed ? [6, 4] : undefined,
    points: { show: false },
    spanGaps: false,
    value: (_u, v) => fmtValue(v, s),
  };
}

function axisOpts(
  scale: 'y' | 'y2',
  side: 1 | 3,
  unit: string,
  colors: ChartColors,
  grid: boolean,
): uPlot.Axis {
  return {
    scale,
    side,
    stroke: colors.muted,
    font: FONT,
    size: 52,
    label: unit,
    labelFont: FONT,
    labelSize: 16,
    grid: grid ? { stroke: colors.line, width: 1 } : { show: false },
    ticks: { stroke: colors.line, width: 1, size: 4 },
  };
}

interface Props {
  def: ChartDef;
  buffer: HistoryBuffer;
  /** Bumps whenever the buffer gained samples. */
  version: number;
  minutes: number;
  /** Epoch seconds the right edge of the window sits at. */
  anchor: number;
  colors: ChartColors;
  /** Height in CSS pixels. */
  height?: number;
}

/** One uPlot chart. Re-created when the colours change; otherwise only the data is replaced. */
export function UPlotChart({ def, buffer, version, minutes, anchor, colors, height = 190 }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const latest = useRef({ buffer, minutes, anchor });
  useEffect(() => {
    latest.current = { buffer, minutes, anchor };
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const keys = def.series.map((s) => s.key);
    const hasY2 = def.series.some((s) => s.scale === 'y2');
    const unitOf = (scale: 'y' | 'y2') =>
      [...new Set(def.series.filter((s) => s.scale === scale).map((s) => s.unit))].join(' / ');
    const dataFor = () => {
      const { buffer: b, minutes: m, anchor: a } = latest.current;
      return windowData(b, keys, a, m) as uPlot.AlignedData;
    };
    const rangeOf =
      (scale: 'y' | 'y2'): uPlot.Scale.Range =>
      (_u, dmin, dmax) => {
        const def0 = def.range[scale] ?? [0, 1];
        const finite = Number.isFinite(dmin) && Number.isFinite(dmax);
        return rangeFor(def0, finite ? dmin : null, finite ? dmax : null, def.fixed);
      };
    const opts: uPlot.Options = {
      width: Math.max(200, el.clientWidth),
      height,
      padding: [8, hasY2 ? 4 : 12, 0, 0],
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, points: { size: 7 } },
      scales: {
        x: { time: true },
        y: { range: rangeOf('y') },
        ...(hasY2 ? { y2: { range: rangeOf('y2') } } : {}),
      },
      axes: [
        {
          stroke: colors.muted,
          font: FONT,
          grid: { stroke: colors.line, width: 1 },
          ticks: { stroke: colors.line, width: 1, size: 4 },
          size: 46,
        },
        axisOpts('y', 3, unitOf('y'), colors, true),
        ...(hasY2 ? [axisOpts('y2', 1, unitOf('y2'), colors, false)] : []),
      ],
      series: [{}, ...def.series.map((s) => seriesOpts(s, colors))],
      plugins: [tooltipPlugin(def, colors)],
    };
    const u = new uPlot(opts, dataFor(), el);
    plot.current = u;
    const ro = new ResizeObserver(() => {
      u.setSize({ width: Math.max(200, el.clientWidth), height });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      u.destroy();
      plot.current = null;
    };
  }, [def, colors, height]);

  useEffect(() => {
    const u = plot.current;
    if (!u) return;
    const keys = def.series.map((s) => s.key);
    u.setData(windowData(buffer, keys, anchor, minutes) as uPlot.AlignedData, false);
    u.setScale('x', { min: anchor - minutes * 60, max: anchor });
  }, [def, buffer, version, minutes, anchor, colors]);

  return <div ref={host} className="chart-host" />;
}
