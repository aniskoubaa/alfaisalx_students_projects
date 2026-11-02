import { describe, expect, it } from 'vitest';
import { splitArgs } from './args';
import { connHint, connView } from './connView';
import { isEstopKey } from './estopKeys';
import type { KeyLike } from './estopKeys';
import { compareFiles, countByStatus, NEW_NAME_RE } from './files';
import { estopLines } from './estopSummary';
import { fmtNum, fmtSize, fmtUptime } from './format';
import { isMotionProgram } from './motion';
import { nameFromTemplate, templateList } from './templates';

describe('splitArgs', () => {
  it('splits on spaces and keeps quoted groups together', () => {
    expect(splitArgs('square --side 0.3 --yes')).toEqual(['square', '--side', '0.3', '--yes']);
    expect(splitArgs('say "hello world" \'a b\'')).toEqual(['say', 'hello world', 'a b']);
    expect(splitArgs('')).toEqual([]);
    expect(splitArgs('   ')).toEqual([]);
    expect(splitArgs('""')).toEqual(['']);
  });
  it('handles escapes', () => {
    expect(splitArgs(String.raw`a\ b`)).toEqual(['a b']);
    expect(splitArgs(String.raw`"a \"q\" b"`)).toEqual(['a "q" b']);
  });
  it('explains an open quote', () => {
    expect(() => splitArgs('say "oops')).toThrow('Unclosed quote');
  });
});

describe('compareFiles', () => {
  it('labels every file by how it differs', () => {
    const rows = compareFiles(
      [
        { name: 'a.py', size: 1, sha1: 'x' },
        { name: 'b.py', size: 2, sha1: 'y' },
        { name: 'c.py', size: 3 },
        { name: 'd.py', size: 4 },
      ],
      [
        { name: 'a.py', size: 1, sha1: 'x' },
        { name: 'b.py', size: 2, sha1: 'z' },
        { name: 'c.py', size: 3 },
        { name: 'e.py', size: 5 },
      ],
    );
    expect(rows.map((r) => [r.name, r.status])).toEqual([
      ['a.py', 'same'],
      ['b.py', 'changed'],
      ['c.py', 'same'],
      ['d.py', 'new'],
      ['e.py', 'robot only'],
    ]);
    expect(countByStatus(rows)).toEqual({ same: 2, changed: 1, new: 1, 'robot only': 1 });
  });
  it('copes with a missing side', () => {
    expect(compareFiles(null, [{ name: 'a.py' }])[0]?.status).toBe('robot only');
    expect(compareFiles(null, null)).toEqual([]);
  });
  it('validates new program names', () => {
    expect(NEW_NAME_RE.test('my_spin-2.py')).toBe(true);
    expect(NEW_NAME_RE.test('spin.sh')).toBe(false);
    expect(NEW_NAME_RE.test('../x.py')).toBe(false);
    expect(NEW_NAME_RE.test('a b.py')).toBe(false);
  });
});

describe('isMotionProgram', () => {
  it('knows built-in, catalog, detected and user-marked programs', () => {
    expect(isMotionProgram('motion_shapes.py', {}, {})).toBe(true);
    expect(isMotionProgram('x.py', { 'x.py': { moves: true } }, {})).toBe(true);
    expect(isMotionProgram('y.py', {}, { 'y.py': { name: 'y.py', moves_detected: true } })).toBe(
      true,
    );
    expect(isMotionProgram('z.py', {}, {}, ['z.py'])).toBe(true);
    expect(isMotionProgram('read.py', { 'read.py': { moves: false } }, {})).toBe(false);
    expect(isMotionProgram('dir/motion_shapes.py', {}, {})).toBe(true);
  });
});

describe('templates', () => {
  it('accepts names and objects', () => {
    const list = templateList(
      ['a.py', { name: 'b.py', entry: { title: 'B' } }, { file: 'c.py' }, {}],
      {
        'a.py': { title: 'A' },
      },
    );
    expect(list.map((t) => t.name)).toEqual(['a.py', 'b.py', 'c.py']);
    expect(list[0]?.entry.title).toBe('A');
    expect(nameFromTemplate(list[0])).toBe('my_a.py');
    expect(nameFromTemplate({ name: 'my_x.py', entry: {} })).toBe('my_x.py');
    expect(nameFromTemplate(undefined)).toBe('my_program.py');
  });
});

describe('format', () => {
  it('shows a dash for missing values', () => {
    expect(fmtNum(null)).toBe('–');
    expect(fmtNum(1.234, 2)).toBe('1.23');
    expect(fmtSize(undefined)).toBe('–');
    expect(fmtSize(2048)).toBe('2.0 KB');
    expect(fmtUptime(90061)).toBe('1d 1h 1m');
    expect(fmtUptime(125)).toBe('2m');
  });
});

describe('connView and connHint', () => {
  const sseOk = { state: 'open', attempt: 0, retryAt: null } as const;
  it('says the state in words', () => {
    expect(
      connView(
        { ev: 'conn', state: 'connected', host: '1.2.3.4', via: 'cable' },
        { ev: 'hello', hostname: 'tb4' },
        sseOk,
      ),
    ).toMatchObject({
      tone: 'ok',
      label: 'Connected',
      host: 'tb4',
      route: 'Ethernet cable',
    });
    expect(connView({ ev: 'conn', state: 'reconnecting' }, null, sseOk)).toMatchObject({
      tone: 'warn',
      busy: true,
    });
    expect(connView({ ev: 'conn', state: 'disconnected' }, null, sseOk).label).toBe(
      'Not connected',
    );
  });
  it('puts a lost Studio link ahead of the robot link', () => {
    const v = connView({ ev: 'conn', state: 'connected' }, null, {
      state: 'down',
      attempt: 1,
      retryAt: 1,
    });
    expect(v).toMatchObject({ tone: 'bad', label: 'Studio not responding' });
  });
  it('finds fixable errors by kind or by message', () => {
    expect(connHint({ ev: 'conn', state: 'error', kind: 'host_key' })?.kind).toBe('host_key');
    expect(
      connHint({ ev: 'conn', state: 'error', error: 'Permission denied (publickey)' })?.kind,
    ).toBe('key_not_set_up');
    expect(connHint({ ev: 'conn', state: 'error', error: 'ssh not found' })?.kind).toBe('no_ssh');
    expect(connHint({ ev: 'conn', state: 'error', error: 'timeout' })).toBeNull();
  });
});

describe('isEstopKey', () => {
  const key = (
    k: string,
    over: Partial<KeyLike> = {},
    target: EventTarget | null = document.body,
  ): KeyLike => ({
    key: k,
    ctrlKey: false,
    shiftKey: false,
    metaKey: false,
    altKey: false,
    repeat: false,
    target,
    ...over,
  });
  const el = (html: string): Element => {
    const d = document.createElement('div');
    d.innerHTML = html;
    document.body.appendChild(d);
    return d.firstElementChild as Element;
  };

  it('fires on Escape and Space anywhere on the page', () => {
    expect(isEstopKey(key('Escape'))).toBe(true);
    expect(isEstopKey(key(' '))).toBe(true);
    expect(isEstopKey(key('a'))).toBe(false);
  });
  it('stays quiet while typing', () => {
    expect(isEstopKey(key('Escape', {}, el('<input type="text">')))).toBe(false);
    expect(isEstopKey(key(' ', {}, el('<textarea></textarea>')))).toBe(false);
    expect(
      isEstopKey(
        key(
          ' ',
          {},
          el('<div contenteditable="true"><span id="in">x</span></div>').querySelector('#in'),
        ),
      ),
    ).toBe(false);
    expect(isEstopKey(key('Escape', {}, el('<select></select>')))).toBe(false);
  });
  it('leaves Space alone on things it activates, but Escape still fires', () => {
    expect(isEstopKey(key(' ', {}, el('<button>b</button>')))).toBe(false);
    expect(isEstopKey(key(' ', {}, el('<a href="#">l</a>')))).toBe(false);
    expect(isEstopKey(key(' ', {}, el('<input type="checkbox">')))).toBe(false);
    expect(isEstopKey(key('Escape', {}, el('<button>b</button>')))).toBe(true);
    expect(isEstopKey(key('Escape', {}, el('<input type="checkbox">')))).toBe(true);
  });
  it('ignores key repeat and other modifiers', () => {
    expect(isEstopKey(key('Escape', { repeat: true }))).toBe(false);
    expect(isEstopKey(key('Escape', { ctrlKey: true }))).toBe(false);
    expect(isEstopKey(key(' ', { altKey: true }))).toBe(false);
  });
  it('works with Ctrl+Shift+E everywhere, also in the editor', () => {
    const inEditor = el('<div contenteditable="true"></div>');
    expect(isEstopKey(key('E', { ctrlKey: true, shiftKey: true }, inEditor))).toBe(true);
    expect(
      isEstopKey(key('e', { ctrlKey: true, shiftKey: true }, el('<textarea></textarea>'))),
    ).toBe(true);
    expect(isEstopKey(key('e', { ctrlKey: true }))).toBe(false);
  });
});

describe('estopLines', () => {
  it('reads the steps from the wrapped answer and says Done or Failed per step', () => {
    const lines = estopLines({
      ok: true,
      bridge: {
        ok: true,
        steps: {
          e_stop_service: { success: true, message: 'x' },
          cancel_goals: { ok: false },
          zero_cmd_vel: { ok: true },
          other_thing: 'sent',
        },
      },
    });
    expect(lines).toEqual([
      { label: 'Drive motors switched off', ok: true },
      { label: 'Running robot actions cancelled', ok: false },
      { label: 'Zero velocity sent', ok: true },
      { label: 'Other thing', ok: null },
    ]);
    expect(estopLines({ ok: true })).toEqual([]);
  });
});
