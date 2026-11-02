import * as RD from '@radix-ui/react-dialog';
import { Search } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useStudio } from '../../state/store';
import { filterCommands } from './commands';
import type { Command } from './commands';
import { paletteCommands, usePalette } from './paletteCommands';

/**
 * Ctrl+K (Cmd+K on a Mac). Type to find a screen or a safe action; Enter runs it.
 * Esc closes it only while the search box has focus, where Esc is not the E-STOP.
 */
export function CommandPalette() {
  const open = usePalette((s) => s.open);
  const setOpen = usePalette((s) => s.setOpen);
  return (
    <RD.Root open={open} onOpenChange={setOpen}>
      <RD.Portal>
        <RD.Overlay className="dialog-overlay palette-overlay" />
        <RD.Content
          className="palette"
          aria-describedby={undefined}
          onEscapeKeyDown={(e) => e.preventDefault()}
          onOpenAutoFocus={(e) => {
            // The search box takes focus itself.
            e.preventDefault();
          }}
        >
          <RD.Title className="sr-only">Command palette</RD.Title>
          <PaletteBody onDone={() => setOpen(false)} />
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

function PaletteBody({ onDone }: { onDone: () => void }) {
  const state = useStudio((s) => s);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    input.current?.focus();
  }, []);

  const all = useMemo(() => paletteCommands(state), [state]);
  const found = useMemo(() => filterCommands(all, query), [all, query]);
  const idx = Math.min(active, Math.max(0, found.length - 1));

  const run = (c: Command | undefined) => {
    if (!c || c.disabled) return;
    onDone();
    void Promise.resolve(c.run());
  };

  const groups: Array<{ name: string; items: Array<{ c: Command; i: number }> }> = [];
  found.forEach((c, i) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) {
      g = { name: c.group, items: [] };
      groups.push(g);
    }
    g.items.push({ c, i });
  });

  return (
    <div className="palette-body">
      <div className="palette-search">
        <Search size={18} aria-hidden="true" />
        <input
          ref={input}
          className="palette-input"
          type="text"
          role="combobox"
          aria-label="Search commands"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={found[idx] ? `${listId}-${idx}` : undefined}
          placeholder="Type a command or a screen name"
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive(Math.min(found.length - 1, idx + 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive(Math.max(0, idx - 1));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              run(found[idx]);
            } else if (e.key === 'Escape') {
              e.preventDefault();
              onDone();
            }
          }}
        />
      </div>
      <div id={listId} role="listbox" aria-label="Commands" className="palette-list">
        {found.length === 0 ? (
          <p className="palette-empty">No command matches &ldquo;{query}&rdquo;.</p>
        ) : null}
        {groups.map((g) => (
          <div key={g.name} role="group" aria-label={g.name}>
            <p className="palette-group" aria-hidden="true">
              {g.name}
            </p>
            {g.items.map(({ c, i }) => (
              <div
                key={c.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === idx}
                aria-disabled={c.disabled ? true : undefined}
                className={
                  'palette-item' +
                  (i === idx ? ' is-active' : '') +
                  (c.disabled ? ' is-disabled' : '')
                }
                onMouseMove={() => setActive(i)}
                onClick={() => run(c)}
              >
                <span>{c.label}</span>
                {c.disabled ? <span className="palette-why">{c.disabled}</span> : null}
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="palette-foot small dim">
        Up and down to choose, Enter to run. Driving and other robot movement are not in this list.
      </p>
    </div>
  );
}
