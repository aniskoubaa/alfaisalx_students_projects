import { Lock } from 'lucide-react';
import { Badge, Panel } from '../../components/ui';
import type { MenuCheck } from '../../api';
import { buildPreview, displayLine } from './model';
import type { MenuDoc } from './model';

/**
 * A picture of the robot display. Uses the robot's own check when it describes this exact document,
 * and the page's own guess until then.
 */
export function MenuPreview({ doc, check }: { doc: MenuDoc; check: MenuCheck | null }) {
  const { lines, hidden } = buildPreview(doc, check);
  return (
    <Panel
      title="What the robot shows"
      actions={
        check ? (
          <Badge tone="ok">Checked by the robot</Badge>
        ) : (
          <Badge tone="neutral">Not checked yet</Badge>
        )
      }
    >
      <div data-testid="menu-preview">
        <ol className="menu-screen" aria-label="Robot display, top to bottom">
          {lines.map((l, i) => (
            <li
              key={l.id}
              className={l.builtin ? 'menu-screen-line is-builtin' : 'menu-screen-line is-own'}
              data-testid={`menu-line-${l.id}`}
            >
              <span className="menu-screen-text">{displayLine(l.label, i === 0)}</span>
              {l.builtin ? (
                <>
                  <Lock size={12} aria-hidden="true" className="menu-screen-lock" />
                  <span className="sr-only">built in, cannot be changed</span>
                </>
              ) : null}
            </li>
          ))}
        </ol>
        <p className="dim small menu-screen-note">
          The display fits 18 characters per line; the first is the cursor. The trip entry reads
          &quot;Back to the lab&quot; on the way back.
        </p>
        {hidden.length > 0 ? (
          <div className="menu-hidden" data-testid="menu-hidden">
            <h3 className="menu-sub">Hidden</h3>
            <ul className="menu-hidden-list">
              {hidden.map((h) => (
                <li key={h.id}>{h.label}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
