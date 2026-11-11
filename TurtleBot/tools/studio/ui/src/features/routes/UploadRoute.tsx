import { Upload } from 'lucide-react';
import { useId, useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { Button, Field, Input, Panel } from '../../components/ui';
import { notify } from '../../state/feedback';
import { uploadRoute } from './api';
import {
  checkUploadFiles,
  existsMessage,
  formatSize,
  suggestRouteName,
  validRouteName,
} from './model';
import { useRoutes } from './store';

// React does not know the folder attribute; it is passed to the element as it is.
const FOLDER_ATTRS = { webkitdirectory: '', directory: '' } as Record<string, string>;

/** Upload a route folder made on a computer by delivery/tools/plan_route.py. */
export function UploadRoute({ connected = true }: { connected?: boolean }) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [taken, setTaken] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const routesList = useRoutes((s) => s.list);
  const known = useMemo(() => routesList?.routes.map((r) => r.name) ?? [], [routesList]);
  const loadRoutes = useRoutes((s) => s.loadRoutes);

  const check = files.length > 0 ? checkUploadFiles(files) : null;
  const nameCheck = validRouteName(name);
  const exists = name !== '' && (taken.includes(name) || known.includes(name));
  const nameError =
    name === '' ? null : !nameCheck.ok ? nameCheck.message : exists ? existsMessage(name) : null;
  const canUpload = connected && !busy && !!check?.ok && nameCheck.ok && !exists;

  const choose = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    setFiles(picked);
    setError(null);
    setTaken([]);
    const c = checkUploadFiles(picked);
    setName(c.folder ? suggestRouteName(c.folder) : '');
  };

  const send = async () => {
    if (!canUpload || !check) return;
    const top = files.filter((f) => (f.webkitRelativePath || f.name).split('/').length <= 2);
    setBusy(true);
    setError(null);
    const r = await uploadRoute(name, top);
    setBusy(false);
    if (r.ok) {
      notify('ok', `Uploaded the route ${name}.`);
      setFiles([]);
      setName('');
      if (inputRef.current) inputRef.current.value = '';
      void loadRoutes();
    } else if (r.exists) {
      setTaken((t) => [...t, name]);
    } else setError(r.error);
  };

  return (
    <Panel title="Upload a route">
      <p className="dim small">
        A route folder is made on a computer by delivery/tools/plan_route.py. It holds route.yaml,
        map.yaml, keepout_mask.yaml and speed_mask.yaml. Choose that folder to copy it to the robot.
        Nothing moves.
      </p>
      <div className="route-pick">
        <label htmlFor={inputId} className="field-label">
          Choose a route folder
        </label>
        <input
          id={inputId}
          ref={inputRef}
          type="file"
          multiple
          className="route-file"
          disabled={busy}
          onChange={choose}
          {...FOLDER_ATTRS}
        />
      </div>
      {check ? (
        <div className="route-found" data-testid="upload-check">
          <p className="small">
            Found in {check.folder || 'the chosen folder'}: {check.found.length} file
            {check.found.length === 1 ? '' : 's'}, {formatSize(check.total)}.
          </p>
          {check.missing.length > 0 ? (
            <p className="mapping-error" role="alert">
              Missing: {check.missing.join(', ')}.
            </p>
          ) : (
            <p className="small">All four route files are there.</p>
          )}
          {check.nested.length > 0 ? (
            <p className="dim small">
              Ignored, because they are inside subfolders: {check.nested.join(', ')}.
            </p>
          ) : null}
          {check.tooBig ? (
            <p className="mapping-error" role="alert">
              The files are over 32 MB together ({formatSize(check.total)}). The robot would refuse
              them.
            </p>
          ) : null}
        </div>
      ) : null}
      {check ? (
        <form
          className="route-upload-form"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <Field
            label="Name on the robot"
            hint="Letters, digits, hyphens and underscores. Up to 48 characters."
            error={nameError}
          >
            {(p) => (
              <Input
                {...p}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setError(null);
                }}
                maxLength={64}
              />
            )}
          </Field>
          <Button
            variant="primary"
            type="submit"
            icon={<Upload size={14} aria-hidden="true" />}
            disabled={!canUpload}
            loading={busy}
          >
            Upload
          </Button>
        </form>
      ) : null}
      {error ? (
        <p className="mapping-error" role="alert">
          Could not upload the route. {error}
        </p>
      ) : null}
      {!connected ? <p className="dim small">Not connected to the robot.</p> : null}
    </Panel>
  );
}
