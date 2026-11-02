import { api } from '../api';
import { SKELETON } from '../lib/templates';
import { loadDescribe, loadPrograms, report, runProgram } from './actions';
import { isCodeDirty, useCode } from './code';
import { confirm, notify } from './feedback';
import { remoteDir } from './selectors';
import { useStudio } from './store';

const code = () => useCode.getState();
const nowStr = () => new Date().toTimeString().slice(0, 8);

/** Open a file from the robot. Asks first when the editor has unsaved changes. */
export async function openFile(name: string): Promise<boolean> {
  const c = code();
  if (name === c.name) return true;
  if (isCodeDirty(c)) {
    const ok = await confirm({
      title: 'Leave without saving?',
      body: (
        <p>
          You have unsaved changes in <strong>{c.name}</strong>. If you open another file they are
          lost.
        </p>
      ),
      confirmLabel: 'Discard changes',
      tone: 'danger',
    });
    if (!ok) return false;
  }
  useCode.setState({ loading: true });
  const r = report(
    await api().bridge('read_file', { path: name, dir: remoteDir(useStudio.getState()) }),
    'Open ' + name,
  );
  if (!r.ok) {
    useCode.setState({ loading: false });
    return false;
  }
  const text = r.text ?? '';
  useCode.setState({
    name,
    orig: text,
    text,
    sha1: r.sha1 ?? null,
    status: 'Opened from the robot',
    loading: false,
  });
  return true;
}

export function setCodeText(text: string): void {
  if (code().text !== text) useCode.setState({ text });
}

/** Save the editor text to the robot. Returns true when the robot has the text afterwards. */
export async function saveCode(): Promise<boolean> {
  const c = code();
  if (!c.name || useStudio.getState().conn.state !== 'connected' || c.saving) return false;
  useCode.setState({ saving: true });
  try {
    const text = c.text;
    const base = { path: c.name, dir: remoteDir(useStudio.getState()), text, overwrite: true };
    let r = await api().bridge('write_file', { ...base, expect_sha1: c.sha1 ?? undefined });
    if (!r.ok && /changed on the robot/i.test(r.error)) {
      const ok = await confirm({
        title: 'This file changed on the robot',
        body: (
          <p>
            The file was changed on the robot after you opened it. Saving now replaces that newer
            version. The newer version is kept as a <code>.bak</code> copy.
          </p>
        ),
        confirmLabel: 'Save anyway',
        tone: 'danger',
      });
      if (!ok) return false;
      r = await api().bridge('write_file', base);
    }
    if (!r.ok) {
      notify('error', 'Save failed: ' + r.error);
      return false;
    }
    useCode.setState({ sha1: r.sha1 ?? code().sha1, orig: text });
    if (r.unchanged) {
      useCode.setState({ status: 'No changes to save' });
      notify('info', 'No changes to save.');
      return true;
    }
    useCode.setState({ status: 'Saved to the robot at ' + nowStr() });
    notify('ok', 'Saved to the robot.');
    void loadDescribe();
    return true;
  } finally {
    useCode.setState({ saving: false });
  }
}

export async function saveAndRun(argStr: string): Promise<boolean> {
  if (!(await saveCode())) return false;
  await loadDescribe();
  const name = code().name;
  return name ? runProgram(name, argStr) : false;
}

export async function revertCode(): Promise<void> {
  if (!isCodeDirty(code())) return;
  const ok = await confirm({
    title: 'Throw away your changes?',
    body: <p>The editor goes back to the last version saved on the robot.</p>,
    confirmLabel: 'Revert',
    tone: 'danger',
  });
  if (ok) useCode.setState({ text: code().orig, status: 'Changes reverted' });
}

export interface NewProgramRequest {
  /** Template file name, or null for an empty program. */
  template: string | null;
  file: string;
  replace: boolean;
}

export async function createProgram(req: NewProgramRequest): Promise<boolean> {
  let text = SKELETON;
  if (req.template) {
    const t = await api().template(req.template);
    if (!t.ok) {
      notify('error', 'Template: ' + t.error);
      return false;
    }
    text = t.text;
  }
  const exists = useStudio.getState().files.some((f) => f.name === req.file);
  const r = report(
    await api().bridge('write_file', {
      path: req.file,
      dir: remoteDir(useStudio.getState()),
      text,
      overwrite: exists,
    }),
    'Create ' + req.file,
  );
  if (!r.ok) return false;
  notify('ok', 'Created ' + req.file + '.');
  await loadPrograms();
  // Opening asks first when the editor has unsaved changes, like opening any other file.
  return openFile(req.file);
}
