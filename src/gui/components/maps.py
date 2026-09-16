import math
import json

from PyQt5 import QtCore, QtWidgets

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except Exception as exc:
    QWebEngineView = None
    QWEBENGINE_IMPORT_ERROR = str(exc)
else:
    QWEBENGINE_IMPORT_ERROR = ""


MAP_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body, #map {
      width: 100%;
      height: 100%;
      margin: 0;
      background: #050505;
    }
    .leaflet-control-attribution {
      background: rgba(0, 0, 0, 0.7) !important;
      color: #a3a3a3 !important;
    }
    .leaflet-control-attribution a {
      color: #d4d4d4 !important;
    }
    .leaflet-bar a {
      background: #171717 !important;
      border-bottom-color: #303030 !important;
      color: #f5f5f5 !important;
    }
    .leaflet-popup-content-wrapper,
    .leaflet-popup-tip {
      background: #171717;
      color: #f5f5f5;
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const map = L.map("map", {
      boxZoom: true,
      doubleClickZoom: true,
      dragging: true,
      keyboard: true,
      preferCanvas: true,
      scrollWheelZoom: true,
      tap: true,
      touchZoom: true,
      zoomControl: true
    }).setView([0, 0], 2);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }).addTo(map);

    let pathMarkers = L.layerGroup().addTo(map);
    let pathLine = L.polyline([], {
      color: "#f5c542",
      weight: 3,
      opacity: 0.95,
      dashArray: "8 10"
    }).addTo(map);

    window.setLocation = function(lat, lon, label, zoom) {
      const target = [lat, lon];
      const nextZoom = zoom || Math.max(map.getZoom(), 14);
      map.setView(target, nextZoom);
    };

    window.setPathPoints = function(points) {
      pathMarkers.clearLayers();
      const latLngs = points.map((point) => [point.latitude, point.longitude]);
      pathLine.setLatLngs(latLngs);

      points.forEach((point, index) => {
        const marker = L.circleMarker([point.latitude, point.longitude], {
          radius: 6,
          color: "#f5c542",
          weight: 2,
          fillColor: "#050505",
          fillOpacity: 1
        });
        marker.bindPopup(point.label || ("Point " + (index + 1)));
        marker.addTo(pathMarkers);
      });

      if (latLngs.length === 1) {
        map.setView(latLngs[0], Math.max(map.getZoom(), 14));
      } else if (latLngs.length > 1) {
        map.fitBounds(latLngs, { padding: [28, 28] });
      }
    };

    window.resetView = function() {
      const latLngs = pathLine.getLatLngs();
      if (latLngs.length === 1) {
        map.setView(latLngs[0], 14);
      } else if (latLngs.length > 1) {
        map.fitBounds(latLngs, { padding: [28, 28] });
      } else {
        map.setView([0, 0], 2);
      }
    };
  </script>
</body>
</html>
"""


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

        if QWebEngineView is None:
            self._show_map_error(layout, QWEBENGINE_IMPORT_ERROR)
        else:
            try:
                self.web_view = QWebEngineView()
                self.web_view.loadFinished.connect(self._map_loaded)
                self.web_view.setHtml(MAP_HTML, QtCore.QUrl("https://localhost/"))
                layout.addWidget(self.web_view, stretch=1)
            except Exception as exc:
                self._show_map_error(layout, str(exc))

    def _show_map_error(self, layout, detail):
        self.web_view = None
        message = "Map unavailable.\nInstall PyQtWebEngine in the same environment as the GUI."
        if detail:
            message += f"\n\nDetails: {detail}"
        error_label = QtWidgets.QLabel(message)
        error_label.setAlignment(QtCore.Qt.AlignCenter)
        error_label.setWordWrap(True)
        layout.addWidget(error_label, stretch=1)

    def _map_loaded(self, loaded):
        if not loaded:
            self.location_status.setText("Map page failed to load")
            return

        self._sync_path_points()
        if self.latitude is not None and self.longitude is not None:
            self.set_location(self.latitude, self.longitude, self.location_name)

    def set_location(self, latitude: float, longitude: float, name: str = "", zoom: int = 14):
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
        self.location_name = name or f"{self.latitude:.5f}, {self.longitude:.5f}"
        self.location_status.setText(f"{self.location_name}  ·  GPS live")

        if self.web_view is None:
            return

        script = (
            "window.setLocation("
            f"{self.latitude}, {self.longitude}, "
            f"{json.dumps(self.location_name)}, {int(zoom)}"
            ");"
        )
        self.web_view.page().runJavaScript(script)

    def add_path_point(self, latitude: float, longitude: float, label: str = ""):
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            return None

        point = {
            "latitude": latitude,
            "longitude": longitude,
            "label": label or f"Point {len(self.path_points) + 1}",
        }
        self.path_points.append(point)
        self._sync_path_points()
        return point

    def set_path_points(self, points):
        normalized_points = []
        for index, point in enumerate(points):
            try:
                latitude = float(point["latitude"])
                longitude = float(point["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                continue
            normalized_points.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "label": point.get("label") or f"Point {index + 1}",
                }
            )
        self.path_points = normalized_points
        self._sync_path_points()

    def clear_path_points(self):
        self.path_points = []
        self._sync_path_points()

    def clear_location(self):
        self.latitude = None
        self.longitude = None
        self.location_name = ""
        self.location_status.setText("GPS data unavailable")

    def reset_view(self):
        if self.web_view is None:
            return
        self.web_view.page().runJavaScript("window.resetView();")

    def _sync_path_points(self):
        if self.web_view is None:
            return

        script = f"window.setPathPoints({json.dumps(self.path_points)});"
        self.web_view.page().runJavaScript(script)
