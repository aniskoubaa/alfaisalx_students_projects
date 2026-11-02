import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { backoffSeconds, createSseClient, parseEvent } from './sse';
import type { SseStatus } from './sse';
import type { StudioEvent } from './types';

class FakeES {
  static all: FakeES[] = [];
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeES.all.push(this);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.(new Event('open'));
  }
  send(data: string) {
    this.onmessage?.(new MessageEvent('message', { data }));
  }
  fail() {
    this.onerror?.(new Event('error'));
  }
}

describe('parseEvent', () => {
  it('accepts known events', () => {
    expect(parseEvent('{"ev":"quit"}')).toEqual({ ev: 'quit' });
    expect(parseEvent('{"ev":"scan","ranges":[1,null]}')).toMatchObject({ ev: 'scan' });
  });
  it('drops anything else', () => {
    expect(parseEvent('not json')).toBeNull();
    expect(parseEvent('[1]')).toBeNull();
    expect(parseEvent('{"ev":"mystery"}')).toBeNull();
    expect(parseEvent('{"x":1}')).toBeNull();
    expect(parseEvent('{"ev":"run_output"}')).toBeNull();
  });
});

describe('backoffSeconds', () => {
  it('doubles up to 10 seconds', () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(backoffSeconds)).toEqual([1, 2, 4, 8, 10, 10, 10]);
  });
});

describe('createSseClient', () => {
  let statuses: SseStatus[];
  let events: StudioEvent[];
  beforeEach(() => {
    vi.useFakeTimers();
    FakeES.all = [];
    statuses = [];
    events = [];
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const make = () =>
    createSseClient({
      url: () => '/api/events?token=t',
      onEvent: (e) => events.push(e),
      onStatus: (s) => statuses.push(s),
      eventSource: FakeES,
      now: () => Date.now(),
    });

  it('connects, reports open and passes parsed events on', () => {
    const c = make();
    c.start();
    expect(statuses.at(-1)?.state).toBe('connecting');
    const es = FakeES.all[0] as FakeES;
    expect(es.url).toBe('/api/events?token=t');
    es.open();
    expect(statuses.at(-1)).toMatchObject({ state: 'open', attempt: 0 });
    es.send('{"ev":"log","text":"hi"}');
    es.send('garbage');
    expect(events).toEqual([{ ev: 'log', text: 'hi' }]);
  });

  it('retries with growing waits and shows when the next try is', () => {
    const c = make();
    c.start();
    const waits: number[] = [];
    for (let i = 0; i < 4; i++) {
      const es = FakeES.all.at(-1) as FakeES;
      es.fail();
      const s = statuses.at(-1) as SseStatus;
      expect(s.state).toBe('down');
      expect(es.closed).toBe(true);
      waits.push((s.retryAt as number) - Date.now());
      vi.advanceTimersByTime(waits.at(-1) as number);
    }
    expect(waits).toEqual([1000, 2000, 4000, 8000]);
    expect(FakeES.all).toHaveLength(5);
  });

  it('starts counting again after a good connection', () => {
    const c = make();
    c.start();
    (FakeES.all[0] as FakeES).fail();
    vi.advanceTimersByTime(1000);
    const second = FakeES.all[1] as FakeES;
    second.open();
    second.fail();
    const s = statuses.at(-1) as SseStatus;
    expect((s.retryAt as number) - Date.now()).toBe(1000);
  });

  it('retryNow skips the wait', () => {
    const c = make();
    c.start();
    (FakeES.all[0] as FakeES).fail();
    expect(FakeES.all).toHaveLength(1);
    c.retryNow();
    expect(FakeES.all).toHaveLength(2);
    vi.advanceTimersByTime(20000);
    expect(FakeES.all).toHaveLength(2);
  });

  it('stop closes the stream and cancels retries', () => {
    const c = make();
    c.start();
    const es = FakeES.all[0] as FakeES;
    es.fail();
    c.stop();
    vi.advanceTimersByTime(60000);
    expect(FakeES.all).toHaveLength(1);
    const c2 = make();
    c2.start();
    const es2 = FakeES.all.at(-1) as FakeES;
    c2.stop();
    expect(es2.closed).toBe(true);
  });
});
