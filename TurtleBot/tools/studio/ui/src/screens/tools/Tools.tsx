import {
  ClipboardList,
  Code2,
  KeyRound,
  Power,
  RefreshCw,
  Settings as SettingsIcon,
  SquareTerminal,
  Wand2,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { Badge, Button, Dash, KV, KeyValue, Panel } from '../../components/ui';
import { isUpdatePage } from '../../lib/update';
import { useAsyncAction } from '../../lib/useAsync';
import { openVscode, quitStudio, setupKeyLogin } from '../../state/actions';
import { navigate } from '../../state/router';
import { useStudio } from '../../state/store';
import { checkForUpdates, openTerminal, showDiagnostics } from '../../state/toolsActions';
import type { UpdateCheck } from '../../state/toolsActions';
import { openWizard } from '../../state/wizardActions';
import { AppLog } from './AppLog';

function ToolCard({
  title,
  icon,
  text,
  children,
}: {
  title: string;
  icon: ReactNode;
  text: ReactNode;
  children: ReactNode;
}) {
  return (
    <Panel
      title={
        <span className="tool-title">
          {icon}
          {title}
        </span>
      }
    >
      <p className="dim small">{text}</p>
      <div className="row">{children}</div>
    </Panel>
  );
}

function UpdatesCard() {
  const [shown, setShown] = useState<UpdateCheck | null>(null);
  const check = useAsyncAction(async () => {
    setShown(await checkForUpdates());
  });
  return (
    <ToolCard
      title="Updates"
      icon={<RefreshCw size={16} aria-hidden="true" />}
      text="Asks GitHub whether a newer version of Studio exists (one small file; nothing about you is sent)."
    >
      <Button loading={check.pending} onClick={() => void check.run()}>
        Check for updates
      </Button>
      <span className="small" role="status">
        {check.pending ? (
          'Checking…'
        ) : shown?.result === 'latest' ? (
          'You have the latest version.'
        ) : shown?.result === 'failed' ? (
          'Could not check. Try again later.'
        ) : shown?.result === 'newer' ? (
          <>
            Version {shown.latest} is available.{' '}
            {isUpdatePage(shown.page) ? (
              <a href={shown.page} target="_blank" rel="noopener noreferrer">
                How to update
              </a>
            ) : null}
          </>
        ) : null}
      </span>
    </ToolCard>
  );
}

function AboutPanel() {
  const hello = useStudio((s) => s.hello);
  const version = useStudio((s) => s.settings.version);
  const studioVersion = typeof version === 'string' ? version : null;
  return (
    <Panel title="About" wide>
      <KeyValue label="About Studio">
        <KV label="Studio version">{studioVersion ?? <Dash />}</KV>
        {hello ? (
          <>
            <KV label="Robot host">{hello.hostname ?? <Dash />}</KV>
            <KV label="Bridge">
              {(hello.bridge ?? '') + ' v' + (hello.version ?? '?') + (hello.fake ? ' (fake)' : '')}
            </KV>
            <KV label="ROS">
              {hello.ros ? (
                <Badge tone="ok">{hello.ros_distro || 'yes'}</Badge>
              ) : (
                <Badge tone="neutral">Not available</Badge>
              )}
            </KV>
            <KV label="RMW">{hello.rmw ?? <Dash />}</KV>
            <KV label="ROS domain">{hello.domain ?? <Dash />}</KV>
            <KV label="Python (robot)">{hello.python ?? <Dash />}</KV>
            <KV label="Bridge PID">{hello.pid ?? <Dash />}</KV>
          </>
        ) : (
          <KV label="Robot">
            <Badge tone="neutral">Not connected</Badge>
          </KV>
        )}
      </KeyValue>
      <p className="dim small">
        E-STOP: Esc or Space (when not typing in a field). Studio runs only on this computer;
        nothing is installed on the robot.
      </p>
    </Panel>
  );
}

export function Tools() {
  const term = useAsyncAction(openTerminal);
  const key = useAsyncAction(setupKeyLogin);
  const diag = useAsyncAction(showDiagnostics);
  const code = useAsyncAction(openVscode);
  const quit = useAsyncAction(quitStudio);

  return (
    <div className="page">
      <h1 className="page-title">Tools</h1>
      <div className="grid">
        <ToolCard
          title="Terminal"
          icon={<SquareTerminal size={16} aria-hidden="true" />}
          text="Opens a normal terminal window logged in to the robot."
        >
          <Button loading={term.pending} onClick={() => void term.run()}>
            Open terminal
          </Button>
        </ToolCard>
        <ToolCard
          title="Setup wizard"
          icon={<Wand2 size={16} aria-hidden="true" />}
          text="Walks you through the first connection: ssh, robot address, robot identity, key and a test login."
        >
          <Button onClick={() => openWizard()}>Open the setup wizard</Button>
        </ToolCard>
        <ToolCard
          title="Key login"
          icon={<KeyRound size={16} aria-hidden="true" />}
          text={
            <>
              Lets this app sign in without a password. A terminal window opens and asks for the
              robot password. <strong>Type the password there. This app never sees it.</strong>
            </>
          }
        >
          <Button loading={key.pending} onClick={() => void key.run()}>
            Set up key login
          </Button>
        </ToolCard>
        <ToolCard
          title="Diagnostics"
          icon={<ClipboardList size={16} aria-hidden="true" />}
          text="Collects a short text about this app, this computer and the connection, to paste into a message when you ask for help. Passwords, keys and the session token are removed."
        >
          <Button loading={diag.pending} onClick={() => void diag.run()}>
            Show diagnostics
          </Button>
        </ToolCard>
        <UpdatesCard />
        <ToolCard
          title="VS Code"
          icon={<Code2 size={16} aria-hidden="true" />}
          text="Opens the robot's code folder in VS Code (Remote SSH). It may need one block added to your ssh config; you see it first."
        >
          <Button loading={code.pending} onClick={() => void code.run()}>
            Open in VS Code
          </Button>
        </ToolCard>
        <ToolCard
          title="Settings"
          icon={<SettingsIcon size={16} aria-hidden="true" />}
          text="Robot name and addresses, key file, trusted robots, driving limits and how Studio opens."
        >
          <Button onClick={() => navigate('/settings')}>Open settings</Button>
        </ToolCard>
        <ToolCard
          title="Quit"
          icon={<Power size={16} aria-hidden="true" />}
          text="Closes Studio and its connection to the robot. Stop any robot program that is running first."
        >
          <Button variant="danger" loading={quit.pending} onClick={() => void quit.run()}>
            Quit Studio
          </Button>
        </ToolCard>
      </div>
      <AppLog />
      <AboutPanel />
    </div>
  );
}
