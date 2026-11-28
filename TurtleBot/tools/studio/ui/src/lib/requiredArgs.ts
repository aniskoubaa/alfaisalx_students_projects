import type { CatalogEntry } from '../api';

/** Positional arguments the program cannot start without (catalog help starting "optional" opts out). */
export function requiredArgNames(entry: CatalogEntry | undefined): string[] {
  return (entry?.args ?? [])
    .filter((a) => !a.name.startsWith('-') && !/^\s*optional/i.test(a.help ?? ''))
    .map((a) => a.name);
}

/** The example to put in an empty box: the first dry run, else the first example, else nothing. */
export function safeExample(entry: CatalogEntry | undefined): string {
  const ex = entry?.examples ?? [];
  return (ex.find((x) => x.args.includes('--dry-run')) ?? ex[0])?.args ?? '';
}

/** Plain words shown when Run is pressed with an empty box but the program needs arguments. */
export function missingArgsMessage(name: string, required: string[], filled: boolean): string {
  const need = required.join(', ');
  return filled
    ? `${name} needs ${need} first. Studio put a safe example in the box (a dry run: nothing moves). Change it if you like, then press Run.`
    : `${name} needs ${need} first. Type it in the arguments box, then press Run.`;
}

/** Text for an empty arguments box: the program's own example, or "Optional" when it has none. */
export function argsPlaceholder(
  entry: CatalogEntry | undefined,
  desc: { example?: string } | undefined,
): string {
  // desc.example: the robot reads it from the "Run it on the robot:" line of the program's docstring
  const example = safeExample(entry) || (desc?.example ?? '').trim();
  return example ? `for example ${example}` : 'Optional';
}
