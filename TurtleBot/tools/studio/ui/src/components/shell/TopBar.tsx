import * as DM from '@radix-ui/react-dropdown-menu';
import {
  Battery,
  BatteryCharging,
  BatteryLow,
  Bot,
  Check,
  Menu,
  Monitor,
  Moon,
  Sun,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { connView } from '../../lib/connView';
import { useStudio } from '../../state/store';
import { useUi } from '../../state/ui';
import type { ThemeChoice } from '../../state/ui';
import { IconButton, StatusPill } from '../ui';
import { EventsToggle, PaletteButton } from '../../screens/events/EventsToggle';
import { EStopButton } from './EStopButton';

export function ConnectionPill() {
  const conn = useStudio((s) => s.conn);
  const hello = useStudio((s) => s.hello);
  const sse = useStudio((s) => s.sse);
  const v = connView(conn, hello, sse);
  return (
    <StatusPill tone={v.tone} busy={v.busy} role="status" aria-live="polite" className="conn-pill">
      <span className="conn-label">{v.label}</span>
      {v.host ? <span className="conn-host mono">{v.host}</span> : null}
      {v.route ? <span className="conn-route">{v.route}</span> : null}
    </StatusPill>
  );
}

export function Vitals() {
  const status = useStudio((s) => s.status);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const b = status?.battery;
  const pct = connected && b?.percent != null ? Math.round(b.percent) : null;
  const charging = b?.charging === true;
  const low = pct !== null && pct < 20;
  const dbm = connected ? (status?.net?.signal_dbm ?? null) : null;
  const BatteryIcon = charging ? BatteryCharging : low ? BatteryLow : Battery;
  return (
    <div className="vitals" aria-label="Robot vitals">
      <span
        className={'vital' + (low ? ' vital-warn' : '')}
        title={charging ? 'Battery, charging' : low ? 'Battery is low' : 'Battery'}
      >
        <BatteryIcon size={18} aria-hidden="true" />
        <span className="sr-only">Battery</span>
        <span className="num">{pct === null ? '–' : pct + '%'}</span>
        {low ? <span className="vital-note">Low</span> : null}
      </span>
      <span className="vital" title="Robot Wi-Fi signal">
        {dbm === null ? (
          <WifiOff size={18} aria-hidden="true" />
        ) : (
          <Wifi size={18} aria-hidden="true" />
        )}
        <span className="sr-only">Wi-Fi signal</span>
        <span className="num">{dbm === null ? '–' : dbm + ' dBm'}</span>
      </span>
    </div>
  );
}

const THEMES: Array<{ id: ThemeChoice; label: string; icon: typeof Sun }> = [
  { id: 'system', label: 'Match this computer', icon: Monitor },
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
];

export function ThemeMenu() {
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const Current = THEMES.find((t) => t.id === theme)?.icon ?? Monitor;
  return (
    <DM.Root>
      <DM.Trigger asChild>
        <button type="button" className="btn btn-ghost btn-icon" aria-label="Colour theme">
          <Current size={18} aria-hidden="true" />
        </button>
      </DM.Trigger>
      <DM.Portal>
        <DM.Content className="menu" align="end" sideOffset={6}>
          <DM.RadioGroup value={theme} onValueChange={(v) => setTheme(v as ThemeChoice)}>
            {THEMES.map(({ id, label, icon: Icon }) => (
              <DM.RadioItem key={id} value={id} className="menu-item">
                <Icon size={16} aria-hidden="true" />
                <span>{label}</span>
                <DM.ItemIndicator className="menu-check">
                  <Check size={14} aria-hidden="true" />
                </DM.ItemIndicator>
              </DM.RadioItem>
            ))}
          </DM.RadioGroup>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}

export function TopBar() {
  const setNavOpen = useUi((s) => s.setNavOpen);
  const navOpen = useUi((s) => s.navOpen);
  return (
    <header className="topbar">
      <IconButton
        label={navOpen ? 'Close menu' : 'Open menu'}
        icon={<Menu size={20} aria-hidden="true" />}
        className="nav-toggle"
        onClick={() => setNavOpen(!navOpen)}
        aria-expanded={navOpen}
        aria-controls="sidebar"
      />
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Bot size={18} />
        </span>
        <span className="brand-name">
          TurtleBot <span className="brand-sub">Studio</span>
        </span>
      </div>
      <ConnectionPill />
      <div className="topbar-spacer" />
      <Vitals />
      <PaletteButton />
      <EventsToggle />
      <ThemeMenu />
      <EStopButton />
    </header>
  );
}
