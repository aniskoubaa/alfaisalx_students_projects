import { X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { fmtTime } from '../../lib/format';
import { latestId, unreadCount } from '../../screens/events/alerts';
import { AlertList, SeverityFilter } from '../../screens/events/AlertList';
import { useAlertsUi } from '../../screens/events/state';
import { useStudio } from '../../state/store';
import { useUi } from '../../state/ui';
import { Badge, Button, IconButton } from '../ui';

const LEVEL_TONE = { info: 'neutral', warn: 'warn', error: 'bad' } as const;

type Tab = 'alerts' | 'activity';

/** Slide-in panel: alerts raised by Studio (with severity), and the activity log of this window. */
export function EventsDrawer() {
  const open = useUi((s) => s.eventsOpen);
  const toggle = useUi((s) => s.toggleEvents);
  const logs = useStudio((s) => s.logs);
  const alerts = useStudio((s) => s.alerts);
  const seenId = useAlertsUi((s) => s.seenId);
  const markSeen = useAlertsUi((s) => s.markSeen);
  const [tab, setTab] = useState<Tab>('alerts');
  const listRef = useRef<HTMLOListElement>(null);
  const unread = unreadCount(alerts, seenId);

  useEffect(() => {
    const el = listRef.current;
    if (open && tab === 'activity' && el) el.scrollTop = el.scrollHeight;
  }, [open, tab, logs.length]);

  // Alerts count as read when the person closes the list (or switches away) after seeing them.
  useEffect(() => {
    if (!open || tab !== 'alerts') return;
    return () => markSeen(latestId(useStudio.getState().alerts));
  }, [open, tab, markSeen]);

  if (!open) return null;
  return (
    <aside className="drawer" aria-label="Events">
      <header className="drawer-head">
        <h2 className="drawer-title">Events</h2>
        <IconButton
          label="Hide events"
          icon={<X size={16} aria-hidden="true" />}
          size="sm"
          onClick={toggle}
        />
      </header>
      <div className="seg drawer-tabs" role="radiogroup" aria-label="Events view">
        <button
          type="button"
          role="radio"
          aria-checked={tab === 'alerts'}
          className={'seg-btn' + (tab === 'alerts' ? ' is-on' : '')}
          onClick={() => setTab('alerts')}
        >
          Alerts{unread ? ` (${unread} new)` : ''}
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={tab === 'activity'}
          className={'seg-btn' + (tab === 'activity' ? ' is-on' : '')}
          onClick={() => setTab('activity')}
        >
          Activity
        </button>
      </div>
      {tab === 'alerts' ? (
        <div className="drawer-scroll">
          <div className="drawer-tools">
            <SeverityFilter />
            <Button size="sm" disabled={unread === 0} onClick={() => markSeen(latestId(alerts))}>
              Mark all as read
            </Button>
          </div>
          <AlertList />
        </div>
      ) : logs.length === 0 ? (
        <p className="drawer-empty">
          Nothing yet. Messages from Studio and from your actions appear here.
        </p>
      ) : (
        <ol className="event-list" ref={listRef} aria-label="Recent activity">
          {logs.map((l) => (
            <li key={l.id} className={`event event-${l.level}`}>
              <time className="event-time num">{fmtTime(new Date(l.at))}</time>
              <Badge tone={LEVEL_TONE[l.level]} icon={false}>
                {l.level}
              </Badge>
              <span className="event-text">{l.text}</span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
