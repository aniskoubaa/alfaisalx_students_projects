import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Badge, Button, ConfirmDialog, EmptyState, Panel } from '../../components/ui';
import { EntryEditor } from './EntryEditor';
import { MAX_ENTRIES, builtinLabel, newEntry, removeEntry, upsertEntry } from './model';
import type { MenuDoc, OwnEntry } from './model';

interface Editing {
  index: number;
  entry: OwnEntry;
}

/** The person's own entries: add, change, remove. */
export function OwnEntries({
  doc,
  onChange,
  disabled = false,
}: {
  doc: MenuDoc;
  onChange: (doc: MenuDoc) => void;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  const full = doc.entries.length >= MAX_ENTRIES;
  const placeName = (id: string): string => {
    const own = doc.entries.find((e) => e.id === id);
    return own ? own.label || own.id : builtinLabel(id);
  };
  const gone = removing === null ? undefined : doc.entries[removing];

  return (
    <Panel
      title="Your own entries"
      actions={
        <Button
          size="sm"
          variant="primary"
          icon={<Plus size={14} aria-hidden="true" />}
          disabled={disabled || full}
          onClick={() => setEditing({ index: -1, entry: newEntry() })}
        >
          Add entry
        </Button>
      }
    >
      {doc.entries.length === 0 ? (
        <EmptyState compact title="No entries of your own">
          Add one to start a program from the robot&apos;s screen.
        </EmptyState>
      ) : (
        <ul className="menu-own">
          {doc.entries.map((e, i) => (
            <li key={e.id || i} className="menu-own-item" data-testid={`menu-entry-${e.id}`}>
              <div className="menu-own-main">
                <strong>{e.label}</strong>
                <span className="mono small dim">{e.program}</span>
                <span className="dim small">
                  After {placeName(e.after)}, time limit {e.timeout} s
                </span>
                <span className="badge-list">
                  {e.moves ? <Badge tone="warn">Moves the robot</Badge> : null}
                  {e.undocks ? <Badge tone="warn">Undocks by itself</Badge> : null}
                  {e.confirm && !e.moves ? <Badge tone="info">Asks first</Badge> : null}
                </span>
              </div>
              <div className="menu-own-actions">
                <Button
                  size="sm"
                  icon={<Pencil size={14} aria-hidden="true" />}
                  aria-label={`Edit ${e.label}`}
                  disabled={disabled}
                  onClick={() => setEditing({ index: i, entry: e })}
                >
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  icon={<Trash2 size={14} aria-hidden="true" />}
                  aria-label={`Remove ${e.label}`}
                  disabled={disabled}
                  onClick={() => setRemoving(i)}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="dim small">
        {full
          ? `That is the most: ${MAX_ENTRIES} entries of your own. Remove one to add another.`
          : `Up to ${MAX_ENTRIES} entries of your own (${doc.entries.length} now).`}
      </p>
      {editing ? (
        <EntryEditor
          initial={editing.entry}
          isNew={editing.index < 0}
          others={doc.entries.filter((_, i) => i !== editing.index)}
          onSave={(entry) => {
            onChange(upsertEntry(doc, editing.index, entry));
            setEditing(null);
          }}
          onCancel={() => setEditing(null)}
        />
      ) : null}
      <ConfirmDialog
        open={gone !== undefined}
        title={`Remove ${gone?.label ?? 'the entry'}?`}
        body="It leaves the menu when you save to the robot. The program file on the robot is not deleted."
        confirmLabel="Remove entry"
        tone="danger"
        onConfirm={() => {
          if (removing !== null) onChange(removeEntry(doc, removing));
          setRemoving(null);
        }}
        onCancel={() => setRemoving(null)}
      />
    </Panel>
  );
}
