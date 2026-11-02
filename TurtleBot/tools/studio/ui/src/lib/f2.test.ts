import { describe, expect, it } from 'vitest';
import { filterTopics, messageText } from './topics';
import { parseUrlOptions, shouldAutoOpenWizard } from './urlOptions';
import { buildPatch, formFromSettings, limitError, limitsPatch, parseLimit } from './settingsForm';
import { currentWay, pollStep, validPsk, wifiFormState, wifiSecurity, wifiView } from './wifi';
import type { PollState, WifiJob } from './wifi';
import { initialWizard, stepEnabled, wizardReducer } from './wizard';

describe('wifi security and form', () => {
  it('knows which networks the robot can join', () => {
    expect(wifiSecurity('WPA2').ok).toBe(true);
    expect(wifiSecurity('WPA2 WPA3').ok).toBe(true);
    expect(wifiSecurity('WPA3').kind).toBe('wpa3');
    expect(wifiSecurity('WPA2 802.1X').kind).toBe('enterprise');
    expect(wifiSecurity('--').kind).toBe('open');
    expect(wifiSecurity('WEP').kind).toBe('wep');
  });
  it('checks the password length', () => {
    expect(validPsk('short')).toBe(false);
    expect(validPsk('longenough')).toBe(true);
    expect(validPsk('a'.repeat(64))).toBe(true);
    expect(validPsk('a'.repeat(64) + 'é')).toBe(false);
  });
  const info = {
    saved: [{ name: 'Home', ssid: 'Home' }],
    scan: [
      { ssid: 'Cafe', security: '--' },
      { ssid: 'Lab', security: 'WPA2' },
    ],
  };
  const base = { ssid: 'Lab', psk: 'password1', connected: true, hotspotSsid: 'Turtlebot4', info };
  it('says what stops the Add button, one thing at a time', () => {
    expect(wifiFormState({ ...base, connected: false }).why).toMatch(/Connect to the robot/);
    expect(wifiFormState({ ...base, ssid: '' }).why).toMatch(/name/);
    expect(wifiFormState({ ...base, ssid: 'Turtlebot4' }).why).toMatch(/hotspot/);
    expect(wifiFormState({ ...base, ssid: 'Home' }).already).toBe(true);
    expect(wifiFormState({ ...base, ssid: 'Cafe' }).why).toMatch(/Open networks/);
    expect(wifiFormState({ ...base, psk: '' }).why).toMatch(/password/);
    expect(wifiFormState({ ...base, psk: 'x' }).why).toMatch(/8 to 63/);
    expect(wifiFormState(base).why).toBe('');
  });
  it('works out which way to connect is in use', () => {
    const o = { connected: true, via: 'cable', mode: null, laptopSsid: null, hotspotSsid: 'T' };
    expect(currentWay(o)).toBe('C');
    expect(currentWay({ ...o, via: 'hotspot' })).toBe('A');
    expect(currentWay({ ...o, via: 'wifi', mode: 'ap' })).toBe('A');
    expect(currentWay({ ...o, via: 'wifi' })).toBe('B');
    expect(currentWay({ ...o, connected: false, laptopSsid: 'T' })).toBe('A');
    expect(currentWay({ ...o, connected: false })).toBeNull();
  });
});

describe('wifi job state machine', () => {
  const job: WifiJob = { nonce: 'n', ssid: 'Lab', now: true, t: 0 };
  const joined = { secret: 'fetched', join: { state: 'joined', ssid: 'Lab', ip: '1.2.3.4' } };
  it('starts waiting for the robot password', () => {
    const v = wifiView(job, null, false);
    expect(v.done).toBe(false);
    expect(v.steps[1]?.state).toBe('wait');
  });
  it('reports joined, failed, saved and expired', () => {
    expect(wifiView(job, joined, false).result).toBe('joined');
    const failed = { secret: 'fetched', join: { state: 'failed', ssid: 'Lab' } };
    expect(wifiView(job, failed, false).result).toBe('failed');
    const saved = { secret: 'fetched', join: null };
    expect(wifiView({ ...job, now: false }, saved, false).result).toBe('saved');
    expect(wifiView(job, { secret: 'expired', join: null }, false).result).toBe('expired');
  });
  it('ignores the result of another network or an older attempt', () => {
    const other = { secret: 'fetched', join: { state: 'joined', ssid: 'Other' } };
    expect(wifiView(job, other, false).result).toBeNull();
    const older = { secret: 'fetched', join: { state: 'joined', ssid: 'Lab', t: 5 } };
    expect(wifiView({ ...job, base: 5 }, older, false).done).toBe(false);
  });
  it('keeps polling, then stops with the result', () => {
    const none = { ok: true, data: { secret: 'none', join: null } } as const;
    const a = pollStep(job, { last: null, fails: 0 }, none, { connected: true, elapsedMs: 1000 });
    expect(a.stop).toBe(false);
    expect(a.base).toBeNull();
    const done = { ok: true, data: joined } as const;
    const b = pollStep({ ...job, base: null }, a.state, done, { connected: true, elapsedMs: 5000 });
    expect(b.stop).toBe(true);
    expect(b.view.result).toBe('joined');
  });
  it('says the robot was lost after three failures or when Studio is disconnected', () => {
    const bad = { ok: false, error: 'x' } as const;
    let st: PollState = { last: null, fails: 0 };
    for (let i = 0; i < 2; i++) {
      const s = pollStep(job, st, bad, { connected: true, elapsedMs: 0 });
      expect(s.stop).toBe(false);
      st = s.state;
    }
    expect(pollStep(job, st, bad, { connected: true, elapsedMs: 0 }).flag).toBe('lost');
    const off = pollStep(job, { last: null, fails: 0 }, bad, { connected: false, elapsedMs: 0 });
    expect(off.flag).toBe('lost');
  });
  it('gives up after 150 seconds', () => {
    const none = { ok: true, data: { secret: 'none', join: null } } as const;
    const s = pollStep(job, { last: null, fails: 0 }, none, {
      connected: true,
      elapsedMs: 151_000,
    });
    expect(s.flag).toBe('timeout');
    expect(s.stop).toBe(true);
  });
});

describe('wizard steps', () => {
  const setup = (found: boolean) => ({
    ok: true as const,
    ssh: { found, version: 'OpenSSH' },
    key: { path: '/k', exists: true, fingerprint: 'SHA256:x' },
    host: '10.0.0.5',
  });
  it('unlocks a step when the one before is done', () => {
    let w = initialWizard();
    expect(stepEnabled(w, 1)).toBe(true);
    expect(stepEnabled(w, 2)).toBe(false);
    w = wizardReducer(w, { type: 'check_done', result: setup(true) });
    expect(w.st[1]).toBe('ok');
    expect(w.st[4]).toBe('ok');
    expect(w.host).toBe('10.0.0.5');
    expect(stepEnabled(w, 2)).toBe(true);
  });
  it('marks step 1 as a problem without ssh', () => {
    const w = wizardReducer(initialWizard(), { type: 'check_done', result: setup(false) });
    expect(w.st[1]).toBe('bad');
    expect(stepEnabled(w, 2)).toBe(false);
  });
  it('refuses an address with spaces and resets later steps when it changes', () => {
    let w = initialWizard('a b');
    w = wizardReducer(w, { type: 'use_addr' });
    expect(w.st[2]).toBe('bad');
    w = wizardReducer({ ...w, host: '10.0.0.5' }, { type: 'use_addr' });
    expect(w.st[2]).toBe('ok');
    const scan = {
      ok: true as const,
      host: '10.0.0.5',
      key: 'k',
      fingerprint: 'f',
      trusted: false,
      label: null,
    };
    w = wizardReducer(w, { type: 'scan_done', result: scan });
    expect(w.st[3]).toBe('wait');
    w = wizardReducer(w, { type: 'trust_done', ok: true, label: 'R1' });
    expect(w.st[3]).toBe('ok');
    expect(w.scan?.trusted).toBe(true);
    w = wizardReducer({ ...w, host: '10.0.0.9' }, { type: 'use_addr' });
    expect(w.scan).toBeNull();
    expect(w.st[3]).toBe('idle');
  });
  it('lets step 6 run while step 5 waits, and sends a failed login back to the right step', () => {
    let w = initialWizard();
    w = { ...w, st: { ...w.st, 5: 'wait' } };
    expect(stepEnabled(w, 6)).toBe(true);
    const fail = { ok: false as const, error: 'denied', kind: 'key_not_set_up' };
    w = wizardReducer(w, { type: 'test_done', result: fail });
    expect(w.st[6]).toBe('bad');
    expect(w.st[5]).toBe('idle');
    expect(w.msg[6]).toMatch(/step 5/);
    w = wizardReducer(w, { type: 'test_done', result: { ok: true, hostname: 'tb4' } });
    expect(w.st[6]).toBe('ok');
    expect(w.st[5]).toBe('ok');
    expect(w.hostname).toBe('tb4');
  });
});

describe('settings diff', () => {
  const defaults = {
    robot_hostname: 'turtlebot4',
    robot_user: 'ubuntu',
    hotspot_ssid: 'Turtlebot4',
    hotspot_addr: '10.42.0.1',
    cable_addr: '192.168.185.3',
  };
  const saved = formFromSettings({ last_host: '10.0.0.5', auto_reconnect: true }, defaults);
  it('sends nothing when nothing changed, also after retyping the default or adding spaces', () => {
    expect(buildPatch(saved, saved, defaults)).toEqual({});
    const typed = { ...saved, robot_hostname: '  ', last_host: ' 10.0.0.5 ' };
    expect(buildPatch(typed, saved, defaults)).toEqual({});
  });
  it('sends only the changed keys', () => {
    const f = {
      ...saved,
      robot_user: 'pi',
      window_mode: 'browser' as const,
      classic_ui: true,
      motion_files: 'a.py\n\n b.py ',
    };
    expect(buildPatch(f, saved, defaults)).toEqual({
      robot_user: 'pi',
      window_mode: 'browser',
      ui: 'classic',
      motion_files: ['a.py', 'b.py'],
    });
  });
  it('turns the classic switch off again with v2', () => {
    const on = formFromSettings({ ui: 'classic' }, defaults);
    expect(buildPatch({ ...on, classic_ui: false }, on, defaults)).toEqual({ ui: 'v2' });
  });
  it('validates driving limits', () => {
    const caps = { linear: 0.3, angular: 1.2 };
    expect(parseLimit('0,15')).toBe(0.15);
    expect(parseLimit('abc')).toBeNull();
    expect(limitError('linear', '0.15', caps)).toBe('');
    expect(limitError('linear', '0.5', caps)).toMatch(/0.02 to 0.3/);
    expect(limitError('angular', '0.05', caps)).toMatch(/0.1 to 1.2/);
    expect(limitError('linear', 'x', caps)).toMatch(/number/);
    const patch = limitsPatch({ linear: '0.2', angular: '0.6' }, { linear: 0.15, angular: 0.6 });
    expect(patch).toEqual({ linear: 0.2 });
  });
});

describe('url options and topics', () => {
  it('reads theme, tab and wizard options', () => {
    const o = parseUrlOptions('?theme=dark&tab=wifi&wizard=1', '');
    expect(o).toMatchObject({ theme: 'dark', path: '/wifi', wizard: true });
    expect(parseUrlOptions('?tab=wifi', '#/tools').path).toBeNull();
    expect(parseUrlOptions('?theme=pink', '').theme).toBeNull();
  });
  it('opens the wizard when setup is not done, unless told not to', () => {
    expect(shouldAutoOpenWizard(parseUrlOptions('', ''), false)).toBe(true);
    expect(shouldAutoOpenWizard(parseUrlOptions('?nowizard', ''), false)).toBe(false);
    expect(shouldAutoOpenWizard(parseUrlOptions('', ''), true)).toBe(false);
    expect(shouldAutoOpenWizard(parseUrlOptions('', ''), undefined)).toBe(false);
    expect(shouldAutoOpenWizard(parseUrlOptions('?wizard=1', ''), true)).toBe(true);
  });
  it('filters topics by name or type', () => {
    const l = [
      { name: '/scan', types: ['sensor_msgs/msg/LaserScan'] },
      { name: '/odom', types: ['nav_msgs/msg/Odometry'] },
    ];
    expect(filterTopics(l, 'LASER')).toHaveLength(1);
    expect(filterTopics(l, 'odom')[0]?.name).toBe('/odom');
    expect(filterTopics(l, '')).toHaveLength(2);
    expect(messageText(null)).toMatch(/waiting/);
    expect(messageText('x'.repeat(10000)).length).toBeLessThan(6100);
  });
});
