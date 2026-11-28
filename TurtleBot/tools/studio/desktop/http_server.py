"""The local HTTP server: request handler (make_handler), Server and serve().
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


PLACEHOLDER = (b'<!doctype html><meta charset="utf-8"><title>TurtleBot Studio</title>'
               b'<body style="font-family:sans-serif;max-width:40em;margin:3em auto"><h1>TurtleBot Studio</h1>'
               b'<p>The user interface files are missing (web/index.html was not found next to studio.py). '
               b'The backend is running; the API works, but there is nothing to show here.</p></body>')
CTYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
          '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json',
          '.txt': 'text/plain; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.map': 'application/json',
          '.woff2': 'font/woff2', '.woff': 'font/woff', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
          '.gif': 'image/gif', '.webmanifest': 'application/manifest+json', '.zip': 'application/zip'}
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def make_handler(app):
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'TurtleBotStudio'

        def log_message(self, *a):
            pass

        def _host_ok(self):
            h = (self.headers.get('Host') or '').lower()
            return h in ('127.0.0.1:%d' % app.port, 'localhost:%d' % app.port)

        def _origin_ok(self):
            o = self.headers.get('Origin')
            return o is None or o in ('http://127.0.0.1:%d' % app.port, 'http://localhost:%d' % app.port)

        def _token_ok(self, query):
            t = self.headers.get('X-Studio-Token') or (query.get('token') or [''])[0]
            return hmac.compare_digest(t.encode(), app.token.encode())

        def _send(self, code, body, ctype='application/json', extra=None):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode())

        def _deny(self, why):
            self._json({'ok': False, 'error': why}, 403)

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._host_ok():
                return self._deny('bad host')
            if u.path.startswith('/api/'):
                if not self._token_ok(q):
                    return self._deny('bad token')
                if u.path == '/api/events':
                    return self._events()
                if u.path == '/api/settings':
                    return self._json(app.get_settings())
                if u.path == '/api/setup_status':
                    return self._json(app.setup_status())
                if u.path == '/api/catalog':
                    return self._json(app.catalog())
                if u.path == '/api/laptop_net':
                    return self._json(app.laptop_net())
                if u.path == '/api/diagnostics':
                    return self._json(app.diagnostics())
                if u.path == '/api/update_status':
                    return self._json(app.update_status())
                if u.path == '/api/history':
                    mins = clamp_minutes(_to_float((q.get('minutes') or ['15'])[0]))
                    return self._json(dict(app.history.query(mins), ok=True, minutes=mins, interval_s=1))
                if u.path == '/api/alerts':
                    since = _to_int((q.get('since') or ['0'])[0])
                    items, last = app.alerts.since(since)
                    return self._json({'ok': True, 'alerts': items, 'last_id': last})
                if u.path == '/api/teleop_limits':
                    return self._json(app.teleop_limits())
                if u.path == '/api/mapping':
                    return self._json(app.mapping_info())
                if u.path == '/api/map/live.png':
                    got = app.maps.get_map()
                    if got is None:
                        return self._json({'ok': False, 'error': 'no map yet'}, 404)
                    return self._send(200, got[0], 'image/png', {'X-Map-Meta': json.dumps(got[1], separators=(',', ':'))})
                if u.path in ('/api/maps/preview.png', '/api/maps/download'):
                    name = (q.get('name') or [''])[0]
                    if u.path == '/api/maps/download':
                        code, body, ctype = app.map_download_zip(name)
                    else:
                        mx = _to_int((q.get('max') or ['512'])[0]) or 512
                        code, body, ctype = app.map_preview_png(name, min(1024, max(64, mx)))
                    if ctype is None:
                        return self._json(body, code)
                    extra = {'Content-Disposition': 'attachment; filename="%s.zip"' % name} if ctype == 'application/zip' else None
                    return self._send(code, body, ctype, extra)
                if u.path.startswith('/api/templates/'):
                    txt = app.template_text(urllib.parse.unquote(u.path[len('/api/templates/'):]))
                    if txt is None:
                        return self._json({'ok': False, 'error': 'no such template'}, 404)
                    return self._send(200, txt.encode('utf-8'), 'text/plain; charset=utf-8')
                return self._json({'ok': False, 'error': 'not found'}, 404)
            self._static(u.path, u.query)

        def _file(self, base, rel, html_ok=True):
            full = safe_member_path(base, rel)
            if full and os.path.isfile(full):
                with open(full, 'rb') as f:
                    body = f.read()
                ext = os.path.splitext(full)[1].lower()
                return self._send(200, body, CTYPES.get(ext, 'application/octet-stream'),
                                  {'Content-Security-Policy': CSP} if ext == '.html' else None)
            return None

        def _redirect(self, where):
            self.send_response(302)
            self.send_header('Location', where)
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        def _static(self, path, query=''):
            web = app.web_dir
            v2 = os.path.join(web, 'v2')
            qs = ('?' + query) if query else ''
            if path == '/favicon.ico':     # the 1.3 page has no icon link: answer "no icon" instead of a 404 in the browser console
                self.send_response(204)
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                return
            if path in ('/', '', '/index.html'):
                if app.settings.get('ui') != 'classic' and os.path.isfile(os.path.join(v2, 'index.html')):
                    return self._file(v2, 'index.html')
                if self._file(web, 'index.html') is None:
                    self._send(200, PLACEHOLDER, 'text/html; charset=utf-8')
                return
            if path in ('/classic', '/v2'):
                return self._redirect(path + '/' + qs)
            if path.startswith('/classic/'):
                if self._file(web, path[len('/classic/'):] or 'index.html') is None:
                    self._send(404, b'not found', 'text/plain')
                return
            if path.startswith('/v2/'):
                if self._file(v2, path[len('/v2/'):] or 'index.html') is None:
                    self._send(404, b'not found', 'text/plain')
                return
            if self._file(web, path.lstrip('/')) is None:
                self._send(404, b'not found', 'text/plain')

        def _events(self):
            q = app.bus.subscribe()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                self.wfile.write(b': hello\n\n')
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=app.heartbeat)
                    except queue.Empty:
                        self.wfile.write(b': heartbeat\n\n')
                        self.wfile.flush()
                        continue
                    if ev is None:
                        break
                    self.wfile.write(b'data: ' + json.dumps(ev).encode() + b'\n\n')
                    self.wfile.flush()
            except (OSError, ValueError):
                pass
            finally:
                app.bus.unsubscribe(q)
                app.client_gone()

        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._host_ok() or not self._origin_ok():
                return self._deny('bad host')
            if not self._token_ok(q):
                return self._deny('bad token')
            try:
                n = int(self.headers.get('Content-Length') or 0)
                limit = ROUTE_UPLOAD_MAX + 1_000_000 if u.path == '/api/routes/upload' else 1_000_000
                if n > limit:
                    return self._json({'ok': False, 'error': 'request too large'}, 413)
                raw = self.rfile.read(n) if n else b'{}'
                req = json.loads(raw.decode('utf-8') or '{}')
                if not isinstance(req, dict):
                    raise ValueError
            except ValueError:
                return self._json({'ok': False, 'error': 'bad JSON'}, 400)
            routes = {
                '/api/discover': lambda: {'ok': True, 'candidates': app.discover(req.get('host'))},
                '/api/connect': lambda: app.connect(req.get('host')),
                '/api/disconnect': app.disconnect,
                '/api/bridge': lambda: app.forward(req),
                '/api/routes/upload': lambda: app.route_upload(req),
                '/api/estop': app.estop,
                '/api/sync': lambda: app.sync(req),
                '/api/settings': lambda: app.post_settings(req),
                '/api/open_terminal': app.open_terminal,
                '/api/setup_key': app.setup_key,
                '/api/setup_status': app.setup_status,
                '/api/create_key': app.create_key,
                '/api/scan_host_key': lambda: app.scan_host_key(req),
                '/api/trust_host_key': lambda: app.trust_key(req),
                '/api/untrust_host_key': lambda: app.untrust_key(req),
                '/api/test_login': lambda: app.test_login(req),
                '/api/robot_wifi_status': lambda: app.robot_wifi_status(req),
                '/api/open_vscode': lambda: app.open_vscode(req),
                '/api/local_files': lambda: app.local_files(req),
                '/api/robot_wifi_add': lambda: app.robot_wifi_add(req),
                '/api/robot_wifi_remove': lambda: app.robot_wifi_remove(req),
                '/api/laptop_wifi_settings': app.laptop_wifi_settings,
                '/api/join_hotspot': app.join_hotspot,
                '/api/deep_discover': app.deep_discover,
                '/api/reconnect_cancel': app.reconnect_cancel,
                '/api/quit': app.quit,
                '/api/teleop_limits': lambda: app.teleop_limits(req),
                '/api/check_updates': lambda: app.check_updates(force=bool(req.get('force', True))),
            }
            if app.fake:
                routes['/api/fake_drop'] = app.fake_drop
            fn = routes.get(u.path)
            if not fn:
                return self._json({'ok': False, 'error': 'not found'}, 404)
            try:
                res = fn()
            except Exception as e:  # never kill the handler thread silently
                app.log('error', 'internal error in %s: %s' % (u.path, e))
                res = {'ok': False, 'error': 'internal error: %s' % e}
            self._json(res)
    return H


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def serve(app, port, tries=1):
    last = None
    for p in range(port, port + tries):
        try:
            srv = Server(('127.0.0.1', p), make_handler(app))
            app.port = srv.server_address[1]
            return srv
        except OSError as e:
            last = e
    raise SystemExit('cannot bind 127.0.0.1:%d (%s)' % (port, last))
