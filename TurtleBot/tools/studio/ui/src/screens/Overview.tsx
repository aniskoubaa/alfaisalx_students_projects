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

export function Overview() {
  return (
    <div className="page">
      <h1 className="page-title">Overview</h1>
      <div className="grid">
        <ConnectionPanel />
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
