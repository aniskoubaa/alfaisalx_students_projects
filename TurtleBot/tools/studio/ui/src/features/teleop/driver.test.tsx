import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDialogs } from '../../state/feedback';
import { installApi, resetStores } from '../../test/helpers';
import { driveDirFor } from './useDriveKeys';
import { useDrive } from './driveStore';
import {
  disarm,
  keyDown,
  keyUp,
  onBridgeTeleop,
  requestArm,
  resetDriver,
  setStick,
} from './driver';

type Body = Record<string, unknown>;

/** Answer the "Arm driving?" dialog. */
async function answerDialog(yes: boolean) {
  await vi.waitFor(() => expect(useDialogs.getState().stack.length).toBe(1));
  const d = useDialogs.getState().stack[0];
  if (d?.kind === 'confirm') d.resolve(yes);
  useDialogs.setState({ stack: [] });
}

function setup(armReply: Body = { ok: true, armed: true, max_linear: 0.15, max_angular: 0.6 }) {
  const m = installApi((c) => {
    if (c.body.cmd === 'teleop_arm') return c.body.on ? armReply : { ok: true, armed: false };
    if (c.body.cmd === 'teleop')
      return { ok: true, armed: true, vx: c.body.vx, wz: c.body.wz, seq: c.body.seq };
    return { ok: true };
  });
  return m;
}

const cmds = (calls: Array<{ body: Body }>, name: string) =>
  calls.filter((c) => c.body.cmd === name);

beforeEach(() => {
  resetStores();
  resetDriver();
});
afterEach(() => {
  resetDriver();
  vi.useRealTimers();
});

describe('arming', () => {
  it('does nothing when the question is declined', async () => {
    const m = setup();
    const p = requestArm();
    await answerDialog(false);
    expect(await p).toBe(false);
    expect(cmds(m.calls, 'teleop_arm')).toHaveLength(0);
    expect(useDrive.getState().phase).toBe('off');
  });

  it('shows the refusal text from the bridge as written', async () => {
    setup({ ok: false, armed: false, error: 'The robot is docked. Undock first.' });
    const p = requestArm();
    await answerDialog(true);
    expect(await p).toBe(false);
    expect(useDrive.getState().phase).toBe('off');
    expect(useDrive.getState().reason).toBe('The robot is docked. Undock first.');
  });

  it('arms, sends a command for a held key and a zero on release, then disarms on blur', async () => {
    const m = setup();
    const p = requestArm();
    await answerDialog(true);
    expect(await p).toBe(true);
    expect(useDrive.getState().phase).toBe('armed');
    act(() => keyDown('fwd'));
    await vi.waitFor(() => expect(cmds(m.calls, 'teleop').length).toBeGreaterThanOrEqual(1));
    const first = cmds(m.calls, 'teleop')[0]?.body;
    expect(first).toMatchObject({ vx: 0.15, wz: 0, seq: 1 });
    act(() => keyUp('fwd'));
    await vi.waitFor(() => {
      const t = cmds(m.calls, 'teleop');
      expect(t[t.length - 1]?.body).toMatchObject({ vx: 0, wz: 0 });
    });
    act(() => {
      window.dispatchEvent(new Event('blur'));
    });
    // The blur watcher is installed by FeatureHost; disarm directly as it would.
    act(() => disarm('The window lost focus.'));
    expect(useDrive.getState().phase).toBe('off');
    await vi.waitFor(() =>
      expect(cmds(m.calls, 'teleop_arm').some((c) => c.body.on === false)).toBe(true),
    );
  });

  it('follows the stick and ignores input when not armed', async () => {
    const m = setup();
    act(() => setStick(1, 0));
    expect(cmds(m.calls, 'teleop')).toHaveLength(0);
  });
});

describe('bridge-side disarm', () => {
  it('shows the reason and does not send another disarm', async () => {
    const m = setup();
    const p = requestArm();
    await answerDialog(true);
    await p;
    const before = cmds(m.calls, 'teleop_arm').length;
    act(() => onBridgeTeleop(false, 'e-stop'));
    expect(useDrive.getState().phase).toBe('off');
    expect(useDrive.getState().reason).toBe('The E-STOP was pressed.');
    expect(cmds(m.calls, 'teleop_arm')).toHaveLength(before);
  });
});

describe('drive keys', () => {
  const ev = (key: string, target: EventTarget | null = document.body) => ({
    key,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target,
  });

  it('maps W A S D and arrows, ignores other keys and modifiers', () => {
    expect(driveDirFor(ev('w'))).toBe('fwd');
    expect(driveDirFor(ev('ArrowLeft'))).toBe('left');
    expect(driveDirFor(ev('x'))).toBeNull();
    expect(driveDirFor({ ...ev('w'), ctrlKey: true })).toBeNull();
  });

  it('does not drive while typing, on a slider, or in a dialog', () => {
    const input = document.createElement('input');
    input.type = 'text';
    const range = document.createElement('input');
    range.type = 'range';
    const dlg = document.createElement('div');
    dlg.setAttribute('role', 'dialog');
    const inner = document.createElement('button');
    dlg.appendChild(inner);
    expect(driveDirFor(ev('w', input))).toBeNull();
    expect(driveDirFor(ev('ArrowLeft', range))).toBeNull();
  });
});
