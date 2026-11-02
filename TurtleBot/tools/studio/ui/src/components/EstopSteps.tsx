import { estopLines } from '../lib/estopSummary';
import { Badge } from './ui';

/** The e-stop answer as a short checklist (what was switched off, cancelled and stopped). */
export function EstopSteps({ steps }: { steps: unknown }) {
  const lines = estopLines(steps);
  if (!lines.length) return null;
  return (
    <ul className="steps">
      {lines.map((l) => (
        <li key={l.label}>
          {l.label}{' '}
          {l.ok === null ? null : (
            <Badge tone={l.ok ? 'ok' : 'bad'}>{l.ok ? 'Done' : 'Failed'}</Badge>
          )}
        </li>
      ))}
    </ul>
  );
}
