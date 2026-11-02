import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { App } from './App';
import { ROUTES } from './state/router';
import { useStudio } from './state/store';
import { applyTheme, useUi } from './state/ui';
import { connectedStatus, installApi, resetStores } from './test/helpers';

beforeEach(() => {
  resetStores();
  window.location.hash = '';
  useUi.setState({ theme: 'system', navCollapsed: false, navOpen: false, eventsOpen: false });
  applyTheme('system');
  installApi((c) => {
    if (c.path === '/api/estop') return { ok: true, steps: {} };
    if (c.body.cmd === 'ls') return { ok: true, files: [] };
    if (c.body.cmd === 'describe') return { ok: true, programs: [] };
    return { ok: true, candidates: [] };
  });
});

describe('App shell', () => {
  it('shows the E-STOP, the connection state and the whole menu', () => {
    render(<App runtime={false} />);
    expect(screen.getByRole('button', { name: /emergency stop/i })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Not connected');
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    for (const r of ROUTES.filter((x) => x.nav !== false))
      expect(within(nav).getByRole('link', { name: r.label })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('shows the robot name, route, battery and Wi-Fi in the top bar', () => {
    render(<App runtime={false} />);
    act(() => {
      const s = useStudio.getState();
      s.dispatch({ ev: 'hello', hostname: 'turtlebot4' });
      s.dispatch({ ev: 'conn', state: 'connected', host: '192.168.185.3', via: 'cable' });
      s.dispatch({ ev: 'status', battery: { percent: 76.4 }, net: { signal_dbm: -57 } });
    });
    const pill = screen.getByRole('status');
    expect(pill).toHaveTextContent('Connected');
    expect(pill).toHaveTextContent('turtlebot4');
    expect(pill).toHaveTextContent('cable');
    expect(screen.getByLabelText('Robot vitals')).toHaveTextContent('76%');
    expect(screen.getByLabelText('Robot vitals')).toHaveTextContent('-57 dBm');
  });

  it('moves between screens with the menu', async () => {
    render(<App runtime={false} />);
    await userEvent.click(screen.getByRole('link', { name: 'Programs' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Programs' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Logs' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Logs' })).toBeInTheDocument();
  });

  it('warns that Studio is unreachable and offers a retry', () => {
    render(<App runtime={false} />);
    act(() =>
      useStudio.getState().setSse({ state: 'down', attempt: 1, retryAt: Date.now() + 4000 }),
    );
    const alert = screen.getByText(/Lost connection to Studio/);
    expect(alert.closest('[role="alert"]')).toHaveTextContent('E-STOP may not reach the robot');
    expect(screen.getByRole('button', { name: 'Retry now' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Studio not responding');
  });

  it('shows the e-stop banner with a release button while the e-stop is on', async () => {
    render(<App runtime={false} />);
    connectedStatus();
    expect(screen.queryByText('E-stop is on.')).not.toBeInTheDocument();
    act(() => useStudio.getState().dispatch({ ev: 'status', estop: { on: true } }));
    expect(await screen.findByText('E-stop is on.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Release e-stop' }));
    expect(await screen.findByRole('dialog', { name: 'Release the e-stop?' })).toBeInTheDocument();
  });

  it('shows the reconnect banner with its countdown and a stop button', () => {
    render(<App runtime={false} />);
    act(() =>
      useStudio.getState().dispatch({
        ev: 'conn',
        state: 'reconnecting',
        attempt: 2,
        next_in: 4,
        since: 1_700_000_000,
      }),
    );
    expect(screen.getByText(/Reconnecting \(attempt 2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop reconnecting' })).toBeInTheDocument();
  });

  it('replaces everything with "Studio has stopped" after a quit', () => {
    render(<App runtime={false} />);
    act(() => useStudio.getState().dispatch({ ev: 'quit' }));
    expect(screen.getByRole('heading', { name: 'Studio has stopped' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('asks before quitting Studio', async () => {
    render(<App runtime={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Quit Studio' }));
    expect(await screen.findByRole('dialog', { name: 'Quit Studio?' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(useStudio.getState().stopped).toBe(false);
  });

  it('keeps the colour theme choice on the page and in storage', async () => {
    render(<App runtime={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Colour theme' }));
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Dark' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem('studio_theme')).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Colour theme' }));
    await userEvent.click(
      await screen.findByRole('menuitemradio', { name: /Match this computer/ }),
    );
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('collapses the menu to icons', async () => {
    render(<App runtime={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Collapse the menu' }));
    expect(screen.getByRole('navigation', { name: 'Sections' })).toHaveClass('is-collapsed');
    expect(useUi.getState().navCollapsed).toBe(true);
  });
});

describe('Overview', () => {
  it('connects to the address that was typed', async () => {
    const m = installApi((c) =>
      c.path === '/api/connect' ? { ok: true } : { ok: true, candidates: [] },
    );
    render(<App runtime={false} />);
    const input = screen.getByRole('textbox', { name: /Robot address/ });
    await userEvent.type(input, '10.0.0.5');
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }));
    expect(m.calls.find((c) => c.path === '/api/connect')?.body).toEqual({ host: '10.0.0.5' });
  });

  it('lists the robots found by Discover', async () => {
    installApi((c) =>
      c.path === '/api/discover'
        ? {
            ok: true,
            candidates: [
              {
                host: '192.168.185.3',
                via: 'cable',
                reachable: true,
                ms: 3,
                identity: 'confirmed',
              },
            ],
          }
        : { ok: true },
    );
    render(<App runtime={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Discover' }));
    expect(await screen.findByText('Your robot (identity confirmed)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect to 192.168.185.3' })).toBeInTheDocument();
  });

  it('shows values as old when the robot is not connected', () => {
    render(<App runtime={false} />);
    expect(screen.getAllByText('Old values').length).toBeGreaterThan(3);
  });

  it('asks the motion question before undocking', async () => {
    const m = installApi(() => ({ ok: true }));
    render(<App runtime={false} />);
    connectedStatus();
    act(() => useStudio.getState().dispatch({ ev: 'status', dock: { is_docked: true } }));
    await userEvent.click(await screen.findByRole('button', { name: 'Undock' }));
    expect(
      await screen.findByRole('dialog', { name: 'Confirm robot movement' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(m.calls.filter((c) => c.body.cmd === 'undock')).toHaveLength(0);
  });
});
