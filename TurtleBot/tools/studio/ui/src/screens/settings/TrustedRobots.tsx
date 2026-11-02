import { useState } from 'react';
import { Badge, Button, Panel, Table } from '../../components/ui';
import { Field, Input } from '../../components/ui';
import type { TrustedEntry } from '../../api/setup-types';
import { useAsyncAction } from '../../lib/useAsync';
import { saveSettings } from '../../state/actions';
import { useStudio } from '../../state/store';
import { trustPasted, trustedLabel, untrustRobot } from '../../state/trustActions';

function RowAction({ t }: { t: TrustedEntry }) {
  const remove = useAsyncAction(() => untrustRobot(t));
  const back = useAsyncAction(() => saveSettings({ builtin_host_key: true }));
  if (t.builtin && t.enabled === false) {
    return (
      <Button size="sm" loading={back.pending} onClick={() => void back.run()}>
        Trust again
      </Button>
    );
  }
  return (
    <Button
      size="sm"
      variant="danger"
      loading={remove.pending}
      aria-label={`Remove ${trustedLabel(t)} from the trusted robots`}
      onClick={() => void remove.run()}
    >
      Remove
    </Button>
  );
}

export function TrustedRobots() {
  const trusted = useStudio((s) => s.trusted) as TrustedEntry[];
  const [label, setLabel] = useState('');
  const [key, setKey] = useState('');
  const add = useAsyncAction(async () => {
    if (await trustPasted(key, label)) {
      setKey('');
      setLabel('');
    }
  });

  return (
    <Panel title="Trusted robots" wide>
      <p className="small dim">
        Studio only talks to robots whose identity (fingerprint) is in this list. The built-in key
        is the lab&apos;s own TurtleBot.
      </p>
      {trusted.length ? (
        <Table label="Trusted robots" maxHeight={220}>
          <thead>
            <tr>
              <th>Label</th>
              <th>Fingerprint</th>
              <th>
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {trusted.map((t, i) => (
              <tr key={t.key ?? i}>
                <td>
                  {trustedLabel(t)}{' '}
                  {t.builtin ? <span className="dim small">(built in)</span> : null}{' '}
                  {t.builtin && t.enabled === false ? (
                    <Badge tone="warn">Switched off</Badge>
                  ) : null}
                </td>
                <td className="mono small wrap-any">{t.fingerprint ?? '–'}</td>
                <td className="cell-action">
                  <RowAction t={t} />
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <p className="dim small">
          No trusted robot yet. Use the setup wizard or paste a key below.
        </p>
      )}
      <details className="more">
        <summary>Add a robot by pasting its key</summary>
        <form
          className="stack stack-tight more-body"
          onSubmit={(e) => {
            e.preventDefault();
            void add.run();
          }}
        >
          <Field label="Label" hint="For example Robot 2.">
            {(p) => <Input {...p} value={label} onChange={(e) => setLabel(e.target.value)} />}
          </Field>
          <div className="field">
            <label className="field-label" htmlFor="trust-key">
              Robot host key line
            </label>
            <textarea
              id="trust-key"
              className="input mono"
              rows={3}
              spellCheck={false}
              placeholder="ssh-ed25519 AAAA..."
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
            <p className="field-hint">
              Only for a TurtleBot you own. A wrong key lets someone else pose as the robot. Compare
              the fingerprint first.
            </p>
          </div>
          <div className="row">
            <Button type="submit" loading={add.pending} disabled={!key.trim()}>
              Trust this key…
            </Button>
          </div>
        </form>
      </details>
    </Panel>
  );
}
