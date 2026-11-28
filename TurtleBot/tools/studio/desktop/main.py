"""Command line, the hidden --fake tar helper and main().
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
from .terminals import *  # bundle: skip
from .settings import *  # bundle: skip
from .trust import *  # bundle: skip
from .map_api import *  # bundle: skip
from .updates import *  # bundle: skip
from .wifi import *  # bundle: skip
from .app import *  # bundle: skip
from .discovery import *  # bundle: skip
from .http_server import *  # bundle: skip


def fake_tar_main(argv):
    """Hidden helper used by --fake: stands in for the robot's tar/rm so the real streaming code is tested."""
    mode, d = argv[0], argv[1]
    if mode == 'extract':
        os.makedirs(d, exist_ok=True)
        extract_tar_stream(sys.stdin.buffer, d)
    elif mode == 'create':
        rels = [x for x in sys.stdin.buffer.read().decode().splitlines() if x]
        write_tar_stream(sys.stdout.buffer, d, rels)
        sys.stdout.buffer.flush()
    elif mode == 'rm':
        for rel in [x for x in sys.stdin.buffer.read().decode().splitlines() if x]:
            p = safe_member_path(d, rel)
            if p and os.path.isfile(p):
                os.remove(p)
    return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='TurtleBot Studio desktop backend')
    ap.add_argument('--port', type=int, default=None, help='port on 127.0.0.1 (default 8765, next free if busy)')
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--host-override', default=None, help='robot address to use instead of discovery')
    ap.add_argument('--fake', action='store_true', help='run robot_bridge.py --fake locally instead of ssh (demo/tests)')
    ap.add_argument('--config-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--fake-home', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--bridge-script', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--catalog', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--templates-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--web-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--heartbeat', type=float, default=15.0, help=argparse.SUPPRESS)
    ap.add_argument('--update-delay', type=float, default=5.0, help=argparse.SUPPRESS)
    ap.add_argument('--exit-when-closed', action='store_true', help='stop Studio when its window has been closed for a while (default in the built app)')
    ap.add_argument('--stay-open', action='store_true', help='keep running after the window is closed (default when run from source)')
    ap.add_argument('--close-grace', type=float, default=CLOSE_GRACE, help=argparse.SUPPRESS)
    ap.add_argument('--version-file', default=None, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '--_fake-tar':
        return fake_tar_main(argv[1:])
    if argv and argv[0] == '--_fake-bridge':  # frozen exe: the fake robot runs from the same binary
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import robot_bridge
        return robot_bridge.main(argv[1:])
    if '--version' in argv:
        line = 'TurtleBot Studio %s' % VERSION
        say(line)
        if '--version-file' in argv:   # hidden: the windowed build has no console, so the build smoke test reads a file
            try:
                with open(argv[argv.index('--version-file') + 1], 'w', encoding='utf-8') as f:
                    f.write(line + '\n')
            except (OSError, IndexError):
                return 1
        return 0
    if sys.version_info < (3, 10):
        say('Python 3.10 or newer is required.')
        return 2
    args = parse_args(argv)
    if args.host_override and not valid_host(args.host_override):
        say('invalid --host-override')
        return 2
    cfg = args.config_dir or config_dir()
    os.makedirs(cfg, exist_ok=True)
    old = read_instance(cfg)
    if old and instance_alive(old):   # Studio is already running for this user: show its window and leave
        url = 'http://127.0.0.1:%d/?token=%s' % (old['port'], old['token'])
        say('TurtleBot Studio is already running; opening its window.')
        if not args.no_browser:
            open_window(url, stored_window_mode(cfg), cfg)
        return 0
    app = Studio(args)
    srv = serve(app, 8765 if args.port is None else args.port, 20 if args.port is None else 1)
    url = 'http://127.0.0.1:%d/?token=%s' % (app.port, app.token)
    say('TurtleBot Studio %s%s' % (VERSION, ' (fake robot)' if app.fake else ''))
    say('Open this address in your browser (keep it private, it contains a one-time token):')
    say('  ' + url)
    say('Press Ctrl+C to stop.')
    app.log('info', 'Studio started on port %d (config: %s)' % (app.port, app.cfg))
    try:
        write_instance(app.cfg, app.port, app.token)
    except OSError as e:
        app.log('warn', 'could not write instance.json: %s' % e)
    app.start_update_check()
    stopping = threading.Event()

    def stop(*_):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=srv.shutdown, daemon=True).start()
    app.stop_cb = stop
    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, OSError, AttributeError):
        pass
    if resolve_exit_when_closed(args.exit_when_closed, args.stay_open, FROZEN, app.fake):
        def watch():
            w = CloseWatcher(args.close_grace)
            while not stopping.wait(0.5):
                if w.tick(app.bus.count(), time.time()):
                    app.log('info', 'No Studio window open for %d s: stopping' % args.close_grace)
                    stop()
                    return
        threading.Thread(target=watch, daemon=True).start()
    if not args.no_browser:
        mode = app.settings.get('window_mode', DEFAULT_WINDOW_MODE)
        t = threading.Timer(0.5, lambda: open_window(url, mode, app.cfg))
        t.daemon = True
        t.start()
    try:
        srv.serve_forever(poll_interval=0.3)
    finally:
        app.shutdown()
        srv.server_close()
        remove_instance(app.cfg, os.getpid())
        say('Stopped.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
