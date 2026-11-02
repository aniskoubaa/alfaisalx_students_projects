import { Power } from 'lucide-react';
import { EmptyState } from '../ui';

/** Shown after Studio quits. Nothing here talks to Studio any more. */
export function StoppedScreen() {
  return (
    <main className="stopped" aria-label="Studio has stopped">
      <EmptyState icon={<Power size={32} />} title="Studio has stopped">
        The connection to the robot is closed. You can close this window. To use Studio again, start
        it from its shortcut.
      </EmptyState>
    </main>
  );
}
