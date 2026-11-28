import { FilePlus, FolderOpen, OctagonX, Play, RefreshCw, Save, Undo2 } from 'lucide-react';
import { Suspense, lazy, useEffect, useState } from 'react';
import { OutputLog } from '../components/OutputLog';
import { Badge, Button, EmptyState, Field, Input, Panel } from '../components/ui';
import { useAsyncAction } from '../lib/useAsync';
import { argsPlaceholder } from '../lib/requiredArgs';
import { loadPrograms, openVscode, stopRun } from '../state/actions';
import { useArgs } from '../state/args';
import { isCodeDirty, useCode } from '../state/code';
import { openFile, revertCode, saveAndRun, saveCode, setCodeText } from '../state/codeActions';
import { runFromList } from '../state/runFlow';
import { aliveRunsOf } from '../state/selectors';
import { useStudio } from '../state/store';
import { useUi } from '../state/ui';
import { NewProgramDialog } from './code/NewProgramDialog';

// CodeMirror is large, so it loads only when the Code screen opens.
const CodeEditor = lazy(() =>
  import('../components/CodeEditor').then((m) => ({ default: m.CodeEditor })),
);

function HowItWorks() {
  return (
    <details className="panel help">
      <summary>How robot code works</summary>
      <ul className="plain">
        <li>
          A robot program is a small Python file. It runs on the robot, in a folder called{' '}
          <code>~/robot_code</code>.
        </li>
        <li>
          In ROS 2 a program is a <em>node</em>. Nodes talk through <em>topics</em>.
        </li>
        <li>
          <strong>To read a sensor, subscribe to a topic.</strong> <code>/odom</code> is where the
          robot thinks it is, <code>/scan</code> is the lidar, <code>/battery_state</code> is the
          battery, <code>/dock_status</code> says whether it sits on the dock.
        </li>
        <li>
          <strong>To move, publish a speed on </strong>
          <code>/cmd_vel</code>. It is a TwistStamped message: <code>linear.x</code> is metres per
          second forward, <code>angular.z</code> is radians per second turning left. Send it 10 to
          20 times per second.
        </li>
        <li>
          <strong>Always finish by publishing zeros.</strong> Otherwise the robot may keep rolling.
          The templates already do this for you.
        </li>
        <li>The robot cannot drive while docked. Undock it first on the Home screen.</li>
        <li>
          Safety: the E-STOP button always works. In this editor Esc and Space just edit text, so
          use the button or <strong>Ctrl+Shift+E</strong>.
        </li>
        <li>
          Editor keys: Tab indents, Ctrl+S saves to the robot, Ctrl+F searches, and Ctrl+M lets Tab
          move focus out of the editor.
        </li>
        <li>
          Run a file here with <em>Save and run</em>, or in a terminal on the robot:{' '}
          <code>python3 my_file.py</code>.
        </li>
        <li>
          Start from <em>New program</em>. Each template has the safety parts built in: speed
          limits, a time limit, and stopping for obstacles.
        </li>
      </ul>
    </details>
  );
}

/** On a narrow screen the output sits below the editor: bring it into view once a run starts. */
function showOutput(): void {
  document.getElementById('code-output')?.scrollIntoView?.({ block: 'nearest' });
}

function FilesPanel({ onNew }: { onNew: () => void }) {
  const files = useStudio((s) => s.files);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const open = useCode((s) => s.name);
  const dirty = useCode(isCodeDirty);
  const refresh = useAsyncAction(loadPrograms);
  const opening = useAsyncAction(async (name: string) => {
    await openFile(name);
  });
  const [notice, setNotice] = useState('');
  const running = useAsyncAction(async (name: string) => {
    if (name === open && dirty) {
      // The editor holds changes the robot does not have yet: run what you see, so save first (as Save and run does).
      if (await saveAndRun(useArgs.getState().args[name] ?? '')) showOutput();
      setNotice('');
      return;
    }
    const r = await runFromList(name);
    setNotice(r.notice);
    if (r.started) showOutput();
  });
  return (
    <Panel
      title="Files"
      actions={
        <>
          <Button
            size="sm"
            icon={<RefreshCw size={14} aria-hidden="true" />}
            disabled={!connected}
            loading={refresh.pending}
            onClick={() => void refresh.run()}
            aria-label="Refresh the file list"
          />
          <Button
            size="sm"
            variant="primary"
            icon={<FilePlus size={14} aria-hidden="true" />}
            disabled={!connected}
            onClick={onNew}
          >
            New program
          </Button>
        </>
      }
    >
      {files.length === 0 ? (
        <p className="dim small">
          {connected
            ? 'No .py or .sh files yet. Press New program.'
            : 'Connect to see the files on the robot.'}
        </p>
      ) : (
        <ul className="file-list" aria-label="Files on the robot">
          {files.map((f) => (
            <li key={f.name} className="file-row">
              <button
                type="button"
                className="file-item"
                aria-current={f.name === open ? 'true' : undefined}
                disabled={opening.pending}
                onClick={() => void opening.run(f.name)}
              >
                <span className="mono">{f.name}</span>
                {f.name === open && dirty ? (
                  <span className="dirty-dot" role="img" aria-label="unsaved changes" />
                ) : null}
              </button>
              <Button
                size="sm"
                icon={<Play size={14} aria-hidden="true" />}
                disabled={!connected || running.pending}
                aria-label={`Run ${f.name}`}
                onClick={() => void running.run(f.name)}
              >
                Run
              </Button>
            </li>
          ))}
        </ul>
      )}
      <p className="prog-notice" role="status">
        {notice}
      </p>
    </Panel>
  );
}

function EditorPanel() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const name = useCode((s) => s.name);
  const text = useCode((s) => s.text);
  const status = useCode((s) => s.status);
  const saving = useCode((s) => s.saving);
  const loading = useCode((s) => s.loading);
  const dirty = useCode(isCodeDirty);
  const runningHere = useStudio((s) => (name ? aliveRunsOf(s, name).length : 0));
  const args = useArgs((s) => (name ? (s.args[name] ?? '') : ''));
  const setArgs = useArgs((s) => s.setArgs);
  const entry = useStudio((s) => (name ? s.catalog[name] : undefined));
  const desc = useStudio((s) => (name ? s.desc[name] : undefined));

  const save = useAsyncAction(saveCode);
  const run = useAsyncAction(async () => {
    const started = await saveAndRun(useArgs.getState().args[useCode.getState().name ?? ''] ?? '');
    if (started) showOutput();
  });
  const revert = useAsyncAction(revertCode);
  const stop = useAsyncAction(async () => {
    const s = useStudio.getState();
    const n = useCode.getState().name;
    if (n) await Promise.all(aliveRunsOf(s, n).map((r) => stopRun(r.id)));
  });
  const vscode = useAsyncAction(openVscode);

  return (
    <Panel
      className="editor-panel"
      title={<span className="mono">{name ?? 'No file open'}</span>}
      actions={
        <>
          {dirty ? <Badge tone="warn">Unsaved changes</Badge> : null}
          {status ? (
            <span className="dim small" role="status">
              {status}
            </span>
          ) : null}
        </>
      }
    >
      <div className="editor-box">
        <Suspense fallback={<p className="editor-loading dim small">Loading the editor.</p>}>
          <CodeEditor
            value={text}
            onChange={setCodeText}
            onSave={() => void save.run()}
            disabled={!name || loading}
            label={name ? `Code of ${name}` : 'Code editor'}
            emptyText="Pick a file on the left, or choose New program."
          />
        </Suspense>
      </div>
      <div className="row editor-actions">
        <Button
          variant="primary"
          icon={<Save size={16} aria-hidden="true" />}
          disabled={!name || !connected}
          loading={saving || save.pending}
          onClick={() => void save.run()}
          aria-label="Save to the robot (Ctrl+S)"
        >
          Save to robot
        </Button>
        <Button
          icon={<Play size={16} aria-hidden="true" />}
          disabled={!name || !connected}
          loading={run.pending}
          onClick={() => void run.run()}
        >
          Save and run
        </Button>
        <Button
          variant="danger"
          icon={<OctagonX size={16} aria-hidden="true" />}
          disabled={!name || runningHere === 0}
          loading={stop.pending}
          onClick={() => void stop.run()}
        >
          Stop
        </Button>
        <Button
          icon={<Undo2 size={16} aria-hidden="true" />}
          disabled={!name || !dirty}
          loading={revert.pending}
          onClick={() => void revert.run()}
        >
          Revert
        </Button>
        <Button
          icon={<FolderOpen size={16} aria-hidden="true" />}
          loading={vscode.pending}
          onClick={() => void vscode.run()}
        >
          Open in VS Code
        </Button>
      </div>
      <Field
        label="Arguments for Save and run"
        hint="Leave it empty if the program needs nothing. Press Enter to save and run."
      >
        {(p) => (
          <Input
            {...p}
            className="mono"
            disabled={!name}
            placeholder={name ? argsPlaceholder(entry, desc) : 'Optional'}
            value={args}
            onChange={(e) => name && setArgs(name, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && name && connected) void run.run();
            }}
          />
        )}
      </Field>
    </Panel>
  );
}

function OutputPanel() {
  const run = useStudio((s) => (s.selectedRun ? s.runs[s.selectedRun] : undefined));
  return (
    <Panel
      id="code-output"
      title="Output"
      actions={
        run ? (
          <span className="dim small mono">
            {run.name} {run.alive ? '(running)' : '(finished)'}
          </span>
        ) : null
      }
    >
      <OutputLog
        lines={run?.lines ?? null}
        label="Output of the running program"
        empty={
          run
            ? run.alive
              ? 'Waiting for output.'
              : 'This run printed nothing.'
            : 'Output appears here when you run the program.'
        }
      />
    </Panel>
  );
}

export function Code() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const [newOpen, setNewOpen] = useState(false);
  const asked = useUi((s) => s.newProgramAsked);
  const setAsked = useUi((s) => s.setNewProgramAsked);
  useEffect(() => {
    if (connected) void loadPrograms();
  }, [connected]);
  // Leaving the screen with the dialog still open must not reopen it on the next visit.
  useEffect(() => () => setAsked(false), [setAsked]);
  // A button on another screen (Home, Programs) can ask for the New program dialog.
  const dialogOpen = newOpen || asked;

  return (
    <div className="page">
      <h1 className="page-title">Code</h1>
      <HowItWorks />
      {!connected ? (
        <Panel>
          <EmptyState compact title="Not connected">
            Connect to the robot on the Home screen to open and edit its programs.
          </EmptyState>
        </Panel>
      ) : null}
      <div className="code-grid">
        <FilesPanel onNew={() => setNewOpen(true)} />
        <div className="code-main">
          <EditorPanel />
          <OutputPanel />
        </div>
      </div>
      {dialogOpen ? (
        <NewProgramDialog
          open
          onClose={() => {
            setNewOpen(false);
            setAsked(false);
          }}
        />
      ) : null}
    </div>
  );
}
