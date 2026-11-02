import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CodeEditor } from '../components/CodeEditor';
import { DialogHost, TooltipProvider } from '../components/ui';
import { connectedStatus, installApi, resetStores } from '../test/helpers';
import { useStudio } from '../state/store';
import { Files } from './Files';

beforeEach(() => {
  resetStores();
  connectedStatus();
  // CodeMirror measures text; jsdom has no layout.
  const rect = {
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    bottom: 0,
    right: 0,
    width: 0,
    height: 0,
    toJSON: () => ({}),
  };
  Range.prototype.getClientRects = () =>
    ({
      length: 0,
      item: () => null,
      [Symbol.iterator]: [][Symbol.iterator],
    }) as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => rect as DOMRect;
});

describe('CodeEditor', () => {
  it('shows the text, reports edits and saves with Ctrl+S', async () => {
    const onChange = vi.fn();
    const onSave = vi.fn();
    render(
      <CodeEditor value={'print(1)\n'} onChange={onChange} onSave={onSave} label="Code of a.py" />,
    );
    const box = await screen.findByRole('textbox', { name: 'Code of a.py' });
    expect(box).toHaveTextContent('print(1)');
    await userEvent.click(box);
    await userEvent.keyboard('x');
    expect(onChange).toHaveBeenCalled();
    await userEvent.keyboard('{Control>}s{/Control}');
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('cannot be typed in while no file is open', async () => {
    const onChange = vi.fn();
    render(
      <CodeEditor value="" onChange={onChange} onSave={() => {}} disabled label="Code editor" />,
    );
    const box = await screen.findByRole('textbox', { name: 'Code editor' });
    expect(box).toHaveAttribute('contenteditable', 'false');
  });

  it('shows new text when the file changes', async () => {
    const { rerender } = render(
      <CodeEditor value="one" onChange={() => {}} onSave={() => {}} label="Code" />,
    );
    rerender(<CodeEditor value="two" onChange={() => {}} onSave={() => {}} label="Code" />);
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Code' })).toHaveTextContent('two'),
    );
  });
});

describe('Files screen', () => {
  const robot = (sync: (body: Record<string, unknown>) => unknown) =>
    installApi((c) => {
      if (c.path === '/api/settings')
        return { ok: true, settings: { local_dir: 'C:\\code', remote_dir: '~/robot_code' } };
      if (c.path === '/api/local_files')
        return { ok: true, files: [{ name: 'a.py', size: 5, sha1: 'x' }] };
      if (c.path === '/api/sync') return sync(c.body);
      if (c.body.cmd === 'ls')
        return {
          ok: true,
          files: [
            { name: 'a.py', size: 5, sha1: 'x' },
            { name: 'old.py', size: 3, sha1: 'o' },
          ],
        };
      return { ok: true, programs: [] };
    });

  const open = async () => {
    useStudio
      .getState()
      .setSettings({ settings: { local_dir: 'C:\\code', remote_dir: '~/robot_code' } });
    render(
      <TooltipProvider>
        <Files />
        <DialogHost />
      </TooltipProvider>,
    );
    expect(await screen.findByText('Comparison')).toBeInTheDocument();
    await screen.findByText('Same');
  };

  it('compares the two folders and shows how each file differs', async () => {
    robot(() => ({ ok: true }));
    await open();
    expect(screen.getByText('Robot only')).toBeInTheDocument();
    expect(screen.getByText(/1 same, 0 changed, 0 new, 1 robot only/)).toBeInTheDocument();
  });

  it('previews without changing anything', async () => {
    const m = robot(() => ({
      ok: true,
      dry_run: true,
      would_transfer: ['a.py'],
      skipped: 2,
      uploaded: [],
      deleted: [],
      would_delete: [],
    }));
    await open();
    await userEvent.click(screen.getByRole('button', { name: /Preview upload/ }));
    expect(await screen.findByText('Preview, nothing changed')).toBeInTheDocument();
    expect(screen.getByText(/Would transfer/)).toHaveTextContent('1 file');
    const sync = m.calls.filter((c) => c.path === '/api/sync');
    expect(sync[0]?.body).toMatchObject({ dry_run: true, delete: false, direction: 'up' });
  });

  it('never deletes by default', async () => {
    const m = robot(() => ({ ok: true, uploaded: ['a.py'], deleted: [], skipped: 0 }));
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Upload changes' }));
    await waitFor(() => expect(m.calls.some((c) => c.path === '/api/sync')).toBe(true));
    const body = m.calls.find((c) => c.path === '/api/sync')?.body;
    expect(body).toMatchObject({ delete: false, dry_run: false });
    expect(body?.confirm_delete).toBeUndefined();
  });

  it('lists what would be deleted and waits for a yes before deleting', async () => {
    const m = robot((b) =>
      b.dry_run
        ? { ok: true, dry_run: true, would_transfer: [], would_delete: ['old.py'], skipped: 1 }
        : { ok: true, uploaded: [], deleted: ['old.py'], skipped: 1 },
    );
    await open();
    await userEvent.click(screen.getByRole('checkbox', { name: /also delete files on the robot/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Upload changes' }));
    expect(
      await screen.findByRole('dialog', { name: 'Delete 1 file on the robot?' }),
    ).toBeInTheDocument();
    expect(screen.getByText('old.py', { selector: 'pre' })).toBeInTheDocument();
    // nothing real was sent yet: only the dry run
    expect(m.calls.filter((c) => c.path === '/api/sync' && c.body.dry_run === false)).toHaveLength(
      0,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Delete and upload' }));
    await waitFor(() =>
      expect(
        m.calls.filter((c) => c.path === '/api/sync' && c.body.dry_run === false),
      ).toHaveLength(1),
    );
    const real = m.calls.find((c) => c.path === '/api/sync' && c.body.dry_run === false);
    expect(real?.body).toMatchObject({ delete: true, confirm_delete: true });
  });

  it('sends nothing when the delete question is cancelled', async () => {
    const m = robot(() => ({
      ok: true,
      dry_run: true,
      would_transfer: [],
      would_delete: ['old.py'],
      skipped: 1,
    }));
    await open();
    await userEvent.click(screen.getByRole('checkbox', { name: /also delete files on the robot/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Upload changes' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(m.calls.filter((c) => c.path === '/api/sync' && c.body.dry_run === false)).toHaveLength(
      0,
    );
  });

  it('asks before a download overwrites local files', async () => {
    const m = robot(() => ({ ok: true, uploaded: [], deleted: [], skipped: 0 }));
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Download from robot' }));
    expect(
      await screen.findByRole('dialog', { name: 'Download from the robot?' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(m.calls.filter((c) => c.path === '/api/sync')).toHaveLength(0);
  });

  it('reports a sync failure in the transfer panel', async () => {
    robot(() => ({ ok: false, error: 'another sync is running' }));
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Upload changes' }));
    expect(
      await screen.findByText('another sync is running', { selector: '.note-bad' }),
    ).toBeInTheDocument();
  });
});
