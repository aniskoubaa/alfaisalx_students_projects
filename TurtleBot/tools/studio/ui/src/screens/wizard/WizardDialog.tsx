import { Search } from 'lucide-react';
import type { ReactNode } from 'react';
import { Badge, Button, Checkbox, Dialog, Field, Input, Spinner } from '../../components/ui';
import type { Candidate } from '../../api';
import { osOf, stepEnabled, validWizardHost } from '../../lib/wizard';
import type { OsName, StepId, StepState, WizardState } from '../../lib/wizard';
import { nameOf } from '../../state/names';
import { useStudio } from '../../state/store';
import { closeWizard, skipWizard, wizAct } from '../../state/wizardActions';
import type { WizardCommand } from '../../state/wizardActions';
import { useWizard, wizDispatch } from '../../state/wizardStore';

const SSH_HELP: Record<OsName, ReactNode> = {
  win: (
    <>
      Open <strong>Settings &gt; System &gt; Optional features</strong>, add{' '}
      <strong>OpenSSH Client</strong>, then press Check again.
    </>
  ),
  mac: (
    <>
      ssh is built into macOS. If it is missing, run <code>xcode-select --install</code> in
      Terminal, then press Check again.
    </>
  ),
  linux: (
    <>
      Install it with <code>sudo apt install openssh-client</code> (or your distribution&apos;s
      package manager), then press Check again.
    </>
  ),
};

function StepBadge({ state }: { state: StepState }) {
  switch (state) {
    case 'ok':
      return <Badge tone="ok">Done</Badge>;
    case 'bad':
      return <Badge tone="bad">Problem</Badge>;
    case 'run':
      return (
        <Badge tone="warn" icon={<Spinner size={12} />}>
          Working
        </Badge>
      );
    case 'wait':
      return <Badge tone="warn">Waiting for you</Badge>;
    default:
      return <Badge tone="neutral">To do</Badge>;
  }
}

function Step({
  n,
  w,
  title,
  children,
  actions,
}: {
  n: StepId;
  w: WizardState;
  title: string;
  children: ReactNode;
  actions: ReactNode;
}) {
  const on = stepEnabled(w, n);
  const msg = w.msg[n];
  return (
    <li className={'wiz-step' + (on ? '' : ' is-off')}>
      <div className="wiz-top">
        <h3 className="wiz-title">
          <span className="wiz-n" aria-hidden="true">
            {n}
          </span>
          {title}
        </h3>
        <StepBadge state={w.st[n]} />
      </div>
      <div className="wiz-body">
        {children}
        {msg ? (
          <div
            className={
              'note ' +
              (w.st[n] === 'bad' ? 'note-bad' : w.st[n] === 'ok' ? 'note-ok' : 'note-warn')
            }
            role={w.st[n] === 'bad' ? 'alert' : undefined}
          >
            {msg}
          </div>
        ) : null}
      </div>
      {on ? null : <p className="dim small">Finish step {n - 1} first.</p>}
      <div className="row">{actions}</div>
    </li>
  );
}

function Act({
  w,
  n,
  cmd,
  children,
  primary,
  extraOff,
  label,
}: {
  w: WizardState;
  n: StepId;
  cmd: WizardCommand;
  children: ReactNode;
  primary?: boolean;
  extraOff?: boolean;
  label?: string;
}) {
  return (
    <Button
      size="sm"
      variant={primary ? 'primary' : 'secondary'}
      disabled={!stepEnabled(w, n) || w.busy || extraOff}
      aria-label={label}
      onClick={() => void wizAct(cmd)}
    >
      {children}
    </Button>
  );
}

export interface WizardStepsProps {
  w: WizardState;
  candidates: Candidate[];
  deep: { running: boolean; done: number; total: number };
  hostname: string;
  platform: string;
}

/** The six steps. Everything it needs comes in as props, so it is easy to test. */
export function WizardSteps({ w, candidates, deep, hostname, platform }: WizardStepsProps) {
  const s = w.setup;
  const retry = (n: StepId, label: string) => (w.st[n] === 'bad' ? 'Retry' : label);
  const host = w.host.trim();
  const pct = deep.total ? Math.min(100, Math.round((100 * deep.done) / deep.total)) : 0;
  const sc = w.scan;
  const key = w.key;

  return (
    <>
      <p className="dim small">
        Six steps to your first connection. You can stop at any time and come back from the Overview
        or Tools screen.
      </p>
      <ol className="wiz">
        <Step
          n={1}
          w={w}
          title="Check that ssh is installed"
          actions={
            <Act w={w} n={1} cmd="check">
              {retry(1, 'Check again')}
            </Act>
          }
        >
          {!s ? (
            <span className="dim">Checking…</span>
          ) : s.ssh?.found ? (
            <span>
              OpenSSH found: <span className="mono">{s.ssh.version || s.ssh.path || 'yes'}</span>
            </span>
          ) : (
            <span>
              <strong>ssh was not found on this computer.</strong> {SSH_HELP[osOf(s, platform)]}
            </span>
          )}
          {s?.ssh?.found && s.keygen && !s.keygen.found ? (
            <div className="note note-warn">
              ssh-keygen was not found, so step 4 cannot create a key.
            </div>
          ) : null}
          {s?.ssh?.found && s.keyscan && !s.keyscan.found ? (
            <div className="note note-warn">
              ssh-keyscan was not found, so step 3 cannot read the robot&apos;s identity.
            </div>
          ) : null}
        </Step>

        <Step
          n={2}
          w={w}
          title="Find the robot"
          actions={
            <>
              <Act w={w} n={2} cmd="discover">
                Discover
              </Act>
              <Act w={w} n={2} cmd="deep">
                Search the whole network
              </Act>
              <Act w={w} n={2} cmd="useaddr" primary extraOff={!validWizardHost(w.host)}>
                Use this address
              </Act>
            </>
          }
        >
          <Field label="Robot address">
            {(p) => (
              <Input
                {...p}
                className="mono"
                value={w.host}
                placeholder={`IP address or name, for example ${hostname}.local`}
                onChange={(e) => wizDispatch({ type: 'set_host', host: e.target.value })}
              />
            )}
          </Field>
          {candidates.length ? (
            <ul className="wiz-cands" aria-label="Robots found">
              {candidates.map((c) => (
                <li key={c.host} className="wiz-cand">
                  <span className="mono">{c.host}</span>
                  {c.identity === 'confirmed' ? (
                    <Badge tone="ok">Your robot (identity confirmed)</Badge>
                  ) : c.label ? (
                    <span className="dim small">{c.label}</span>
                  ) : null}
                  {c.reachable ? (
                    <Badge tone="ok">Reachable</Badge>
                  ) : (
                    <Badge tone="bad">No answer</Badge>
                  )}
                  <span className="grow" />
                  <Button
                    size="sm"
                    variant={c.identity === 'confirmed' ? 'primary' : 'secondary'}
                    disabled={w.busy}
                    aria-label={`Use ${c.host}`}
                    onClick={() => {
                      wizDispatch({ type: 'set_host', host: c.host });
                      void wizAct('useaddr');
                    }}
                  >
                    Use
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dim small">
              Press Discover to look for the robot on the cable and Wi-Fi, or type its address.
            </p>
          )}
          {deep.running ? (
            <div className="progress-wrap" role="status" aria-live="polite">
              <div
                className="progress"
                role="progressbar"
                aria-label="Search progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
              >
                <i style={{ width: pct + '%' }} />
              </div>
              <span className="dim small">
                {deep.total ? `Checking addresses: ${deep.done} of ${deep.total}` : 'Starting…'}
              </span>
            </div>
          ) : null}
          <p className="dim small">
            <Search size={12} aria-hidden="true" /> Search the whole network checks every address on
            this computer&apos;s network for your robot (about 15 s). Or read the address on the
            robot&apos;s screen and type it.
          </p>
        </Step>

        <Step
          n={3}
          w={w}
          title="Check the robot's identity"
          actions={
            <>
              <Act w={w} n={3} cmd="scan">
                {retry(3, sc ? 'Check again' : 'Check robot identity')}
              </Act>
              {sc && !sc.trusted ? (
                <Act w={w} n={3} cmd="trust" primary extraOff={!w.sure}>
                  Trust this robot
                </Act>
              ) : null}
            </>
          }
        >
          <p>
            Studio asks the robot for its identity key (fingerprint) so you know you are talking to
            the right robot.
          </p>
          {sc && sc.trusted ? (
            <div className="note note-ok">
              <p>
                Known robot
                {sc.label ? (
                  <>
                    : <strong>{sc.label}</strong>
                  </>
                ) : null}
                . Fingerprint <span className="mono">{sc.fingerprint}</span>
              </p>
            </div>
          ) : sc ? (
            <>
              <div className="note note-warn">
                <p>Fingerprint reported by {host}:</p>
                <p className="mono">{sc.fingerprint}</p>
                <p>
                  Compare it with the robot. On the robot (display and keyboard, or another trusted
                  terminal) run <code>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code>. The
                  fingerprints must be identical.
                </p>
              </div>
              <Checkbox
                label="I compared them and they are the same"
                checked={w.sure}
                onChange={(e) => wizDispatch({ type: 'set_sure', sure: e.target.checked })}
              />
              <Field label="Name for this robot">
                {(p) => (
                  <Input
                    {...p}
                    value={w.label}
                    placeholder="for example Robot 1"
                    onChange={(e) => wizDispatch({ type: 'set_label', label: e.target.value })}
                  />
                )}
              </Field>
            </>
          ) : null}
        </Step>

        <Step
          n={4}
          w={w}
          title="Create this computer's key"
          actions={
            <Act w={w} n={4} cmd="mkkey">
              {retry(4, key?.path ? 'Create again' : 'Create key')}
            </Act>
          }
        >
          {key?.path ? (
            <>
              <div>
                Key file: <span className="mono">{key.path}</span>
              </div>
              {key.fingerprint ? (
                <div>
                  Fingerprint: <span className="mono">{key.fingerprint}</span>
                </div>
              ) : null}
            </>
          ) : (
            <span>
              Studio makes a key pair for this computer. The private part never leaves it.
            </span>
          )}
        </Step>

        <Step
          n={5}
          w={w}
          title="Allow key login"
          actions={
            <Act w={w} n={5} cmd="term">
              {retry(5, 'Open terminal')}
            </Act>
          }
        >
          <span>
            A terminal window opens and asks for the <strong>robot password</strong> once. Type it{' '}
            <strong>in that window</strong>. Studio never sees it. Afterwards logging in needs no
            password.
          </span>
        </Step>

        <Step
          n={6}
          w={w}
          title="Test the login"
          actions={
            <>
              <Act w={w} n={6} cmd="test">
                {retry(6, 'Test login')}
              </Act>
              {w.st[6] === 'ok' ? (
                <Act w={w} n={6} cmd="connect" primary>
                  Connect
                </Act>
              ) : null}
            </>
          }
        >
          {w.hostname ? (
            <span>
              Logged in to <strong>{w.hostname}</strong>.
            </span>
          ) : (
            <span>Studio logs in with the key (no password) and reads the robot&apos;s name.</span>
          )}
        </Step>
      </ol>
    </>
  );
}

/** The first-run setup dialog. Opens from openWizard(). */
export function WizardDialog() {
  const open = useWizard((s) => s.open);
  const w = useWizard((s) => s.w);
  const candidates = useStudio((s) => s.candidates);
  const deep = useStudio((s) => s.deep);
  const hostname = useStudio((s) => nameOf(s, 'robot_hostname'));
  if (!open) return null;
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) closeWizard();
      }}
      title="Set up TurtleBot Studio"
      size="lg"
      footer={
        <>
          <Button onClick={() => void skipWizard()}>Skip setup</Button>
          <Button variant="primary" onClick={closeWizard}>
            Close
          </Button>
        </>
      }
    >
      <WizardSteps
        w={w}
        candidates={candidates}
        deep={deep}
        hostname={hostname}
        platform={typeof navigator === 'undefined' ? '' : navigator.platform}
      />
    </Dialog>
  );
}
