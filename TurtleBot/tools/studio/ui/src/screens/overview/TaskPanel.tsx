import type { LucideIcon } from 'lucide-react';
import { Undo2 } from 'lucide-react';
import { Code, FolderSync, ListOrdered, Map as MapIcon, Play, Radar } from 'lucide-react';
import { useAsyncAction } from '../../lib/useAsync';
import { dockAction } from '../../state/actions';
import { startNewProgram } from '../../state/codeActions';
import { navigate } from '../../state/router';
import { useStudio } from '../../state/store';
import { Button, Panel } from '../../components/ui';

interface Task {
  label: string;
  line: string;
  icon: LucideIcon;
  go: () => void;
}

/** The six things people come here to do. */
export const TASKS: Task[] = [
  {
    label: 'Drive the robot',
    line: 'Steer it with the keyboard or a joystick and watch the lidar map.',
    icon: Radar,
    go: () => navigate('/live'),
  },
  {
    label: 'Run a program',
    line: 'Pick a ready-made program and start it.',
    icon: Play,
    go: () => navigate('/programs'),
  },
  {
    label: 'Write your own program',
    line: 'Start from a template and edit it here.',
    icon: Code,
    go: () => startNewProgram(),
  },
  {
    label: 'Make a map',
    line: 'Drive around once and save a map of the place.',
    icon: MapIcon,
    go: () => navigate('/maps'),
  },
  {
    label: "Change the robot's menu",
    line: "Choose what shows on the robot's own screen.",
    icon: ListOrdered,
    go: () => navigate('/menu'),
  },
  {
    label: 'Copy a folder to the robot',
    line: 'Send a folder from this computer to the robot.',
    icon: FolderSync,
    go: () => navigate('/files'),
  },
];

export function TaskPanel() {
  const docked = useStudio((s) => s.status?.dock?.is_docked === true);
  const undock = useAsyncAction(() => dockAction('undock'));
  return (
    <Panel wide title="What do you want to do?">
      {docked ? (
        <div className="note note-warn task-docked" role="status">
          <span>The robot is on its dock. Undock it before you drive or run a moving program.</span>
          <Button
            size="sm"
            variant="primary"
            icon={<Undo2 size={14} aria-hidden="true" />}
            loading={undock.pending}
            onClick={() => void undock.run()}
          >
            Undock
          </Button>
        </div>
      ) : null}
      <div className="task-grid">
        {TASKS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.label} type="button" className="task" onClick={t.go}>
              <Icon size={24} aria-hidden="true" />
              <span className="task-text">
                <span className="task-label">{t.label}</span>
                <span className="task-line">{t.line}</span>
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
