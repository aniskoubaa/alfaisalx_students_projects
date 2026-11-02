import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../../api';
import { setupApi } from '../../api/setup';
import { Button, Checkbox, EmptyState, Field, Input, Panel, Select } from '../../components/ui';
import { classicHref } from '../../lib/classic';
import {
  LIMIT_CAPS,
  LIMIT_FLOORS,
  buildPatch,
  defaultFor,
  formFromSettings,
  limitError,
  limitsPatch,
  limitsToText,
} from '../../lib/settingsForm';
import type { LimitsText, SettingsForm } from '../../lib/settingsForm';
import { useAsyncAction } from '../../lib/useAsync';
import { notify } from '../../state/feedback';
import { navigate } from '../../state/router';
import { useStudio } from '../../state/store';
import { TrustedRobots } from './TrustedRobots';

type TextKey = {
  [K in keyof SettingsForm]: SettingsForm[K] extends string ? K : never;
}[keyof SettingsForm];

interface Caps {
  linear: number;
  angular: number;
}

export function Settings() {
  const loaded = useStudio((s) => s.settingsLoaded);
  const settings = useStudio((s) => s.settings);
  const defaults = useStudio((s) => s.defaults);
  const saved = useMemo(() => formFromSettings(settings, defaults), [settings, defaults]);

  const [edit, setEdit] = useState<Partial<SettingsForm>>({});
  const form: SettingsForm = { ...saved, ...edit };
  const patch = buildPatch(form, saved, defaults);
  const changed = Object.keys(patch).length;

  // Driving limits come from their own endpoint.
  const [limSaved, setLimSaved] = useState<Caps | null>(null);
  const [caps, setCaps] = useState<Caps>({
    linear: LIMIT_CAPS.linear,
    angular: LIMIT_CAPS.angular,
  });
  const [limEdit, setLimEdit] = useState<Partial<LimitsText>>({});
  const [limLoadErr, setLimLoadErr] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void setupApi.teleopLimits().then((r) => {
      if (!alive) return;
      if (r.ok) {
        setLimSaved({ linear: r.linear, angular: r.angular });
        setCaps({ linear: r.max_linear, angular: r.max_angular });
        setLimLoadErr(null);
      } else setLimLoadErr(r.error);
    });
    return () => {
      alive = false;
    };
  }, []);

  const limText: LimitsText = {
    ...(limSaved ? limitsToText(limSaved) : { linear: '', angular: '' }),
    ...limEdit,
  };
  const limErr = {
    linear: limSaved ? limitError('linear', limText.linear, caps) : '',
    angular: limSaved ? limitError('angular', limText.angular, caps) : '',
  };
  const limPatch = limSaved ? limitsPatch(limText, limSaved) : {};
  const limChanged = Object.keys(limPatch).length;
  const limInvalid = !!(limErr.linear || limErr.angular);

  const set = <K extends keyof SettingsForm>(k: K, v: SettingsForm[K]) =>
    setEdit((e) => ({ ...e, [k]: v }));

  const save = useAsyncAction(async () => {
    setSaveErr(null);
    if (changed) {
      const r = await api().saveSettings(patch);
      if (!r.ok) {
        setSaveErr(r.error);
        return;
      }
      useStudio.getState().setSettings(r);
      setEdit({});
    }
    if (limChanged) {
      const r = await setupApi.saveTeleopLimits(limPatch);
      if (!r.ok) {
        setSaveErr(r.error);
        return;
      }
      setLimSaved({ linear: r.linear, angular: r.angular });
      setCaps({ linear: r.max_linear, angular: r.max_angular });
      setLimEdit({});
    }
    const later = 'window_mode' in patch || 'ui' in patch;
    notify(
      'ok',
      'Settings saved.' + (later ? ' The way Studio opens changes the next time it starts.' : ''),
    );
  });

  const text = (
    k: TextKey,
    label: string,
    opts: { hint?: ReactNode; mono?: boolean; placeholder?: string } = {},
  ) => (
    <Field label={label} hint={opts.hint}>
      {(p) => (
        <Input
          {...p}
          className={opts.mono ? 'mono' : undefined}
          value={form[k]}
          placeholder={opts.placeholder ?? defaultFor(defaults, k)}
          onChange={(e) => set(k, e.target.value as SettingsForm[typeof k])}
        />
      )}
    </Field>
  );

  if (!loaded) {
    return (
      <div className="page">
        <h1 className="page-title">Settings</h1>
        <Panel>
          <EmptyState compact title="Loading the settings…">
            If this stays, check that Studio is still running.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const dirty = changed + limChanged > 0;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Settings</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate('/tools')}>
          Back to Tools
        </Button>
      </div>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty && !limInvalid) void save.run();
        }}
      >
        <div className="grid grid-settings">
          <Panel title="Robot names and addresses">
            <div className="stack stack-tight">
              {text('robot_hostname', 'Robot host name', {
                hint: (
                  <>
                    Studio also tries{' '}
                    <span className="mono">{form.robot_hostname || 'turtlebot4'}.local</span>
                  </>
                ),
              })}
              {text('robot_user', 'Robot user')}
              {text('hotspot_ssid', 'Robot hotspot name')}
              {text('hotspot_addr', 'Robot hotspot address', { mono: true })}
              {text('cable_addr', 'Robot cable address', { mono: true })}
              {text('last_host', 'Last robot address', {
                mono: true,
                placeholder: 'Set by Connect',
              })}
            </div>
          </Panel>

          <Panel title="Key and folders">
            <div className="stack stack-tight">
              {text('key_path', 'SSH key file', {
                hint: 'Empty means the default key.',
                mono: true,
                placeholder: 'Default key',
              })}
              {text('local_dir', 'Local folder', { mono: true, placeholder: 'Not set' })}
              {text('remote_dir', 'Robot folder', { mono: true, placeholder: '~/robot_code' })}
              <Field
                label="Extra programs that move the robot"
                hint="One file name per line. Studio asks before it runs them."
              >
                {(p) => (
                  <textarea
                    {...p}
                    className="input mono"
                    rows={3}
                    spellCheck={false}
                    value={form.motion_files}
                    onChange={(e) => set('motion_files', e.target.value)}
                  />
                )}
              </Field>
            </div>
          </Panel>

          <Panel title="How Studio behaves">
            <div className="stack stack-tight">
              <Field label="How Studio opens" hint="Takes effect the next time Studio starts.">
                {(p) => (
                  <Select
                    {...p}
                    value={form.window_mode}
                    onChange={(e) =>
                      set('window_mode', e.target.value === 'browser' ? 'browser' : 'app')
                    }
                  >
                    <option value="app">Its own window (Edge or Chrome)</option>
                    <option value="browser">A tab in my web browser</option>
                  </Select>
                )}
              </Field>
              <Checkbox
                label={
                  <>
                    Reconnect by myself when the connection drops
                    <span className="dim"> (never restarts programs or releases the e-stop)</span>
                  </>
                }
                checked={form.auto_reconnect}
                onChange={(e) => set('auto_reconnect', e.target.checked)}
              />
              <Checkbox
                label={
                  <>
                    Tell me when a new version of Studio is out
                    <span className="dim"> (checked at most once a day)</span>
                  </>
                }
                checked={form.update_check}
                onChange={(e) => set('update_check', e.target.checked)}
              />
              <div className="stack stack-tight">
                <Checkbox
                  label="Use the classic interface"
                  checked={form.classic_ui}
                  onChange={(e) => set('classic_ui', e.target.checked)}
                />
                <p className="field-hint">
                  Studio 1.3&apos;s interface stays as a fallback. This applies the next time Studio
                  starts. You can{' '}
                  <a href={classicHref('/classic/')}>open the classic interface now</a> without
                  changing the setting.
                </p>
              </div>
            </div>
          </Panel>

          <Panel title="Driving limits">
            <div className="stack stack-tight">
              <p className="small dim">
                The top speeds for driving by joystick or keys. Studio never goes above{' '}
                {caps.linear} m/s and {caps.angular} rad/s, whatever is typed here.
              </p>
              {limLoadErr ? (
                <div className="note note-warn" role="alert">
                  Could not read the driving limits: {limLoadErr}
                </div>
              ) : null}
              <Field
                label="Top forward speed (m/s)"
                hint={`From ${LIMIT_FLOORS.linear} to ${caps.linear}.`}
                error={limErr.linear}
              >
                {(p) => (
                  <Input
                    {...p}
                    inputMode="decimal"
                    disabled={!limSaved}
                    value={limText.linear}
                    onChange={(e) => setLimEdit((l) => ({ ...l, linear: e.target.value }))}
                  />
                )}
              </Field>
              <Field
                label="Top turning speed (rad/s)"
                hint={`From ${LIMIT_FLOORS.angular} to ${caps.angular}.`}
                error={limErr.angular}
              >
                {(p) => (
                  <Input
                    {...p}
                    inputMode="decimal"
                    disabled={!limSaved}
                    value={limText.angular}
                    onChange={(e) => setLimEdit((l) => ({ ...l, angular: e.target.value }))}
                  />
                )}
              </Field>
            </div>
          </Panel>
        </div>

        <div className="savebar" role="group" aria-label="Save settings">
          <Button
            type="submit"
            variant="primary"
            loading={save.pending}
            disabled={!dirty || limInvalid}
          >
            Save settings
          </Button>
          <Button
            disabled={!dirty || save.pending}
            onClick={() => {
              setEdit({});
              setLimEdit({});
              setSaveErr(null);
            }}
          >
            Discard changes
          </Button>
          <span className="small dim" role="status">
            {dirty ? 'You have unsaved changes.' : 'No changes to save.'}
          </span>
          {saveErr ? (
            <span className="small save-err" role="alert">
              Could not save: {saveErr}
            </span>
          ) : null}
        </div>
      </form>

      <TrustedRobots />
    </div>
  );
}
