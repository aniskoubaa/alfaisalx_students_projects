import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApi } from '../../api';
import type { MenuCheck, MenuGetAnswer } from '../../api';
import { DialogHost, TooltipProvider } from '../../components/ui';
import { Menu } from '../../screens/menu/Menu';
import { ROUTES, parseHash, routeFor } from '../../state/router';
import { connectedStatus, installApi, resetStores } from '../../test/helpers';
import { BuiltinList } from './BuiltinList';
import { EntryEditor } from './EntryEditor';
import { MenuPreview } from './MenuPreview';
import {
  BUILTINS,
  buildPreview,
  displayLine,
  docFromCheck,
  emptyDoc,
  labelCounter,
  newEntry,
  previewLayout,
  removeEntry,
  setHidden,
  toYaml,
  upsertEntry,
  validateDoc,
  validateEntry,
  yq,
} from './model';
import type { MenuDoc, OwnEntry } from './model';
import { useMenu } from './store';

type Body = Record<string, unknown>;

/** The robot checker's answer for menu.example.yaml. */
const EXAMPLE_CHECK: MenuCheck = {
  ok: true,
  errors: [],
  warnings: [],
  hide: ['wall_left', 'wall_right'],
  layout: ['trip', 'dock', 'hello', 'square', 'undock', 'estop', 'power', 'help'],
  labels: {
    trip: 'Go to food court',
    dock: 'Dock',
    hello: 'Hello demo',
    square: 'Drive a square',
    undock: 'Undock',
    estop: 'EStop',
    power: 'Power',
    help: 'Help',
  },
  custom: {
    hello: {
      id: 'hello',
      label: 'Hello demo',
      program: 'programs/hello.py',
      args: [],
      confirm: false,
      moves: false,
      undocks: false,
      timeout: 300,
      after: 'dock',
    },
    square: {
      id: 'square',
      label: 'Drive a square',
      program: 'programs/square.py',
      args: ['--side', '0.5'],
      confirm: true,
      moves: true,
      undocks: false,
      timeout: 120,
      after: 'hello',
    },
  },
};

const entry = (over: Partial<OwnEntry> = {}): OwnEntry => ({
  ...newEntry('dock'),
  id: 'lights',
  label: 'Lights demo',
  program: '~/robot_code/programs/lights.py',
  ...over,
});

/** A tiny parser for the subset toYaml writes, used only to check the output structure. */
function parseSubset(text: string): { version: number; hide: string[]; entries: Body[] } {
  const out = { version: 0, hide: [] as string[], entries: [] as Body[] };
  let cur: Body | null = null;
  const value = (v: string): unknown => {
    if (v === 'true') return true;
    if (v === 'false') return false;
    if (/^-?\d+$/.test(v)) return Number(v);
    if (v.startsWith('"')) return JSON.parse(v);
    if (v.startsWith('[')) return JSON.parse(v);
    throw new Error('cannot parse ' + v);
  };
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    let m: RegExpMatchArray | null;
    if ((m = line.match(/^version: (\d+)$/))) out.version = Number(m[1]);
    else if ((m = line.match(/^hide: \[(.*)\]$/)))
      out.hide = (m[1] as string).split(', ').filter(Boolean);
    else if (line === 'entries:') continue;
    else if ((m = line.match(/^ {2}- (\w+): (.*)$/))) {
      cur = { [m[1] as string]: value(m[2] as string) };
      out.entries.push(cur);
    } else if ((m = line.match(/^ {4}(\w+): (.*)$/)) && cur)
      cur[m[1] as string] = value(m[2] as string);
    else throw new Error('unexpected line: ' + line);
  }
  return out;
}

const withUi = (ui: React.ReactNode) =>
  render(
    <TooltipProvider>
      {ui}
      <DialogHost />
    </TooltipProvider>,
  );

const calls = (cs: Array<{ body: Body }>, cmd: string) => cs.filter((c) => c.body.cmd === cmd);

const robot = (over: Partial<MenuGetAnswer> = {}): MenuGetAnswer => ({
  path: '/home/ubuntu/robot_code/menu/menu.yaml',
  exists: true,
  text: 'version: 1\n',
  check: EXAMPLE_CHECK,
  checker_ok: true,
  ...over,
});

beforeEach(() => {
  resetStores();
  useMenu.getState().reset();
});
afterEach(() => {
  setApi(null);
  useMenu.getState().reset();
});

/* ---------- model ---------- */

describe('menu model: built-ins', () => {
  it('has the robot order, labels and flags', () => {
    expect(BUILTINS.map((b) => b.id)).toEqual([
      'trip',
      'dock',
      'undock',
      'estop',
      'wall_left',
      'wall_right',
      'power',
      'help',
    ]);
    expect(BUILTINS.map((b) => b.label)).toEqual([
      'Go to food court',
      'Dock',
      'Undock',
      'EStop',
      'Wall Follow Left',
      'Wall Follow Right',
      'Power',
      'Help',
    ]);
    expect(BUILTINS.filter((b) => b.locked).map((b) => b.id)).toEqual([
      'trip',
      'dock',
      'estop',
      'power',
    ]);
    expect(BUILTINS.filter((b) => b.hideable).map((b) => b.id)).toEqual([
      'undock',
      'wall_left',
      'wall_right',
      'help',
    ]);
  });

  it('setHidden changes only the four that can be hidden, in the robot order', () => {
    let d = setHidden(emptyDoc(), 'help', true);
    d = setHidden(d, 'undock', true);
    expect(d.hide).toEqual(['undock', 'help']);
    expect(setHidden(d, 'dock', true)).toBe(d);
    expect(setHidden(d, 'trip', true)).toBe(d);
    expect(setHidden(d, 'help', false).hide).toEqual(['undock']);
  });
});

describe('menu model: validation', () => {
  const others = [entry({ id: 'other', label: 'Other one' })];
  const cases: Array<[string, Partial<OwnEntry>, string | null]> = [
    ['a good entry', {}, null],
    ['id with capital', { id: 'Lights' }, 'id'],
    ['id starting with a digit', { id: '1lights' }, 'id'],
    ['empty id', { id: '' }, 'id'],
    ['id of 24 characters', { id: 'a'.repeat(24) }, null],
    ['id of 25 characters', { id: 'a'.repeat(25) }, 'id'],
    ['built-in id', { id: 'dock' }, 'id'],
    ['id used by another entry', { id: 'other' }, 'id'],
    ['label of 17 characters', { label: 'A'.repeat(17) }, null],
    ['label of 18 characters', { label: 'A'.repeat(18) }, 'label'],
    ['empty label', { label: '  ' }, 'label'],
    ['label with a non-ASCII character', { label: 'Café' }, 'label'],
    ['label with a tab', { label: 'a\tb' }, 'label'],
    ['built-in label', { label: 'Dock' }, 'label'],
    ['built-in label in other case', { label: 'wall follow left' }, 'label'],
    ['the trip label on the way back', { label: 'Back to the lab' }, 'label'],
    ['label used by another entry', { label: 'other ONE' }, 'label'],
    ['label with : and #', { label: 'a: b # c' }, null],
    ['program ~/robot_code/x/y.py', { program: '~/robot_code/x/y.py' }, null],
    ['program relative x/y.sh', { program: 'x/y.sh' }, null],
    ['program ~/x.py', { program: '~/x.py' }, 'program'],
    ['program with ..', { program: '~/robot_code/../x.py' }, 'program'],
    ['program relative with ..', { program: 'a/../../x.py' }, 'program'],
    ['program with backslash', { program: 'x\\y.py' }, 'program'],
    ['program absolute', { program: '/etc/x.py' }, 'program'],
    ['program not py or sh', { program: 'x/y.txt' }, 'program'],
    ['empty program', { program: '' }, 'program'],
    ['program folder only', { program: '~/robot_code/' }, 'program'],
    ['program over 200 characters', { program: 'a/'.repeat(100) + 'x.py' }, 'program'],
    ['10 args', { args: Array.from({ length: 10 }, () => 'a') }, null],
    ['11 args', { args: Array.from({ length: 11 }, () => 'a') }, 'args'],
    ['an arg of 200 characters', { args: ['a'.repeat(200)] }, null],
    ['an arg of 201 characters', { args: ['a'.repeat(201)] }, 'args'],
    ['timeout 1', { timeout: 1 }, null],
    ['timeout 3600', { timeout: 3600 }, null],
    ['timeout 0', { timeout: 0 }, 'timeout'],
    ['timeout 3601', { timeout: 3601 }, 'timeout'],
    ['timeout 1.5', { timeout: 1.5 }, 'timeout'],
    ['timeout not a number', { timeout: Number.NaN }, 'timeout'],
    ['after a built-in', { after: 'trip' }, null],
    ['after another own entry', { after: 'other' }, null],
    ['after an unknown id', { after: 'nowhere' }, 'after'],
    ['after itself', { after: 'lights' }, 'after'],
  ];
  it.each(cases)('%s', (_name, over, field) => {
    const errs = validateEntry(entry(over), others);
    if (field === null) expect(errs).toEqual({});
    else {
      expect(Object.keys(errs)).toContain(field);
      expect(errs[field as keyof typeof errs]).toBeTruthy();
    }
  });

  it('detects loops in after', () => {
    const a = entry({ id: 'a', label: 'A', after: 'b' });
    const b = entry({ id: 'b', label: 'B', after: 'a' });
    expect(validateEntry(a, [b]).after).toMatch(/loop/);
    const c = entry({ id: 'c', label: 'C', after: 'b' });
    const b2 = entry({ id: 'b', label: 'B', after: 'a' });
    const a2 = entry({ id: 'a', label: 'A', after: 'c' });
    expect(validateEntry(c, [b2, a2]).after).toMatch(/loop/);
    expect(validateDoc({ hide: [], entries: [a, b] }).ok).toBe(false);
    const fine = entry({ id: 'b', label: 'B', after: 'dock' });
    expect(validateEntry(a, [fine]).after).toBeUndefined();
  });

  it('allows at most 8 entries', () => {
    const mk = (n: number): MenuDoc => ({
      hide: [],
      entries: Array.from({ length: n }, (_, i) => entry({ id: `e${i}`, label: `Entry ${i}` })),
    });
    expect(validateDoc(mk(8)).ok).toBe(true);
    const nine = validateDoc(mk(9));
    expect(nine.ok).toBe(false);
    expect(nine.messages.join(' ')).toMatch(/At most 8/);
  });

  it('flags the same id twice in a document', () => {
    const d: MenuDoc = { hide: [], entries: [entry(), entry({ label: 'Other name' })] };
    expect(validateDoc(d).ok).toBe(false);
  });

  it('counts the label as the robot does', () => {
    expect(labelCounter('Hello demo')).toBe('10 of 17');
    expect(labelCounter('  padded  ')).toBe('6 of 17');
    expect(labelCounter('')).toBe('0 of 17');
  });

  it('flags move/confirm coupling only through normalizeFlags (the robot forces it)', () => {
    const d = upsertEntry(emptyDoc(), -1, entry({ undocks: true }));
    const e = d.entries[0] as OwnEntry;
    expect(e).toMatchObject({ undocks: true, moves: true, confirm: true });
    const m = upsertEntry(emptyDoc(), -1, entry({ moves: true })).entries[0] as OwnEntry;
    expect(m).toMatchObject({ moves: true, confirm: true, undocks: false });
    const p = upsertEntry(emptyDoc(), -1, entry()).entries[0] as OwnEntry;
    expect(p).toMatchObject({ moves: false, confirm: false });
  });
});

describe('menu model: editing a document', () => {
  it('renames follow the entries that were placed after the old id', () => {
    const base: MenuDoc = {
      hide: [],
      entries: [
        entry({ id: 'a', label: 'A', after: 'dock' }),
        entry({ id: 'b', label: 'B', after: 'a' }),
      ],
    };
    const d = upsertEntry(base, 0, entry({ id: 'a2', label: 'A', after: 'dock' }));
    expect(d.entries.map((e) => [e.id, e.after])).toEqual([
      ['a2', 'dock'],
      ['b', 'a2'],
    ]);
  });

  it('removing an entry moves the entries after it to its place', () => {
    const base: MenuDoc = {
      hide: [],
      entries: [
        entry({ id: 'a', label: 'A', after: 'dock' }),
        entry({ id: 'b', label: 'B', after: 'a' }),
      ],
    };
    const d = removeEntry(base, 0);
    expect(d.entries).toHaveLength(1);
    expect(d.entries[0]).toMatchObject({ id: 'b', after: 'dock' });
  });
});

describe('menu model: YAML', () => {
  const doc = (): MenuDoc => docFromCheck(EXAMPLE_CHECK);

  it('writes the example exactly', () => {
    expect(toYaml(doc())).toBe(
      [
        'version: 1',
        'hide: [wall_left, wall_right]',
        'entries:',
        '  - id: "hello"',
        '    label: "Hello demo"',
        '    program: "~/robot_code/programs/hello.py"',
        '    confirm: false',
        '    moves: false',
        '    undocks: false',
        '    timeout: 300',
        '    after: "dock"',
        '  - id: "square"',
        '    label: "Drive a square"',
        '    program: "~/robot_code/programs/square.py"',
        '    args: ["--side", "0.5"]',
        '    confirm: true',
        '    moves: true',
        '    undocks: false',
        '    timeout: 120',
        '    after: "hello"',
        '',
      ].join('\n'),
    );
  });

  it('round trips the structure of the example', () => {
    const p = parseSubset(toYaml(doc()));
    expect(p.version).toBe(1);
    expect(p.hide).toEqual(['wall_left', 'wall_right']);
    expect(p.entries).toEqual([
      {
        id: 'hello',
        label: 'Hello demo',
        program: '~/robot_code/programs/hello.py',
        confirm: false,
        moves: false,
        undocks: false,
        timeout: 300,
        after: 'dock',
      },
      {
        id: 'square',
        label: 'Drive a square',
        program: '~/robot_code/programs/square.py',
        args: ['--side', '0.5'],
        confirm: true,
        moves: true,
        undocks: false,
        timeout: 120,
        after: 'hello',
      },
    ]);
  });

  it('writes only the version for an empty document, with no hide line', () => {
    expect(toYaml(emptyDoc())).toBe('version: 1\n');
    expect(toYaml({ hide: ['help'], entries: [] })).toBe('version: 1\nhide: [help]\n');
  });

  it('omits args when there are none and keeps the key order', () => {
    const t = toYaml({ hide: [], entries: [entry()] });
    expect(t).not.toContain('args');
    const keys = t
      .split('\n')
      .filter((l) => /^ {2,4}-? ?\w+:/.test(l))
      .map((l) => l.trim().replace(/^- /, '').split(':')[0]);
    expect(keys).toEqual([
      'id',
      'label',
      'program',
      'confirm',
      'moves',
      'undocks',
      'timeout',
      'after',
    ]);
  });

  it('quotes strings and escapes backslash, quote and control characters', () => {
    expect(yq('a: b # c')).toBe('"a: b # c"');
    expect(yq('say "hi" \\ now')).toBe('"say \\"hi\\" \\\\ now"');
    expect(yq('a\tb')).toBe('"a\\x09b"');
    const d: MenuDoc = {
      hide: [],
      entries: [entry({ label: 'a: b # "c"', args: ['--x=1: 2', 'say "hi" \\'] })],
    };
    const p = parseSubset(toYaml(d));
    expect(p.entries[0]).toMatchObject({ label: 'a: b # "c"', args: ['--x=1: 2', 'say "hi" \\'] });
  });
});

describe('menu model: from the robot check and preview', () => {
  it('docFromCheck gives the entries in layout order with ~/robot_code programs', () => {
    const d = docFromCheck(EXAMPLE_CHECK);
    expect(d.hide).toEqual(['wall_left', 'wall_right']);
    expect(d.entries.map((e) => e.id)).toEqual(['hello', 'square']);
    expect(d.entries[0]?.program).toBe('~/robot_code/programs/hello.py');
    expect(d.entries[1]).toMatchObject({ args: ['--side', '0.5'], moves: true, after: 'hello' });
    expect(validateDoc(d).ok).toBe(true);
  });

  it('docFromCheck keeps entries that are missing from the layout', () => {
    const c: MenuCheck = { ...EXAMPLE_CHECK, layout: ['trip', 'square'] };
    expect(docFromCheck(c).entries.map((e) => e.id)).toEqual(['square', 'hello']);
  });

  it('previewLayout matches the robot layout of the example', () => {
    expect(previewLayout(docFromCheck(EXAMPLE_CHECK))).toEqual(
      EXAMPLE_CHECK.layout.filter((k) => !['wall_left', 'wall_right'].includes(k)),
    );
  });

  it('previewLayout rules', () => {
    // default place: the end
    expect(previewLayout({ hide: [], entries: [entry({ after: 'help' })] }).at(-1)).toBe('lights');
    // after trip is second, never above trip
    expect(previewLayout({ hide: [], entries: [entry({ after: 'trip' })] }).slice(0, 2)).toEqual([
      'trip',
      'lights',
    ]);
    // a hidden built-in still marks the place
    const h = previewLayout({ hide: ['undock'], entries: [entry({ after: 'undock' })] });
    expect(h).toEqual([
      'trip',
      'dock',
      'lights',
      'estop',
      'wall_left',
      'wall_right',
      'power',
      'help',
    ]);
    // same target keeps file order; after another own entry sits right below it
    const two = previewLayout({
      hide: [],
      entries: [
        entry({ id: 'a', label: 'A', after: 'dock' }),
        entry({ id: 'b', label: 'B', after: 'dock' }),
        entry({ id: 'c', label: 'C', after: 'a' }),
      ],
    });
    expect(two.slice(0, 5)).toEqual(['trip', 'dock', 'a', 'c', 'b']);
  });

  it('previewLayout survives a loop without hanging', () => {
    const l = previewLayout({
      hide: [],
      entries: [
        entry({ id: 'a', label: 'A', after: 'b' }),
        entry({ id: 'b', label: 'B', after: 'a' }),
      ],
    });
    expect(l).toEqual(expect.arrayContaining(['a', 'b']));
  });

  it('buildPreview uses the robot layout and labels when given a check', () => {
    const p = buildPreview(docFromCheck(EXAMPLE_CHECK), EXAMPLE_CHECK);
    expect(p.lines.map((l) => l.id)).toEqual(EXAMPLE_CHECK.layout);
    expect(p.hidden.map((l) => l.label)).toEqual(['Wall Follow Left', 'Wall Follow Right']);
    const own = buildPreview(docFromCheck(EXAMPLE_CHECK), null);
    expect(own.lines.map((l) => l.label)).toContain('Drive a square');
  });

  it('display lines are 18 characters with the cursor on the first', () => {
    expect(displayLine('Dock', true)).toBe('>Dock');
    expect(displayLine('Dock', false)).toBe(' Dock');
    expect(displayLine('A'.repeat(30), true)).toHaveLength(18);
  });
});

/* ---------- components ---------- */

describe('BuiltinList', () => {
  it('has no edit or hide control on the locked entries', () => {
    render(<BuiltinList doc={emptyDoc()} onChange={() => {}} />);
    for (const id of ['trip', 'dock', 'estop', 'power']) {
      const row = screen.getByTestId(`menu-builtin-${id}`);
      expect(within(row).getByText('Locked')).toBeInTheDocument();
      expect(within(row).queryByRole('switch')).toBeNull();
      expect(within(row).queryByRole('button')).toBeNull();
      expect(within(row).queryByRole('checkbox')).toBeNull();
    }
  });

  it('has the Show on the robot switch only on the four that can be hidden', () => {
    const changes: MenuDoc[] = [];
    render(<BuiltinList doc={emptyDoc()} onChange={(d) => changes.push(d)} />);
    expect(screen.getAllByRole('switch')).toHaveLength(4);
    for (const id of ['undock', 'wall_left', 'wall_right', 'help']) {
      const row = screen.getByTestId(`menu-builtin-${id}`);
      expect(within(row).getByRole('switch')).toBeChecked();
      expect(within(row).queryByText('Locked')).toBeNull();
      expect(within(row).queryByRole('button')).toBeNull();
    }
    return userEvent
      .click(screen.getByRole('switch', { name: 'Show Help on the robot' }))
      .then(() => {
        expect(changes.at(-1)?.hide).toEqual(['help']);
      });
  });

  it('shows hidden entries as off', () => {
    render(<BuiltinList doc={{ hide: ['undock'], entries: [] }} onChange={() => {}} />);
    expect(screen.getByRole('switch', { name: 'Show Undock on the robot' })).not.toBeChecked();
  });
});

describe('MenuPreview', () => {
  it('draws the robot lines with the cursor, locks and the hidden list', () => {
    const doc = docFromCheck(EXAMPLE_CHECK);
    render(<MenuPreview doc={doc} check={EXAMPLE_CHECK} />);
    const preview = screen.getByTestId('menu-preview');
    const lines = within(preview).getAllByRole('listitem');
    expect(
      within(screen.getByTestId('menu-line-trip')).getByText('>Go to food court'),
    ).toBeVisible();
    expect(screen.getByTestId('menu-line-dock').textContent).toContain(' Dock');
    expect(screen.getByTestId('menu-line-hello').textContent).toBe(' Hello demo');
    expect(
      within(screen.getByTestId('menu-line-hello')).queryByText('built in, cannot be changed'),
    ).toBeNull();
    expect(
      within(screen.getByTestId('menu-line-dock')).getByText('built in, cannot be changed'),
    ).toBeInTheDocument();
    expect(lines.length).toBeGreaterThan(6);
    const hidden = screen.getByTestId('menu-hidden');
    expect(within(hidden).getByText('Hidden')).toBeInTheDocument();
    expect(within(hidden).getByText('Wall Follow Left')).toBeInTheDocument();
    expect(screen.getByText('Checked by the robot')).toBeInTheDocument();
  });

  it('falls back to its own order when there is no current check', () => {
    render(<MenuPreview doc={docFromCheck(EXAMPLE_CHECK)} check={null} />);
    expect(screen.getByText('Not checked yet')).toBeInTheDocument();
    expect(screen.getByTestId('menu-line-hello')).toBeInTheDocument();
  });
});

describe('EntryEditor', () => {
  const open = (initial: OwnEntry = newEntry(), onSave = vi.fn()) => {
    withUi(<EntryEditor initial={initial} isNew others={[]} onSave={onSave} onCancel={() => {}} />);
    return onSave;
  };

  it('counts the label and refuses 18 characters but not 17', async () => {
    const u = userEvent.setup();
    open();
    const label = screen.getByRole('textbox', { name: 'Name on the display' });
    await u.type(label, 'Hello demo');
    expect(screen.getByTestId('menu-label-counter')).toHaveTextContent('10 of 17');
    await u.clear(label);
    await u.type(label, 'A'.repeat(17));
    expect(screen.queryByText(/the display fits 17/)).toBeNull();
    await u.type(label, 'A');
    expect(screen.getByText(/18 characters; the display fits 17/)).toBeInTheDocument();
  });

  it('moves forces confirm on and disabled, with the reason; undocks forces moves', async () => {
    const u = userEvent.setup();
    open();
    const confirm = screen.getByRole('checkbox', { name: 'Ask before starting' });
    const moves = screen.getByRole('checkbox', { name: 'Moves the robot' });
    const undocks = screen.getByRole('checkbox', { name: 'Undocks by itself' });
    expect(confirm).toBeEnabled();
    expect(moves).toBeEnabled();
    await u.click(moves);
    expect(confirm).toBeChecked();
    expect(confirm).toBeDisabled();
    expect(screen.getByTestId('menu-forced-note')).toHaveTextContent(/always asks first/);
    await u.click(undocks);
    expect(moves).toBeChecked();
    expect(moves).toBeDisabled();
    expect(confirm).toBeDisabled();
    await u.click(undocks);
    expect(moves).toBeEnabled();
    await u.click(moves);
    expect(confirm).toBeEnabled();
  });

  it('shows errors and does not save a bad entry', async () => {
    const u = userEvent.setup();
    const onSave = open();
    await u.click(screen.getByRole('button', { name: 'Add entry' }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('Enter the name shown on the display.')).toBeInTheDocument();
    expect(screen.getByText(/Use a-z, 0-9/)).toBeInTheDocument();
    expect(screen.getByText(/must name a file/)).toBeInTheDocument();
  });

  it('refuses a program outside robot_code as you type', async () => {
    const u = userEvent.setup();
    open();
    const program = screen.getByRole('textbox', { name: 'Program' });
    await u.clear(program);
    await u.type(program, '~/x.py');
    expect(screen.getByText(/under ~\/robot_code/)).toBeInTheDocument();
  });

  it('saves a good entry with one argument per line and the forced flags', async () => {
    const u = userEvent.setup();
    const onSave = open();
    await u.type(screen.getByRole('textbox', { name: 'Name on the display' }), 'Square');
    await u.type(screen.getByRole('textbox', { name: 'Id' }), 'square');
    const program = screen.getByRole('textbox', { name: 'Program' });
    await u.clear(program);
    await u.type(program, 'programs/square.py');
    await u.type(screen.getByRole('textbox', { name: 'Arguments' }), '--side{Enter}0.5{Enter}');
    await u.click(screen.getByRole('checkbox', { name: 'Moves the robot' }));
    await u.selectOptions(screen.getByRole('combobox', { name: 'Place after' }), 'dock');
    await u.click(screen.getByRole('button', { name: 'Add entry' }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0]?.[0]).toMatchObject({
      id: 'square',
      label: 'Square',
      program: 'programs/square.py',
      args: ['--side', '0.5'],
      confirm: true,
      moves: true,
      undocks: false,
      timeout: 300,
      after: 'dock',
    });
  });

  it('lists the built-ins and the other entries in Place after', () => {
    withUi(
      <EntryEditor
        initial={newEntry()}
        isNew
        others={[entry({ id: 'other', label: 'Other one' })]}
        onSave={() => {}}
        onCancel={() => {}}
      />,
    );
    const options = within(screen.getByRole('combobox', { name: 'Place after' }))
      .getAllByRole('option')
      .map((o) => o.textContent);
    expect(options).toContain('Dock');
    expect(options).toContain('Other one');
    expect(options).toHaveLength(9);
  });
});

/* ---------- screen ---------- */

describe('Robot menu screen', () => {
  const run = (answer: MenuGetAnswer, extra: (c: { body: Body }) => unknown = () => undefined) =>
    installApi((c) => {
      const cmd = c.body.cmd;
      if (cmd === 'menu_get') return answer;
      return extra(c) ?? { ok: false, error: 'unexpected ' + String(cmd) };
    });

  it('loads the file on open and shows its entries and the checked preview', async () => {
    connectedStatus();
    const m = run(robot());
    withUi(<Menu />);
    expect(await screen.findByTestId('menu-entry-hello')).toBeInTheDocument();
    expect(screen.getByTestId('menu-entry-square')).toBeInTheDocument();
    expect(calls(m.calls, 'menu_get')).toHaveLength(1);
    expect(screen.getByText('Checked by the robot')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Robot menu' })).toBeInTheDocument();
    expect(screen.queryByTestId('menu-checker-missing')).toBeNull();
  });

  it('says the standard menu is shown when there is no file', async () => {
    connectedStatus();
    run(robot({ exists: false, text: '', check: null }));
    withUi(<Menu />);
    expect(await screen.findByTestId('menu-no-file')).toHaveTextContent(
      'The robot shows the standard menu.',
    );
    expect(screen.getByText('No entries of your own')).toBeInTheDocument();
  });

  it('does not ask the robot when not connected', () => {
    const m = run(robot());
    withUi(<Menu />);
    expect(screen.getAllByText(/Not connected to the robot/).length).toBeGreaterThan(0);
    expect(m.calls).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeDisabled();
  });

  it('with no checker: shows the notice and keeps Save off', async () => {
    connectedStatus();
    run(robot({ checker_ok: false, exists: false, check: null, text: '' }));
    withUi(<Menu />);
    const note = await screen.findByTestId('menu-checker-missing');
    expect(note).toHaveTextContent(
      'The robot does not have the menu checker yet. Deploy the delivery package (delivery/tools/deploy.py) before saving a menu.',
    );
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Check with the robot' })).toBeDisabled();
  });

  it('a file the robot rejects: shows its errors and text, and offers the standard menu', async () => {
    connectedStatus();
    const bad: MenuCheck = {
      ...EXAMPLE_CHECK,
      ok: false,
      errors: ['entry 1: program must be a path'],
      custom: {},
    };
    run(robot({ check: bad, text: 'entries: [oops]\n' }));
    const u = userEvent.setup();
    withUi(<Menu />);
    expect(await screen.findByTestId('menu-file-errors')).toHaveTextContent(
      'entry 1: program must be a path',
    );
    const text = screen.getByRole('textbox', { name: /The file on the robot/ });
    expect(text).toHaveAttribute('readonly');
    expect(text).toHaveValue('entries: [oops]\n');
    expect(screen.queryByRole('button', { name: 'Add entry' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeDisabled();
    await u.click(screen.getByRole('button', { name: 'Start from the standard menu' }));
    expect(screen.getByRole('button', { name: 'Add entry' })).toBeInTheDocument();
    expect(screen.queryByTestId('menu-file-errors')).toBeNull();
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeEnabled();
  });

  it('Save is off while the document is invalid', async () => {
    connectedStatus();
    run(robot());
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeEnabled();
    act(() => {
      const d = useMenu.getState().doc;
      useMenu
        .getState()
        .setDoc({ ...d, entries: [{ ...(d.entries[0] as OwnEntry), label: 'X'.repeat(18) }] });
    });
    expect(screen.getByRole('button', { name: 'Save to the robot' })).toBeDisabled();
    expect(screen.getByTestId('menu-local-errors')).toHaveTextContent(/18 characters/);
  });

  it('saving asks first, then sends menu_put with the generated text and confirm', async () => {
    connectedStatus();
    const m = run(robot(), (c) =>
      c.body.cmd === 'menu_put' ? { path: '/p', check: EXAMPLE_CHECK } : undefined,
    );
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    await u.click(screen.getByRole('switch', { name: 'Show Help on the robot' }));
    await u.click(screen.getByRole('button', { name: 'Save to the robot' }));
    const dlg = await screen.findByRole('dialog', { name: 'Save the menu to the robot?' });
    expect(dlg).toHaveTextContent('menu.yaml.bak');
    expect(dlg).toHaveTextContent('Nothing moves now');
    expect(calls(m.calls, 'menu_put')).toHaveLength(0);
    const expected = toYaml(useMenu.getState().doc);
    expect(expected).toContain('hide: [wall_left, wall_right, help]');
    await u.click(within(dlg).getByRole('button', { name: 'Save to the robot' }));
    await waitFor(() => expect(calls(m.calls, 'menu_put')).toHaveLength(1));
    expect(calls(m.calls, 'menu_put')[0]?.body).toMatchObject({
      cmd: 'menu_put',
      text: expected,
      confirm: true,
    });
    // after saving it reads the file again
    await waitFor(() => expect(calls(m.calls, 'menu_get')).toHaveLength(2));
  });

  it('cancelling the save dialog sends nothing', async () => {
    connectedStatus();
    const m = run(robot());
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    await u.click(screen.getByRole('button', { name: 'Save to the robot' }));
    const dlg = await screen.findByRole('dialog', { name: 'Save the menu to the robot?' });
    await u.click(within(dlg).getByRole('button', { name: 'Cancel' }));
    expect(calls(m.calls, 'menu_put')).toHaveLength(0);
  });

  it('shows what the robot says when saving is refused', async () => {
    connectedStatus();
    run(robot(), (c) =>
      c.body.cmd === 'menu_put'
        ? { ok: false, error: 'the checker says it is not valid' }
        : undefined,
    );
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    await u.click(screen.getByRole('button', { name: 'Save to the robot' }));
    const dlg = await screen.findByRole('dialog', { name: 'Save the menu to the robot?' });
    await u.click(within(dlg).getByRole('button', { name: 'Save to the robot' }));
    expect(await screen.findByTestId('menu-save-error')).toHaveTextContent(
      'the checker says it is not valid',
    );
  });

  it('Check with the robot shows its errors and warnings and marks the preview as checked', async () => {
    connectedStatus();
    const answer: MenuCheck = {
      ...EXAMPLE_CHECK,
      ok: false,
      errors: ['entry "hello": program must be a file under ~/robot_code'],
      warnings: ['entry "square": moves is true, so it always asks'],
    };
    const m = run(robot({ exists: false, check: null, text: '' }), (c) =>
      c.body.cmd === 'menu_check' ? { check: answer } : undefined,
    );
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-no-file');
    expect(screen.getByText('Not checked yet')).toBeInTheDocument();
    await u.click(screen.getByRole('switch', { name: 'Show Help on the robot' }));
    await u.click(screen.getByRole('button', { name: 'Check with the robot' }));
    const result = await screen.findByTestId('menu-check-result');
    expect(result).toHaveTextContent('program must be a file under ~/robot_code');
    expect(result).toHaveTextContent('moves is true, so it always asks');
    expect(result).toHaveTextContent('The robot does not accept this menu');
    expect(calls(m.calls, 'menu_check')[0]?.body.text).toBe(toYaml(useMenu.getState().doc));
    // the check is of this exact document; the preview says so and the next change clears it
    await u.click(screen.getByRole('switch', { name: 'Show Undock on the robot' }));
    expect(screen.getByTestId('menu-check-result')).toHaveTextContent('changed since');
  });

  it('shows the generated file in a read-only disclosure', async () => {
    connectedStatus();
    run(robot());
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    const box = screen.getByRole('textbox', { name: /menu file Studio will write/ });
    expect(box).toHaveAttribute('readonly');
    expect((box as HTMLTextAreaElement).value).toContain('version: 1');
    expect((box as HTMLTextAreaElement).value).toContain('id: "square"');
  });

  it('removing an entry asks first (danger dialog)', async () => {
    connectedStatus();
    run(robot());
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-entry-hello');
    await u.click(screen.getByRole('button', { name: 'Remove Hello demo' }));
    const dlg = await screen.findByRole('dialog', { name: 'Remove Hello demo?' });
    expect(screen.getByTestId('menu-entry-hello')).toBeInTheDocument();
    await u.click(within(dlg).getByRole('button', { name: 'Remove entry' }));
    expect(screen.queryByTestId('menu-entry-hello')).toBeNull();
    // the other entry that was after it moves to Dock
    expect(useMenu.getState().doc.entries[0]).toMatchObject({ id: 'square', after: 'dock' });
  });

  it('adding an entry through the dialog puts it in the list and the preview', async () => {
    connectedStatus();
    run(robot({ exists: false, check: null, text: '' }));
    const u = userEvent.setup();
    withUi(<Menu />);
    await screen.findByTestId('menu-no-file');
    await u.click(screen.getByRole('button', { name: 'Add entry' }));
    await u.type(screen.getByRole('textbox', { name: 'Name on the display' }), 'Lights demo');
    await u.type(screen.getByRole('textbox', { name: 'Id' }), 'lights');
    const program = screen.getByRole('textbox', { name: 'Program' });
    await u.clear(program);
    await u.type(program, '~/robot_code/programs/lights.py');
    await u.click(screen.getByRole('button', { name: 'Add entry', hidden: false }));
    expect(await screen.findByTestId('menu-entry-lights')).toBeInTheDocument();
    expect(screen.getByTestId('menu-line-lights').textContent).toBe(' Lights demo');
  });

  it('only one Add entry button is disabled once there are 8 entries', async () => {
    connectedStatus();
    run(robot({ exists: false, check: null, text: '' }));
    withUi(<Menu />);
    await screen.findByTestId('menu-no-file');
    act(() => {
      useMenu.getState().setDoc({
        hide: [],
        entries: Array.from({ length: 8 }, (_, i) => entry({ id: `e${i}`, label: `Entry ${i}` })),
      });
    });
    expect(screen.getByRole('button', { name: 'Add entry' })).toBeDisabled();
    expect(screen.getByText(/the most: 8 entries/)).toBeInTheDocument();
  });

  it('explains what happens when an entry starts', async () => {
    connectedStatus();
    run(robot());
    withUi(<Menu />);
    expect(
      await screen.findByRole('heading', { name: 'What happens when an entry starts' }),
    ).toBeInTheDocument();
  });
});

describe('router', () => {
  it('has the Robot menu route right after Routes', () => {
    const i = ROUTES.findIndex((r) => r.path === '/menu');
    expect(i).toBeGreaterThan(0);
    expect(ROUTES[i - 1]?.path).toBe('/routes');
    expect(routeFor('/menu').label).toBe('Robot menu');
    expect(parseHash('#/menu')).toBe('/menu');
  });
});
