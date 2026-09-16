import math

from PyQt5 import QtCore, QtGui, QtWidgets


class RouteCanvas(QtWidgets.QWidget):
    """A small native route view that does not depend on QtWebEngine."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path_points = []
        self.current_location = None
        self.setMinimumSize(320, 220)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)

    def set_data(self, path_points, current_location=None):
        self.path_points = [dict(point) for point in path_points]
        self.current_location = (
            dict(current_location) if current_location is not None else None
        )
        self.update()

    def reset_view(self):
        self.update()

    def paintEvent(self, event):
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#050505"))

        coordinates = [
            (point["latitude"], point["longitude"])
            for point in self.path_points
        ]
        if self.current_location is not None:
            coordinates.append(
                (
                    self.current_location["latitude"],
                    self.current_location["longitude"],
                )
            )

        if not coordinates:
            painter.setPen(QtGui.QColor("#737373"))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Waiting for GPS data")
            return

        left = 52.0
        top = 24.0
        right = 18.0
        bottom = 36.0
        canvas_width = max(1.0, self.width() - left - right)
        canvas_height = max(1.0, self.height() - top - bottom)

        min_lat = min(latitude for latitude, _longitude in coordinates)
        max_lat = max(latitude for latitude, _longitude in coordinates)
        min_lon = min(longitude for _latitude, longitude in coordinates)
        max_lon = max(longitude for _latitude, longitude in coordinates)

        lat_span = max(max_lat - min_lat, 0.00002)
        lon_span = max(max_lon - min_lon, 0.00002)
        canvas_ratio = canvas_width / canvas_height
        if lon_span / lat_span < canvas_ratio:
            lon_span = lat_span * canvas_ratio
        else:
            lat_span = lon_span / canvas_ratio

        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        min_lat = center_lat - lat_span / 2.0
        max_lat = center_lat + lat_span / 2.0
        min_lon = center_lon - lon_span / 2.0

        def to_point(latitude, longitude):
            x = left + ((longitude - min_lon) / lon_span) * canvas_width
            y = top + ((max_lat - latitude) / lat_span) * canvas_height
            return QtCore.QPointF(x, y)

        self._draw_grid(
            painter,
            left,
            top,
            canvas_width,
            canvas_height,
            min_lat,
            min_lon,
            lat_span,
            lon_span,
        )

        if len(self.path_points) > 1:
            route = QtGui.QPainterPath()
            first_point = self.path_points[0]
            route.moveTo(to_point(first_point["latitude"], first_point["longitude"]))
            for point in self.path_points[1:]:
                route.lineTo(to_point(point["latitude"], point["longitude"]))
            painter.setPen(QtGui.QPen(QtGui.QColor("#f5c542"), 2.5))
            painter.drawPath(route)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#f5c542"))
        for point in self.path_points:
            painter.drawEllipse(
                to_point(point["latitude"], point["longitude"]),
                3.5,
                3.5,
            )

        if self.current_location is not None:
            current_point = to_point(
                self.current_location["latitude"],
                self.current_location["longitude"],
            )
            painter.setBrush(QtGui.QColor("#22c55e"))
            painter.drawEllipse(current_point, 7.0, 7.0)
            painter.setBrush(QtGui.QColor("#050505"))
            painter.drawEllipse(current_point, 3.0, 3.0)

        painter.setPen(QtGui.QColor("#a3a3a3"))
        painter.drawText(8, 16, "GPS route")

    def _draw_grid(
        self,
        painter,
        left,
        top,
        canvas_width,
        canvas_height,
        min_lat,
        min_lon,
        lat_span,
        lon_span,
    ):
        grid_pen = QtGui.QPen(QtGui.QColor("#1d1d1d"), 1)
        label_pen = QtGui.QColor("#626262")
        painter.setPen(grid_pen)
        for index in range(1, 5):
            x = left + canvas_width * index / 5.0
            y = top + canvas_height * index / 5.0
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, top + canvas_height))
            painter.drawLine(QtCore.QPointF(left, y), QtCore.QPointF(left + canvas_width, y))

        painter.setPen(label_pen)
        for index in range(0, 6):
            latitude = min_lat + lat_span * (5 - index) / 5.0
            longitude = min_lon + lon_span * index / 5.0
            y = top + canvas_height * index / 5.0
            x = left + canvas_width * index / 5.0
            painter.drawText(4, int(y + 4), f"{latitude:.5f}")
            painter.drawText(int(x - 24), self.height() - 10, f"{longitude:.5f}")


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
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = QtWidgets.QLabel("Route map")
        title.setStyleSheet("color: #f5f5f5; font-size: 14px; font-weight: 800;")

        reset_button = QtWidgets.QPushButton("⟲")
        reset_button.setFixedSize(24, 22)
        reset_button.setToolTip("Reset map view")
        reset_button.clicked.connect(self.reset_view)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(reset_button)
        layout.addLayout(header)

        self.location_status = QtWidgets.QLabel("Waiting for GPS data")
        self.location_status.setStyleSheet("color: #a3a3a3; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.location_status)

        self.map_canvas = RouteCanvas()
        layout.addWidget(self.map_canvas, stretch=1)

    def set_location(self, latitude: float, longitude: float, name: str = "", zoom: int = 14):
        del zoom
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            self.clear_location()
            return
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            self.clear_location()
            return

        self.latitude = latitude
        self.longitude = longitude
        self.location_name = name or f"{latitude:.5f}, {longitude:.5f}"
        self.location_status.setText(f"{self.location_name}  ·  GPS live")
        self._sync_canvas()

    def add_path_point(self, latitude: float, longitude: float, label: str = ""):
        del label
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            return None

        self.path_points.append(
            {
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        if len(self.path_points) > 1000:
            del self.path_points[:-1000]
        self._sync_canvas()
        return self.path_points[-1]

    def set_path_points(self, points):
        normalized_points = []
        for point in points:
            try:
                latitude = float(point["latitude"])
                longitude = float(point["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(latitude) and math.isfinite(longitude):
                normalized_points.append(
                    {
                        "latitude": latitude,
                        "longitude": longitude,
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

    def _sync_canvas(self):
        current_location = None
        if self.latitude is not None and self.longitude is not None:
            current_location = {
                "latitude": self.latitude,
                "longitude": self.longitude,
            }
        self.map_canvas.set_data(self.path_points, current_location)
