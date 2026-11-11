import type {
  AlertsAnswer,
  ApiFailure,
  ApiResult,
  BridgeAnswers,
  BridgeArgs,
  BridgeCmd,
  Catalog,
  CatalogTemplate,
  DiscoverAnswer,
  EstopAnswer,
  HistoryAnswer,
  LocalFilesAnswer,
  OpenVscodeAnswer,
  Settings,
  SettingsAnswer,
  SyncAnswer,
  SyncRequest,
  TeleopLimits,
  TrustedKey,
  UpdateStatusAnswer,
} from './types';

/* ---------- token ---------- */

export const TOKEN_KEY = 'studio_token';

interface TokenEnv {
  search: string;
  pathname: string;
  hash: string;
  storage: Pick<Storage, 'getItem' | 'setItem'> | null;
  replaceUrl: (url: string) => void;
}

/**
 * The token arrives as ?token= on the first load. Keep it in sessionStorage for this tab and
 * remove it from the address bar. Storage can be blocked, so every access is guarded.
 */
export function resolveToken(env: TokenEnv): string {
  const qs = new URLSearchParams(env.search);
  let token = qs.get('token') ?? '';
  try {
    if (token) env.storage?.setItem(TOKEN_KEY, token);
    else token = env.storage?.getItem(TOKEN_KEY) ?? '';
  } catch {
    /* storage blocked: keep the token in memory only */
  }
  if (qs.has('token')) {
    qs.delete('token');
    const rest = qs.toString();
    env.replaceUrl(env.pathname + (rest ? '?' + rest : '') + env.hash);
  }
  return token;
}

export function browserToken(): string {
  let storage: Storage | null = null;
  try {
    storage = window.sessionStorage;
  } catch {
    storage = null;
  }
  return resolveToken({
    search: window.location.search,
    pathname: window.location.pathname,
    hash: window.location.hash,
    storage,
    replaceUrl: (url) => window.history.replaceState(null, '', url),
  });
}

/* ---------- JSON boundary ---------- */

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function fail(error: string, extra: Partial<ApiFailure> = {}): ApiFailure {
  return { ok: false, error, ...extra };
}

/** Turn one parsed JSON body into a typed result. Exported for tests. */
export function toResult<T>(status: number, httpOk: boolean, body: unknown): ApiResult<T> {
  if (!isRecord(body)) return fail('HTTP ' + status, { status });
  if (body.ok === false || !httpOk) {
    const extra: Partial<ApiFailure> = { status };
    if (typeof body.kind === 'string') extra.kind = body.kind;
    if (body.needs_confirm === true) extra.needs_confirm = true;
    if (body.needs_settings === true) extra.needs_settings = true;
    if (body.exists === true) extra.exists = true;
    if (typeof body.preview === 'string') extra.preview = body.preview;
    const msg = typeof body.error === 'string' && body.error ? body.error : 'HTTP ' + status;
    return fail(status === 403 && msg === 'bad token' ? BAD_TOKEN : msg, extra);
  }
  return { ...(body as object), ok: true } as ApiResult<T>;
}

export const BAD_TOKEN =
  'Studio did not accept this window. Close it and open Studio again from its own shortcut.';

/* ---------- client ---------- */

export interface CallOptions {
  /** Give up after this many milliseconds. */
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface ClientOptions {
  token: string;
  fetchImpl?: typeof fetch;
  /** Default timeout for every call. */
  timeoutMs?: number;
}

const SLOW_PATHS: Record<string, number> = {
  '/api/discover': 60_000,
  '/api/deep_discover': 120_000,
  '/api/sync': 180_000,
  '/api/check_updates': 30_000,
  '/api/connect': 90_000,
};

type NoArgs<K extends BridgeCmd> = BridgeArgs[K] extends Record<string, never> ? true : false;
type BridgeRest<K extends BridgeCmd> =
  NoArgs<K> extends true
    ? [args?: BridgeArgs[K], opts?: CallOptions]
    : [args: BridgeArgs[K], opts?: CallOptions];

export class StudioClient {
  private token: string;
  private readonly fetchImpl: typeof fetch;
  private readonly defaultTimeout: number;

  constructor(opts: ClientOptions) {
    this.token = opts.token;
    this.fetchImpl = opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
    this.defaultTimeout = opts.timeoutMs ?? 30_000;
  }

  /** Address of the live event stream, including the token (EventSource cannot send headers). */
  eventsUrl(): string {
    return '/api/events?token=' + encodeURIComponent(this.token);
  }

  /** A URL for a page outside this app, for example the classic interface. */
  pageUrl(path: string): string {
    return path + (this.token ? '?token=' + encodeURIComponent(this.token) : '');
  }

  private async send(
    method: 'GET' | 'POST',
    path: string,
    body: unknown,
    opts: CallOptions,
  ): Promise<{ status: number; ok: boolean; text: string } | ApiFailure> {
    const timeoutMs = opts.timeoutMs ?? SLOW_PATHS[path] ?? this.defaultTimeout;
    const ctl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ctl.abort();
    }, timeoutMs);
    const onAbort = () => ctl.abort();
    opts.signal?.addEventListener('abort', onAbort);
    try {
      const headers: Record<string, string> = { 'X-Studio-Token': this.token };
      const init: RequestInit = { method, headers, signal: ctl.signal };
      if (method === 'POST') {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body ?? {});
      }
      const res = await this.fetchImpl(path, init);
      const text = await res.text();
      return { status: res.status, ok: res.ok, text };
    } catch (e) {
      if (timedOut) {
        return fail(
          `Studio did not answer within ${Math.round(timeoutMs / 1000)} s. Check that it is still running.`,
          { network: true },
        );
      }
      if (opts.signal?.aborted) return fail('Cancelled.', { network: true });
      const why = e instanceof Error ? e.message : String(e);
      return fail('Cannot reach Studio (' + why + '). Check that it is still running.', {
        network: true,
      });
    } finally {
      clearTimeout(timer);
      opts.signal?.removeEventListener('abort', onAbort);
    }
  }

  async request<T = Record<string, never>>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown,
    opts: CallOptions = {},
  ): Promise<ApiResult<T>> {
    const r = await this.send(method, path, body, opts);
    if ('error' in r) return r;
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(r.text);
    } catch {
      parsed = null;
    }
    return toResult<T>(r.status, r.ok, parsed);
  }

  get<T = Record<string, never>>(path: string, opts?: CallOptions) {
    return this.request<T>('GET', path, undefined, opts);
  }

  post<T = Record<string, never>>(path: string, body?: unknown, opts?: CallOptions) {
    return this.request<T>('POST', path, body ?? {}, opts);
  }

  /** Plain-text GET, used for template files. */
  async getText(path: string, opts: CallOptions = {}): Promise<ApiResult<{ text: string }>> {
    const r = await this.send('GET', path, undefined, opts);
    if ('error' in r) return r;
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try {
        const j: unknown = JSON.parse(r.text);
        if (isRecord(j) && typeof j.error === 'string') msg = j.error;
      } catch {
        if (r.text) msg = r.text.slice(0, 120);
      }
      return fail(msg, { status: r.status });
    }
    return { ok: true, text: r.text };
  }

  /**
   * Binary GET with the token header (images, downloads). Returns the body and the response
   * headers it was asked for, or a failure with the server's words.
   */
  async getBlob(
    path: string,
    opts: CallOptions = {},
  ): Promise<ApiResult<{ blob: Blob; headers: Record<string, string> }>> {
    const timeoutMs = opts.timeoutMs ?? 60_000;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const res = await this.fetchImpl(path, {
        method: 'GET',
        headers: { 'X-Studio-Token': this.token },
        signal: opts.signal ?? ctl.signal,
      });
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try {
          const j: unknown = JSON.parse(await res.text());
          if (isRecord(j) && typeof j.error === 'string' && j.error) msg = j.error;
        } catch {
          /* not JSON: keep the status */
        }
        return fail(res.status === 403 && msg === 'bad token' ? BAD_TOKEN : msg, {
          status: res.status,
        });
      }
      const blob = await res.blob();
      const headers: Record<string, string> = {};
      res.headers.forEach((v, k) => {
        headers[k.toLowerCase()] = v;
      });
      return { ok: true, blob, headers };
    } catch (e) {
      const why = e instanceof Error ? e.message : String(e);
      return fail('Cannot reach Studio (' + why + '). Check that it is still running.', {
        network: true,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  /* ---- robot bridge ---- */

  bridge<K extends BridgeCmd>(
    cmd: K,
    ...rest: BridgeRest<K>
  ): Promise<ApiResult<BridgeAnswers[K]>> {
    const [args, opts] = rest;
    const slow = cmd === 'health' ? { timeoutMs: 60_000 } : {};
    return this.post<BridgeAnswers[K]>(
      '/api/bridge',
      { cmd, ...(args ?? {}) },
      { ...slow, ...opts },
    );
  }

  /* ---- Studio endpoints ---- */

  estop() {
    return this.post<EstopAnswer>('/api/estop', {}, { timeoutMs: 20_000 });
  }
  discover(host?: string) {
    return this.post<DiscoverAnswer>('/api/discover', host ? { host } : {});
  }
  deepDiscover() {
    return this.post<DiscoverAnswer>('/api/deep_discover', {});
  }
  connect(host?: string) {
    return this.post('/api/connect', host ? { host } : {});
  }
  disconnect() {
    return this.post('/api/disconnect', {});
  }
  reconnectCancel() {
    return this.post<{ was_reconnecting?: boolean }>('/api/reconnect_cancel', {});
  }
  quit() {
    return this.post('/api/quit', {});
  }
  setupKey(host?: string) {
    return this.post<{ note?: string }>('/api/setup_key', host ? { host } : {});
  }

  async settings(): Promise<ApiResult<SettingsAnswer>> {
    return normalizeSettings(await this.get<Record<string, unknown>>('/api/settings'));
  }
  async saveSettings(patch: Settings): Promise<ApiResult<SettingsAnswer>> {
    return normalizeSettings(await this.post<Record<string, unknown>>('/api/settings', patch));
  }

  async catalog(): Promise<ApiResult<Catalog>> {
    const r = await this.get<Record<string, unknown>>('/api/catalog');
    if (!r.ok) return r;
    const programs = isRecord(r.programs) ? (r.programs as Catalog['programs']) : {};
    const templates = Array.isArray(r.templates) ? (r.templates as CatalogTemplate[]) : [];
    return {
      ok: true,
      programs,
      templates,
      version: typeof r.version === 'number' ? r.version : undefined,
    };
  }
  template(name: string) {
    return this.getText('/api/templates/' + encodeURIComponent(name));
  }

  localFiles(dir: string) {
    return this.post<LocalFilesAnswer>('/api/local_files', { dir });
  }
  sync(req: SyncRequest) {
    return this.post<SyncAnswer>('/api/sync', req);
  }
  openVscode(confirmWriteSshConfig = false) {
    return this.post<OpenVscodeAnswer>(
      '/api/open_vscode',
      confirmWriteSshConfig ? { confirm_write_ssh_config: true } : {},
    );
  }
  updateStatus() {
    return this.get<UpdateStatusAnswer>('/api/update_status');
  }
  checkUpdates() {
    return this.post<UpdateStatusAnswer>('/api/check_updates', { force: true });
  }

  /* ---- 2.0 ---- */

  history(minutes = 15) {
    return this.get<HistoryAnswer>('/api/history?minutes=' + encodeURIComponent(String(minutes)));
  }
  alerts(since?: number) {
    return this.get<AlertsAnswer>('/api/alerts' + (since != null ? '?since=' + since : ''));
  }
  setTeleopLimits(limits: TeleopLimits) {
    return this.post('/api/teleop_limits', limits);
  }
}

function normalizeSettings(r: ApiResult<Record<string, unknown>>): ApiResult<SettingsAnswer> {
  if (!r.ok) return r;
  const { ok: _ok, defaults, lab_host_key, trusted, settings, ...flat } = r;
  void _ok;
  const out: SettingsAnswer = {
    settings: (isRecord(settings) ? settings : flat) as Settings,
  };
  if (isRecord(defaults)) out.defaults = defaults as Record<string, string>;
  if (typeof lab_host_key === 'string' || lab_host_key === null) out.lab_host_key = lab_host_key;
  if (Array.isArray(trusted)) out.trusted = trusted as TrustedKey[];
  return { ok: true, ...out };
}
