import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { DialogHost, TooltipProvider } from '../components/ui';
import { connectedStatus, installApi, resetStores } from '../test/helpers';
import { isCodeDirty, useCode } from './code';
import { openFile, revertCode, saveCode } from './codeActions';
import { useStudio } from './store';

function Host() {
  return (
    <TooltipProvider>
      <DialogHost />
    </TooltipProvider>
  );
}

const files: Record<string, { text: string; sha1: string }> = {
  'a.py': { text: 'print("a")\n', sha1: 'sa' },
  'b.py': { text: 'print("b")\n', sha1: 'sb' },
};

function robot(over: (c: { body: Record<string, unknown> }) => unknown = () => undefined) {
  return installApi((c) => {
    const o = over(c);
    if (o !== undefined) return o;
    if (c.body.cmd === 'read_file') {
      const f = files[String(c.body.path)];
      return f ? { ok: true, path: c.body.path, ...f } : { ok: false, error: 'no such file' };
    }
    if (c.body.cmd === 'write_file') return { ok: true, sha1: 'new' };
    return { ok: true, programs: [] };
  });
}

beforeEach(() => {
  resetStores();
  connectedStatus();
});

describe('opening files', () => {
  it('opens a file and shows it as clean', async () => {
    robot();
    await expect(openFile('a.py')).resolves.toBe(true);
    const s = useCode.getState();
    expect(s).toMatchObject({ name: 'a.py', text: files['a.py']?.text, sha1: 'sa' });
    expect(isCodeDirty(s)).toBe(false);
  });

  it('opens another file straight away when nothing is unsaved', async () => {
    const { calls } = robot();
    await openFile('a.py');
    await openFile('b.py');
    expect(calls.filter((c) => c.body.cmd === 'read_file')).toHaveLength(2);
    expect(useCode.getState().name).toBe('b.py');
  });

  it('asks before throwing away unsaved changes, and keeps them on Cancel', async () => {
    const { calls } = robot();
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    render(<Host />);
    let result: Promise<boolean> = Promise.resolve(true);
    act(() => {
      result = openFile('b.py');
    });
    expect(
      await screen.findByRole('dialog', { name: 'Leave without saving?' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await expect(result).resolves.toBe(false);
    expect(useCode.getState()).toMatchObject({ name: 'a.py', text: 'edited' });
    expect(calls.filter((c) => c.body.cmd === 'read_file')).toHaveLength(1);
  });

  it('discards the changes when the person agrees', async () => {
    robot();
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    render(<Host />);
    let result: Promise<boolean> = Promise.resolve(false);
    act(() => {
      result = openFile('b.py');
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));
    await expect(result).resolves.toBe(true);
    expect(useCode.getState()).toMatchObject({ name: 'b.py', text: files['b.py']?.text });
  });

  it('does not reload the file that is already open (that would lose edits quietly)', async () => {
    const { calls } = robot();
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    await expect(openFile('a.py')).resolves.toBe(true);
    expect(useCode.getState().text).toBe('edited');
    expect(calls.filter((c) => c.body.cmd === 'read_file')).toHaveLength(1);
  });
});

describe('saving', () => {
  it('saves with the checksum from when the file was opened', async () => {
    const { calls } = robot();
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    await expect(saveCode()).resolves.toBe(true);
    const w = calls.find((c) => c.body.cmd === 'write_file');
    expect(w?.body).toMatchObject({
      path: 'a.py',
      text: 'edited',
      overwrite: true,
      expect_sha1: 'sa',
    });
    const s = useCode.getState();
    expect(s.orig).toBe('edited');
    expect(isCodeDirty(s)).toBe(false);
    expect(s.status).toMatch(/^Saved to the robot at /);
  });

  it('says "No changes to save" when the robot already has the text', async () => {
    robot((c) =>
      c.body.cmd === 'write_file' ? { ok: true, sha1: 'sa', unchanged: true } : undefined,
    );
    await openFile('a.py');
    await saveCode();
    expect(useCode.getState().status).toBe('No changes to save');
  });

  it('does nothing without a connection or an open file', async () => {
    const { calls } = robot();
    await expect(saveCode()).resolves.toBe(false);
    await openFile('a.py');
    useStudio.getState().dispatch({ ev: 'conn', state: 'disconnected' });
    await expect(saveCode()).resolves.toBe(false);
    expect(calls.filter((c) => c.body.cmd === 'write_file')).toHaveLength(0);
  });

  it('asks before replacing a newer version on the robot', async () => {
    let first = true;
    const { calls } = robot((c) => {
      if (c.body.cmd !== 'write_file') return undefined;
      if (first) {
        first = false;
        return { ok: false, error: 'file changed on the robot since you opened it' };
      }
      return { ok: true, sha1: 'forced' };
    });
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    render(<Host />);
    let result: Promise<boolean> = Promise.resolve(false);
    act(() => {
      result = saveCode();
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Save anyway' }));
    await expect(result).resolves.toBe(true);
    const writes = calls.filter((c) => c.body.cmd === 'write_file');
    expect(writes).toHaveLength(2);
    expect(writes[0]?.body.expect_sha1).toBe('sa');
    expect(writes[1]?.body.expect_sha1).toBeUndefined();
  });

  it('keeps the edits when the save fails', async () => {
    robot((c) => (c.body.cmd === 'write_file' ? { ok: false, error: 'disk full' } : undefined));
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    await expect(saveCode()).resolves.toBe(false);
    expect(isCodeDirty(useCode.getState())).toBe(true);
  });
});

describe('revert', () => {
  it('asks, then restores the saved text', async () => {
    robot();
    await openFile('a.py');
    useCode.setState({ text: 'edited' });
    render(<Host />);
    act(() => {
      void revertCode();
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Revert' }));
    await waitFor(() => expect(useCode.getState().text).toBe(files['a.py']?.text));
  });
});
