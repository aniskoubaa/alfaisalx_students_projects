import { useState } from 'react';
import { Button, ConfirmDialog, Dialog, Field, Input } from '../../components/ui';
import { notify } from '../../state/feedback';
import { disarm } from '../teleop/driver';
import { saveMap } from './api';
import { suggestName, validMapName } from './model';
import { useMapping } from './store';

/**
 * Ask for a name, then save. When the robot says the name is taken, ask a second question and
 * send the save again with overwrite on.
 */
export function SaveMapDialog({
  open,
  onClose,
  now,
}: {
  open: boolean;
  onClose: () => void;
  /** The clock for the suggested name (tests). */
  now?: Date;
}) {
  const [name, setName] = useState(() => suggestName(now));
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [replace, setReplace] = useState<string | null>(null);

  const check = validMapName(name);
  const shown = touched && !check.ok ? check.message : null;

  const send = async (overwrite: boolean) => {
    setBusy(true);
    setError(null);
    disarm('You are saving the map.');
    const r = await saveMap(name, overwrite);
    setBusy(false);
    if (r.ok) {
      const { ok: _ok, ...info } = r;
      void _ok;
      useMapping.getState().setInfo(info);
      setReplace(null);
      onClose();
      return;
    }
    if (r.exists && !overwrite) {
      setReplace(name);
      return;
    }
    setReplace(null);
    setError(r.error);
    notify('error', 'The map was not saved. ' + r.error);
  };

  const submit = () => {
    setTouched(true);
    if (!check.ok || busy) return;
    void send(false);
  };

  return (
    <>
      <Dialog
        open={open && replace === null}
        onOpenChange={(o) => {
          if (!o && !busy) onClose();
        }}
        title="Save the map"
        description="Pick a name for this map. It is saved on the robot."
        footer={
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" onClick={submit} loading={busy} disabled={!check.ok}>
              Save map
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Field
            label="Map name"
            hint="Letters, digits, hyphens and underscores. Up to 48 characters."
            error={shown ?? error}
          >
            {(p) => (
              <Input
                {...p}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setTouched(true);
                  setError(null);
                }}
                maxLength={64}
                autoFocus
              />
            )}
          </Field>
        </form>
      </Dialog>
      <ConfirmDialog
        open={open && replace !== null}
        title="Replace the map?"
        tone="danger"
        body={`A map named ${replace ?? name} already exists on the robot. Replace it?`}
        confirmLabel="Replace map"
        pending={busy}
        onConfirm={() => void send(true)}
        onCancel={() => setReplace(null)}
      />
    </>
  );
}
