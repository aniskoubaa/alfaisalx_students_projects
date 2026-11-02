import { Pause, Play, RefreshCw } from 'lucide-react';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { Button, Panel } from '../../components/ui';
import { useNow } from '../../lib/useNow';
import { useStudio } from '../../state/store';
import { AlertList, SeverityFilter } from '../events/AlertList';
import { UPlotChart, readChartColors } from './UPlotChart';
import type { ChartColors } from './UPlotChart';
import { getBuffer, getVersion, loadHistory, subscribeHistory } from './feed';
import { CHARTS, WINDOWS, fmtValue, lastValue } from './history';
import type { ChartDef, WindowMinutes } from './history';

/** Re-read the colour tokens whenever the theme changes. */
function useChartColors(): ChartColors {
  const [colors, setColors] = useState(readChartColors);
  useEffect(() => {
    const update = () => setColors(readChartColors());
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', update);
    return () => {
      mo.disconnect();
      mq.removeEventListener('change', update);
    };
  }, []);
  return colors;
}

function Legend({ def, colors, version }: { def: ChartDef; colors: ChartColors; version: number }) {
  void version;
  const buf = getBuffer();
  return (
    <ul className="chart-legend" aria-label={`${def.title} now`}>
      {def.series.map((s) => (
        <li key={s.key}>
          <span
            className={'chart-swatch' + (s.dashed ? ' is-dashed' : '')}
            style={{ ['--sw' as string]: colors[s.color] }}
            aria-hidden="true"
          />
          <span>{s.label}</span>
          <strong className="num">{fmtValue(lastValue(buf, s.key), s)}</strong>
        </li>
      ))}
    </ul>
  );
}

export default function Charts() {
  const [minutes, setMinutes] = useState<WindowMinutes>(15);
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [state, setState] = useState<{ loading: boolean; error: string | null }>({
    loading: true,
    error: null,
  });
  const colors = useChartColors();
  const connected = useStudio((s) => s.conn.state === 'connected');
  const now = useNow(1000);
  const version = useSyncExternalStore(subscribeHistory, getVersion);
  const buffer = getBuffer();

  const load = async () => {
    const r = await loadHistory();
    setState({ loading: false, error: r.ok ? null : r.error });
  };
  const reload = () => {
    setState({ loading: true, error: null });
    void load();
  };

  // First load when the screen opens. The state starts as "loading".
  useEffect(() => {
    void loadHistory().then((r) => setState({ loading: false, error: r.ok ? null : r.error }));
  }, []);

  const anchor = pausedAt ?? Math.floor(now / 1000);
  const hasData = buffer.t.length > 0;

  return (
    <div className="page charts">
      <div className="page-head">
        <h1 className="page-title">Charts</h1>
        <div className="row chart-controls">
          <div className="seg" role="radiogroup" aria-label="Time window">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                role="radio"
                aria-checked={minutes === w}
                className={'seg-btn' + (minutes === w ? ' is-on' : '')}
                onClick={() => setMinutes(w)}
              >
                {w} min
              </button>
            ))}
          </div>
          <Button
            icon={
              pausedAt === null ? (
                <Pause size={16} aria-hidden="true" />
              ) : (
                <Play size={16} aria-hidden="true" />
              )
            }
            aria-pressed={pausedAt !== null}
            onClick={() => setPausedAt(pausedAt === null ? Math.floor(Date.now() / 1000) : null)}
          >
            {pausedAt === null ? 'Pause' : 'Resume'}
          </Button>
          <Button
            icon={<RefreshCw size={16} aria-hidden="true" />}
            loading={state.loading}
            onClick={reload}
          >
            Reload history
          </Button>
        </div>
      </div>

      {state.error ? (
        <div className="note note-warn" role="alert">
          <strong>Could not load the history.</strong> {state.error} The charts fill in from now on.
        </div>
      ) : null}
      {!connected ? (
        <p className="note note-warn" role="status">
          Not connected to the robot. The charts show what was recorded until now; new values appear
          after you connect.
        </p>
      ) : null}
      {pausedAt !== null ? (
        <p className="note" role="status">
          Paused. New values are still recorded and show when you resume.
        </p>
      ) : null}

      <div className="chart-grid">
        {CHARTS.map((def) => (
          <Panel key={def.id} title={def.title} className="chart-panel">
            <Legend def={def} colors={colors} version={version} />
            {hasData ? (
              <UPlotChart
                def={def}
                buffer={buffer}
                version={version}
                minutes={minutes}
                anchor={anchor}
                colors={colors}
              />
            ) : (
              <p className="chart-empty dim">
                {state.loading
                  ? 'Loading history.'
                  : 'No values recorded yet. Connect to the robot to start.'}
              </p>
            )}
            {def.hint ? <p className="chart-hint small dim">{def.hint}</p> : null}
          </Panel>
        ))}
      </div>

      <Panel title="Events" className="events-panel">
        <div className="stack">
          <SeverityFilter />
          <AlertList />
        </div>
      </Panel>
    </div>
  );
}
