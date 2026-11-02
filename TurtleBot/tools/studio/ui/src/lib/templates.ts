import type { CatalogEntry, CatalogTemplate } from '../api';

export interface TemplateItem {
  name: string;
  entry: CatalogEntry;
}

/** The template list from the catalog, whichever shape the backend sent. */
export function templateList(
  templates: CatalogTemplate[],
  programs: Record<string, CatalogEntry>,
): TemplateItem[] {
  const out: TemplateItem[] = [];
  for (const t of templates) {
    if (typeof t === 'string') out.push({ name: t, entry: programs[t] ?? {} });
    else {
      const name = t.name ?? t.file;
      if (name) out.push({ name, entry: t.entry ?? (t as CatalogEntry) });
    }
  }
  return out;
}

/** Suggested file name for a new program made from a template. */
export const nameFromTemplate = (t: TemplateItem | undefined): string =>
  t ? 'my_' + t.name.replace(/^my_/, '') : 'my_program.py';

export const SKELETON =
  '#!/usr/bin/env python3\n"""My program. Describe here what it does."""\n\nprint("Hello from the TurtleBot")\n';
