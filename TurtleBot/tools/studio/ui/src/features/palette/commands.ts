/**
 * The command list for the palette and the pure search over it.
 * Safe actions only: nothing here moves the robot (no drive, dock, undock or program run).
 */
import { routeWords } from '../../lib/connView';
import type { StudioState } from '../../state/store';

export type CommandGroup = 'Go to' | 'Actions';

export interface Command {
  id: string;
  label: string;
  group: CommandGroup;
  /** Extra words that should find this command. */
  keywords?: string;
  /** Why the command cannot run right now, or null when it can. */
  disabled: string | null;
  run: () => void | Promise<void>;
}

/** Words of the query must each be found at the start of a word of the label or in the keywords. */
export function scoreCommand(c: Pick<Command, 'label' | 'keywords'>, query: string): number {
  const q = query.trim().toLowerCase();
  if (q === '') return 1;
  const label = c.label.toLowerCase();
  const words = (label + ' ' + (c.keywords ?? '').toLowerCase())
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  let score = 0;
  for (const part of q.split(/\s+/)) {
    if (label.startsWith(part)) score += 6;
    else if (words.some((w) => w.startsWith(part))) score += 4;
    else if (label.includes(part)) score += 2;
    else return 0;
  }
  return score;
}

/** Commands that match, best first; ties keep the original order. */
export function filterCommands<T extends Pick<Command, 'label' | 'keywords'>>(
  commands: readonly T[],
  query: string,
): T[] {
  return commands
    .map((c, i) => ({ c, i, s: scoreCommand(c, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .map((x) => x.c);
}

/** Plain-text summary for support: versions and state, never the token or any password. */
export function buildDiagnostics(s: StudioState, now: Date = new Date()): string {
  const lines: string[] = [];
  const add = (k: string, v: unknown) =>
    lines.push(`${k}: ${v === null || v === undefined || v === '' ? 'unknown' : String(v)}`);
  lines.push('TurtleBot Studio diagnostics');
  add('Time', now.toISOString());
  add('Studio version', s.hello?.version ?? s.update?.current);
  add('Browser', typeof navigator === 'undefined' ? null : navigator.userAgent);
  add('Event stream', s.sse.state);
  add(
    'Robot connection',
    s.conn.state + (s.conn.host ? ` (${s.conn.host}${s.conn.via ? ', ' + (routeWords(s.conn.via) ?? '') : ''})` : ''),
  );
  if (s.conn.error) add('Connection error', s.conn.error);
  add('Robot hostname', s.hello?.hostname);
  add(
    'ROS',
    s.hello?.ros
      ? `${s.hello.ros_distro ?? ''} ${s.hello.rmw ?? ''}`.trim()
      : s.hello
        ? 'not available'
        : null,
  );
  add('Demo robot', s.hello?.fake ? 'yes' : 'no');
  const st = s.status;
  add('Battery', st?.battery?.percent != null ? st.battery.percent + ' %' : null);
  add('Docked', st?.dock?.is_docked);
  add('E-stop', st?.estop?.on);
  add('Odometry rate', st?.odom?.rate_hz != null ? st.odom.rate_hz + ' Hz' : null);
  add('Lidar rate', st?.scan?.rate_hz != null ? st.scan.rate_hz + ' Hz' : null);
  add(
    'Wi-Fi',
    st?.net?.signal_dbm != null ? `${st.net.ssid ?? ''} ${st.net.signal_dbm} dBm`.trim() : null,
  );
  add('CPU temperature', st?.system?.temp_c != null ? st.system.temp_c + ' C' : null);
  add('Hazards', st?.hazards?.length ? st.hazards.join(', ') : 'none');
  add('Driving armed', s.teleopArmed);
  add('Programs running', Object.values(s.runs).filter((r) => r.alive).length);
  const recent = s.alerts.slice(-5);
  if (recent.length) {
    lines.push('Recent alerts:');
    for (const a of recent) lines.push(`  [${a.severity}] ${a.code}: ${a.text}`);
  }
  return lines.join('\n') + '\n';
}
