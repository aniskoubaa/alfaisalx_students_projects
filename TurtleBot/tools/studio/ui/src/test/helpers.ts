import { StudioClient, setApi } from '../api';
import { useCode } from '../state/code';
import { useDialogs, useToasts } from '../state/feedback';
import { useStudio } from '../state/store';

export interface Call {
  method: string;
  path: string;
  body: Record<string, unknown>;
  headers: Record<string, string>;
}

type Handler = (call: Call) => unknown | Promise<unknown>;

/** A client whose fetch is a function: records every call and answers with JSON. */
export function mockClient(handler: Handler): { client: StudioClient; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const call: Call = {
      method: init?.method ?? 'GET',
      path: String(url),
      body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {},
      headers: (init?.headers ?? {}) as Record<string, string>,
    };
    calls.push(call);
    const out = await handler(call);
    if (typeof out === 'string') return new Response(out, { status: 200 });
    return new Response(JSON.stringify(out ?? { ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;
  return { client: new StudioClient({ token: 'tok', fetchImpl }), calls };
}

/** Install a mock client as the app's shared client. */
export function installApi(handler: Handler) {
  const m = mockClient(handler);
  setApi(m.client);
  return m;
}

/** Put every store back to its start state. */
export function resetStores(): void {
  useStudio.getState().reset();
  useCode.setState({
    name: null,
    orig: '',
    text: '',
    sha1: null,
    status: '',
    loading: false,
    saving: false,
  });
  useDialogs.setState({ stack: [] });
  useToasts.setState({ items: [] });
}

export function connectedStatus(): void {
  const s = useStudio.getState();
  s.dispatch({ ev: 'conn', state: 'connected', host: 'turtlebot4', via: 'cable' });
  s.dispatch({
    ev: 'status',
    battery: { percent: 76 },
    dock: { is_docked: false },
    estop: { on: false },
  });
}
