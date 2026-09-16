class Listener:
    """Small callback store retained for non-ROS path consumers.

    ROS 2 subscriptions are owned by ``src.backend.ros_bridge``.  Keeping this
    class free of a ROS 1 import prevents an unused legacy dependency from
    breaking the application when the ROS 2 environment is sourced.
    """

    def __init__(self):
        self.path_points = []
        self.path_point_callbacks = []

    def on_path_point_added(self, callback):
        self.path_point_callbacks.append(callback)

    def add_path_point(self, latitude: float, longitude: float, label: str = ""):
        point = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "label": label or f"Point {len(self.path_points) + 1}",
        }
        self.path_points.append(point)

        for callback in self.path_point_callbacks:
            callback(point)

        return point
