"""Opens a terminal or VS Code on the laptop, connected to the robot.
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
from .connection import *  # bundle: skip
from .forwarding import *  # bundle: skip
from .telemetry import *  # bundle: skip
from .file_sync import *  # bundle: skip


class TerminalMixin:
    # ---------------------------------------------------------------- terminals / vscode
    def _terminal_argv(self, inner_argv):
        """Returns argv that opens a system terminal running inner_argv."""
        if IS_WIN:
            cmd = '& ' + ' '.join(ps_quote(a) for a in inner_argv)
            ps = shutil.which('powershell') or 'powershell'
            return [ps, '-NoExit', '-NoProfile', '-Command', cmd], subprocess.CREATE_NEW_CONSOLE
        line = ' '.join(shlex.quote(a) for a in inner_argv)
        if sys.platform == 'darwin':
            esc = line.replace('\\', '\\\\').replace('"', '\\"')
            return ['osascript', '-e', 'tell application "Terminal" to activate', '-e',
                    'tell application "Terminal" to do script "%s"' % esc], 0
        wrapped = line + '; echo; echo "Finished. Press Enter to close."; read _x'
        for t in ('x-terminal-emulator', 'gnome-terminal', 'konsole', 'xterm'):
            exe = shutil.which(t)
            if exe:
                if t == 'gnome-terminal':
                    return [exe, '--', 'bash', '-c', wrapped], 0
                return [exe, '-e', 'bash', '-c', wrapped], 0
        raise BridgeError('no terminal program found (tried x-terminal-emulator, gnome-terminal, konsole, xterm)')

    def _launch_terminal(self, inner_argv):
        argv, flags = self._terminal_argv(inner_argv)
        # Windows: no std handles at all, so the new console window gets its own keyboard input. With
        # stdin=DEVNULL PowerShell read end-of-input and the window closed at once (seen 2026-10-24).
        kw = {'creationflags': flags} if IS_WIN else {'stdin': subprocess.DEVNULL}
        subprocess.Popen(argv, **kw)

    def _terminal_host(self):
        host = self.bridge.host if self.bridge.host and self.bridge.host != 'fake' else None
        host = host or self.settings.get('last_host') or self.args.host_override
        if not host or not valid_host(host):
            raise BridgeError('no robot address yet: press Discover or Connect first')
        return host

    def open_terminal(self):
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        try:
            host = self._terminal_host()
            argv = build_ssh_argv(ssh, host, self.key_path(), self.known_hosts, None, batch=False, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def setup_key(self):
        if self.fake:
            return {'ok': True, 'fake': True, 'note': 'fake mode: no terminal'}
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        try:
            host = self._terminal_host()
            pub = self.public_key_line()
            q = shlex.quote(pub)
            remote = ("umask 077; mkdir -p ~/.ssh; grep -qxF %s ~/.ssh/authorized_keys 2>/dev/null || "
                      "echo %s >> ~/.ssh/authorized_keys" % (q, q))
            argv = build_ssh_argv(ssh, host, None, self.known_hosts, remote, batch=False, password_only=True, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'note': 'Type the robot password in the terminal window that opened. The app never sees it.'}

    def open_vscode(self, req):
        code = shutil.which('code')
        if not code:
            return {'ok': False, 'error': "VS Code command 'code' not found on PATH"}
        try:
            host = self._terminal_host()
            block = ssh_config_block(host, self.key_path(), self.known_hosts, user=self.user())
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        cfg_path = os.path.join(os.path.expanduser('~'), '.ssh', 'config')
        try:
            with open(cfg_path, encoding='utf-8', newline='') as f:
                existing = f.read()
        except OSError:
            existing = ''
        new, action = insert_ssh_config_block(existing, block)
        if action != 'unchanged' and not req.get('confirm_write_ssh_config'):
            return {'ok': False, 'needs_confirm': True, 'preview': block, 'action': action, 'file': cfg_path}
        if action != 'unchanged':
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            if existing:
                shutil.copy2(cfg_path, cfg_path + '.studio-backup')
            with open(cfg_path, 'w', encoding='utf-8', newline='') as f:
                f.write(new)
            self.log('info', 'ssh config block %s in %s (backup: config.studio-backup)' % (action, cfg_path))
        rd = (self.settings.get('remote_dir') or DEFAULT_REMOTE_DIR)
        rd = '/home/%s/%s' % (self.user(), rd[2:]) if rd.startswith('~/') else rd
        try:
            subprocess.Popen([code, '--remote', 'ssh-remote+turtlebot-studio', rd], stdin=subprocess.DEVNULL,
                             **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        except OSError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'config': action}
