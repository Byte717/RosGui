class PathTraceBackend:
    def __init__(self):
        self.path_points = []
        self.point_added_callbacks = []

    def on_point_added(self, callback):
        self.point_added_callbacks.append(callback)

    def add_path_point(self, latitude: float, longitude: float, label: str = ""):
        point = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "label": label or f"Point {len(self.path_points) + 1}",
        }
        self.path_points.append(point)

        for callback in self.point_added_callbacks:
            callback(point)

        return point

    def clear_path(self):
        self.path_points = []
