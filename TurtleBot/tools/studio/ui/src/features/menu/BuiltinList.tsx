import { Lock } from 'lucide-react';
import { Badge, Panel } from '../../components/ui';
import { BUILTINS, setHidden } from './model';
import type { MenuDoc } from './model';

/** The robot's own entries. Four are always there; four can be hidden. Nothing here can be renamed or moved. */
export function BuiltinList({
  doc,
  onChange,
  disabled = false,
}: {
  doc: MenuDoc;
  onChange: (doc: MenuDoc) => void;
  disabled?: boolean;
}) {
  return (
    <Panel title="The robot's own entries">
      <p className="dim small menu-lead">
        Their names and order are fixed. You can hide the ones that are not locked.
      </p>
      <ul className="menu-builtins">
        {BUILTINS.map((b) => {
          const shown = !doc.hide.includes(b.id);
          return (
            <li key={b.id} className="menu-builtin" data-testid={`menu-builtin-${b.id}`}>
              <span className="menu-builtin-name">{b.label}</span>
              {b.locked ? (
                <Badge tone="neutral" icon={<Lock size={14} aria-hidden="true" />}>
                  Locked
                </Badge>
              ) : null}
              {b.hideable ? (
                <label className="menu-switch">
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={`Show ${b.label} on the robot`}
                    checked={shown}
                    disabled={disabled}
                    onChange={(e) => onChange(setHidden(doc, b.id, !e.target.checked))}
                  />
                  <span>Show on the robot</span>
                </label>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
