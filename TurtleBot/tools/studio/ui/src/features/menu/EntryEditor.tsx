import { useState } from 'react';
import { Button, Checkbox, Dialog, Field, Input, Select } from '../../components/ui';
import { MAX_LABEL, labelCounter, normalizeFlags, placeOptions, validateEntry } from './model';
import type { EntryErrors, OwnEntry } from './model';

/** Arguments are typed one per line; empty lines are dropped. */
export const parseArgs = (text: string): string[] =>
  text
    .split('\n')
    .map((l) => l.replace(/\r$/, ''))
    .filter((l) => l.trim() !== '');

/** The dialog that adds or changes one of the person's own entries. */
export function EntryEditor({
  initial,
  isNew,
  others,
  onSave,
  onCancel,
}: {
  initial: OwnEntry;
  isNew: boolean;
  /** The other own entries (not the one being edited). */
  others: readonly OwnEntry[];
  onSave: (entry: OwnEntry) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<OwnEntry>(initial);
  const [argsText, setArgsText] = useState(initial.args.join('\n'));
  const [timeoutText, setTimeoutText] = useState(String(initial.timeout));
  const [attempted, setAttempted] = useState(false);

  const timeout = timeoutText.trim() === '' ? Number.NaN : Number(timeoutText);
  const entry = normalizeFlags({ ...draft, args: parseArgs(argsText), timeout });
  const errors = validateEntry(entry, others);
  const show = (f: keyof EntryErrors, changed: boolean): string | undefined =>
    attempted || changed ? errors[f] : undefined;

  const set = (patch: Partial<OwnEntry>) => setDraft((d) => ({ ...d, ...patch }));
  const forcedConfirm = entry.moves || entry.undocks;

  const submit = () => {
    setAttempted(true);
    if (Object.keys(errors).length === 0) onSave(entry);
  };

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
      title={isNew ? 'Add an entry' : 'Change entry'}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit}>
            {isNew ? 'Add entry' : 'Save entry'}
          </Button>
        </>
      }
    >
      <div className="menu-editor">
        <Field
          label="Name on the display"
          hint={
            <span data-testid="menu-label-counter">
              {labelCounter(draft.label)} (at most {MAX_LABEL})
            </span>
          }
          error={show('label', draft.label !== initial.label)}
        >
          {(p) => (
            <Input {...p} value={draft.label} onChange={(e) => set({ label: e.target.value })} />
          )}
        </Field>
        <Field
          label="Id"
          hint="Letters a-z, digits and _ , starting with a letter. Other entries use it to find this one."
          error={show('id', draft.id !== initial.id)}
        >
          {(p) => <Input {...p} value={draft.id} onChange={(e) => set({ id: e.target.value })} />}
        </Field>
        <Field
          label="Program"
          hint="A .py or .sh file on the robot, as ~/robot_code/... or relative to ~/robot_code."
          error={show('program', draft.program !== initial.program)}
        >
          {(p) => (
            <Input
              {...p}
              className="mono"
              value={draft.program}
              onChange={(e) => set({ program: e.target.value })}
            />
          )}
        </Field>
        <Field
          label="Arguments"
          hint="One per line. Passed as they are, no shell."
          error={show('args', argsText !== initial.args.join('\n'))}
        >
          {(p) => (
            <textarea
              {...p}
              className="input mono menu-args"
              rows={3}
              spellCheck={false}
              value={argsText}
              onChange={(e) => setArgsText(e.target.value)}
            />
          )}
        </Field>
        <div className="menu-flags">
          <Checkbox
            label="Ask before starting"
            checked={entry.confirm}
            disabled={forcedConfirm}
            onChange={(e) => set({ confirm: e.target.checked })}
          />
          <Checkbox
            label="Moves the robot"
            checked={entry.moves}
            disabled={entry.undocks}
            onChange={(e) => set({ moves: e.target.checked })}
          />
          <Checkbox
            label="Undocks by itself"
            checked={entry.undocks}
            onChange={(e) => set({ undocks: e.target.checked })}
          />
        </div>
        {forcedConfirm ? (
          <p className="dim small" data-testid="menu-forced-note">
            {entry.undocks
              ? 'A program that undocks the robot also moves it, and a moving program always asks first, so those two stay on.'
              : 'A program that moves the robot always asks first, so that stays on.'}
          </p>
        ) : null}
        <Field
          label="Time limit in seconds"
          hint="The program is stopped when the time is up."
          error={show('timeout', timeoutText !== String(initial.timeout))}
        >
          {(p) => (
            <Input
              {...p}
              inputMode="numeric"
              value={timeoutText}
              onChange={(e) => setTimeoutText(e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Place after"
          hint="The entry goes right below this one. A hidden built-in entry still marks the place."
          error={show('after', draft.after !== initial.after)}
        >
          {(p) => (
            <Select {...p} value={draft.after} onChange={(e) => set({ after: e.target.value })}>
              {placeOptions(others, draft.id).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
    </Dialog>
  );
}
