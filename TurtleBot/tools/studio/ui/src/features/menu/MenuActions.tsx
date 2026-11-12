import { RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { Badge, Button, ConfirmDialog, Panel } from '../../components/ui';
import { notify } from '../../state/feedback';
import { toYaml, validateDoc } from './model';
import { currentCheck, useMenu } from './store';

export const SAVE_TEXT =
  'The robot keeps the old file as menu.yaml.bak and shows the new menu the next time it returns to the top menu. Nothing moves now.';

/** Check with the robot, save, reload, and the generated file. */
export function MenuActions({ connected }: { connected: boolean }) {
  const s = useMenu();
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [askReload, setAskReload] = useState(false);

  const text = toYaml(s.doc);
  const valid = validateDoc(s.doc);
  const checkerOk = s.robot?.checker_ok === true;
  const changed = text !== s.baseText;
  const check = currentCheck(s);
  const canSave = connected && valid.ok && checkerOk && !s.blocked && s.robot !== null;
  const why = !connected
    ? 'Not connected to the robot.'
    : !checkerOk
      ? 'The robot has no menu checker yet.'
      : !valid.ok
        ? 'Fix the problems above first.'
        : '';

  const reload = async () => {
    setReloading(true);
    setAskReload(false);
    await s.load();
    setReloading(false);
  };

  const doSave = async () => {
    const ok = await s.save();
    setSaving(false);
    if (ok) notify('ok', 'The menu is saved on the robot.');
    else notify('error', 'The menu was not saved.');
  };

  return (
    <Panel
      title="Check and save"
      actions={changed ? <Badge tone="warn">Not saved yet</Badge> : <Badge tone="ok">Saved</Badge>}
    >
      {!valid.ok ? (
        <ul className="menu-problems" data-testid="menu-local-errors">
          {valid.messages.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      ) : null}
      <div className="menu-actions">
        <Button
          loading={s.checking}
          disabled={!connected || !checkerOk}
          onClick={() => void s.runCheck()}
        >
          Check with the robot
        </Button>
        <Button variant="primary" disabled={!canSave} onClick={() => setSaving(true)}>
          Save to the robot
        </Button>
        <Button
          icon={<RefreshCw size={14} aria-hidden="true" />}
          loading={reloading}
          disabled={!connected}
          onClick={() => (changed ? setAskReload(true) : void reload())}
        >
          Reload from the robot
        </Button>
      </div>
      {why ? <p className="dim small">{why}</p> : null}
      {s.checkError ? (
        <p className="mapping-error" role="alert">
          Could not ask the robot to check. {s.checkError}
        </p>
      ) : null}
      {s.saveError ? (
        <p className="mapping-error" role="alert" data-testid="menu-save-error">
          The robot did not save the menu. {s.saveError}
        </p>
      ) : null}
      {s.lastCheck ? (
        <div data-testid="menu-check-result" className="menu-check-result">
          {check ? (
            <>
              <p role="status">
                {check.ok ? (
                  <Badge tone="ok">The robot accepts this menu</Badge>
                ) : (
                  <Badge tone="bad">The robot does not accept this menu</Badge>
                )}
              </p>
              {check.errors.length > 0 ? (
                <ul className="menu-problems" aria-label="Problems the robot found">
                  {check.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              ) : null}
              {check.warnings.length > 0 ? (
                <ul className="menu-warnings" aria-label="Notes from the robot">
                  {check.warnings.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="dim small">
              The menu changed since the robot last checked it. Check again to see its answer.
            </p>
          )}
        </div>
      ) : null}
      <details className="menu-file">
        <summary>Show the file</summary>
        <label className="sr-only" htmlFor="menu-yaml">
          The menu file Studio will write (read only)
        </label>
        <textarea
          id="menu-yaml"
          className="input mono menu-yaml"
          readOnly
          rows={Math.min(18, text.split('\n').length + 1)}
          value={text}
        />
      </details>
      <ConfirmDialog
        open={saving}
        title="Save the menu to the robot?"
        body={SAVE_TEXT}
        confirmLabel="Save to the robot"
        pending={s.saving}
        onConfirm={() => void doSave()}
        onCancel={() => setSaving(false)}
      />
      <ConfirmDialog
        open={askReload}
        title="Drop your changes?"
        body="Reloading brings back the menu that is on the robot and discards what you changed here."
        confirmLabel="Reload"
        tone="danger"
        onConfirm={() => void reload()}
        onCancel={() => setAskReload(false)}
      />
    </Panel>
  );
}
