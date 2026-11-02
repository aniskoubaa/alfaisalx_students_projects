import { OctagonAlert, TriangleAlert, Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { fmtClock } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { dismissUpdate, releaseEstop, stopReconnecting } from '../../state/actions';
import { retryEventStream } from '../../state/runtime';
import { isEstopOn } from '../../state/selectors';
import { useStudio } from '../../state/store';
import { Button } from '../ui';

function Banner({
  tone,
  icon,
  children,
  actions,
  role = 'status',
}: {
  tone: 'red' | 'amber' | 'blue';
  icon: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  role?: 'status' | 'alert';
}) {
  return (
    <div className={`banner banner-${tone}`} role={role}>
      <span className="banner-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="banner-text">{children}</div>
      {actions ? <div className="banner-actions">{actions}</div> : null}
    </div>
  );
}

const secondsLeft = (at: number, now: number) => Math.max(0, Math.ceil((at - now) / 1000));

export function Banners() {
  const sse = useStudio((s) => s.sse);
  const conn = useStudio((s) => s.conn);
  const reconn = useStudio((s) => s.reconn);
  const update = useStudio((s) => s.update);
  const dismissed = useStudio((s) => s.settings.update_dismissed);
  const estop = useStudio(isEstopOn);
  const now = useNow(500);

  const showUpdate = !!(update?.latest && update.newer !== false && dismissed !== update.latest);
  const retryIn = sse.retryAt ? secondsLeft(sse.retryAt, now) : 0;

  return (
    <div className="banners">
      {sse.state === 'down' ? (
        <Banner
          tone="amber"
          role="alert"
          icon={<TriangleAlert size={18} />}
          actions={
            <Button size="sm" onClick={retryEventStream}>
              Retry now
            </Button>
          }
        >
          <strong>Lost connection to Studio.</strong> Trying again
          {retryIn ? ` in ${retryIn} s` : ' now'}. Values shown are old, and the E-STOP may not
          reach the robot. Hold the robot if it moves.
        </Banner>
      ) : null}
      {estop ? (
        <Banner
          tone="red"
          role="alert"
          icon={<OctagonAlert size={18} />}
          actions={
            <Button size="sm" variant="danger" onClick={() => void releaseEstop()}>
              Release e-stop
            </Button>
          }
        >
          <strong>E-stop is on.</strong> Drive motors are off.
        </Banner>
      ) : null}
      {conn.state === 'reconnecting' && reconn ? (
        <Banner
          tone="amber"
          role="alert"
          icon={<TriangleAlert size={18} />}
          actions={
            <Button size="sm" onClick={() => void stopReconnecting()}>
              Stop reconnecting
            </Button>
          }
        >
          <strong>Connection lost at {fmtClock(reconn.since)}.</strong> Reconnecting (attempt{' '}
          {reconn.attempt},{' '}
          {secondsLeft(reconn.nextAt, now)
            ? `next in ${secondsLeft(reconn.nextAt, now)} s`
            : 'trying now'}
          ).
        </Banner>
      ) : null}
      {showUpdate && update ? (
        <Banner
          tone="blue"
          icon={<Info size={18} />}
          actions={
            <Button size="sm" onClick={() => void dismissUpdate()}>
              Dismiss
            </Button>
          }
        >
          <strong>Version {update.latest} is available.</strong>{' '}
          {update.page &&
          update.page.startsWith('https://github.com/aniskoubaa/alfaisalx_students_projects/') ? (
            <a href={update.page} target="_blank" rel="noopener noreferrer">
              How to update
            </a>
          ) : null}
        </Banner>
      ) : null}
    </div>
  );
}
