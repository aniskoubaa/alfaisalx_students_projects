import { Badge } from '../../components/ui';
import { useStudio } from '../../state/store';
import {
  SEVERITIES,
  SEVERITY_WORD,
  countBySeverity,
  filterAlerts,
  fmtAlertTime,
  toneOf,
} from './alerts';
import { useAlertsUi } from './state';

/** Three toggle chips. The word and the count carry the meaning; colour only supports it. */
export function SeverityFilter() {
  const alerts = useStudio((s) => s.alerts);
  const show = useAlertsUi((s) => s.show);
  const toggle = useAlertsUi((s) => s.toggle);
  const counts = countBySeverity(alerts);
  return (
    <div className="chips" role="group" aria-label="Show alerts of severity">
      {SEVERITIES.map((sev) => {
        const on = show.includes(sev);
        return (
          <button
            key={sev}
            type="button"
            className={'chip chip-' + toneOf(sev) + (on ? ' is-on' : '')}
            aria-pressed={on}
            onClick={() => toggle(sev)}
          >
            {SEVERITY_WORD[sev]} <span className="num">{counts[sev]}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Alerts, newest first, filtered by the chips above. */
export function AlertList({ limit }: { limit?: number }) {
  const alerts = useStudio((s) => s.alerts);
  const show = useAlertsUi((s) => s.show);
  const seenId = useAlertsUi((s) => s.seenId);
  const rows = filterAlerts(alerts, new Set(show));
  const shown = limit ? rows.slice(0, limit) : rows;
  if (alerts.length === 0) {
    return (
      <p className="drawer-empty">
        No alerts yet. Studio raises one when the battery runs low, the lidar goes quiet, the e-stop
        is pressed or the connection drops.
      </p>
    );
  }
  if (shown.length === 0) {
    return <p className="drawer-empty">No alerts match the chosen severities.</p>;
  }
  return (
    <ol className="alert-rows" aria-label="Alerts, newest first">
      {shown.map((a) => (
        <li
          key={a.id}
          className={'alert-row' + (a.id > seenId && a.severity !== 'info' ? ' is-new' : '')}
        >
          <Badge tone={toneOf(a.severity)}>{SEVERITY_WORD[a.severity]}</Badge>
          <time className="alert-time num" dateTime={new Date(a.t * 1000).toISOString()}>
            {fmtAlertTime(a.t)}
          </time>
          <span className="alert-text">{a.text}</span>
        </li>
      ))}
    </ol>
  );
}
