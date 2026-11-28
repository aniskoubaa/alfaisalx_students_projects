"""Mapping features of the app: map events, previews, map download and route upload.
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


class MappingMixin:
    # ---------------------------------------------------------------- mapping (2.1)
    def on_map(self, ev):
        """A bridge `map` event: keep the picture, publish the same event without its data."""
        try:
            if ev.get('encoding') != 'cells':
                raise ValueError('live map must use the cells encoding')
            meta, gray = decode_map_payload(ev)
            png = png_gray(meta['width'], meta['height'], gray)
        except (ValueError, KeyError) as e:
            self.log('warn', 'bad map event dropped: %s' % e)
            return
        self.maps.set_map(meta, png)
        self.bus.publish(dict(meta, ev='map'))

    def mapping_info(self):
        info = self.maps.get_info()
        return dict(info, ok=True) if info else {'ok': True, 'state': 'unknown'}

    def map_preview_png(self, name, max_px):
        """(status, body, content type) of a saved map's preview picture; body is a dict for an error."""
        if not valid_map_name(name):
            return 400, {'ok': False, 'error': 'bad map name'}, None
        try:
            r = self.bridge.request({'cmd': 'map_preview', 'name': name, 'max_px': max_px}, 30)
        except BridgeError as e:
            return (409 if str(e) == 'not connected' else 502), {'ok': False, 'error': str(e)}, None
        if not r.get('ok'):
            err = str(r.get('error') or 'the robot refused')
            return (404 if re.search(r'no such|not found|missing|no map named', err, re.I) else 502), {'ok': False, 'error': err}, None
        try:
            meta, gray = decode_map_payload(r)
            return 200, png_gray(meta['width'], meta['height'], gray), 'image/png'
        except (ValueError, KeyError) as e:
            return 502, {'ok': False, 'error': 'bad preview from the robot: %s' % e}, None

    def map_download_zip(self, name):
        """(status, body, content type): the existing files of a saved map as a zip, built in memory."""
        if not valid_map_name(name):
            return 400, {'ok': False, 'error': 'bad map name'}, None
        try:
            r = self.bridge.request({'cmd': 'maps_list'}, 15)
        except BridgeError as e:
            return (409 if str(e) == 'not connected' else 502), {'ok': False, 'error': str(e)}, None
        if not r.get('ok'):
            return 502, {'ok': False, 'error': str(r.get('error') or 'the robot refused')}, None
        entry = next((m for m in r.get('maps') or [] if isinstance(m, dict) and m.get('name') == name), None)
        if entry is None:
            return 404, {'ok': False, 'error': 'no such map'}, None
        files = entry.get('files') if isinstance(entry.get('files'), dict) else {}
        rels = [name + ext for key, ext in MAP_FILE_EXTS if files.get(key) is not None]
        if not rels:
            return 404, {'ok': False, 'error': 'the map has no files'}, None
        tmp = tempfile.mkdtemp(prefix='studio_map_')
        try:
            self._download(tmp, MAP_REMOTE_DIR, rels)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                for rel in rels:
                    p = os.path.join(tmp, rel)
                    if os.path.isfile(p):
                        z.write(p, rel)
            return 200, buf.getvalue(), 'application/zip'
        except (BridgeError, OSError, ValueError, tarfile.TarError) as e:
            return 502, {'ok': False, 'error': str(e)}, None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def route_upload(self, req):
        """Copy a route folder (files as base64) to ~/robot_code/routes/<name> on the robot, atomically.

        The files go to a hidden .upload-<name> folder first and the robot renames it into place, so a failed
        upload never leaves a half route; an existing route is never overwritten."""
        name = req.get('name')
        ok, info = validate_route_upload(name, req.get('files'))
        if not ok:
            return {'ok': False, 'error': info}
        started, tmp = False, None
        try:
            r = self.bridge.request({'cmd': 'route_upload_cleanup', 'name': name}, 15)
            if not r.get('ok'):
                return {'ok': False, 'error': str(r.get('error') or 'the robot refused')}
            if r.get('exists'):
                return {'ok': False, 'error': 'A route named %s already exists on the robot.' % name, 'exists': True}
            tmp = tempfile.mkdtemp(prefix='studio_route_')
            rels = []
            for rel, data in info:
                with open(os.path.join(tmp, rel), 'wb') as f:
                    f.write(data)
                rels.append(rel)
            started = True
            self._upload(tmp, '~/robot_code/routes/.upload-' + name, rels)
            r = self.bridge.request({'cmd': 'route_upload_finish', 'name': name}, 15)
            if not r.get('ok'):
                res = {'ok': False, 'error': str(r.get('error') or 'the robot refused')}
                if r.get('exists'):
                    res['exists'] = True
                self._route_upload_cleanup(name)
                return res
            return {'ok': True, 'name': name, 'route': r.get('route')}
        except (BridgeError, OSError) as e:
            if started:
                self._route_upload_cleanup(name)
            return {'ok': False, 'error': str(e)}
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)

    def _route_upload_cleanup(self, name):
        """Best effort: remove a leftover hidden upload folder on the robot."""
        try:
            self.bridge.request({'cmd': 'route_upload_cleanup', 'name': name}, 15)
        except Exception:
            pass
