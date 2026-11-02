import { useMemo, useState } from 'react';
import { NEW_NAME_RE } from '../../lib/files';
import { nameFromTemplate, templateList } from '../../lib/templates';
import { useAsyncAction } from '../../lib/useAsync';
import { createProgram } from '../../state/codeActions';
import { useStudio } from '../../state/store';
import { Button, Checkbox, Dialog, Field, Input, Select } from '../../components/ui';

const EMPTY = '__empty__';

export function NewProgramDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const templates = useStudio((s) => s.templates);
  const catalog = useStudio((s) => s.catalog);
  const files = useStudio((s) => s.files);
  const list = useMemo(() => templateList(templates, catalog), [templates, catalog]);

  const [tmpl, setTmpl] = useState<string>(list[0]?.name ?? EMPTY);
  const [file, setFile] = useState(() => nameFromTemplate(list[0]));
  const [replace, setReplace] = useState(false);

  const current = list.find((t) => t.name === tmpl);
  const validName = NEW_NAME_RE.test(file.trim());
  const exists = files.some((f) => f.name === file.trim());
  const blocked = !validName || (exists && !replace);

  const create = useAsyncAction(async () => {
    const ok = await createProgram({
      template: tmpl === EMPTY ? null : tmpl,
      file: file.trim(),
      replace,
    });
    if (ok) onClose();
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="New program"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={blocked}
            loading={create.pending}
            onClick={() => void create.run()}
          >
            Create program
          </Button>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (!blocked) void create.run();
        }}
      >
        <Field label="Start from">
          {(p) => (
            <Select
              {...p}
              value={tmpl}
              onChange={(e) => {
                setTmpl(e.target.value);
                setFile(nameFromTemplate(list.find((t) => t.name === e.target.value)));
                setReplace(false);
              }}
            >
              {list.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.entry.title ?? t.name}
                </option>
              ))}
              <option value={EMPTY}>Empty program</option>
            </Select>
          )}
        </Field>
        <p className="dim small">
          {current
            ? (current.entry.summary ?? '')
            : 'A tiny file that only prints a line. Good for starting from scratch.'}
        </p>
        <Field
          label="File name"
          hint="Letters, digits, - and _, ending in .py"
          error={
            validName
              ? undefined
              : 'The name needs letters, digits, - or _, then .py. For example my_spin.py.'
          }
        >
          {(p) => (
            <Input
              {...p}
              className="mono"
              value={file}
              onChange={(e) => {
                setFile(e.target.value);
                setReplace(false);
              }}
            />
          )}
        </Field>
        {validName && exists ? (
          <div className="note note-warn">
            <strong>{file.trim()}</strong> already exists on the robot.
            <Checkbox
              label="Replace it (the old version is kept as a .bak copy)"
              checked={replace}
              onChange={(e) => setReplace(e.target.checked)}
            />
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
