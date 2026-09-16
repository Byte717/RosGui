import math
import os
import time
from collections import OrderedDict

from PyQt5 import QtCore, QtGui, QtNetwork, QtWidgets


TILE_SIZE = 256
MIN_ZOOM = 2
MAX_ZOOM = 19
DEFAULT_ZOOM = 14
MAX_MERCATOR_LATITUDE = 85.05112878
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def _valid_coordinate(latitude, longitude):
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude


class RouteCanvas(QtWidgets.QWidget):
    """Native slippy map with asynchronous raster tiles and a GPS route overlay."""

    def __init__(self, parent=None, tile_url_template=None):
        super().__init__(parent)
        self.path_points = []
        self.current_location = None

        self.zoom = MIN_ZOOM
        self.center_latitude = 0.0
        self.center_longitude = 0.0
        self._follow_location = True
        self._last_mouse_position = None
        self._dragged = False

        self.tile_url_template = (
            tile_url_template
            or os.environ.get("ROSGUI_TILE_URL")
            or DEFAULT_TILE_URL
        )
        self._tile_cache = OrderedDict()
        self._tile_cache_limit = 256
        self._pending_tiles = {}
        self._failed_tiles = {}
        self._max_concurrent_requests = 6

        self.network_manager = QtNetwork.QNetworkAccessManager(self)
        disk_cache = QtNetwork.QNetworkDiskCache(self.network_manager)
        cache_root = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.CacheLocation
        )
        if cache_root:
            disk_cache.setCacheDirectory(os.path.join(cache_root, "RosGui", "map_tiles"))
            disk_cache.setMaximumCacheSize(128 * 1024 * 1024)
            self.network_manager.setCache(disk_cache)

        self.setMinimumSize(320, 220)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setToolTip("Drag to pan, use the mouse wheel or +/− to zoom")

    def set_data(self, path_points, current_location=None, zoom=None):
        had_geometry = bool(self.path_points or self.current_location)
        had_location = self.current_location is not None
        self.path_points = [dict(point) for point in path_points]
        self.current_location = (
            dict(current_location) if current_location is not None else None
        )

        if self.current_location is not None:
            latitude = self.current_location["latitude"]
            longitude = self.current_location["longitude"]
            if not had_location:
                self.zoom = self._bounded_zoom(zoom if zoom is not None else DEFAULT_ZOOM)
                self._follow_location = True
            if self._follow_location:
                self.center_latitude = latitude
                self.center_longitude = longitude
        elif not had_geometry and self.path_points:
            self.reset_view()
            return

        self.update()

    def reset_view(self):
        coordinates = self._route_coordinates()
        if not coordinates:
            self.zoom = MIN_ZOOM
            self.center_latitude = 0.0
            self.center_longitude = 0.0
            self._follow_location = True
        elif len(coordinates) == 1:
            self.zoom = DEFAULT_ZOOM
            self.center_latitude, self.center_longitude = coordinates[0]
            self._follow_location = True
        else:
            self._fit_coordinates(coordinates)
            self._follow_location = False
        self.update()

    def zoom_in(self):
        self._zoom_at(self.zoom + 1, QtCore.QPointF(self.width() / 2, self.height() / 2))

    def zoom_out(self):
        self._zoom_at(self.zoom - 1, QtCore.QPointF(self.width() / 2, self.height() / 2))

    def paintEvent(self, event):
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#101010"))

        loaded_count, missing_count = self._paint_tiles(painter)

        # The standard OSM tiles are deliberately dimmed to match the dashboard and
        # keep the yellow route legible without depending on a third-party dark theme.
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 58))
        self._paint_route(painter)

        if loaded_count == 0 and missing_count:
            if self._pending_tiles:
                message = "Loading map tiles…"
            else:
                message = "Map tiles unavailable · GPS route is still available"
            self._paint_badge(painter, message)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._last_mouse_position = event.pos()
            self._dragged = False
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._last_mouse_position is None:
            super().mouseMoveEvent(event)
            return

        delta = event.pos() - self._last_mouse_position
        self._last_mouse_position = event.pos()
        if delta.manhattanLength() > 0:
            self._dragged = True
            self._follow_location = False
            center_x, center_y = self._latlon_to_world(
                self.center_latitude,
                self.center_longitude,
                self.zoom,
            )
            self._set_center_from_world(center_x - delta.x(), center_y - delta.y())
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._last_mouse_position = None
            self.setCursor(QtCore.Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self._follow_location = False
            self._zoom_at(self.zoom + (1 if delta > 0 else -1), event.pos())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._follow_location = False
            self._zoom_at(self.zoom + 1, event.pos())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _paint_tiles(self, painter):
        center_x, center_y = self._latlon_to_world(
            self.center_latitude,
            self.center_longitude,
            self.zoom,
        )
        left = center_x - self.width() / 2.0
        top = center_y - self.height() / 2.0
        first_x = math.floor(left / TILE_SIZE)
        last_x = math.floor((left + self.width()) / TILE_SIZE)
        first_y = math.floor(top / TILE_SIZE)
        last_y = math.floor((top + self.height()) / TILE_SIZE)
        tile_count = 1 << self.zoom
        loaded_count = 0
        missing_count = 0

        for tile_y in range(first_y, last_y + 1):
            if tile_y < 0 or tile_y >= tile_count:
                continue
            for unwrapped_x in range(first_x, last_x + 1):
                tile_x = unwrapped_x % tile_count
                key = (self.zoom, tile_x, tile_y)
                target = QtCore.QRectF(
                    unwrapped_x * TILE_SIZE - left,
                    tile_y * TILE_SIZE - top,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                pixmap = self._tile_cache.get(key)
                if pixmap is not None:
                    self._tile_cache.move_to_end(key)
                    painter.drawPixmap(
                        target,
                        pixmap,
                        QtCore.QRectF(pixmap.rect()),
                    )
                    loaded_count += 1
                else:
                    painter.fillRect(target, QtGui.QColor("#151515"))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#202020"), 1))
                    painter.drawRect(target)
                    missing_count += 1
                    self._request_tile(key)

        return loaded_count, missing_count

    def _paint_route(self, painter):
        if len(self.path_points) > 1:
            route = QtGui.QPainterPath()
            first = self._screen_point(
                self.path_points[0]["latitude"],
                self.path_points[0]["longitude"],
            )
            route.moveTo(first)
            for point in self.path_points[1:]:
                route.lineTo(
                    self._screen_point(point["latitude"], point["longitude"])
                )
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor("#1a1a1a"),
                    6,
                    QtCore.Qt.SolidLine,
                    QtCore.Qt.RoundCap,
                    QtCore.Qt.RoundJoin,
                )
            )
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(route)
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor("#f5c542"),
                    3,
                    QtCore.Qt.SolidLine,
                    QtCore.Qt.RoundCap,
                    QtCore.Qt.RoundJoin,
                )
            )
            painter.drawPath(route)

        painter.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1.5))
        painter.setBrush(QtGui.QColor("#f5c542"))
        for point in self.path_points:
            screen_point = self._screen_point(
                point["latitude"], point["longitude"]
            )
            if self.rect().adjusted(-6, -6, 6, 6).contains(screen_point.toPoint()):
                painter.drawEllipse(screen_point, 3.5, 3.5)

        if self.current_location is not None:
            current_point = self._screen_point(
                self.current_location["latitude"],
                self.current_location["longitude"],
            )
            painter.setPen(QtGui.QPen(QtGui.QColor(34, 197, 94, 75), 1))
            painter.setBrush(QtGui.QColor(34, 197, 94, 55))
            painter.drawEllipse(current_point, 13.0, 13.0)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f5f5f5"), 2))
            painter.setBrush(QtGui.QColor("#22c55e"))
            painter.drawEllipse(current_point, 7.0, 7.0)

    def _paint_badge(self, painter, message):
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(message)
        badge = QtCore.QRectF(10, 10, text_width + 20, metrics.height() + 12)
        painter.setPen(QtGui.QPen(QtGui.QColor("#404040"), 1))
        painter.setBrush(QtGui.QColor(5, 5, 5, 220))
        painter.drawRoundedRect(badge, 5, 5)
        painter.setPen(QtGui.QColor("#b5b5b5"))
        painter.drawText(badge, QtCore.Qt.AlignCenter, message)

    def _request_tile(self, key):
        if key in self._pending_tiles:
            return
        if len(self._pending_tiles) >= self._max_concurrent_requests:
            return
        retry_after = self._failed_tiles.get(key)
        if retry_after is not None and time.monotonic() < retry_after:
            return

        zoom, tile_x, tile_y = key
        try:
            url = self.tile_url_template.format(z=zoom, x=tile_x, y=tile_y)
        except (KeyError, ValueError):
            self._failed_tiles[key] = time.monotonic() + 60.0
            return

        request = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        request.setRawHeader(
            b"User-Agent",
            b"RosGui/1.0 (PyQt rover dashboard; OpenStreetMap tile client)",
        )
        request.setAttribute(
            QtNetwork.QNetworkRequest.CacheLoadControlAttribute,
            QtNetwork.QNetworkRequest.PreferCache,
        )
        if hasattr(QtNetwork.QNetworkRequest, "RedirectPolicyAttribute"):
            request.setAttribute(
                QtNetwork.QNetworkRequest.RedirectPolicyAttribute,
                QtNetwork.QNetworkRequest.NoLessSafeRedirectPolicy,
            )
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(12000)

        reply = self.network_manager.get(request)
        self._pending_tiles[key] = reply
        reply.finished.connect(
            lambda requested_key=key, network_reply=reply: self._tile_finished(
                requested_key,
                network_reply,
            )
        )

    def _tile_finished(self, key, reply):
        self._pending_tiles.pop(key, None)
        loaded = False
        if reply.error() == QtNetwork.QNetworkReply.NoError:
            image = QtGui.QImage()
            loaded = image.loadFromData(bytes(reply.readAll()))
            if loaded:
                self._tile_cache[key] = QtGui.QPixmap.fromImage(image)
                self._tile_cache.move_to_end(key)
                while len(self._tile_cache) > self._tile_cache_limit:
                    self._tile_cache.popitem(last=False)
                self._failed_tiles.pop(key, None)

        if not loaded:
            self._failed_tiles[key] = time.monotonic() + 30.0
        reply.deleteLater()
        self.update()

    def _screen_point(self, latitude, longitude):
        world_x, world_y = self._latlon_to_world(latitude, longitude, self.zoom)
        center_x, center_y = self._latlon_to_world(
            self.center_latitude,
            self.center_longitude,
            self.zoom,
        )
        world_size = TILE_SIZE * (1 << self.zoom)
        world_x += round((center_x - world_x) / world_size) * world_size
        return QtCore.QPointF(
            world_x - center_x + self.width() / 2.0,
            world_y - center_y + self.height() / 2.0,
        )

    def _zoom_at(self, next_zoom, position):
        next_zoom = self._bounded_zoom(next_zoom)
        if next_zoom == self.zoom:
            return

        center_x, center_y = self._latlon_to_world(
            self.center_latitude,
            self.center_longitude,
            self.zoom,
        )
        cursor_x = center_x + position.x() - self.width() / 2.0
        cursor_y = center_y + position.y() - self.height() / 2.0
        cursor_latitude, cursor_longitude = self._world_to_latlon(
            cursor_x,
            cursor_y,
            self.zoom,
        )

        self.zoom = next_zoom
        next_cursor_x, next_cursor_y = self._latlon_to_world(
            cursor_latitude,
            cursor_longitude,
            self.zoom,
        )
        self._set_center_from_world(
            next_cursor_x - position.x() + self.width() / 2.0,
            next_cursor_y - position.y() + self.height() / 2.0,
        )
        self.update()

    def _fit_coordinates(self, coordinates):
        padding = 48.0
        available_width = max(1.0, self.width() - padding * 2)
        available_height = max(1.0, self.height() - padding * 2)

        selected = None
        for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
            world_points = [
                self._latlon_to_world(latitude, longitude, zoom)
                for latitude, longitude in coordinates
            ]
            world_size = TILE_SIZE * (1 << zoom)
            anchor_x = world_points[0][0]
            unwrapped = [
                (
                    x + round((anchor_x - x) / world_size) * world_size,
                    y,
                )
                for x, y in world_points
            ]
            min_x = min(point[0] for point in unwrapped)
            max_x = max(point[0] for point in unwrapped)
            min_y = min(point[1] for point in unwrapped)
            max_y = max(point[1] for point in unwrapped)
            selected = (zoom, min_x, max_x, min_y, max_y)
            if max_x - min_x <= available_width and max_y - min_y <= available_height:
                break

        zoom, min_x, max_x, min_y, max_y = selected
        self.zoom = zoom
        self._set_center_from_world((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def _set_center_from_world(self, world_x, world_y):
        world_size = TILE_SIZE * (1 << self.zoom)
        world_x %= world_size
        world_y = max(0.0, min(world_size - 1.0, world_y))
        self.center_latitude, self.center_longitude = self._world_to_latlon(
            world_x,
            world_y,
            self.zoom,
        )

    def _route_coordinates(self):
        coordinates = [
            (point["latitude"], point["longitude"])
            for point in self.path_points
        ]
        if self.current_location is not None:
            current = (
                self.current_location["latitude"],
                self.current_location["longitude"],
            )
            if not coordinates or coordinates[-1] != current:
                coordinates.append(current)
        return coordinates

    @staticmethod
    def _bounded_zoom(zoom):
        try:
            zoom = int(zoom)
        except (TypeError, ValueError):
            zoom = DEFAULT_ZOOM
        return max(MIN_ZOOM, min(MAX_ZOOM, zoom))

    @staticmethod
    def _latlon_to_world(latitude, longitude, zoom):
        latitude = max(-MAX_MERCATOR_LATITUDE, min(MAX_MERCATOR_LATITUDE, latitude))
        world_size = TILE_SIZE * (1 << zoom)
        latitude_radians = math.radians(latitude)
        x = (longitude + 180.0) / 360.0 * world_size
        y = (
            0.5
            - math.log(
                (1.0 + math.sin(latitude_radians))
                / (1.0 - math.sin(latitude_radians))
            )
            / (4.0 * math.pi)
        ) * world_size
        return x, y

    @staticmethod
    def _world_to_latlon(world_x, world_y, zoom):
        world_size = TILE_SIZE * (1 << zoom)
        longitude = world_x / world_size * 360.0 - 180.0
        mercator_y = math.pi * (1.0 - 2.0 * world_y / world_size)
        latitude = math.degrees(math.atan(math.sinh(mercator_y)))
        return latitude, longitude


class MapWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.latitude = None
        self.longitude = None
        self.location_name = ""
        self.path_points = []

        self.setMinimumSize(420, 300)
        self.setStyleSheet(
            """
            QFrame {
                background-color: #050505;
                border: 1px solid #262626;
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                border: none;
                color: #a3a3a3;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #f5c542;
                font-size: 16px;
                font-weight: 800;
                padding: 0;
            }
            QPushButton:hover {
                color: #ffe08a;
                background-color: #171717;
                border-radius: 4px;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = QtWidgets.QLabel("Route map")
        title.setStyleSheet("color: #f5f5f5; font-size: 14px; font-weight: 800;")

        zoom_out_button = QtWidgets.QPushButton("−")
        zoom_out_button.setFixedSize(24, 22)
        zoom_out_button.setToolTip("Zoom out")
        zoom_out_button.clicked.connect(self.zoom_out)

        zoom_in_button = QtWidgets.QPushButton("+")
        zoom_in_button.setFixedSize(24, 22)
        zoom_in_button.setToolTip("Zoom in")
        zoom_in_button.clicked.connect(self.zoom_in)

        reset_button = QtWidgets.QPushButton("⟲")
        reset_button.setFixedSize(24, 22)
        reset_button.setToolTip("Fit the GPS route in the map")
        reset_button.clicked.connect(self.reset_view)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(zoom_out_button)
        header.addWidget(zoom_in_button)
        header.addWidget(reset_button)
        layout.addLayout(header)

        self.location_status = QtWidgets.QLabel("Waiting for GPS data")
        self.location_status.setStyleSheet(
            "color: #a3a3a3; font-size: 12px; font-weight: 700;"
        )
        layout.addWidget(self.location_status)

        self.map_canvas = RouteCanvas()
        layout.addWidget(self.map_canvas, stretch=1)

        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        help_label = QtWidgets.QLabel("Drag to pan · scroll to zoom")
        help_label.setStyleSheet("color: #737373; font-size: 10px;")
        attribution = QtWidgets.QLabel(
            '<a style="color:#737373" href="https://www.openstreetmap.org/copyright">'
            "© OpenStreetMap contributors</a>"
        )
        attribution.setStyleSheet("color: #737373; font-size: 10px;")
        attribution.setOpenExternalLinks(True)
        footer.addWidget(help_label)
        footer.addStretch()
        footer.addWidget(attribution)
        layout.addLayout(footer)

    def set_location(
        self,
        latitude: float,
        longitude: float,
        name: str = "",
        zoom: int = DEFAULT_ZOOM,
    ):
        coordinate = _valid_coordinate(latitude, longitude)
        if coordinate is None:
            self.clear_location()
            return
        latitude, longitude = coordinate

        self.latitude = latitude
        self.longitude = longitude
        self.location_name = name or f"{latitude:.5f}, {longitude:.5f}"
        self.location_status.setText(
            f"{self.location_name} · {latitude:.5f}, {longitude:.5f} · GPS live"
        )
        self._sync_canvas(zoom=zoom)

    def add_path_point(self, latitude: float, longitude: float, label: str = ""):
        coordinate = _valid_coordinate(latitude, longitude)
        if coordinate is None:
            return None
        latitude, longitude = coordinate

        point = {
            "latitude": latitude,
            "longitude": longitude,
            "label": label or f"Point {len(self.path_points) + 1}",
        }
        self.path_points.append(point)
        if len(self.path_points) > 1000:
            del self.path_points[:-1000]
        self._sync_canvas()
        return point

    def set_path_points(self, points):
        normalized_points = []
        for index, point in enumerate(points):
            try:
                coordinate = _valid_coordinate(
                    point["latitude"],
                    point["longitude"],
                )
            except (KeyError, TypeError):
                continue
            if coordinate is None:
                continue
            latitude, longitude = coordinate
            normalized_points.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "label": point.get("label") or f"Point {index + 1}",
                }
            )
        self.path_points = normalized_points[-1000:]
        self._sync_canvas()

    def clear_path_points(self):
        self.path_points = []
        self._sync_canvas()

    def clear_location(self):
        self.latitude = None
        self.longitude = None
        self.location_name = ""
        self.location_status.setText("GPS data unavailable")
        self._sync_canvas()

    def reset_view(self):
        self.map_canvas.reset_view()

    def zoom_in(self):
        self.map_canvas.zoom_in()

    def zoom_out(self):
        self.map_canvas.zoom_out()

    def _sync_canvas(self, zoom=None):
        current_location = None
        if self.latitude is not None and self.longitude is not None:
            current_location = {
                "latitude": self.latitude,
                "longitude": self.longitude,
            }
        self.map_canvas.set_data(
            self.path_points,
            current_location,
            zoom=zoom,
        )
