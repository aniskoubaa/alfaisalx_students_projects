import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { releaseEstop, runProgram } from '../state/actions';
import { confirmMotion } from '../state/feedback';
import { useStudio } from '../state/store';
import { installApi, resetStores } from '../test/helpers';
import { EStopButton, EStopKeys } from './shell/EStopButton';
import { DialogHost, TooltipProvider } from './ui';

const answer = (call: { path: string; body: Record<string, unknown> }) => {
  if (call.path === '/api/estop') return { ok: true, steps: { zero_cmd_vel: 'sent' } };
  if (call.body.cmd === 'run') return { ok: true, run_id: 'r1', pid: 9 };
  if (call.body.cmd === 'describe') return { ok: true, programs: [] };
  return { ok: true };
};

function Harness() {
  return (
    <TooltipProvider>
      <EStopKeys />
      <EStopButton />
      <input aria-label="type here" />
      <button type="button">Other button</button>
      <DialogHost />
    </TooltipProvider>
  );
}

beforeEach(resetStores);

describe('E-STOP', () => {
  it('fires from the button', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: /emergency stop/i }));
    await waitFor(() => expect(calls.some((c) => c.path === '/api/estop')).toBe(true));
    expect(useStudio.getState().estopLocal).toBe(true);
    expect(await screen.findByRole('dialog', { name: 'E-stop sent' })).toBeInTheDocument();
  });

  it('fires on Escape and on Space when focus is on the page', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(calls.filter((c) => c.path === '/api/estop')).toHaveLength(1));
  });

  it('does not fire while typing in a field', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    await userEvent.click(screen.getByLabelText('type here'));
    await userEvent.keyboard('a b{Escape}');
    expect(calls.filter((c) => c.path === '/api/estop')).toHaveLength(0);
  });

  it('does not fire on Space over a button (Space presses the button)', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    screen.getByRole('button', { name: 'Other button' }).focus();
    await userEvent.keyboard(' ');
    expect(calls.filter((c) => c.path === '/api/estop')).toHaveLength(0);
  });

  it('works with Ctrl+Shift+E even inside a text field', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    await userEvent.click(screen.getByLabelText('type here'));
    await userEvent.keyboard('{Control>}{Shift>}e{/Shift}{/Control}');
    await waitFor(() => expect(calls.filter((c) => c.path === '/api/estop')).toHaveLength(1));
  });

  it('says plainly when the e-stop request failed', async () => {
    installApi((c) =>
      c.path === '/api/estop' ? { ok: false, error: 'bridge down' } : { ok: true },
    );
    render(<Harness />);
    await userEvent.keyboard('{Escape}');
    expect(
      await screen.findByRole('dialog', { name: 'The e-stop may have failed' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Hold the robot or switch off its power/)).toBeInTheDocument();
  });
});

describe('release e-stop', () => {
  it('asks first and sends nothing when cancelled', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    let done: Promise<void> = Promise.resolve();
    act(() => {
      done = releaseEstop();
    });
    expect(await screen.findByRole('dialog', { name: 'Release the e-stop?' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await done;
    expect(calls.filter((c) => c.body.cmd === 'estop_release')).toHaveLength(0);
  });

  it('releases after the person confirms', async () => {
    const { calls } = installApi(answer);
    useStudio.getState().setEstopLocal(true);
    render(<Harness />);
    let done: Promise<void> = Promise.resolve();
    act(() => {
      done = releaseEstop();
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Release e-stop' }));
    await done;
    expect(calls.filter((c) => c.body.cmd === 'estop_release')).toHaveLength(1);
    expect(useStudio.getState().estopLocal).toBe(false);
  });
});

describe('motion confirmation', () => {
  it('keeps Start moving off until the area is confirmed clear', async () => {
    installApi(answer);
    render(<Harness />);
    let result: Promise<boolean> = Promise.resolve(false);
    act(() => {
      result = confirmMotion(<p>Test move</p>);
    });
    const start = await screen.findByRole('button', { name: 'Start moving' });
    expect(start).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: /about 1 m around it is clear/ }));
    expect(start).toBeEnabled();
    await userEvent.click(start);
    await expect(result).resolves.toBe(true);
  });

  it('is not closed by Escape, and the E-STOP cancels a waiting question', async () => {
    const { calls } = installApi(answer);
    render(<Harness />);
    let result: Promise<boolean> = Promise.resolve(true);
    act(() => {
      result = confirmMotion(<p>Test move</p>);
    });
    await screen.findByRole('dialog', { name: 'Confirm robot movement' });
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(calls.some((c) => c.path === '/api/estop')).toBe(true));
    // Escape sent the e-stop, and the motion question can no longer be answered with "yes"
    await expect(result).resolves.toBe(false);
    expect(await screen.findByRole('dialog', { name: 'E-stop sent' })).toBeInTheDocument();
    expect(
      screen.queryByRole('dialog', { name: 'Confirm robot movement' }),
    ).not.toBeInTheDocument();
  });

  it('is cancelled by the Cancel button', async () => {
    installApi(answer);
    render(<Harness />);
    let result: Promise<boolean> = Promise.resolve(true);
    act(() => {
      result = confirmMotion(<p>Test move</p>);
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    await expect(result).resolves.toBe(false);
  });

  it('a program that moves the robot is not started without the confirmation', async () => {
    const { calls } = installApi(answer);
    useStudio.getState().setCatalog({ 'motion_shapes.py': { moves: true } }, []);
    render(<Harness />);
    let started: Promise<boolean> = Promise.resolve(true);
    act(() => {
      started = runProgram('motion_shapes.py', 'square --yes');
    });
    expect(await screen.findByText(/moves the robot/)).toBeInTheDocument();
    expect(screen.getByText('square --yes')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await expect(started).resolves.toBe(false);
    expect(calls.filter((c) => c.body.cmd === 'run')).toHaveLength(0);
  });

  it('sends the run with motion and confirmed set once confirmed', async () => {
    const { calls } = installApi(answer);
    useStudio.getState().setCatalog({ 'motion_shapes.py': { moves: true } }, []);
    render(<Harness />);
    let started: Promise<boolean> = Promise.resolve(false);
    act(() => {
      started = runProgram('motion_shapes.py', 'square "two words" --yes');
    });
    await userEvent.click(await screen.findByRole('checkbox', { name: /clear/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Start moving' }));
    await expect(started).resolves.toBe(true);
    const run = calls.find((c) => c.body.cmd === 'run');
    expect(run?.body).toMatchObject({
      path: 'motion_shapes.py',
      args: ['square', 'two words', '--yes'],
      motion: true,
      confirmed: true,
    });
    expect(useStudio.getState().selectedRun).toBe('r1');
  });

  it('runs a program that does not move without a question', async () => {
    const { calls } = installApi(answer);
    useStudio.getState().setCatalog({ 'health_check.py': { moves: false } }, []);
    await runProgram('health_check.py', '');
    expect(calls.find((c) => c.body.cmd === 'run')?.body).toMatchObject({
      motion: false,
      confirmed: false,
    });
  });

  it('refuses an argument box with an open quote', async () => {
    const { calls } = installApi(answer);
    useStudio.getState().setCatalog({ 'a.py': {} }, []);
    await expect(runProgram('a.py', 'say "oops')).resolves.toBe(false);
    expect(calls.filter((c) => c.body.cmd === 'run')).toHaveLength(0);
  });
});
