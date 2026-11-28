"""Sync of a laptop folder with the robot (upload, download, delete) and the local file list.
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


class FileSyncMixin:
    # ---------------------------------------------------------------- sync
    def _remote_exec_argv(self, shell_cmd, fake_args):
        """Argv for a command on the robot (ssh) or, in fake mode, the local helper standing in for it."""
        if self.fake:
            return self_argv('--_fake-tar', *fake_args)
        ssh = find_exe('ssh')
        if not ssh:
            raise BridgeError('ssh not found')
        host = self.bridge.host or self.settings.get('last_host')
        if not host:
            raise BridgeError('not connected')
        return build_ssh_argv(ssh, host, self.key_path(create=False), self.known_hosts, shell_cmd, connect_timeout=8,
                              user=self.user())

    def sync(self, req):
        direction = req.get('direction', 'up')
        if direction not in ('up', 'down'):
            return {'ok': False, 'error': 'direction must be up or down'}
        local_dir = req.get('local_dir') or self.settings.get('local_dir')
        remote_dir = req.get('remote_dir') or self.settings.get('remote_dir') or DEFAULT_REMOTE_DIR
        delete, dry = bool(req.get('delete')), bool(req.get('dry_run'))
        if not local_dir:
            return {'ok': False, 'error': 'choose a local folder first'}
        local_dir = os.path.abspath(os.path.expanduser(local_dir))
        if direction == 'up' and not os.path.isdir(local_dir):
            return {'ok': False, 'error': 'local folder does not exist: ' + local_dir}
        if not self.sync_lock.acquire(blocking=False):
            return {'ok': False, 'error': 'another sync is running'}
        try:
            self.bus.publish({'ev': 'sync', 'state': 'running', 'direction': direction})
            res = self._sync(direction, local_dir, remote_dir, delete, dry, bool(req.get('confirm_delete')))
        except (BridgeError, OSError, ValueError, tarfile.TarError) as e:
            res = {'ok': False, 'error': str(e)}
        finally:
            self.sync_lock.release()
        self.bus.publish({'ev': 'sync', 'state': 'done' if res.get('ok') else 'error', 'direction': direction,
                          'uploaded': res.get('uploaded', []), 'skipped': res.get('skipped', 0),
                          'deleted': res.get('deleted', []), 'error': res.get('error')})
        return res

    def _sync(self, direction, local_dir, remote_dir, delete, dry, confirm_delete):
        r = self.bridge.request({'cmd': 'ls', 'dir': remote_dir, 'recursive': True}, 20)
        remote = {}
        if r.get('ok'):
            remote = {f['name'].replace('\\', '/'): {'size': f.get('size'), 'sha1': f.get('sha1')}
                      for f in r.get('files', []) if not f.get('is_dir')
                      and not should_skip_local(f['name'].split('/'), f['name'].split('/')[-1])}
        elif direction == 'down' or not re.search(r'no such|not exist|not found', str(r.get('error', '')), re.I):
            return {'ok': False, 'error': r.get('error') or 'could not list the robot folder'}
        local = scan_local(local_dir) if os.path.isdir(local_dir) else {}
        plan = plan_sync(local, remote, direction)
        out = {'ok': True, 'direction': direction, 'dry_run': dry, 'new': plan['new'], 'changed': plan['changed'],
               'skipped': plan['same'], 'uploaded': [], 'deleted': [], 'would_delete': plan['extra'] if delete else []}
        if dry:
            out['would_transfer'] = plan['transfer']
            return out
        if delete and plan['extra'] and not confirm_delete:
            out['ok'] = False
            out['error'] = 'delete needs confirmation: run with dry_run first and send confirm_delete=true'
            return out
        if plan['transfer']:
            if direction == 'up':
                self._upload(local_dir, remote_dir, plan['transfer'])
            else:
                self._download(local_dir, remote_dir, plan['transfer'])
            out['uploaded'] = plan['transfer']
        if delete and plan['extra']:
            self._delete(direction, local_dir, remote_dir, plan['extra'])
            out['deleted'] = plan['extra']
        return out

    def _run_stream(self, argv, writer, timeout):
        """Run argv with stdin pipe; writer(stdin) feeds it. Returns (code, stdout, stderr)."""
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        err = io.BytesIO()
        t = threading.Thread(target=lambda: err.write(p.stderr.read()), daemon=True)
        t.start()
        try:
            try:
                writer(p.stdin)
            except BrokenPipeError:     # the far end quit early: its exit code and stderr say why
                pass
            finally:
                try:
                    p.stdin.close()
                except OSError:
                    pass
            out = p.stdout.read()
            code = p.wait()
        finally:
            timer.cancel()
            if p.poll() is None:
                p.kill()
        t.join(2)
        return code, out, err.getvalue().decode('utf-8', 'replace')

    def _upload(self, local_dir, remote_dir, rels):
        rd = remote_path_expr(remote_dir)
        total = sum(os.path.getsize(os.path.join(local_dir, *r.split('/'))) for r in rels)
        argv = self._remote_exec_argv('mkdir -p %s && tar -xmf - -C %s' % (rd, rd),
                                      ['extract', expand_remote(remote_dir, self.fake_home)])
        code, _, err = self._run_stream(argv, lambda w: write_tar_stream(w, local_dir, rels), 60 + total / 200000)
        if code != 0:
            kind, msg = map_ssh_error(err, code)
            if 'tar' in err.lower() and 'not found' in err.lower():
                return self._upload_scp(local_dir, remote_dir, rels)
            raise BridgeError('upload failed: ' + (msg if kind != 'other' else err.strip()[-200:] or msg))

    def _upload_scp(self, local_dir, remote_dir, rels):
        scp, host = find_exe('scp'), self.bridge.host or self.settings.get('last_host')
        if not scp or not host:
            raise BridgeError('remote tar is missing and scp is not available')
        for rel in rels:
            rpath = remote_dir.rstrip('/') + '/' + rel
            parent = rpath.rsplit('/', 1)[0]
            argv = build_ssh_argv(find_exe('ssh'), host, self.key_path(False), self.known_hosts, 'mkdir -p ' + remote_path_expr(parent),
                                 user=self.user())
            subprocess.run(argv, capture_output=True, timeout=20, **hide_flags())
            r = subprocess.run(build_scp_argv(scp, host, self.key_path(False), self.known_hosts,
                                              os.path.join(local_dir, *rel.split('/')), rpath, user=self.user()), capture_output=True, text=True, timeout=60, **hide_flags())
            if r.returncode != 0:
                raise BridgeError('scp failed for %s: %s' % (rel, r.stderr.strip()[-200:]))

    def _download(self, local_dir, remote_dir, rels):
        rd = remote_path_expr(remote_dir)
        argv = self._remote_exec_argv('tar -cf - -C %s -T -' % rd, ['create', expand_remote(remote_dir, self.fake_home)])
        os.makedirs(local_dir, exist_ok=True)
        code, out, err = self._run_stream(argv, lambda w: w.write(('\n'.join(rels) + '\n').encode()), 120)
        if code != 0:
            kind, msg = map_ssh_error(err, code)
            raise BridgeError('download failed: ' + (msg if kind != 'other' else err.strip()[-200:] or msg))
        extract_tar_stream(io.BytesIO(out), local_dir)

    def _delete(self, direction, local_dir, remote_dir, rels):
        if direction == 'down':
            for rel in rels:
                p = safe_member_path(local_dir, rel)
                if p and os.path.isfile(p):
                    os.remove(p)
            return
        rd = remote_path_expr(remote_dir)
        argv = self._remote_exec_argv("cd %s && xargs -d '\\n' -r rm -f --" % rd, ['rm', expand_remote(remote_dir, self.fake_home)])
        code, _, err = self._run_stream(argv, lambda w: w.write(('\n'.join(rels) + '\n').encode()), 60)
        if code != 0:
            raise BridgeError('delete failed: ' + err.strip()[-200:])

    def local_files(self, req):
        d = req.get('dir') or self.settings.get('local_dir')
        if not d or not os.path.isdir(os.path.expanduser(d)):
            return {'ok': False, 'error': 'folder not found: %s' % d}
        files = scan_local(os.path.expanduser(d))
        items = [{'name': k, 'size': v['size'], 'mtime': v['mtime'], 'sha1': v['sha1']} for k, v in sorted(files.items())][:5000]
        return {'ok': True, 'dir': os.path.abspath(os.path.expanduser(d)), 'files': items}
