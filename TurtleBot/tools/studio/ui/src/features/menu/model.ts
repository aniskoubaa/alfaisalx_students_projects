/**
 * The robot's front-panel menu file, as the page edits it. Pure code, no network.
 * The robot's own checker is the single source of truth; the rules here only give instant feedback
 * (they mirror delivery/menu_config.py).
 */
import type { MenuCheck } from '../../api';

export const MAX_LABEL = 17;
export const DISPLAY_CHARS = 18;
export const MAX_ENTRIES = 8;
export const MAX_ARGS = 10;
export const MAX_ARG_CHARS = 200;
export const MAX_PROGRAM_CHARS = 200;
export const MAX_FILE_CHARS = 16000;
export const DEFAULT_TIMEOUT_S = 300;
export const MAX_TIMEOUT_S = 3600;
export const PROGRAM_PREFIX = '~/robot_code/';

export interface Builtin {
  id: string;
  label: string;
  locked: boolean;
  hideable: boolean;
}

/** In the robot's order. The trip entry reads "Back to the lab" on the way back. */
export const BUILTINS: readonly Builtin[] = [
  { id: 'trip', label: 'Go to food court', locked: true, hideable: false },
  { id: 'dock', label: 'Dock', locked: true, hideable: false },
  { id: 'undock', label: 'Undock', locked: false, hideable: true },
  { id: 'estop', label: 'EStop', locked: true, hideable: false },
  { id: 'wall_left', label: 'Wall Follow Left', locked: false, hideable: true },
  { id: 'wall_right', label: 'Wall Follow Right', locked: false, hideable: true },
  { id: 'power', label: 'Power', locked: true, hideable: false },
  { id: 'help', label: 'Help', locked: false, hideable: true },
];

export const BUILTIN_IDS: readonly string[] = BUILTINS.map((b) => b.id);
export const HIDEABLE: readonly string[] = BUILTINS.filter((b) => b.hideable).map((b) => b.id);
/** Labels an own entry may not use. */
export const RESERVED_LABELS: readonly string[] = [
  ...BUILTINS.map((b) => b.label),
  'Back to the lab',
];
export const LAST_BUILTIN = 'help';

export interface OwnEntry {
  id: string;
  label: string;
  program: string;
  args: string[];
  confirm: boolean;
  moves: boolean;
  undocks: boolean;
  timeout: number;
  after: string;
}

export interface MenuDoc {
  hide: string[];
  entries: OwnEntry[];
}

export const emptyDoc = (): MenuDoc => ({ hide: [], entries: [] });

export function newEntry(after: string = LAST_BUILTIN): OwnEntry {
  return {
    id: '',
    label: '',
    program: PROGRAM_PREFIX,
    args: [],
    confirm: false,
    moves: false,
    undocks: false,
    timeout: DEFAULT_TIMEOUT_S,
    after,
  };
}

export const builtinLabel = (id: string): string => BUILTINS.find((b) => b.id === id)?.label ?? id;

/** Make the flags agree the way the robot does: undocks implies moves, moves implies confirm. */
export function normalizeFlags<T extends Pick<OwnEntry, 'confirm' | 'moves' | 'undocks'>>(e: T): T {
  const moves = e.moves || e.undocks;
  return { ...e, moves, confirm: e.confirm || moves };
}

/** The document that a robot check describes (entries in the order of the menu). */
export function docFromCheck(check: MenuCheck): MenuDoc {
  const custom = check.custom ?? {};
  const order = (check.layout ?? []).filter((k) => k in custom);
  for (const k of Object.keys(custom)) if (!order.includes(k)) order.push(k);
  const entries: OwnEntry[] = order.map((k) => {
    const c = custom[k] as MenuCheck['custom'][string];
    return {
      id: c.id,
      label: c.label,
      program: PROGRAM_PREFIX + c.program,
      args: [...(c.args ?? [])],
      confirm: c.confirm,
      moves: c.moves,
      undocks: c.undocks,
      timeout: c.timeout,
      after: c.after,
    };
  });
  return { hide: HIDEABLE.filter((h) => (check.hide ?? []).includes(h)), entries };
}

/* ---------- validation ---------- */

export type EntryField = 'id' | 'label' | 'program' | 'args' | 'timeout' | 'after';
export type EntryErrors = Partial<Record<EntryField, string>>;

const ID_RE = /^[a-z][a-z0-9_]{0,23}$/;

export const isPrintableAscii = (s: string): boolean => /^[\x20-\x7e]*$/.test(s);

/** The error in a program path, or '' when it is acceptable. */
export function programError(value: string): string {
  const v = value.trim();
  if (!v) return 'Enter the path of the program.';
  if (v.length > MAX_PROGRAM_CHARS) return `At most ${MAX_PROGRAM_CHARS} characters.`;
  if (v.includes('\\')) return 'Use / in paths, not \\.';
  if (v.includes('\0')) return 'The path has a character that is not allowed.';
  let rel: string;
  if (v.startsWith('~')) {
    if (!v.startsWith(PROGRAM_PREFIX)) return 'The program must be under ~/robot_code/.';
    rel = v.slice(PROGRAM_PREFIX.length);
  } else if (v.startsWith('/')) {
    return 'Write the path as ~/robot_code/... or relative to ~/robot_code (for example programs/hello.py).';
  } else {
    rel = v;
  }
  const parts = rel.split('/');
  if (parts.includes('..')) return 'The path may not contain "..".';
  if (!rel || parts.some((p) => p === '')) return 'The path must name a file under ~/robot_code/.';
  const norm = parts.filter((p) => p !== '.');
  if (norm.length === 0) return 'The path must name a file under ~/robot_code/.';
  if (!/\.(py|sh)$/.test(norm[norm.length - 1] as string))
    return 'The program must be a .py or .sh file.';
  return '';
}

/** Follows `after` from an entry; true when it comes back to a loop instead of a built-in. */
function leadsInLoop(start: string, byId: Map<string, OwnEntry>): boolean {
  const seen = new Set<string>([start]);
  let at = byId.get(start)?.after ?? '';
  while (byId.has(at)) {
    if (seen.has(at)) return true;
    seen.add(at);
    at = (byId.get(at) as OwnEntry).after;
  }
  return false;
}

/** Errors of one entry, given the other own entries (those already in the document). */
export function validateEntry(entry: OwnEntry, others: readonly OwnEntry[]): EntryErrors {
  const out: EntryErrors = {};
  if (!ID_RE.test(entry.id)) {
    out.id = 'Use a-z, 0-9 and _ , start with a letter, at most 24 characters.';
  } else if (BUILTIN_IDS.includes(entry.id)) {
    out.id = 'This is the id of a built-in entry. Use another id.';
  } else if (others.some((o) => o.id === entry.id)) {
    out.id = 'Another entry already uses this id.';
  }

  const label = entry.label.trim();
  if (!label) out.label = 'Enter the name shown on the display.';
  else if (label.length > MAX_LABEL)
    out.label = `${label.length} characters; the display fits ${MAX_LABEL} (one is the cursor).`;
  else if (!isPrintableAscii(label)) out.label = 'Use plain letters, digits and punctuation only.';
  else if (RESERVED_LABELS.some((r) => r.toLowerCase() === label.toLowerCase()))
    out.label = 'This is the name of a built-in entry. Use another name.';
  else if (others.some((o) => o.label.trim().toLowerCase() === label.toLowerCase()))
    out.label = 'Another entry already uses this name.';

  const pe = programError(entry.program);
  if (pe) out.program = pe;

  if (entry.args.length > MAX_ARGS) out.args = `At most ${MAX_ARGS} arguments.`;
  else if (entry.args.some((a) => a.length > MAX_ARG_CHARS))
    out.args = `Each argument is at most ${MAX_ARG_CHARS} characters.`;
  else if (entry.args.some((a) => a.includes('\0')))
    out.args = 'An argument has a character that is not allowed.';

  if (!Number.isInteger(entry.timeout) || entry.timeout < 1 || entry.timeout > MAX_TIMEOUT_S)
    out.timeout = `A whole number of seconds from 1 to ${MAX_TIMEOUT_S}.`;

  if (entry.after === entry.id && entry.id) out.after = 'An entry cannot be placed after itself.';
  else if (!BUILTIN_IDS.includes(entry.after) && !others.some((o) => o.id === entry.after))
    out.after = 'Choose a built-in entry or another entry of yours.';
  else {
    const byId = new Map<string, OwnEntry>(others.map((o) => [o.id, o]));
    byId.set(entry.id, entry);
    if (leadsInLoop(entry.id, byId))
      out.after = 'These entries are placed after each other in a loop.';
  }
  return out;
}

export interface DocValidation {
  ok: boolean;
  /** Per entry id (index when the id is empty). */
  byEntry: Record<string, EntryErrors>;
  /** Problems of the whole document, then each entry's, in words. */
  messages: string[];
}

export function validateDoc(doc: MenuDoc): DocValidation {
  const byEntry: Record<string, EntryErrors> = {};
  const messages: string[] = [];
  if (doc.entries.length > MAX_ENTRIES)
    messages.push(`At most ${MAX_ENTRIES} entries of your own.`);
  for (const h of doc.hide)
    if (!HIDEABLE.includes(h)) messages.push(`${builtinLabel(h)} cannot be hidden.`);
  doc.entries.forEach((e, i) => {
    const errs = validateEntry(
      e,
      doc.entries.filter((_, j) => j !== i),
    );
    if (Object.keys(errs).length > 0) {
      byEntry[e.id || `#${i + 1}`] = errs;
      for (const m of Object.values(errs))
        messages.push(`${e.label || e.id || `Entry ${i + 1}`}: ${m}`);
    }
  });
  const text = toYaml(doc);
  if (text.length > MAX_FILE_CHARS) messages.push('The file is too long (over 16000 characters).');
  return { ok: messages.length === 0, byEntry, messages };
}

/* ---------- YAML ---------- */

/** A YAML double-quoted string: backslash and quote escaped, control characters as \xNN. */
export function yq(s: string): string {
  let out = '"';
  for (const ch of s) {
    const c = ch.codePointAt(0) as number;
    if (ch === '\\') out += '\\\\';
    else if (ch === '"') out += '\\"';
    else if (c < 0x20 || c === 0x7f) out += '\\x' + c.toString(16).padStart(2, '0');
    else out += ch;
  }
  return out + '"';
}

/** The file the robot accepts. */
export function toYaml(doc: MenuDoc): string {
  const lines: string[] = ['version: 1'];
  if (doc.hide.length > 0) lines.push(`hide: [${doc.hide.join(', ')}]`);
  if (doc.entries.length === 0) return lines.join('\n') + '\n';
  lines.push('entries:');
  for (const e of doc.entries) {
    lines.push(`  - id: ${yq(e.id)}`);
    lines.push(`    label: ${yq(e.label.trim())}`);
    lines.push(`    program: ${yq(e.program.trim())}`);
    if (e.args.length > 0) lines.push(`    args: [${e.args.map(yq).join(', ')}]`);
    lines.push(`    confirm: ${e.confirm ? 'true' : 'false'}`);
    lines.push(`    moves: ${e.moves ? 'true' : 'false'}`);
    lines.push(`    undocks: ${e.undocks ? 'true' : 'false'}`);
    lines.push(
      `    timeout: ${Number.isFinite(e.timeout) ? Math.trunc(e.timeout) : DEFAULT_TIMEOUT_S}`,
    );
    lines.push(`    after: ${yq(e.after)}`);
  }
  return lines.join('\n') + '\n';
}

/* ---------- preview ---------- */

/**
 * The menu keys top to bottom as the robot would show them. Own entries go right below their `after`
 * target in file order; a hidden built-in still marks the place; nothing goes above the trip entry;
 * the default place is the end of the list.
 */
export function previewLayout(doc: MenuDoc): string[] {
  const own = new Set(doc.entries.map((e) => e.id));
  const children = new Map<string, string[]>();
  for (const e of doc.entries) {
    const at = BUILTIN_IDS.includes(e.after) || own.has(e.after) ? e.after : LAST_BUILTIN;
    const list = children.get(at) ?? [];
    list.push(e.id);
    children.set(at, list);
  }
  const out: string[] = [];
  const emit = (key: string, depth: number): void => {
    if (depth > MAX_ENTRIES + 1) return;
    if (!doc.hide.includes(key)) out.push(key);
    for (const c of children.get(key) ?? []) emit(c, depth + 1);
  };
  for (const id of BUILTIN_IDS) emit(id, 0);
  // Entries caught in a loop are never reached; the robot rejects such a file, so just keep them visible.
  for (const e of doc.entries) if (!out.includes(e.id)) out.push(e.id);
  return out;
}

export interface PreviewLine {
  id: string;
  label: string;
  /** One of the robot's own entries (built in, cannot be changed). */
  builtin: boolean;
}

export interface Preview {
  lines: PreviewLine[];
  /** Built-in entries the file hides. */
  hidden: PreviewLine[];
}

/** What the picture shows: from the robot's check when it is current, else from the document. */
export function buildPreview(doc: MenuDoc, check: MenuCheck | null): Preview {
  const useCheck = check !== null && check.ok && Array.isArray(check.layout);
  const keys = useCheck ? check.layout : previewLayout(doc);
  const own = new Map(doc.entries.map((e) => [e.id, e.label.trim()]));
  const labelOf = (k: string): string =>
    (useCheck ? check.labels[k] : undefined) ?? own.get(k) ?? builtinLabel(k);
  const hide = useCheck ? check.hide : doc.hide;
  return {
    lines: keys.map((k) => ({ id: k, label: labelOf(k), builtin: BUILTIN_IDS.includes(k) })),
    hidden: BUILTINS.filter((b) => hide.includes(b.id)).map((b) => ({
      id: b.id,
      label: b.label,
      builtin: true,
    })),
  };
}

/** One display line: 18 characters, the first is the cursor. */
export function displayLine(label: string, first: boolean): string {
  return ((first ? '>' : ' ') + label).slice(0, DISPLAY_CHARS);
}

export const labelCounter = (label: string): string => `${label.trim().length} of ${MAX_LABEL}`;

/** The places an entry can be put: built-ins first, then the other own entries. */
export function placeOptions(
  entries: readonly OwnEntry[],
  selfId: string,
): Array<{ id: string; label: string }> {
  return [
    ...BUILTINS.map((b) => ({ id: b.id, label: `${b.label}` })),
    ...entries
      .filter((e) => e.id !== selfId && e.id)
      .map((e) => ({ id: e.id, label: e.label || e.id })),
  ];
}

/** Hide or show a built-in; only the four that can be hidden are changed. */
export function setHidden(doc: MenuDoc, id: string, hidden: boolean): MenuDoc {
  if (!HIDEABLE.includes(id)) return doc;
  const set = new Set(doc.hide);
  if (hidden) set.add(id);
  else set.delete(id);
  return { ...doc, hide: HIDEABLE.filter((h) => set.has(h)) };
}

/** Replace the entry at `index` (or add when index is -1); entries that were placed after the old id follow a rename. */
export function upsertEntry(doc: MenuDoc, index: number, entry: OwnEntry): MenuDoc {
  const clean = normalizeFlags({
    ...entry,
    label: entry.label.trim(),
    program: entry.program.trim(),
  });
  if (index < 0) return { ...doc, entries: [...doc.entries, clean] };
  const old = doc.entries[index];
  const entries = doc.entries.map((e, i) => {
    if (i === index) return clean;
    return old && old.id !== clean.id && e.after === old.id ? { ...e, after: clean.id } : e;
  });
  return { ...doc, entries };
}

/** Remove an entry; entries placed after it move to where it was. */
export function removeEntry(doc: MenuDoc, index: number): MenuDoc {
  const gone = doc.entries[index];
  if (!gone) return doc;
  return {
    ...doc,
    entries: doc.entries
      .filter((_, i) => i !== index)
      .map((e) => (e.after === gone.id ? { ...e, after: gone.after } : e)),
  };
}
