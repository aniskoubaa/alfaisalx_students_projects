import { useStudio } from '../state/store';
import { ConnectionPanel } from './overview/ConnectionPanel';
import { HealthPanel } from './overview/HealthPanel';
import {
  BatteryPanel,
  DockPanel,
  NetworkPanel,
  PosePanel,
  ScanPanel,
  SystemPanel,
} from './overview/StatusPanels';
import { TaskPanel } from './overview/TaskPanel';

function ConnectionCard() {
  return (
    <div className="grid">
      <ConnectionPanel />
    </div>
  );
}

/** The Home screen. The file keeps its old name so imports stay the same. */
export function Overview() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  return (
    <div className="page">
      <h1 className="page-title">Home</h1>
      {connected ? <TaskPanel /> : <ConnectionCard />}
      <h2 className="section-title">Robot status</h2>
      <div className="grid">
        {connected ? <ConnectionPanel /> : null}
        <BatteryPanel />
        <DockPanel />
        <PosePanel />
        <ScanPanel />
        <NetworkPanel />
        <SystemPanel />
        <HealthPanel />
      </div>
    </div>
  );
}
