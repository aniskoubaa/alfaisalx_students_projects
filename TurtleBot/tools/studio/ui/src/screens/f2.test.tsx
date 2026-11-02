import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { DialogHost, TooltipProvider } from '../components/ui';
import { useStudio } from '../state/store';
import { useTopics, initialTopics } from '../state/topicsStore';
import { initialWifi, useWifi } from '../state/wifiStore';
import { useWizard } from '../state/wizardStore';
import { openWizard } from '../state/wizardActions';
import { initialWizard } from '../lib/wizard';
import { connectedStatus, installApi, resetStores } from '../test/helpers';
import { Settings } from './settings/Settings';
import { Topics } from './topics/Topics';
import { Wifi } from './wifi/Wifi';
import { WizardDialog } from './wizard/WizardDialog';

const wifiInfo = {
  ok: true,
  wlan0: { mode: 'infrastructure', ssid: 'HomeNet', ip: '192.168.50.12', signal_dbm: -55 },
  saved: [
    { name: 'HomeNet', ssid: 'HomeNet', priority: 10, autoconnect: true, active: true },
    { name: 'netplan-wlan0-Turtlebot4', ssid: 'Turtlebot4', mode: 'ap' },
  ],
  scan: [
    { ssid: 'Lab', signal: 70, security: 'WPA2', chan: '6' },
    { ssid: 'Cafe', signal: 40, security: '--', chan: '1' },
  ],
};

function wrap(ui: React.ReactElement) {
  return render(
    <TooltipProvider>
      {ui}
      <DialogHost />
    </TooltipProvider>,
  );
}

beforeEach(() => {
  resetStores();
  useWifi.setState(initialWifi());
  useTopics.setState(initialTopics());
  useWizard.setState({ open: false, w: initialWizard() });
  window.location.hash = '';
});

describe('Wi-Fi screen', () => {
  it('adds a network, clears the password and follows the job', async () => {
    connectedStatus();
    const m = installApi((c) => {
      if (c.path === '/api/laptop_net')
        return { ok: true, wifi: { ssid: 'Lab' }, wired: [], os: 'windows' };
      if (c.body.cmd === 'wifi_info') return wifiInfo;
      if (c.path === '/api/robot_wifi_add') return { ok: true, nonce: 'a'.repeat(32), fake: true };
      if (c.path === '/api/robot_wifi_status') {
        return {
          ok: true,
          secret: 'fetched',
          join: { state: 'joined', ssid: 'Lab', ip: '10.1.1.9' },
        };
      }
      return { ok: true };
    });
    wrap(<Wifi />);
    const name = await screen.findByLabelText('Network name (SSID)');
    await waitFor(() => expect(name).toHaveValue('Lab'));
    const add = screen.getByRole('button', { name: /^Add (this Wi-Fi|“Lab”)/ });
    expect(add).toBeDisabled();
    const psk = screen.getByLabelText('Wi-Fi password');
    await userEvent.type(psk, 'secret-pass-1');
    await waitFor(() => expect(add).toBeEnabled());
    await userEvent.click(add);
    await userEvent.click(await screen.findByRole('button', { name: 'Open terminal' }));
    await screen.findByText(/The robot joined Lab/);
    expect(psk).toHaveValue('');
    const call = m.calls.find((c) => c.path === '/api/robot_wifi_add');
    expect(call?.body).toMatchObject({
      ssid: 'Lab',
      psk: 'secret-pass-1',
      confirm: true,
      connect_now: false,
    });
    // the password is not left in anything the page remembers
    expect(JSON.stringify(sessionStorage)).not.toContain('secret-pass-1');
  });

  it('protects the robot own entries and disables unsupported networks', async () => {
    connectedStatus();
    installApi((c) => {
      if (c.path === '/api/laptop_net') return { ok: true, wifi: null, wired: [] };
      if (c.body.cmd === 'wifi_info') return wifiInfo;
      return { ok: true };
    });
    wrap(<Wifi />);
    const saved = await screen.findByRole('table', { name: 'Saved networks on the robot' });
    expect(within(saved).getByText('Protected')).toBeInTheDocument();
    expect(within(saved).getAllByRole('button', { name: /Remove/ })).toHaveLength(1);
    expect(
      await screen.findByRole('button', { name: 'Use Cafe as the network to join' }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Use Lab as the network to join' })).toBeEnabled();
  });
});

describe('Topics screen', () => {
  it('lists topics, watches at most four and unwatches', async () => {
    connectedStatus();
    const names = ['/a', '/b', '/c', '/d', '/e'];
    let id = 0;
    const m = installApi((c) => {
      if (c.body.cmd === 'topics')
        return {
          ok: true,
          topics: names.map((name) => ({ name, types: ['x/msg/Y'], publishers: 1 })),
        };
      if (c.body.cmd === 'watch') return { ok: true, watch_id: ++id };
      return { ok: true };
    });
    wrap(<Topics />);
    for (const n of names.slice(0, 4)) {
      await userEvent.click(await screen.findByRole('button', { name: `Watch ${n}` }));
      await screen.findByRole('button', { name: `Watching ${n}` });
    }
    expect(screen.getByRole('button', { name: 'Watch /e' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Stop watching /a' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Watch /e' })).toBeEnabled());
    expect(m.calls.some((c) => c.body.cmd === 'unwatch' && c.body.watch_id === 1)).toBe(true);
  });
});

describe('Settings screen', () => {
  it('saves only the changed keys and shows driving limits', async () => {
    connectedStatus();
    useStudio.getState().setSettings({
      settings: { robot_user: 'ubuntu', auto_reconnect: true },
      defaults: { robot_hostname: 'turtlebot4', robot_user: 'ubuntu' },
      trusted: [{ key: 'k', label: 'Built-in robot key', builtin: true, fingerprint: 'SHA256:z' }],
    });
    const m = installApi((c) => {
      if (c.path === '/api/teleop_limits' && c.method === 'GET') {
        return { ok: true, linear: 0.15, angular: 0.6, max_linear: 0.3, max_angular: 1.2 };
      }
      if (c.path === '/api/settings')
        return { ok: true, robot_user: 'pi', auto_reconnect: true, ui: 'classic' };
      return { ok: true };
    });
    wrap(<Settings />);
    const save = screen.getByRole('button', { name: 'Save settings' });
    expect(save).toBeDisabled();
    const user = screen.getByLabelText('Robot user');
    await userEvent.clear(user);
    await userEvent.type(user, 'pi');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Use the classic interface' }));
    await waitFor(() =>
      expect(screen.getByLabelText('Top forward speed (m/s)')).toHaveValue('0.15'),
    );
    await userEvent.click(save);
    await waitFor(() =>
      expect(m.calls.some((c) => c.path === '/api/settings' && c.method === 'POST')).toBe(true),
    );
    const post = m.calls.find((c) => c.path === '/api/settings' && c.method === 'POST');
    expect(post?.body).toEqual({ robot_user: 'pi', ui: 'classic' });
    expect(m.calls.some((c) => c.path === '/api/teleop_limits' && c.method === 'POST')).toBe(false);
  });

  it('blocks a driving limit above the cap', async () => {
    connectedStatus();
    useStudio.getState().setSettings({ settings: {}, defaults: {} });
    installApi((c) => {
      if (c.path === '/api/teleop_limits') {
        return { ok: true, linear: 0.15, angular: 0.6, max_linear: 0.3, max_angular: 1.2 };
      }
      return { ok: true };
    });
    wrap(<Settings />);
    const lin = await screen.findByLabelText('Top forward speed (m/s)');
    await waitFor(() => expect(lin).toHaveValue('0.15'));
    await userEvent.clear(lin);
    await userEvent.type(lin, '0.9');
    expect(await screen.findByText(/Use a value from 0.02 to 0.3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();
  });
});

describe('Setup wizard', () => {
  it('walks the six steps with a fake robot', async () => {
    connectedStatus();
    const m = installApi((c) => {
      if (c.path === '/api/setup_status') {
        return {
          ok: true,
          ssh: { found: true, version: 'OpenSSH_9' },
          key: { path: '/k', exists: true },
          host: '10.0.0.5',
          os: 'windows',
        };
      }
      if (c.path === '/api/scan_host_key') {
        return {
          ok: true,
          host: '10.0.0.5',
          key: 'ssh-ed25519 AAAA',
          fingerprint: 'SHA256:abc',
          trusted: false,
          label: null,
        };
      }
      if (c.path === '/api/trust_host_key') return { ok: true, trusted: [] };
      if (c.path === '/api/setup_key') return { ok: true, note: 'Terminal opened.' };
      if (c.path === '/api/test_login') return { ok: true, hostname: 'tb4' };
      if (c.path === '/api/connect') return { ok: true };
      if (c.path === '/api/settings') return { ok: true, setup_done: true };
      return { ok: true };
    });
    wrap(<WizardDialog />);
    openWizard();
    await screen.findByText(/OpenSSH found/);
    const titles = [
      'Check that ssh is installed',
      'Find the robot',
      "Check the robot's identity",
      "Create this computer's key",
      'Allow key login',
      'Test the login',
    ];
    const step = (n: number) =>
      screen.getByRole('heading', { level: 3, name: titles[n - 1] }).closest('li') as HTMLElement;
    expect(within(step(3)).getByRole('button', { name: 'Check robot identity' })).toBeDisabled();
    await userEvent.click(within(step(2)).getByRole('button', { name: 'Use this address' }));
    await waitFor(() =>
      expect(within(step(3)).getByRole('button', { name: 'Check robot identity' })).toBeEnabled(),
    );
    await userEvent.click(within(step(3)).getByRole('button', { name: 'Check robot identity' }));
    const trust = await within(step(3)).findByRole('button', { name: 'Trust this robot' });
    expect(trust).toBeDisabled();
    await userEvent.click(within(step(3)).getByRole('checkbox'));
    await userEvent.click(trust);
    await waitFor(() => expect(within(step(3)).getByText('Done')).toBeInTheDocument());
    await userEvent.click(within(step(4)).getByRole('button', { name: 'Create again' }));
    await userEvent.click(within(step(5)).getByRole('button', { name: 'Open terminal' }));
    await within(step(5)).findByText('Terminal opened.');
    await userEvent.click(within(step(6)).getByRole('button', { name: 'Test login' }));
    await userEvent.click(await within(step(6)).findByRole('button', { name: 'Connect' }));
    await waitFor(() => expect(useWizard.getState().open).toBe(false));
    expect(m.calls.some((c) => c.path === '/api/connect' && c.body.host === '10.0.0.5')).toBe(true);
    expect(m.calls.some((c) => c.path === '/api/settings' && c.body.setup_done === true)).toBe(
      true,
    );
  });

  it('shows how to install ssh when it is missing', async () => {
    installApi((c) => {
      if (c.path === '/api/setup_status') return { ok: true, ssh: { found: false }, os: 'linux' };
      return { ok: true };
    });
    wrap(<WizardDialog />);
    openWizard();
    await screen.findByText(/ssh was not found on this computer/);
    expect(screen.getByText(/sudo apt install openssh-client/)).toBeInTheDocument();
  });
});
