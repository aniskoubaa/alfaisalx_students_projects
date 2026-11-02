import { Gamepad2, OctagonAlert, ShieldAlert } from 'lucide-react';
import { useEffect } from 'react';
import { Badge, Button, Panel } from '../../components/ui';
import { isDocked } from '../../state/selectors';
import { useStudio } from '../../state/store';
import { MIN_LIMITS, fmtVelocity } from './controller';
import { changeLimits, disarm, loadLimits, requestArm } from './driver';
import { useDrive } from './driveStore';
import { Joystick } from './Joystick';

function Speeds() {
  const limits = useDrive((s) => s.limits);
  const caps = useDrive((s) => s.caps);
  return (
    <div className="speeds">
      <label className="speed">
        <span className="speed-head">
          <span>Top speed</span>
          <span className="num speed-val">{limits.linear.toFixed(2)} m/s</span>
        </span>
        <input
          type="range"
          min={MIN_LIMITS.linear}
          max={caps.linear}
          step={0.01}
          value={limits.linear}
          onChange={(e) =>
            changeLimits({ linear: Number(e.target.value), angular: limits.angular })
          }
          aria-valuetext={`${limits.linear.toFixed(2)} metres per second`}
        />
        <span className="speed-range dim">
          {MIN_LIMITS.linear.toFixed(2)} to {caps.linear.toFixed(2)} m/s
        </span>
      </label>
      <label className="speed">
        <span className="speed-head">
          <span>Turn rate</span>
          <span className="num speed-val">{limits.angular.toFixed(2)} rad/s</span>
        </span>
        <input
          type="range"
          min={MIN_LIMITS.angular}
          max={caps.angular}
          step={0.05}
          value={limits.angular}
          onChange={(e) => changeLimits({ linear: limits.linear, angular: Number(e.target.value) })}
          aria-valuetext={`${limits.angular.toFixed(2)} radians per second`}
        />
        <span className="speed-range dim">
          {MIN_LIMITS.angular.toFixed(2)} to {caps.angular.toFixed(2)} rad/s
        </span>
      </label>
    </div>
  );
}

function Echo() {
  const echo = useDrive((s) => s.echo);
  const moving = useDrive((s) => s.moving);
  return (
    <div className="echo" aria-live="off">
      <span className="dim">Robot is told</span>
      <span className="num echo-val">
        {echo ? fmtVelocity(echo.vx, echo.wz) : 'No command sent yet'}
      </span>
      <Badge tone={moving ? 'warn' : 'neutral'} icon={false}>
        {moving ? 'Moving' : 'Stopped'}
      </Badge>
    </div>
  );
}

/** Arm, drive, disarm. The only place on the Live screen that can move the robot. */
export function DrivePanel() {
  const phase = useDrive((s) => s.phase);
  const reason = useDrive((s) => s.reason);
  const tone = useDrive((s) => s.reasonTone);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const docked = useStudio(isDocked);
  const armed = phase === 'armed';

  useEffect(() => {
    void loadLimits();
  }, []);

  return (
    <Panel
      className={'drive' + (armed ? ' drive-armed' : '')}
      title="Drive"
      actions={
        armed ? (
          <Badge tone="warn" icon={<ShieldAlert size={14} aria-hidden="true" />}>
            Armed
          </Badge>
        ) : (
          <Badge tone="neutral">Off</Badge>
        )
      }
    >
      <div className="stack">
        {armed ? (
          <>
            <div className="stick-wrap">
              <Joystick enabled />
            </div>
            <p className="drive-keys small">
              Hold <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> or the arrow keys. Release to
              stop. <kbd>Esc</kbd> or <kbd>Space</kbd> is the E-STOP.
            </p>
            <Echo />
            <Speeds />
            <Button variant="secondary" onClick={() => disarm('You switched driving off.')}>
              Disarm driving
            </Button>
          </>
        ) : (
          <>
            <div className="stick-wrap">
              <Joystick enabled={false} />
            </div>
            <p className="small dim">
              Driving is off. Arm it to move the robot with the keys or the stick. It switches off
              by itself when you leave this screen, the window loses focus, or the link drops.
            </p>
            {reason ? (
              <div
                className={'note ' + (tone === 'error' ? 'note-bad' : 'note-warn')}
                role={tone === 'error' ? 'alert' : 'status'}
              >
                <OctagonAlert size={16} aria-hidden="true" /> <span>{reason}</span>
              </div>
            ) : null}
            {docked === true && connected ? (
              <p className="small dim">The robot is on its dock. Undock it first (Overview).</p>
            ) : null}
            <Speeds />
            <Button
              variant="primary"
              icon={<Gamepad2 size={16} aria-hidden="true" />}
              loading={phase === 'arming'}
              disabled={!connected}
              onClick={() => void requestArm()}
            >
              Arm driving
            </Button>
            {!connected ? <p className="small dim">Connect to the robot first.</p> : null}
          </>
        )}
      </div>
    </Panel>
  );
}
