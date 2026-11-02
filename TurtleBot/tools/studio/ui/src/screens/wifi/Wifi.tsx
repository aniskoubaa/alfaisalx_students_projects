import { useEffect, useState } from 'react';
import { Panel } from '../../components/ui';
import { currentWay, robotMode } from '../../lib/wifi';
import { nameOf } from '../../state/names';
import { useStudio } from '../../state/store';
import { loadWifi } from '../../state/wifiActions';
import { useWifi } from '../../state/wifiStore';
import { SavedPanel, SeenPanel } from './Tables';
import { RobotPanel, ThisComputerPanel } from './StatusPanels';
import { WayA, WayB, WayC } from './Ways';
import type { SsidPick } from './Ways';

export function Wifi() {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const via = useStudio((s) => s.conn.via);
  const netMode = useStudio((s) => s.status?.net?.wifi_mode);
  const hotspot = useStudio((s) => nameOf(s, 'hotspot_ssid'));
  const mrobot = useWifi((s) => s.robot);
  const lssid = useWifi((s) => s.laptop?.wifi?.ssid);
  const host = useStudio((s) => nameOf(s, 'robot_hostname'));
  const [pick, setPick] = useState<SsidPick | null>(null);

  // Read both sides when the screen opens, and again whenever the robot connects or disconnects.
  useEffect(() => {
    void loadWifi();
  }, [connected]);

  const way = currentWay({
    connected,
    via,
    mode: robotMode(mrobot, netMode),
    laptopSsid: lssid,
    hotspotSsid: hotspot,
  });

  return (
    <div className="page">
      <h1 className="page-title">Wi-Fi</h1>
      <Panel title="Connect over Wi-Fi" wide>
        <p>
          The robot and this computer must be on the same network to talk. There are three ways to
          do that. The boxes below show where you are now. Pick the way that fits, and follow its
          steps.
        </p>
      </Panel>
      <div className="grid grid-2">
        <ThisComputerPanel />
        <RobotPanel />
      </div>
      <div className="grid grid-ways">
        <WayA here={way === 'A'} />
        <WayB here={way} pick={pick} />
        <WayC here={way === 'C'} />
      </div>
      <SavedPanel />
      <SeenPanel onUse={(ssid) => setPick((p) => ({ ssid, n: (p?.n ?? 0) + 1 }))} />
      <Panel title="Does not work? Try this" wide>
        <ul className="plain">
          <li>
            Robot not found on Wi-Fi: read its address on the robot&apos;s display and type it into
            the address box on the Overview screen.
          </li>
          <li>
            <code>{host}.local</code> often fails on shared Wi-Fi, so Studio does not rely on it.
          </li>
          <li>After switching on, the robot can need about 2 minutes before it is on Wi-Fi.</li>
          <li>
            If the connection keeps dropping, check &ldquo;Power save&rdquo; in the table above.
          </li>
          <li>No luck at all: use the Ethernet cable (option C).</li>
        </ul>
      </Panel>
    </div>
  );
}
