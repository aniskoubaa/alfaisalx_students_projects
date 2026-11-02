import { Download, Eye, RefreshCw, Rocket, Upload } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import type { RemoteFile, SyncEvent } from '../api';
import { Badge, Button, Checkbox, EmptyState, Field, Input, Panel, Table } from '../components/ui';
import { compareFiles, countByStatus, isRunnable } from '../lib/files';
import type { CompareRow } from '../lib/files';
import { fmtSize } from '../lib/format';
import { useAsyncAction } from '../lib/useAsync';
import { loadPrograms, report, runProgram, saveSettings } from '../state/actions';
import { useArgs } from '../state/args';
import { confirm, notify } from '../state/feedback';
import { navigate } from '../state/router';
import { remoteDir } from '../state/selectors';
import { useStudio } from '../state/store';

const STATUS_TONE = { same: 'ok', changed: 'warn', new: 'warn', 'robot only': 'neutral' } as const;
const STATUS_TEXT = {
  same: 'Same',
  changed: 'Changed',
  new: 'New (only here)',
  'robot only': 'Robot only',
} as const;

function SyncResult({ e }: { e: SyncEvent }) {
  const preview = e.state === 'preview';
  const up = (preview ? e.would_upload : e.uploaded) ?? [];
  const del = (preview ? e.would_delete : e.deleted) ?? [];
  const verb = e.direction === 'down' ? 'Downloaded' : 'Uploaded';
  const state =
    e.state === 'running' ? (
      <Badge tone="warn">Working&hellip;</Badge>
    ) : e.state === 'done' ? (
      <Badge tone="ok">Done</Badge>
    ) : e.state === 'preview' ? (
      <Badge tone="ok">Preview, nothing changed</Badge>
    ) : (
      <Badge tone="bad">Something went wrong</Badge>
    );
  return (
    <div aria-live="polite">
      <p>{state}</p>
      {e.error ? (
        <div className="note note-bad" role="alert">
          {e.error}
        </div>
      ) : null}
      {e.state !== 'running' && !e.error ? (
        <p className="small">
          {e.state === 'preview' ? 'Would transfer' : verb}: <strong>{up.length}</strong> file
          {up.length === 1 ? '' : 's'}. Skipped because they are the same:{' '}
          <strong>{e.skipped ?? 0}</strong>
          {del.length ? (
            <>
              . {e.state === 'preview' ? 'Would delete' : 'Deleted'}: <strong>{del.length}</strong>
            </>
          ) : null}
          .
        </p>
      ) : null}
      {up.length ? <pre className="pre-block">{up.join('\n')}</pre> : null}
    </div>
  );
}

export function Files() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const settings = useStudio((s) => s.settings);
  const defaultRemote = useStudio(remoteDir);
  const sync = useStudio((s) => s.sync);
  const setSync = useStudio((s) => s.setSync);

  const [localEdit, setLocalDir] = useState<string | null>(null);
  const [remoteEdit, setRemote] = useState<string | null>(null);
  const settingsLoaded = useStudio((s) => s.settingsLoaded);
  const localDir = localEdit ?? settings.local_dir ?? '';
  const remote = remoteEdit ?? (settings.remote_dir || '~/robot_code');
  const dirsReady = settingsLoaded;
  const [local, setLocal] = useState<RemoteFile[] | null>(null);
  const [robot, setRobot] = useState<RemoteFile[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [withDelete, setWithDelete] = useState(false);

  const rows = useMemo(() => compareFiles(local, robot), [local, robot]);
  const counts = useMemo(() => countByStatus(rows), [rows]);

  const compare = useAsyncAction(async () => {
    const dir = localDir.trim();
    if (!dir) {
      notify('warn', 'Enter a folder on this computer first.');
      return;
    }
    const [l, r] = await Promise.all([
      report(await api().localFiles(dir), 'Local files'),
      connected
        ? report(
            await api().bridge('ls', { dir: remote.trim() || defaultRemote, recursive: true }),
            'Robot files',
          )
        : Promise.resolve(null),
    ]);
    setLocal(l.ok ? (l.files ?? []).filter((f) => !f.is_dir) : null);
    setRobot(r && r.ok ? (r.files ?? []).filter((f) => !f.is_dir) : null);
    if (!connected) notify('warn', 'Not connected: showing the files on this computer only.');
  });

  // Compare once when the screen opens with a saved folder, and again after the robot connects.
  const comparedFor = useRef<boolean | null>(null);
  useEffect(() => {
    if (!dirsReady || !localDir.trim() || comparedFor.current === connected) return;
    comparedFor.current = connected;
    void compare.run();
    // `compare.run` is stable; localDir is read once when the screen opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirsReady, connected]);

  const useDirs = useAsyncAction(async () => {
    const ok = await saveSettings({
      local_dir: localDir.trim(),
      remote_dir: remote.trim() || '~/robot_code',
    });
    if (ok) await compare.run();
  });

  const runSync = async (direction: 'up' | 'down', dry: boolean): Promise<boolean> => {
    const local_dir = localDir.trim();
    if (!local_dir) {
      notify('warn', 'Enter a folder on this computer first.');
      return false;
    }
    const remote_dir = remote.trim() || defaultRemote;
    const del = withDelete && direction === 'up';
    if (direction === 'down' && !dry) {
      const ok = await confirm({
        title: 'Download from the robot?',
        body: (
          <p>
            Files from the robot replace files with the same name in your folder. Use Preview first
            if you are not sure.
          </p>
        ),
        confirmLabel: 'Download',
      });
      if (!ok) return false;
    }
    if (del && !dry) {
      const p = await api().sync({ local_dir, remote_dir, direction, delete: true, dry_run: true });
      if (!p.ok) {
        setSync({ ev: 'sync', state: 'error', error: p.error });
        notify('error', 'Preview: ' + p.error);
        return false;
      }
      const list = p.would_delete ?? p.deleted ?? [];
      const ok = await confirm({
        title: list.length
          ? `Delete ${list.length} file${list.length === 1 ? '' : 's'} on the robot?`
          : 'Upload and delete?',
        tone: 'danger',
        confirmLabel: list.length ? 'Delete and upload' : 'Upload',
        body: (
          <>
            <p>
              These files are on the robot but not in your folder. They are deleted from the robot,
              and the robot keeps no copy.
            </p>
            {list.length ? (
              <pre className="pre-block">{list.join('\n')}</pre>
            ) : (
              <p>No file would be deleted.</p>
            )}
          </>
        ),
      });
      if (!ok) return false;
    }
    setSync({ ev: 'sync', state: 'running', direction });
    const r = await api().sync({
      local_dir,
      remote_dir,
      direction,
      delete: del,
      dry_run: dry,
      ...(del && !dry ? { confirm_delete: true } : {}),
    });
    if (!r.ok) {
      setSync({ ev: 'sync', state: 'error', direction, error: r.error });
      notify('error', (dry ? 'Preview' : 'Sync') + ': ' + r.error);
      return false;
    }
    setSync({
      ev: 'sync',
      state: dry ? 'preview' : 'done',
      direction,
      uploaded: r.uploaded,
      would_upload: dry ? (r.would_transfer ?? r.would_upload ?? r.uploaded ?? []) : undefined,
      would_delete: dry ? (r.would_delete ?? r.deleted ?? []) : undefined,
      skipped: r.skipped,
      deleted: dry ? undefined : r.deleted,
    });
    if (!dry) {
      void compare.run();
      void loadPrograms();
    }
    return true;
  };

  const preview = useAsyncAction(() => runSync('up', true));
  const upload = useAsyncAction(() => runSync('up', false));
  const download = useAsyncAction(() => runSync('down', false));
  const syncRun = useAsyncAction(async () => {
    if (!selected) {
      notify('warn', 'Select a file in the table first.');
      return;
    }
    if (!(await runSync('up', false))) return;
    const ok = await runProgram(
      selected,
      useArgs.getState().args[selected.split('/').pop() ?? selected] ?? '',
    );
    if (ok) navigate('/programs');
  });

  const busy = preview.pending || upload.pending || download.pending || syncRun.pending;

  return (
    <div className="page">
      <h1 className="page-title">Files</h1>
      <Panel title="Folders">
        <form
          className="folders"
          onSubmit={(e) => {
            e.preventDefault();
            void useDirs.run();
          }}
        >
          <Field label="Folder on this computer" className="grow2">
            {(p) => (
              <Input
                {...p}
                className="mono"
                value={localDir}
                placeholder={'C:\\Users\\you\\robot_code'}
                onChange={(e) => setLocalDir(e.target.value)}
              />
            )}
          </Field>
          <Field label="Folder on the robot" className="grow">
            {(p) => (
              <Input
                {...p}
                className="mono"
                value={remote}
                onChange={(e) => setRemote(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" loading={useDirs.pending}>
            Use these folders
          </Button>
        </form>
        <div className="row sync-actions">
          <Button
            icon={<RefreshCw size={16} aria-hidden="true" />}
            loading={compare.pending}
            onClick={() => void compare.run()}
          >
            Refresh comparison
          </Button>
          <Button
            icon={<Eye size={16} aria-hidden="true" />}
            disabled={!connected || busy}
            loading={preview.pending}
            onClick={() => void preview.run()}
          >
            Preview upload (dry run)
          </Button>
          <Button
            variant="primary"
            icon={<Upload size={16} aria-hidden="true" />}
            disabled={!connected || busy}
            loading={upload.pending}
            onClick={() => void upload.run()}
          >
            Upload changes
          </Button>
          <Button
            icon={<Download size={16} aria-hidden="true" />}
            disabled={!connected || busy}
            loading={download.pending}
            onClick={() => void download.run()}
          >
            Download from robot
          </Button>
          <Button
            icon={<Rocket size={16} aria-hidden="true" />}
            disabled={!connected || busy || !selected}
            loading={syncRun.pending}
            onClick={() => void syncRun.run()}
          >
            Sync and run selected
          </Button>
        </div>
        <Checkbox
          label="When I upload, also delete files on the robot that are not in my folder (asks first)"
          checked={withDelete}
          onChange={(e) => setWithDelete(e.target.checked)}
        />
        <p className="dim small">
          {withDelete
            ? 'Deleting is on. You will see the list of files before anything is removed.'
            : 'Nothing is ever deleted from the robot unless you tick the box above.'}
        </p>
      </Panel>

      {sync ? (
        <Panel title="Last transfer">
          <SyncResult e={sync} />
        </Panel>
      ) : null}

      <Panel
        title="Comparison"
        actions={
          rows.length ? (
            <span className="dim small">
              {counts.same} same, {counts.changed} changed, {counts.new} new, {counts['robot only']}{' '}
              robot only
            </span>
          ) : null
        }
      >
        {rows.length === 0 ? (
          <EmptyState compact title="Nothing to compare yet">
            Enter a folder on this computer and press Refresh comparison.
          </EmptyState>
        ) : (
          <Table label="Files on this computer and on the robot" maxHeight={480}>
            <thead>
              <tr>
                <th>
                  <span className="sr-only">Select</span>
                </th>
                <th>File</th>
                <th>Status</th>
                <th className="num">Size here</th>
                <th className="num">Size on robot</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: CompareRow) => (
                <tr key={r.name} className={selected === r.name ? 'is-selected' : undefined}>
                  <td>
                    {isRunnable(r.name) ? (
                      <input
                        type="radio"
                        name="select-file"
                        checked={selected === r.name}
                        onChange={() => setSelected(r.name)}
                        aria-label={`Select ${r.name} for Sync and run`}
                      />
                    ) : null}
                  </td>
                  <td className="mono">{r.name}</td>
                  <td>
                    <Badge tone={STATUS_TONE[r.status]}>{STATUS_TEXT[r.status]}</Badge>
                  </td>
                  <td className="num">{fmtSize(r.local?.size)}</td>
                  <td className="num">{fmtSize(r.robot?.size)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
