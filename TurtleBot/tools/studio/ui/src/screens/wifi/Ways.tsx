import { MapPin } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Badge, Button, Checkbox, Field, Input, Panel } from '../../components/ui';
import { useAsyncAction } from '../../lib/useAsync';
import { wifiFormState } from '../../lib/wifi';
import type { Way } from '../../lib/wifi';
import { discover } from '../../state/actions';
import { navigate } from '../../state/router';
import { nameOf } from '../../state/names';
import { useStudio } from '../../state/store';
import { addWifi, joinHotspot, openWifiSettings } from '../../state/wifiActions';
import { useWifi } from '../../state/wifiStore';

function Here({ on }: { on: boolean }) {
  return on ? (
    <span className="here">
      <MapPin size={14} aria-hidden="true" /> You are here
    </span>
  ) : null;
}

export function WayA({ here }: { here: boolean }) {
  const hs = useStudio((s) => nameOf(s, 'hotspot_ssid'));
  const addr = useStudio((s) => nameOf(s, 'hotspot_addr'));
  const doJoin = useAsyncAction(joinHotspot);
  const doSettings = useAsyncAction(openWifiSettings);
  const doDiscover = useAsyncAction(async () => {
    navigate('/overview');
    await discover();
  });
  return (
    <Panel
      title="A. The robot's own Wi-Fi (hotspot)"
      className={here ? 'panel-here' : undefined}
      actions={<Here on={here} />}
    >
      <p className="small dim">
        Use this when there is no other network, for example when you are away from your usual
        Wi-Fi. If the robot cannot find a saved network, it makes its own Wi-Fi called{' '}
        <strong>{hs}</strong>.
      </p>
      <ol className="way-steps">
        <li>
          Join the <strong>{hs}</strong> network on this computer. The password is in the TurtleBot
          4 manual, or ask whoever set up the robot.
        </li>
        <li>
          Press <em>Discover</em>, then <em>Connect</em>. The robot is at <code>{addr}</code>.
        </li>
      </ol>
      <div className="row">
        <Button loading={doJoin.pending} onClick={() => void doJoin.run()}>
          Join {hs}
        </Button>
        <Button loading={doSettings.pending} onClick={() => void doSettings.run()}>
          Open Wi-Fi settings
        </Button>
        <Button loading={doDiscover.pending} onClick={() => void doDiscover.run()}>
          Discover
        </Button>
      </div>
      <p className="small dim">
        While this computer is on the robot&apos;s hotspot it has no internet, unless it has a
        second connection.
      </p>
    </Panel>
  );
}

export function WayC({ here }: { here: boolean }) {
  const cable = useStudio((s) => nameOf(s, 'cable_addr'));
  return (
    <Panel
      title="C. Ethernet cable"
      className={here ? 'panel-here' : undefined}
      actions={<Here on={here} />}
    >
      <p className="small dim">
        Always works and needs no settings. Plug the cable between this computer and the robot, wait
        a few seconds, then press Discover and Connect. The robot&apos;s cable address is{' '}
        <code>{cable}</code>.
      </p>
      <p className="small dim">A cable is also the way to set up option B the first time.</p>
    </Panel>
  );
}

/** A network picked in the table of networks the robot can see. `n` makes a second pick of the same name count. */
export interface SsidPick {
  ssid: string;
  n: number;
}

export function WayB({ here, pick }: { here: Way; pick: SsidPick | null }) {
  const connected = useStudio((s) => s.conn.state === 'connected');
  const hotspot = useStudio((s) => nameOf(s, 'hotspot_ssid'));
  const laptop = useWifi((s) => s.laptop);
  const info = useWifi((s) => s.robot);
  const lssid = laptop?.wifi?.ssid ?? null;
  const listId = useId();

  const [ssid, setSsid] = useState('');
  const [psk, setPsk] = useState('');
  const [now, setNow] = useState(false);
  const auto = useRef('');
  const pskBox = useRef<HTMLInputElement>(null);

  // The name box follows this computer's network until the person types their own.
  useEffect(() => {
    const next = lssid ?? '';
    setSsid((cur) => (!cur || cur === auto.current ? next : cur));
    auto.current = next;
  }, [lssid]);

  // "Use" in the table of networks the robot can see.
  const [seen, setSeen] = useState<SsidPick | null>(null);
  if (pick && pick !== seen) {
    setSeen(pick);
    setSsid(pick.ssid);
  }
  useEffect(() => {
    if (pick) {
      document.getElementById('way-b')?.scrollIntoView({ block: 'nearest' });
      pskBox.current?.focus();
    }
  }, [pick]);

  const f = wifiFormState({ ssid, psk, connected, hotspotSsid: hotspot, info });
  const names = [
    ...new Set([lssid, ...(info?.scan ?? []).map((x) => x.ssid)].filter((x): x is string => !!x)),
  ];

  const doAdd = useAsyncAction(async () => {
    await addWifi({
      ssid: f.ssid,
      now,
      takePsk: () => {
        const typed = psk;
        setPsk('');
        return typed;
      },
    });
  });

  return (
    <Panel
      id="way-b"
      title="B. Join a Wi-Fi network"
      className={here === 'B' ? 'panel-here' : undefined}
      actions={<Here on={here === 'B'} />}
    >
      <p className="small dim">
        Best for daily work: robot and computer both join the same Wi-Fi (home, school or office).
        You teach the robot the network once. Works with a normal Wi-Fi password (WPA or WPA2
        personal).
      </p>
      <p className="row">
        <span>
          This computer is on:{' '}
          <strong>
            {lssid
              ? lssid + (laptop?.wifi?.ssid_guess ? ' (Windows network name, check it)' : '')
              : '(cannot tell)'}
          </strong>
        </span>
        {lssid ? (
          <Button
            size="sm"
            aria-label="Use this computer's Wi-Fi name"
            onClick={() => {
              setSsid(lssid);
              pskBox.current?.focus();
            }}
          >
            Use
          </Button>
        ) : null}
      </p>
      <form
        className="stack stack-tight"
        onSubmit={(e) => {
          e.preventDefault();
          if (!f.why) void doAdd.run();
        }}
      >
        <Field
          label="Network name (SSID)"
          hint="Pick one from the list, press Use in the table below, or type it (also for hidden networks)."
        >
          {(p) => (
            <>
              <Input
                {...p}
                list={listId}
                maxLength={32}
                value={ssid}
                onChange={(e) => setSsid(e.target.value)}
              />
              <datalist id={listId}>
                {names.map((n) => (
                  <option key={n} value={n} />
                ))}
              </datalist>
            </>
          )}
        </Field>
        {laptop?.wifi?.note ? <p className="small dim">{laptop.wifi.note}</p> : null}
        <div className="small" role="status">
          {!f.ssid ? null : f.sec ? (
            f.sec.ok ? (
              <Badge tone="ok">Security: {f.sec.label} (supported)</Badge>
            ) : (
              <Badge tone="warn">{f.sec.why}</Badge>
            )
          ) : (
            <span className="dim">
              The robot did not list this network (hidden, out of range, or it cannot scan now), so
              its security cannot be checked.
            </span>
          )}
        </div>
        <Field
          label="Wi-Fi password"
          hint="8 to 63 characters. Sent once to the robot's memory, never saved by Studio."
        >
          {(p) => (
            <Input
              {...p}
              ref={pskBox}
              type="password"
              maxLength={64}
              autoComplete="new-password"
              value={psk}
              onChange={(e) => setPsk(e.target.value)}
            />
          )}
        </Field>
        <Checkbox
          label="Switch the robot to it now and test it (if it fails, the robot goes back to its current network)"
          checked={now}
          onChange={(e) => setNow(e.target.checked)}
        />
        <div className="row">
          <Button
            type="submit"
            variant="primary"
            disabled={!!f.why}
            loading={doAdd.pending}
          >
            {f.already
              ? `“${f.ssid}” is already saved on the robot`
              : f.ssid
                ? `Add “${f.ssid}” to the robot`
                : 'Add this Wi-Fi to the robot'}
          </Button>
        </div>
        {f.why ? <p className="small dim">{f.why}</p> : null}
      </form>
      <p className="small dim">
        You need to be connected to the robot already (cable or hotspot). The robot keeps its own
        hotspot as a backup. Afterwards press Discover: Studio remembers the robot&apos;s address,
        or read it on the robot&apos;s little display.
      </p>
      <p className="small dim">
        Not supported: networks with a login web page, with a username and password (802.1X /
        WPA2-Enterprise), open networks and WPA3-only networks.
      </p>
    </Panel>
  );
}
