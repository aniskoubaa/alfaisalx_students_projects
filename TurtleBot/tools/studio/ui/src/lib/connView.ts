import type { ConnEvent, HelloEvent, SseStatus } from '../api';
import type { Tone } from '../components/ui';

const ROUTE_WORDS: Record<string, string> = {
  cable: 'Ethernet cable',
  wifi: 'Wi-Fi',
  hotspot: 'robot hotspot',
  custom: 'typed address',
};

/** How Studio reaches the robot, in words. The internal names (cable, wifi, hotspot, custom) never reach the screen. */
export function routeWords(via: string | null | undefined): string | null {
  if (!via) return null;
  return ROUTE_WORDS[via] ?? via;
}

export interface ConnView {
  tone: Tone;
  busy: boolean;
  /** What the state is, in words. */
  label: string;
  /** The robot name or address, when known. */
  host: string | null;
  /** How Studio reaches the robot: cable, hotspot, wifi. */
  route: string | null;
}

/** Everything the connection pill and the Overview heading need to say about the link. */
export function connView(conn: ConnEvent, hello: HelloEvent | null, sse: SseStatus): ConnView {
  const host = (conn.state === 'connected' && hello?.hostname) || conn.host || null;
  const route = routeWords(conn.via);
  if (sse.state === 'down') {
    return { tone: 'bad', busy: false, label: 'Studio not responding', host: null, route: null };
  }
  switch (conn.state) {
    case 'connected':
      return { tone: 'ok', busy: false, label: 'Connected', host, route };
    case 'connecting':
      return { tone: 'warn', busy: true, label: 'Connecting', host, route };
    case 'reconnecting':
      return { tone: 'warn', busy: true, label: 'Reconnecting', host, route };
    case 'discovering':
      return {
        tone: 'warn',
        busy: true,
        label: 'Searching for the robot',
        host: null,
        route: null,
      };
    case 'error':
      return { tone: 'bad', busy: false, label: 'Connection problem', host, route };
    default:
      return { tone: 'neutral', busy: false, label: 'Not connected', host: null, route: null };
  }
}

export interface ConnHint {
  kind: 'key_not_set_up' | 'host_key' | 'no_ssh';
  title: string;
  text: string;
}

/** Connection errors the setup steps can fix. */
export function connHint(c: ConnEvent): ConnHint | null {
  const e = c.error ?? '';
  const kind =
    c.kind ??
    (/key not set up|permission denied/i.test(e)
      ? 'key_not_set_up'
      : /host key|identification has changed|not the trusted/i.test(e)
        ? 'host_key'
        : /no ssh|ssh.*not found|cannot find.*ssh/i.test(e)
          ? 'no_ssh'
          : '');
  if (kind === 'key_not_set_up') {
    return {
      kind,
      title: 'Key login is not set up',
      text: "The robot did not accept this computer's key yet. Set up key login: a terminal window opens and you type the robot password there, never in this app.",
    };
  }
  if (kind === 'host_key') {
    return {
      kind,
      title: 'The robot is not trusted yet',
      text: "The robot's identity key is not one you trusted, or it changed. The setup wizard shows its fingerprint so you can compare and trust it.",
    };
  }
  if (kind === 'no_ssh') {
    return {
      kind,
      title: 'ssh is missing',
      text: 'Studio needs the ssh program on this computer. The setup wizard shows how to install it.',
    };
  }
  return null;
}
