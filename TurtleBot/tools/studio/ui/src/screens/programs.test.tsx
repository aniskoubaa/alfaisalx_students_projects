import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { App } from '../App';
import { DialogHost, TooltipProvider } from '../components/ui';
import { useArgs } from '../state/args';
import { useCode } from '../state/code';
import { useStudio } from '../state/store';
import { connectedStatus, installApi, resetStores } from '../test/helpers';
import { Programs } from './Programs';

const catalog = {
  'motion_shapes.py': {
    title: 'Drive shapes',
    summary: 'Drives a shape on the floor.',
    moves: true,
    needs_undock: true,
    args: [{ name: '--side', help: 'side length in metres' }],
    examples: [{ args: 'square --side 0.3 --yes', what: 'drives a 30 cm square' }],
    stop: 'Press E-STOP.',
  },
  'motion_common.py': { title: 'Shared code', summary: 'Helper.', category: 'helper' },
};

function setup() {
  resetStores();
  useArgs.setState({ args: {} });
  connectedStatus();
  const s = useStudio.getState();
  s.setCatalog(catalog, []);
  s.setFiles([{ name: 'motion_common.py' }, { name: 'motion_shapes.py' }, { name: 'my_spin.py' }]);
  return installApi((c) => {
    if (c.body.cmd === 'run') return { ok: true, run_id: 'r1', pid: 11 };
    if (c.body.cmd === 'ls')
      return {
        ok: true,
        files: [{ name: 'motion_common.py' }, { name: 'motion_shapes.py' }, { name: 'my_spin.py' }],
      };
    if (c.body.cmd === 'describe') return { ok: true, programs: [] };
    if (c.path === '/api/settings') return { ok: true, settings: { motion_files: ['my_spin.py'] } };
    return { ok: true };
  });
}

const view = () =>
  render(
    <TooltipProvider>
      <Programs />
      <DialogHost />
    </TooltipProvider>,
  );

describe('Programs screen', () => {
  beforeEach(() => {
    window.location.hash = '';
  });

  it('explains each program and says which ones move the robot', () => {
    setup();
    view();
    expect(screen.getByRole('heading', { name: 'Drive shapes' })).toBeInTheDocument();
    expect(screen.getByText('Drives a shape on the floor.')).toBeInTheDocument();
    expect(screen.getByText('Moves the robot')).toBeInTheDocument();
    expect(screen.getByText('Undock first')).toBeInTheDocument();
    expect(screen.getByText('Helper, not run directly')).toBeInTheDocument();
    expect(screen.getByText('Your own program')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run motion_common.py' })).toBeDisabled();
  });

  it('fills the arguments box from an example', async () => {
    setup();
    view();
    await userEvent.click(screen.getAllByText('What does it do?')[1] as HTMLElement);
    await userEvent.click(screen.getByRole('button', { name: /square --side 0.3 --yes/ }));
    expect(screen.getByLabelText('Arguments for motion_shapes.py')).toHaveValue(
      'square --side 0.3 --yes',
    );
  });

  it('asks before a moving program runs, then shows its run', async () => {
    const m = setup();
    view();
    await userEvent.type(screen.getByLabelText('Arguments for motion_shapes.py'), 'square --yes');
    await userEvent.click(screen.getByRole('button', { name: 'Run motion_shapes.py' }));
    await userEvent.click(await screen.findByRole('checkbox', { name: /clear/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Start moving' }));
    await waitFor(() => expect(m.calls.some((c) => c.body.cmd === 'run')).toBe(true));
    expect(m.calls.find((c) => c.body.cmd === 'run')?.body).toMatchObject({
      path: 'motion_shapes.py',
      args: ['square', '--yes'],
    });
    expect(await screen.findByRole('button', { name: 'Stop motion_shapes.py' })).toBeEnabled();
    act(() => useStudio.getState().dispatch({ ev: 'run_output', run_id: 'r1', lines: ['step 1'] }));
    expect(screen.getByLabelText('Program output')).toHaveTextContent('step 1');
  });

  it('stops a run and then every run', async () => {
    const m = setup();
    useStudio.getState().addRun({ id: 'r1', name: 'a.py', pid: 1, motion: false });
    view();
    await userEvent.click(screen.getByRole('button', { name: 'Stop a.py' }));
    await userEvent.click(screen.getByRole('button', { name: 'Stop all' }));
    const stops = m.calls.filter((c) => c.body.cmd === 'stop').map((c) => c.body.run_id);
    expect(stops).toEqual(['r1', 'all']);
  });

  it('lets the person mark their own program as moving the robot', async () => {
    const m = setup();
    view();
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Mark my_spin.py as moving the robot' }),
    );
    await waitFor(() => expect(m.calls.some((c) => c.path === '/api/settings')).toBe(true));
    expect(m.calls.find((c) => c.path === '/api/settings')?.body).toEqual({
      motion_files: ['my_spin.py'],
    });
  });

  it('says so when there is nothing to list', () => {
    resetStores();
    view();
    expect(screen.getByText('Not connected')).toBeInTheDocument();
  });
});

describe('unsaved code and closing the page', () => {
  it('asks before the page closes while the editor has unsaved changes', () => {
    resetStores();
    installApi(() => ({ ok: true }));
    render(<App runtime={false} />);
    const ask = () => {
      const e = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    expect(ask()).toBe(false);
    act(() => useCode.setState({ name: 'a.py', orig: 'x', text: 'y' }));
    expect(ask()).toBe(true);
    act(() => useCode.setState({ orig: 'y' }));
    expect(ask()).toBe(false);
  });
});
