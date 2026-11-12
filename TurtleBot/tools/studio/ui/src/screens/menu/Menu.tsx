import { useEffect } from 'react';
import { Spinner } from '../../components/ui';
import { BuiltinList } from '../../features/menu/BuiltinList';
import { HowItWorks } from '../../features/menu/HowItWorks';
import { MenuActions } from '../../features/menu/MenuActions';
import { MenuPreview } from '../../features/menu/MenuPreview';
import { OwnEntries } from '../../features/menu/OwnEntries';
import { RobotFileNotice } from '../../features/menu/RobotFile';
import { currentCheck, useMenu } from '../../features/menu/store';
import { useStudio } from '../../state/store';

export function Menu() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const robot = useMenu((s) => s.robot);
  const robotError = useMenu((s) => s.robotError);
  const blocked = useMenu((s) => s.blocked);
  const doc = useMenu((s) => s.doc);
  const lastCheck = useMenu((s) => s.lastCheck);
  const check = currentCheck({ lastCheck, doc });
  const load = useMenu((s) => s.load);
  const setDoc = useMenu((s) => s.setDoc);
  const startStandard = useMenu((s) => s.startStandard);

  // Read the robot's file when the screen opens and again after the connection comes back.
  useEffect(() => {
    if (connected) void load();
  }, [connected, load]);

  return (
    <div className="page menu-page">
      <h1 className="page-title">Robot menu</h1>
      {!connected ? (
        <p className="live-note maps-note" role="status">
          Not connected to the robot. Connect to read and change its menu.
        </p>
      ) : null}
      {connected && robotError ? (
        <p className="mapping-error" role="alert">
          Could not read the menu from the robot. {robotError}
        </p>
      ) : null}
      {connected && robot === null && !robotError ? (
        <p className="dim small" role="status">
          <Spinner size={14} /> Reading the menu from the robot
        </p>
      ) : null}
      <div className="menu-grid">
        <div className="menu-col">
          {robot ? (
            <RobotFileNotice robot={robot} blocked={blocked} onStartStandard={startStandard} />
          ) : null}
          {!blocked ? (
            <>
              <BuiltinList doc={doc} onChange={setDoc} />
              <OwnEntries doc={doc} onChange={setDoc} />
            </>
          ) : null}
          <MenuActions connected={connected} />
        </div>
        <div className="menu-col">
          <MenuPreview doc={doc} check={check} />
          <HowItWorks />
        </div>
      </div>
    </div>
  );
}
