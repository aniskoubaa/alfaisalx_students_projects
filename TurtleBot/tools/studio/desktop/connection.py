"""Finding the robot and keeping the link: connect, disconnect, discovery, the whole-network
search and automatic reconnect.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip
from .programs import *  # bundle: skip
from .events import *  # bundle: skip
from .alerts import *  # bundle: skip
from .mapping import *  # bundle: skip
from .bridge_process import *  # bundle: skip


class ConnectionMixin:
    # ---------------------------------------------------------------- connect
    def connect(self, host=None, auto=False):
        if not auto:
            self.reconnect_cancel(quiet=True)  # the user takes over
        self.teleop_off('reconnecting' if auto else 'connecting')  # a new bridge process always starts disarmed
        host = (host or self.args.host_override or '').strip()
        if self.fake:
            return self._connect_fake()
        ssh = find_exe('ssh')
        if not ssh:
            self.conn('error', None, None, 'ssh not found: install the OpenSSH client', kind='no_ssh')
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        via = 'custom' if host else None
        if not host:
            cands = self.discover()
            best = next((c for c in cands if c['reachable']), None)
            if not best:
                self.conn('error', None, None, 'robot not reachable', kind='unreachable')
                return {'ok': False, 'error': 'robot not reachable', 'candidates': cands}
            host, via = best['host'], best['via']
        elif host == self.settings.get('last_host') and self.settings.get('last_via'):
            via = self.settings['last_via']
        if not valid_host(host):
            return {'ok': False, 'error': 'invalid host name or address'}
        try:
            key = self.key_path()
            payload = self._bridge_bytes()
        except (BridgeError, OSError) as e:
            self.conn('error', host, via, str(e), kind='other')
            return {'ok': False, 'error': str(e)}
        self.write_known_hosts()
        argv = build_bridge_ssh_argv(ssh, host, key, self.known_hosts, user=self.user())
        self.bridge.start(argv, host, via, payload=payload)
        return self._await_hello(host, via)

    def _connect_fake(self):
        try:
            os.makedirs(self.fake_home, exist_ok=True)
            if not is_frozen() and not os.path.isfile(self.bridge_script):
                raise BridgeError('robot_bridge.py not found next to studio.py')
        except (OSError, BridgeError) as e:
            self.conn('error', 'fake', 'custom', str(e), kind='other')
            return {'ok': False, 'error': str(e)}
        # STUDIO_BRIDGE_HOME: the fake robot keeps maps, routes and logs in the fake home, where the fake tar helper looks
        env = dict(os.environ, HOME=self.fake_home, USERPROFILE=self.fake_home, STUDIO_BRIDGE_HOME=self.fake_home,
                   PYTHONDONTWRITEBYTECODE='1')
        checker = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'delivery',
                                                'menu_config.py'))
        if 'STUDIO_MENU_CHECKER' not in env and os.path.isfile(checker):
            env['STUDIO_MENU_CHECKER'] = checker
        self.bridge.start(fake_bridge_argv(self.bridge_script), 'fake', 'custom', env=env)
        return self._await_hello('fake', 'custom')

    def _bridge_bytes(self):
        try:
            with open(self.bridge_script, 'rb') as f:
                return f.read()
        except OSError:
            raise BridgeError('robot_bridge.py not found next to studio.py')

    def _await_hello(self, host, via):
        ok = self.bridge.hello_evt.wait(25) and self.bridge.connected
        if ok:
            if not self.fake:
                self.settings['last_host'], self.settings['last_via'] = host, via
                self.save_settings()
            return {'ok': True, 'host': host, 'via': via, 'hello': self.bridge.hello}
        if self.bridge.alive():  # no hello and no exit: give up
            self.bridge.stop()
            self.conn('error', host, via, 'robot did not answer', kind='unreachable')
            return {'ok': False, 'error': 'robot did not answer'}
        time.sleep(0.3)
        c = self.bus.last_conn
        return {'ok': False, 'error': c.get('error') or 'connection failed', 'kind': c.get('kind')}

    def disconnect(self):
        self.teleop_off('Disconnected.')
        self.reconnect_cancel(quiet=True)
        self.bridge.stop()
        self.conn('disconnected', self.bridge.host, self.bridge.via)
        return {'ok': True}

    # ---------------------------------------------------------------- discovery
    def candidate_list(self, extra=None, v6=(), wifi_ssid=None):
        cands = []

        def add(host, label, via):
            if host and valid_host(host) and all(c['host'] != host for c in cands):
                cands.append({'host': host, 'label': label, 'via': via})
        last = self.settings.get('last_host')
        if extra:
            add(extra, 'Typed address', 'custom')
        if self.args.host_override:
            add(self.args.host_override, 'Host override', 'custom')
        add(last, 'Last used', self.settings.get('last_via') or 'custom')
        add(self.settings['hotspot_addr'], 'Robot hotspot (%s Wi-Fi)' % self.settings['hotspot_ssid'], 'hotspot')
        for h in v6:
            add(h, 'Cable (IPv6)', 'cable')
        if has_cable_v4():
            add(self.settings['cable_addr'], 'Cable (%s)' % self.settings['cable_addr'], 'cable')
        known = (self.settings.get('known_addresses') or {}).get(wifi_ssid) if wifi_ssid else None
        if isinstance(known, dict) and known.get('ip'):
            add(known['ip'], 'Robot on %s (last seen %s)' % (wifi_ssid, known['ip']), 'wifi')
        mdns = self.settings['robot_hostname'] + '.local'
        add(mdns, 'Robot name on the Wi-Fi (%s)' % mdns, 'wifi')
        return cands

    def discover(self, extra=None):
        if self.fake:
            c = [{'host': 'fake', 'label': 'Fake robot (local)', 'via': 'custom', 'reachable': True, 'ms': 0}]
            self.last_cands = c
            self.bus.publish({'ev': 'discover', 'candidates': c})
            return c
        prev = self.bus.last_conn
        if prev.get('state') not in ('connected', 'connecting', 'reconnecting'):
            self.conn('discovering', prev.get('host'), prev.get('via'))
        t0 = time.time()
        deadline = t0 + 4.0
        res = {}
        threads = []

        def probe(c):
            t = time.time()
            try:
                s = socket.create_connection((c['host'], 22), timeout=1.5)
                s.close()
                res[c['host']] = (True, int((time.time() - t) * 1000))
            except OSError:
                res[c['host']] = (False, int((time.time() - t) * 1000))

        def start_probes(cs):
            for c in cs:
                th = threading.Thread(target=probe, args=(c,), daemon=True)
                th.start()
                threads.append(th)
        v6box = []
        nb = threading.Thread(target=lambda: v6box.extend(find_cable_ipv6(3.2)), daemon=True)
        nb.start()
        wbox = []
        wt = threading.Thread(target=lambda: wbox.append(laptop_wifi()), daemon=True)
        wt.start()
        wt.join(max(0.1, min(2.0, deadline - time.time())))
        wifi_ssid = (wbox[0] or {}).get('ssid') if wbox else None
        static = self.candidate_list(extra, wifi_ssid=wifi_ssid)
        start_probes(static)
        nb.join(max(0.1, deadline - time.time()))
        cands = self.candidate_list(extra, v6box, wifi_ssid)
        start_probes([c for c in cands if c['host'] not in res and c['host'] not in [s['host'] for s in static]])
        for th in threads:
            th.join(max(0.05, deadline - time.time()))
        for c in cands:
            ok, ms = res.get(c['host'], (False, int((time.time() - t0) * 1000)))
            c['reachable'], c['ms'] = ok, ms
        cands.sort(key=lambda c: not c['reachable'])  # stable: reachable first, order kept
        self.last_cands = cands
        self.bus.publish({'ev': 'discover', 'candidates': cands})
        if self.bus.last_conn.get('state') == 'discovering':
            self.conn('disconnected', prev.get('host'), prev.get('via'))
        return cands

    # ---------------------------------------------------------------- v1.3: search the whole network
    def deep_discover(self):
        if not self.deep_lock.acquire(blocking=False):
            return {'ok': False, 'error': 'already searching'}
        try:
            return self._deep_discover()
        except Exception as e:  # never leave the button spinning
            self.log('error', 'network search failed: %s' % e)
            return {'ok': False, 'error': 'search failed: %s' % e}
        finally:
            self.deep_lock.release()

    def _deep_discover(self):
        def progress(done, total):
            self.bus.publish({'ev': 'deep_progress', 'done': done, 'total': total})
        if self.fake:
            for i in range(1, 21):
                time.sleep(0.1)
                progress(254 * i // 20, 254)
            cands = [{'host': 'fake', 'label': 'Your robot (identity confirmed)', 'via': 'custom', 'reachable': True,
                      'ms': 1, 'identity': 'confirmed', 'pi': True}]
        else:
            cands, err = deep_scan(self.trusted_keys(), progress)
            if err:
                return {'ok': False, 'error': err}
        self.last_cands = cands
        self.bus.publish({'ev': 'discover', 'candidates': cands, 'deep': True})
        self.log('info', 'network search: %d device(s) with ssh, %d confirmed as your robot'
                 % (len(cands), sum(1 for c in cands if c.get('identity') == 'confirmed')))
        return {'ok': True, 'candidates': cands}

    # ---------------------------------------------------------------- v1.3: automatic reconnect
    def bridge_lost(self, host, via, msg, kind):
        """Called by the bridge when it ended on its own while connected. True = Studio takes over (reconnects)."""
        self.teleop_off('Connection lost.')
        if self.closing or not host or not self.settings.get('auto_reconnect', True):
            return False
        if kind in ('host_key', 'key_not_set_up', 'key_missing', 'no_ssh'):
            return False  # waiting will not fix these
        with self.reconn_lock:
            if self.reconn is not None:
                return True
            st = self.reconn = {'cancel': threading.Event(), 'since': time.time(), 'host': host, 'via': via}
        threading.Thread(target=self._reconnect_loop, args=(st, msg), daemon=True, name='reconnect').start()
        return True

    def _reconnect_end(self, st):
        with self.reconn_lock:
            if self.reconn is not st:
                return False
            self.reconn = None
        return True

    def _reconnect_loop(self, st, msg):
        """Backoff 2, 4, 8, 15, 30, 30 ... s for up to reconnect_give_up s. It only opens the connection again:
        it never starts a program, never sends motion and never releases an e-stop."""
        host, via, attempt, fails = st['host'], st['via'], 0, 0
        self.log('warn', 'connection to %s lost (%s): reconnecting' % (host, msg))
        while not st['cancel'].is_set():
            attempt += 1
            delay = reconnect_delay(attempt, self.reconnect_delays)
            self.bus.publish({'ev': 'conn', 'state': 'reconnecting', 'host': host, 'via': via, 'error': msg,
                              'attempt': attempt, 'next_in': delay, 'since': st['since']})
            if st['cancel'].wait(delay):
                return
            if time.time() - st['since'] >= self.reconnect_give_up:
                break
            res = self.connect(host, auto=True)
            if st['cancel'].is_set():
                return
            if res.get('ok'):
                if self._reconnect_end(st):
                    self.log('info', 'reconnected to %s after %d attempt(s)' % (res.get('host') or host, attempt))
                    if not self.bridge.connected and not self.closing:  # dropped again at once
                        self.bridge_lost(host, via, 'connection lost again', 'other')
                return
            fails += 1
            msg = res.get('error') or msg
            if fails >= 2:  # the robot may have a new address: look around quickly
                try:
                    best = next((c for c in self.discover() if c.get('reachable')), None)
                except Exception:
                    best = None
                if best and not st['cancel'].is_set():
                    host, via = best['host'], best.get('via') or via
            if time.time() - st['since'] >= self.reconnect_give_up:
                break
        if st['cancel'].is_set() or not self._reconnect_end(st):
            return
        text = gave_up_text(self.reconnect_give_up)
        self.log('error', text)
        self.conn('disconnected', host, via, text, kind='gave_up')

    def reconnect_cancel(self, quiet=False):
        """Stop trying. quiet=True is used by Disconnect / Connect / shutdown, which publish the next state themselves."""
        with self.reconn_lock:
            st, self.reconn = self.reconn, None
        if st is None:
            return {'ok': True, 'was_reconnecting': False}
        st['cancel'].set()
        try:
            self.bridge.stop()  # also ends an attempt that is in flight
        except Exception:
            pass
        self.log('info', 'automatic reconnect stopped')
        if not quiet:
            self.conn('disconnected', st['host'], st['via'])
        return {'ok': True, 'was_reconnecting': True}

    def fake_drop(self):
        """Fake mode only: end the fake bridge like a lost ssh connection (exit code non-zero)."""
        p = self.bridge.proc
        if p is None or p.poll() is not None or not self.bridge.connected:
            return {'ok': False, 'error': 'not connected'}
        p.kill()
        return {'ok': True}
