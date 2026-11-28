"""Thin Bridge commands for mapping, the map library, routes, trips and the menu. Each one checks its
arguments and calls a service; the real work is in the service modules."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .stack_adapters import *  # bundle: skip


class ServiceHandlersMixin:
    # ---- Studio 2.1: mapping and the map library (thin: check the arguments, call a service)
    @staticmethod
    def _svc(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ServiceError as e:
            raise BridgeError(str(e), **e.extra)

    def h_mapping_status(self, c):
        return self.mapping.status()

    def h_mapping_start(self, c):
        kc = c.get("keep_camera", False)
        if not isinstance(kc, bool):
            raise BridgeError("keep_camera must be true or false")
        return self._svc(self.mapping.start, kc)

    def h_mapping_save(self, c):
        ow = c.get("overwrite", False)
        if not isinstance(ow, bool):
            raise BridgeError("overwrite must be true or false")
        return self._svc(self.mapping.save, c.get("name"), ow)

    def h_mapping_stop(self, c):
        return self._svc(self.mapping.stop)

    def h_mapping_reset(self, c):
        return self.mapping.reset()

    def h_maps_list(self, c):
        return {"maps": self.maps.list(), "dir": self.maps_dir}

    def h_map_preview(self, c):
        try:
            mp = clamp_int(c.get("max_px"), 64, 1024, 512)
        except ValueError:
            raise BridgeError("max_px must be a number")
        return self._svc(self.maps.preview, c.get("name"), mp)

    def h_map_rename(self, c):
        return self._svc(self.maps.rename, c.get("name"), c.get("new_name"))

    def h_map_delete(self, c):
        return self._svc(self.maps.delete, c.get("name"), c.get("confirm"))

    def h_routes_list(self, c):
        return self.routes.list()

    def h_route_set_current(self, c):
        return self._svc(self.routes.set_current, c.get("name"), c.get("confirm"))

    def h_route_upload_cleanup(self, c):
        return self._svc(self.routes.upload_cleanup, c.get("name"))

    def h_route_upload_finish(self, c):
        return self._svc(self.routes.upload_finish, c.get("name"))

    def h_trip_status(self, c):
        try:
            n = clamp_int(c.get("lines"), 1, 200, 40)
        except ValueError:
            raise BridgeError("lines must be a number")
        return self.routes.trip_status(n)

    def h_menu_get(self, c):
        return self._svc(self.menu.get)

    def h_menu_check(self, c):
        text = c.get("text")
        if not isinstance(text, str):
            raise BridgeError("text is required and must be a string")
        return self._svc(self.menu.check, text)

    def h_menu_put(self, c):
        return self._svc(self.menu.put, c.get("text"), c.get("confirm"))

    def h_fake_trip(self, c):
        """Fake robot only (tests): mark a trip (delivery_mission.py) as running or not."""
        if not self.fake:
            raise BridgeError("only available in fake mode")
        v = c.get("running")
        if not isinstance(v, bool):
            raise BridgeError("running must be true or false")
        self.trip_probe.mission = v
        return {"running": v}
