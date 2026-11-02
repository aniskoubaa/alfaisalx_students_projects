import { Check, Circle, CircleAlert, CircleHelp, Hourglass } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button, Spinner } from '../../components/ui';
import type { StepState } from '../../lib/wifi';
import { discover } from '../../state/actions';
import { closeInfoDialog } from '../../state/dialogs2';
import { notify } from '../../state/feedback';
import { navigate } from '../../state/router';
import { useStudio } from '../../state/store';
import { useWifi } from '../../state/wifiStore';

const STEP_WORDS: Record<StepState, string> = {
  ok: 'Done',
  bad: 'Problem',
  run: 'Working',
  wait: 'Waiting for you',
  idle: 'Later',
  warn: 'Unknown',
};

function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case 'ok':
      return <Check size={16} aria-hidden="true" />;
    case 'bad':
      return <CircleAlert size={16} aria-hidden="true" />;
    case 'run':
      return <Spinner size={16} />;
    case 'wait':
      return <Hourglass size={16} aria-hidden="true" />;
    case 'warn':
      return <CircleHelp size={16} aria-hidden="true" />;
    default:
      return <Circle size={16} aria-hidden="true" />;
  }
}

function Note({ tone, children }: { tone: 'ok' | 'bad' | 'warn'; children: ReactNode }) {
  return (
    <div className={`note note-${tone}`} role={tone === 'bad' ? 'alert' : undefined}>
      {children}
    </div>
  );
}

/** The content of the "Adding a network" dialog. It follows the Wi-Fi store, so it updates by itself. */
export function WifiJobBody() {
  const job = useWifi((s) => s.shown);
  const view = useWifi((s) => s.jobView);
  const flag = useWifi((s) => s.jobFlag);
  const err = useWifi((s) => s.jobErr);
  if (!job || !view) return null;
  const jn = view.join ?? {};

  const applyAddress = (ip: string) => {
    closeInfoDialog('wifi-job');
    useStudio.getState().patchSettings({ last_host: ip });
    navigate('/overview');
    notify('ok', 'Address filled in. Press Connect.');
  };
  const goDiscover = () => {
    closeInfoDialog('wifi-job');
    navigate('/overview');
    void discover();
  };

  return (
    <div className="job" aria-live="polite">
      <ol className="job-steps" aria-label="Progress">
        {view.steps.map((s, i) => (
          <li key={i} className={`job-step job-${s.state}`}>
            <span className="job-icon">
              <StepIcon state={s.state} />
            </span>
            <span className="job-text">{s.text}</span>
            <span className="job-state">{STEP_WORDS[s.state]}</span>
          </li>
        ))}
      </ol>

      {view.result === 'joined' ? (
        <Note tone="ok">
          <p>
            <strong>The robot joined {job.ssid}.</strong> Its address there:{' '}
            <code>{jn.ip || 'unknown'}</code>.
          </p>
          <p>
            Join this computer to <strong>{job.ssid}</strong> too, then use the address below or
            press Discover.
          </p>
          <div className="row">
            {jn.ip ? (
              <Button variant="primary" size="sm" onClick={() => applyAddress(jn.ip as string)}>
                Use this address
              </Button>
            ) : null}
            <Button size="sm" onClick={goDiscover}>
              Discover
            </Button>
          </div>
        </Note>
      ) : null}

      {view.result === 'failed' ? (
        <Note tone="bad">
          <p>
            <strong>The robot could not join {job.ssid}.</strong> {jn.reason || 'Unknown reason'}.
          </p>
          <p>
            {jn.fallback ? (
              jn.fallback_ok === false ? (
                <>
                  It tried to return to <strong>{jn.fallback}</strong> but that did not work yet. It
                  should reach it or its hotspot within about 1.5 minutes.
                </>
              ) : (
                <>
                  It is back on <strong>{jn.fallback}</strong>.
                </>
              )
            ) : (
              'It stays on its previous network.'
            )}
            {jn.removed
              ? ' The saved entry was removed, so you can try again with the right password.'
              : ''}
          </p>
        </Note>
      ) : null}

      {view.result === 'saved' ? (
        <Note tone="ok">
          <p>
            <strong>{job.ssid} is saved on the robot.</strong> It joins it by itself when it is in
            range and no better network is available. Press Refresh to see it in the saved list.
          </p>
        </Note>
      ) : null}

      {view.result === 'expired' ? (
        <Note tone="bad">
          <p>
            <strong>The password handoff timed out.</strong> Nothing was saved. The robot password
            was not entered in time. Close this and start again.
          </p>
        </Note>
      ) : null}

      {!view.result && flag === 'lost' ? (
        <Note tone="warn">
          <p>
            <strong>Studio lost the connection to the robot.</strong> This is expected when the
            robot changes network{err ? ` (${err})` : ''}.
          </p>
          <p>
            Join this computer to <strong>{job.ssid}</strong>, then press Discover and Connect.
            Studio then shows the result. If the join failed, the robot returns to its previous
            network within about 1.5 minutes.
          </p>
        </Note>
      ) : null}

      {!view.result && flag === 'timeout' ? (
        <Note tone="warn">
          <p>
            <strong>No final answer yet.</strong> The robot may still be working. Reconnect to it
            later and Studio shows the result then.
          </p>
        </Note>
      ) : null}
    </div>
  );
}
