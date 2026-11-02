import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockClient } from '../test/helpers';
import { BAD_TOKEN, StudioClient, TOKEN_KEY, resolveToken, toResult } from './client';

describe('resolveToken', () => {
  const base = { pathname: '/v2/', hash: '#/code' };

  it('takes the token from the address, stores it and cleans the address', () => {
    const store: Record<string, string> = {};
    const replaced: string[] = [];
    const token = resolveToken({
      ...base,
      search: '?token=abc&tab=x',
      storage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => void (store[k] = v) },
      replaceUrl: (u) => replaced.push(u),
    });
    expect(token).toBe('abc');
    expect(store[TOKEN_KEY]).toBe('abc');
    expect(replaced).toEqual(['/v2/?tab=x#/code']);
  });

  it('falls back to the stored token on a reload', () => {
    const token = resolveToken({
      ...base,
      search: '',
      storage: { getItem: () => 'old', setItem: () => {} },
      replaceUrl: () => {
        throw new Error('should not rewrite the address');
      },
    });
    expect(token).toBe('old');
  });

  it('works when storage is blocked', () => {
    const blocked = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    };
    expect(
      resolveToken({ ...base, search: '?token=t1', storage: blocked, replaceUrl: () => {} }),
    ).toBe('t1');
    expect(resolveToken({ ...base, search: '', storage: blocked, replaceUrl: () => {} })).toBe('');
  });
});

describe('toResult', () => {
  it('passes a good answer through with ok true', () => {
    expect(toResult(200, true, { ok: true, files: [1] })).toEqual({ ok: true, files: [1] });
    expect(toResult(200, true, { files: [] })).toMatchObject({ ok: true });
  });
  it('turns ok:false into a typed failure with the hints', () => {
    const r = toResult(200, true, {
      ok: false,
      error: 'nope',
      kind: 'host_key',
      needs_confirm: true,
      preview: 'p',
    });
    expect(r).toEqual({
      ok: false,
      error: 'nope',
      status: 200,
      kind: 'host_key',
      needs_confirm: true,
      preview: 'p',
    });
  });
  it('explains a rejected token in plain words', () => {
    const r = toResult(403, false, { ok: false, error: 'bad token' });
    expect(r).toMatchObject({ ok: false, error: BAD_TOKEN });
  });
  it('reports the HTTP status when the body is not usable', () => {
    expect(toResult(502, false, null)).toMatchObject({ ok: false, error: 'HTTP 502' });
    expect(toResult(500, false, { oops: 1 })).toMatchObject({ ok: false, error: 'HTTP 500' });
  });
});

describe('StudioClient', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends the token header and a JSON body on POST', async () => {
    const { client, calls } = mockClient(() => ({ ok: true, candidates: [] }));
    const r = await client.discover();
    expect(r.ok).toBe(true);
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/api/discover' });
    expect(calls[0]?.headers['X-Studio-Token']).toBe('tok');
    expect(calls[0]?.headers['Content-Type']).toBe('application/json');
  });

  it('sends bridge commands as { cmd, ...args }', async () => {
    const { client, calls } = mockClient(() => ({ ok: true, files: [] }));
    await client.bridge('ls', { dir: '~/robot_code', recursive: true });
    await client.bridge('estop_release');
    expect(calls[0]?.body).toEqual({ cmd: 'ls', dir: '~/robot_code', recursive: true });
    expect(calls[1]?.body).toEqual({ cmd: 'estop_release' });
  });

  it('returns failures as values, never throws', async () => {
    const { client } = mockClient(() => ({ ok: false, error: 'not connected' }));
    const r = await client.bridge('health');
    expect(r).toMatchObject({ ok: false, error: 'not connected' });
  });

  it('reports a network error in plain words', async () => {
    const client = new StudioClient({
      token: 't',
      fetchImpl: (() => Promise.reject(new TypeError('Failed to fetch'))) as typeof fetch,
    });
    const r = await client.settings();
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.network).toBe(true);
      expect(r.error).toContain('Cannot reach Studio');
    }
  });

  it('gives up after the timeout', async () => {
    vi.useFakeTimers();
    const fetchImpl = ((_url: string, init?: RequestInit) =>
      new Promise((_res, rej) => {
        init?.signal?.addEventListener('abort', () =>
          rej(new DOMException('aborted', 'AbortError')),
        );
      })) as unknown as typeof fetch;
    const client = new StudioClient({ token: 't', fetchImpl, timeoutMs: 5000 });
    const p = client.get('/api/settings');
    await vi.advanceTimersByTimeAsync(5001);
    const r = await p;
    expect(r).toMatchObject({ ok: false, network: true });
    if (!r.ok) expect(r.error).toContain('did not answer within 5 s');
  });

  it('survives a non-JSON answer', async () => {
    const client = new StudioClient({
      token: 't',
      fetchImpl: (async () => new Response('<html>oops</html>', { status: 502 })) as typeof fetch,
    });
    expect(await client.get('/api/settings')).toMatchObject({ ok: false, error: 'HTTP 502' });
  });

  it('accepts both settings shapes', async () => {
    const nested = mockClient(() => ({
      ok: true,
      settings: { remote_dir: '~/a' },
      defaults: { robot_user: 'u' },
      trusted: [],
    }));
    const flat = mockClient(() => ({ ok: true, remote_dir: '~/b', last_host: 'h' }));
    const a = await nested.client.settings();
    const b = await flat.client.settings();
    expect(a).toMatchObject({
      ok: true,
      settings: { remote_dir: '~/a' },
      defaults: { robot_user: 'u' },
    });
    expect(b).toMatchObject({ ok: true, settings: { remote_dir: '~/b', last_host: 'h' } });
  });

  it('reads plain-text templates and reports failures', async () => {
    const ok = mockClient(() => 'print(1)\n');
    expect(await ok.client.template('a b.py')).toEqual({ ok: true, text: 'print(1)\n' });
    expect(ok.calls[0]?.path).toBe('/api/templates/a%20b.py');
    const bad = new StudioClient({
      token: 't',
      fetchImpl: (async () =>
        new Response('{"ok":false,"error":"no such template"}', { status: 404 })) as typeof fetch,
    });
    expect(await bad.template('x')).toMatchObject({ ok: false, error: 'no such template' });
  });

  it('builds the event stream address with the encoded token', () => {
    const c = new StudioClient({ token: 'a b&c' });
    expect(c.eventsUrl()).toBe('/api/events?token=a%20b%26c');
    expect(c.pageUrl('/classic/?tab=wifi')).toContain('token=a%20b%26c');
  });
});
