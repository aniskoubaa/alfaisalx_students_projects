import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { Sidebar } from '../components/shell/Sidebar';
import { TopBar } from '../components/shell/TopBar';
import { DialogHost, TooltipProvider } from '../components/ui';
import { argsPlaceholder } from '../lib/requiredArgs';
import { useArgs } from '../state/args';
import { useCode } from '../state/code';
import { saveAndRun } from '../state/codeActions';
import { confirmMotion } from '../state/feedback';
import { NAV_GROUPS, ROUTES } from '../state/router';
import { useStudio } from '../state/store';
import { useUi } from '../state/ui';
import { connectedStatus, installApi, resetStores } from '../test/helpers';
import { Code } from './Code';
import { Overview } from './Overview';
import { Programs } from './Programs';

beforeEach(() => {
  resetStores();
  useArgs.setState({ args: {} });
  useUi.setState({ navCollapsed: false, newProgramAsked: false });
  window.location.hash = '';
  installApi(() => ({ ok: true }));
});

function dock(isDocked: boolean) {
  act(() => useStudio.getState().dispatch({ ev: 'status', dock: { is_docked: isDocked } }));
}

describe('Home', () => {
  const tasks = [
    ['Drive the robot', '#/live'],
    ['Run a program', '#/programs'],
    ['Make a map', '#/maps'],
    ["Change the robot's menu", '#/menu'],
    ['Copy a folder to the robot', '#/files'],
  ] as const;

  it('shows six task buttons once connected, each going to its screen', async () => {
    connectedStatus();
    render(
      <TooltipProvider>
        <Overview />
      </TooltipProvider>,
    );
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What do you want to do?' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Robot status' })).toBeInTheDocument();
    expect(document.querySelectorAll('.task')).toHaveLength(6);
    for (const [label, hash] of tasks) {
      window.location.hash = '';
      await userEvent.click(screen.getByRole('button', { name: new RegExp(label) }));
      expect(window.location.hash).toBe(hash);
    }
  });

  it('"Write your own program" goes to Code and asks for the New program dialog', async () => {
    connectedStatus();
    render(<Overview />);
    await userEvent.click(screen.getByRole('button', { name: /Write your own program/ }));
    expect(window.location.hash).toBe('#/code');
    expect(useUi.getState().newProgramAsked).toBe(true);
  });

  it('shows no task buttons before connecting', () => {
    render(<Overview />);
    expect(screen.queryByText('What do you want to do?')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Robot status' })).toBeInTheDocument();
  });

  it('says so, with an Undock button, when the robot is docked', async () => {
    const m = installApi(() => ({ ok: true }));
    connectedStatus();
    render(
      <TooltipProvider>
        <Overview />
        <DialogHost />
      </TooltipProvider>,
    );
    expect(screen.queryByText(/The robot is on its dock/)).toBeNull();
    dock(true);
    const line = (await screen.findByText(/The robot is on its dock/)).closest('.task-docked');
    expect(line).not.toBeNull();
    await userEvent.click(within(line as HTMLElement).getByRole('button', { name: 'Undock' }));
    expect(
      await screen.findByRole('dialog', { name: 'Confirm robot movement' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(m.calls.filter((c) => c.body.cmd === 'undock')).toHaveLength(0);
  });
});

describe('sidebar groups', () => {
  it('has the four group headings and every link under its own group', () => {
    render(
      <TooltipProvider>
        <Sidebar />
      </TooltipProvider>,
    );
    const heads = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(heads).toEqual(['Use the robot', 'Make your own', 'Check on it', 'Set up']);
    const names = (g: string) =>
      within(screen.getByRole('region', { name: g }))
        .getAllByRole('link')
        .map((a) => a.textContent);
    expect(names('Use the robot')).toEqual(['Home', 'Drive', 'Programs', 'Maps', 'Routes']);
    expect(names('Make your own')).toEqual(['Code', 'Robot menu', 'Files']);
    expect(names('Check on it')).toEqual(['Charts', 'Logs', 'Topics']);
    expect(names('Set up')).toEqual(['Wi-Fi', 'Settings and help']);
  });

  it('keeps the paths and puts every menu screen in a group', () => {
    expect(ROUTES.find((r) => r.label === 'Home')?.path).toBe('/overview');
    expect(ROUTES.find((r) => r.label === 'Drive')?.path).toBe('/live');
    expect(ROUTES.find((r) => r.label === 'Settings and help')?.path).toBe('/tools');
    for (const r of ROUTES.filter((x) => x.nav !== false))
      expect(NAV_GROUPS.some((g) => g.id === r.group)).toBe(true);
  });

  it('still lists every link when the menu is collapsed', () => {
    useUi.setState({ navCollapsed: true });
    render(
      <TooltipProvider>
        <Sidebar />
      </TooltipProvider>,
    );
    expect(screen.getAllByRole('link')).toHaveLength(ROUTES.filter((r) => r.nav !== false).length);
    expect(screen.getByRole('link', { name: 'Drive' })).toBeInTheDocument();
  });
});

describe('top bar', () => {
  it('gives every icon-only button a tooltip text and a name', () => {
    render(
      <TooltipProvider>
        <TopBar />
      </TooltipProvider>,
    );
    const buttons = screen
      .getAllByRole('button')
      .filter((b) => !(b.textContent ?? '').trim() || b.classList.contains('btn-icon'));
    expect(buttons.length).toBeGreaterThanOrEqual(4);
    for (const b of buttons) {
      expect(b.getAttribute('aria-label')).toBeTruthy();
      expect(b.getAttribute('title')).toBeTruthy();
    }
  });
});

describe('arguments placeholder', () => {
  it('uses the catalog example, else the docstring example, else Optional', () => {
    expect(
      argsPlaceholder({ examples: [{ args: 'square --dry-run', what: '' }] }, undefined),
    ).toBe('for example square --dry-run');
    expect(argsPlaceholder(undefined, undefined)).toBe('Optional');
    expect(argsPlaceholder({ examples: [{ args: '', what: '' }] }, undefined)).toBe(
      'Optional',
    );
    expect(argsPlaceholder(undefined, { example: '--count 5' })).toBe('for example --count 5');
    expect(argsPlaceholder(undefined, { example: '  ' })).toBe('Optional');
    expect(
      argsPlaceholder({ examples: [{ args: 'square --dry-run', what: '' }] }, { example: '--count 5' }),
    ).toBe('for example square --dry-run');
  });

  it('is shown in the Code screen and is never the fixed --turns 1', () => {
    connectedStatus();
    const s = useStudio.getState();
    s.setCatalog({ 'spin.py': { examples: [{ args: '--angle 90 --dry-run', what: 'spin' }] } }, []);
    s.setFiles([{ name: 'spin.py' }, { name: 'mine.py' }]);
    useCode.setState({ name: 'spin.py', orig: 'x', text: 'x' });
    const { unmount } = render(
      <TooltipProvider>
        <Code />
      </TooltipProvider>,
    );
    const box = screen.getByLabelText('Arguments for Save and run');
    expect(box).toHaveAttribute('placeholder', 'for example --angle 90 --dry-run');
    unmount();
    useCode.setState({ name: 'mine.py' });
    render(
      <TooltipProvider>
        <Code />
      </TooltipProvider>,
    );
    const box2 = screen.getByLabelText('Arguments for Save and run');
    expect(box2).toHaveAttribute('placeholder', 'Optional');
    expect(document.body.textContent).not.toContain('--turns 1');
  });
});

describe('Programs and Code link to each other', () => {
  it('gives the empty Programs list a New program and a Copy a folder button', async () => {
    connectedStatus();
    render(
      <TooltipProvider>
        <Programs />
      </TooltipProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Copy a folder' }));
    expect(window.location.hash).toBe('#/files');
    await userEvent.click(screen.getByRole('button', { name: 'New program' }));
    expect(window.location.hash).toBe('#/code');
    expect(useUi.getState().newProgramAsked).toBe(true);
  });

  it('opens the New program dialog in Code when it was asked for', async () => {
    connectedStatus();
    useUi.setState({ newProgramAsked: true });
    render(
      <TooltipProvider>
        <Code />
      </TooltipProvider>,
    );
    expect(await screen.findByRole('dialog', { name: 'New program' })).toBeInTheDocument();
  });

  it('puts an Edit code button on a program card and a Run button on each Code file', async () => {
    const m = installApi((c) => {
      if (c.body.cmd === 'read_file') return { ok: true, path: 'mine.py', text: 'hi\n', sha1: 's' };
      if (c.body.cmd === 'run') return { ok: true, run_id: 'r1', pid: 3 };
      return { ok: true, programs: [], files: [{ name: 'mine.py' }] };
    });
    connectedStatus();
    useStudio.getState().setFiles([{ name: 'mine.py' }]);
    const { unmount } = render(
      <TooltipProvider>
        <Programs />
      </TooltipProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Edit code of mine.py' }));
    await waitFor(() => expect(useCode.getState().name).toBe('mine.py'));
    expect(window.location.hash).toBe('#/code');
    unmount();
    render(
      <TooltipProvider>
        <Code />
        <DialogHost />
      </TooltipProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Run mine.py' }));
    await waitFor(() => expect(m.calls.some((c) => c.body.cmd === 'run')).toBe(true));
  });

  it('asks the movement question when a moving program is run from the Code list', async () => {
    const m = installApi(() => ({
      ok: true,
      run_id: 'r1',
      pid: 3,
      programs: [],
      files: [{ name: 'go.py' }],
    }));
    connectedStatus();
    const s = useStudio.getState();
    s.setCatalog({ 'go.py': { moves: true } }, []);
    s.setFiles([{ name: 'go.py' }]);
    render(
      <TooltipProvider>
        <Code />
        <DialogHost />
      </TooltipProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Run go.py' }));
    expect(
      await screen.findByRole('dialog', { name: 'Confirm robot movement' }),
    ).toBeInTheDocument();
    expect(m.calls.filter((c) => c.body.cmd === 'run')).toHaveLength(0);
  });
});

describe('Save and run', () => {
  it('says Running <name> when the file did not change', async () => {
    installApi((c) => {
      if (c.body.cmd === 'write_file') return { ok: true, unchanged: true, sha1: 's' };
      if (c.body.cmd === 'run') return { ok: true, run_id: 'r1', pid: 3 };
      return { ok: true, programs: [] };
    });
    connectedStatus();
    useCode.setState({ name: 'spin.py', orig: 'x', text: 'x', sha1: 's' });
    await expect(saveAndRun('')).resolves.toBe(true);
    expect(useCode.getState().status).toBe('Running spin.py');
  });
});

describe('docked warning in the movement question', () => {
  function open() {
    render(
      <TooltipProvider>
        <DialogHost />
      </TooltipProvider>,
    );
    act(() => {
      void confirmMotion(<p>Test move</p>);
    });
  }

  it('shows the warning and an Undock button while docked', async () => {
    connectedStatus();
    dock(true);
    open();
    const dialog = await screen.findByRole('dialog', { name: 'Confirm robot movement' });
    expect(within(dialog).getByText('The robot is on its dock. Undock it first.')).toBeVisible();
    expect(within(dialog).getByRole('button', { name: 'Undock' })).toBeInTheDocument();
  });

  it('shows nothing extra when the robot is off its dock', async () => {
    connectedStatus();
    open();
    const dialog = await screen.findByRole('dialog', { name: 'Confirm robot movement' });
    expect(within(dialog).queryByText(/on its dock/)).toBeNull();
    expect(within(dialog).queryByRole('button', { name: 'Undock' })).toBeNull();
  });
});

describe('dialogs are never reused', () => {
  it('gives each dialog its own number, even with the same title', async () => {
    const { useDialogs, confirm: ask } = await import('../state/feedback');
    void ask({ title: 'Confirm robot movement', body: 'one', requireCheck: 'clear' });
    const first = useDialogs.getState().stack.at(-1);
    if (first?.kind === 'confirm') first.resolve(false);
    if (first) useDialogs.getState().close(first);
    void ask({ title: 'Confirm robot movement', body: 'two', requireCheck: 'clear' });
    const second = useDialogs.getState().stack.at(-1);
    expect(first?.uid).toBeDefined();
    expect(second?.uid).toBeDefined();
    expect(second?.uid).not.toBe(first?.uid);
    if (second) useDialogs.getState().close(second);
  });
});
