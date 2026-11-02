import { Play } from 'lucide-react';
import type { CatalogEntry, ProgramDescription, RemoteFile } from '../../api';
import { isBuiltinMotion, isHelperProgram, isMotionProgram } from '../../lib/motion';
import { useAsyncAction } from '../../lib/useAsync';
import { runProgram, saveSettings } from '../../state/actions';
import { useArgs } from '../../state/args';
import { useStudio } from '../../state/store';
import { Badge, Button, Checkbox, Input, Table } from '../../components/ui';

function Details({
  entry,
  desc,
  onExample,
}: {
  entry: CatalogEntry | undefined;
  desc: ProgramDescription | undefined;
  onExample: (args: string) => void;
}) {
  const c = entry;
  const d = desc;
  const nothing = !c && !(d && (d.docstring || d.usage?.length || d.moves_detected));
  return (
    <div className="prog-details">
      {!c ? (
        <p>
          This is not one of Studio&apos;s ready-made programs. Below is what the file says about
          itself.
        </p>
      ) : null}
      {c?.args?.length ? (
        <>
          <h4>What you can type in the arguments box</h4>
          <Table label="Arguments">
            <thead>
              <tr>
                <th>Argument</th>
                <th>Meaning</th>
              </tr>
            </thead>
            <tbody>
              {c.args.map((a) => (
                <tr key={a.name}>
                  <td className="mono">{a.name}</td>
                  <td>{a.help}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      ) : null}
      {c?.examples?.length ? (
        <>
          <h4>Examples (select one to fill the box)</h4>
          <div className="examples">
            {c.examples.map((x) => (
              <button
                type="button"
                key={x.args + x.what}
                className="example"
                onClick={() => onExample(x.args)}
              >
                <code>{x.args || '(no arguments)'}</code>
                <span>{x.what}</span>
              </button>
            ))}
          </div>
        </>
      ) : null}
      {c?.stop ? (
        <>
          <h4>How to stop it</h4>
          <p>{c.stop}</p>
        </>
      ) : null}
      {c?.notes?.length ? (
        <>
          <h4>Good to know</h4>
          <ul className="plain">
            {c.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
      {c?.doc ? (
        <>
          <h4>More</h4>
          <p>
            {/^https?:\/\//.test(c.doc) ? (
              <a href={c.doc} target="_blank" rel="noopener noreferrer">
                More in the docs
              </a>
            ) : (
              <>
                More in the docs: <code>{c.doc}</code>
              </>
            )}
          </p>
        </>
      ) : null}
      {d?.docstring && (!c || !(c.summary ?? '').includes(d.docstring.slice(0, 40))) ? (
        <>
          <h4>Written in the file on the robot</h4>
          <pre className="pre-block">{d.docstring}</pre>
        </>
      ) : null}
      {!c && d?.usage?.length ? (
        <>
          <h4>Options found in the file</h4>
          <pre className="pre-block">{d.usage.join('\n')}</pre>
        </>
      ) : null}
      {!c && d?.moves_detected ? (
        <>
          <h4>Why we think it moves the robot</h4>
          <p>
            It mentions: {(d.moves_reasons ?? []).join(', ')}. Studio asks you to confirm before
            running it.
          </p>
        </>
      ) : null}
      {nothing && !c ? <p className="dim">No description yet.</p> : null}
    </div>
  );
}

export function ProgramCard({ file }: { file: RemoteFile }) {
  const name = file.name;
  const entry = useStudio((s) => s.catalog[name]);
  const catalog = useStudio((s) => s.catalog);
  const desc = useStudio((s) => s.desc[name]);
  const descAll = useStudio((s) => s.desc);
  const extra = useStudio((s) => s.settings.motion_files);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const value = useArgs((s) => s.args[name] ?? '');
  const setArgs = useArgs((s) => s.setArgs);

  const moves = isMotionProgram(name, catalog, descAll, extra ?? []);
  const helper = isHelperProgram(name, catalog);
  const builtin = isBuiltinMotion(name, catalog);
  const run = useAsyncAction(async () => {
    const started = await runProgram(name, useArgs.getState().args[name] ?? '');
    // On narrow screens the output sits below the list: bring it into view.
    if (started) document.getElementById('run-output')?.scrollIntoView({ block: 'nearest' });
  });
  const mark = useAsyncAction(async (on: boolean) => {
    const set = new Set(extra ?? []);
    if (on) set.add(name);
    else set.delete(name);
    await saveSettings({ motion_files: [...set] });
  });

  return (
    <article className="prog" aria-label={entry?.title ?? name}>
      <div className="prog-head">
        <h3 className="prog-title">{entry?.title ?? name}</h3>
        <span className="badge-list">
          {helper ? (
            <Badge tone="neutral">Helper, not run directly</Badge>
          ) : (
            <>
              {moves ? (
                <Badge tone="warn">
                  Moves the robot{!entry && desc?.moves_detected ? ' (detected)' : ''}
                </Badge>
              ) : null}
              {entry?.safe_on_dock ? <Badge tone="ok">Safe on the dock</Badge> : null}
              {entry?.needs_undock ? <Badge tone="neutral">Undock first</Badge> : null}
              {!entry ? <Badge tone="neutral">Your own program</Badge> : null}
            </>
          )}
        </span>
      </div>
      <p className="prog-file mono">{name}</p>
      {entry?.summary ? <p className="prog-summary">{entry.summary}</p> : null}
      <form
        className="prog-run"
        onSubmit={(e) => {
          e.preventDefault();
          if (connected && !helper) void run.run();
        }}
      >
        <Input
          value={value}
          onChange={(e) => setArgs(name, e.target.value)}
          placeholder="arguments (optional)"
          aria-label={`Arguments for ${name}`}
          className="mono"
        />
        <Button
          type="submit"
          variant="primary"
          icon={<Play size={14} aria-hidden="true" />}
          loading={run.pending}
          disabled={!connected || helper}
          aria-label={`Run ${name}`}
        >
          Run
        </Button>
      </form>
      {!builtin && !helper ? (
        <Checkbox
          className="prog-mark"
          label="It moves the robot (ask me to confirm first)"
          checked={moves}
          disabled={mark.pending}
          aria-label={`Mark ${name} as moving the robot`}
          onChange={(e) => void mark.run(e.target.checked)}
        />
      ) : null}
      <details className="prog-more">
        <summary>What does it do?</summary>
        <Details entry={entry} desc={desc} onExample={(a) => setArgs(name, a)} />
      </details>
    </article>
  );
}
