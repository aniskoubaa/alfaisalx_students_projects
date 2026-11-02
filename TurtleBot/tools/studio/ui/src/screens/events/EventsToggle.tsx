import { Command, PanelRight } from 'lucide-react';
import { IconButton } from '../../components/ui';
import { usePalette } from '../../features/palette/paletteCommands';
import { useStudio } from '../../state/store';
import { useUi } from '../../state/ui';
import { unreadCount } from './alerts';
import { useAlertsUi } from './state';

/** Top-bar button that opens the events drawer, with the number of unread warnings. */
export function EventsToggle() {
  const open = useUi((s) => s.eventsOpen);
  const toggle = useUi((s) => s.toggleEvents);
  const alerts = useStudio((s) => s.alerts);
  const seenId = useAlertsUi((s) => s.seenId);
  const unread = unreadCount(alerts, seenId);
  const base = open ? 'Hide events' : 'Show events';
  return (
    <span className="events-toggle badge-wrap">
      <IconButton
        label={unread ? `${base}. ${unread} unread warning${unread > 1 ? 's' : ''}` : base}
        icon={<PanelRight size={18} aria-hidden="true" />}
        onClick={toggle}
        aria-pressed={open}
      />
      {unread > 0 ? (
        <span className="count-badge num" aria-hidden="true">
          {unread > 99 ? '99+' : unread}
        </span>
      ) : null}
    </span>
  );
}

/** Top-bar button for the command palette (Ctrl+K). */
export function PaletteButton() {
  const setOpen = usePalette((s) => s.setOpen);
  return (
    <span className="palette-btn">
      <IconButton
        label="Command palette (Ctrl+K)"
        icon={<Command size={18} aria-hidden="true" />}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      />
    </span>
  );
}
