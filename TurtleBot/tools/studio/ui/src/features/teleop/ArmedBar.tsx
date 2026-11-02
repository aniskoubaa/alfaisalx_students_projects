import { ShieldAlert } from 'lucide-react';
import { teleopArm } from '../../api/live';
import { Button } from '../../components/ui';
import { useStudio } from '../../state/store';
import { disarm } from './driver';
import { useDrive } from './driveStore';

/** Amber bar across the top of the whole app while manual driving is armed. */
export function ArmedBar() {
  const phase = useDrive((s) => s.phase);
  const studioSaysArmed = useStudio((s) => s.teleopArmed);
  if (phase !== 'armed' && !studioSaysArmed) return null;
  return (
    <div className="armed-bar" role="status">
      <ShieldAlert size={18} aria-hidden="true" />
      <p className="armed-text">
        <strong>Driving armed.</strong> Release keys to stop. Esc = E-STOP
      </p>
      <Button
        size="sm"
        onClick={() => {
          if (phase === 'armed') disarm('You switched driving off.');
          else {
            void teleopArm(false, 'disarmed from the bar');
            useStudio.setState({ teleopArmed: false });
          }
        }}
      >
        Disarm
      </Button>
    </div>
  );
}
