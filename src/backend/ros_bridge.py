"""Non-blocking ROS 2 bridge for the PyQt dashboard.

The ROS 2 imports are optional so the GUI can still be edited and inspected on
machines that do not have a ROS installation.  When ROS 2 is available, the
bridge lives in a QThread and uses a short Qt timer to call ``spin_once``.
That keeps all Qt widgets on the main thread and prevents a ROS executor from
blocking the UI event loop.
"""

import math
import time

from PyQt5 import QtCore

from src.backend.ros_topics import (
    BATTERY_TOPIC,
    COMMAND_QUEUE_DEPTH,
    COLLECT_SAMPLE_COMMAND_TOPIC,
    CONTAINER_STATE_TOPIC,
    ENABLE_COMMAND_TOPIC,
    ENABLE_STATE_TOPIC,
    GPS_TOPIC,
    IMU_TOPIC,
    SAMPLE_DATA_TOPIC,
    SENSOR_TIMEOUT_SECONDS,
    TAKE_READING_COMMAND_TOPIC,
)

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState, Imu, NavSatFix
    from std_msgs.msg import Bool, Empty, Float64MultiArray
except ImportError as exc:  # ROS 2 is installed with the ROS environment.
    rclpy = None
    Node = None
    BatteryState = None
    Imu = None
    NavSatFix = None
    Bool = None
    Empty = None
    Float64MultiArray = None
    ROS_IMPORT_ERROR = str(exc)
else:
    ROS_IMPORT_ERROR = ""


ROS_AVAILABLE = rclpy is not None


def finite_or_none(value):
    """Return a finite float, or ``None`` for missing/invalid sensor data."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class RosBridge(QtCore.QObject):
    """Subscribe to rover telemetry and publish GUI operator commands."""

    gps_updated = QtCore.pyqtSignal(object)
    imu_updated = QtCore.pyqtSignal(object)
    battery_updated = QtCore.pyqtSignal(object)
    sample_updated = QtCore.pyqtSignal(object)
    enabled_updated = QtCore.pyqtSignal(object)
    container_updated = QtCore.pyqtSignal(object)
    connection_changed = QtCore.pyqtSignal(bool, str)
    bridge_error = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.node = None
        self.spin_timer = None
        self._initialized_rclpy = False
        self._reported_error = False
        self._last_seen = {
            "gps": None,
            "imu": None,
            "battery": None,
        }
        self._stale_streams = set()

        self._enable_publisher = None
        self._collect_publisher = None
        self._reading_publisher = None
        self._pending_commands = []

    @QtCore.pyqtSlot()
    def start(self):
        """Initialize ROS and start polling it from the bridge thread."""

        if not ROS_AVAILABLE:
            self.connection_changed.emit(
                False,
                "ROS 2 unavailable; start the GUI from a sourced ROS 2 shell.",
            )
            return

        try:
            rclpy.init(args=None)
            self._initialized_rclpy = True
            self.node = Node("ros_gui_dashboard")

            self.node.create_subscription(NavSatFix, GPS_TOPIC, self._gps_callback, 10)
            self.node.create_subscription(Imu, IMU_TOPIC, self._imu_callback, 10)
            self.node.create_subscription(BatteryState, BATTERY_TOPIC, self._battery_callback, 10)
            self.node.create_subscription(
                Float64MultiArray,
                SAMPLE_DATA_TOPIC,
                self._sample_callback,
                10,
            )
            self.node.create_subscription(Bool, ENABLE_STATE_TOPIC, self._enabled_callback, 10)
            self.node.create_subscription(
                Bool,
                CONTAINER_STATE_TOPIC,
                self._container_callback,
                10,
            )

            self._enable_publisher = self.node.create_publisher(
                Bool,
                ENABLE_COMMAND_TOPIC,
                COMMAND_QUEUE_DEPTH,
            )
            self._collect_publisher = self.node.create_publisher(
                Empty,
                COLLECT_SAMPLE_COMMAND_TOPIC,
                COMMAND_QUEUE_DEPTH,
            )
            self._reading_publisher = self.node.create_publisher(
                Empty,
                TAKE_READING_COMMAND_TOPIC,
                COMMAND_QUEUE_DEPTH,
            )
            self._flush_pending_commands()

            self.spin_timer = QtCore.QTimer(self)
            self.spin_timer.setInterval(20)
            self.spin_timer.timeout.connect(self._spin_once)
            self.spin_timer.start()
            self.connection_changed.emit(True, "ROS 2 connected")
        except Exception as exc:  # Keep the GUI alive if the ROS environment is incomplete.
            self._report_error(f"ROS 2 bridge could not start: {exc}")
            self._cleanup_ros()

    @QtCore.pyqtSlot()
    def shutdown(self):
        """Stop ROS from inside the bridge thread before Qt closes it."""

        if self.spin_timer is not None:
            self.spin_timer.stop()
            self.spin_timer.deleteLater()
            self.spin_timer = None

        self._cleanup_ros()
        thread = QtCore.QThread.currentThread()
        if thread is not None:
            thread.quit()

    @QtCore.pyqtSlot(bool)
    def publish_enabled(self, enabled: bool):
        if self._enable_publisher is None or Bool is None:
            self._pending_commands.append(("enable", bool(enabled)))
            return
        self._publish_enabled_message(enabled)

    @QtCore.pyqtSlot()
    def publish_collect_sample(self):
        if self._collect_publisher is None or Empty is None:
            self._pending_commands.append(("collect", None))
            return
        self._collect_publisher.publish(Empty())

    @QtCore.pyqtSlot()
    def publish_take_reading(self):
        if self._reading_publisher is None or Empty is None:
            self._pending_commands.append(("reading", None))
            return
        self._reading_publisher.publish(Empty())

    def _publish_enabled_message(self, enabled):
        message = Bool()
        message.data = bool(enabled)
        self._enable_publisher.publish(message)

    def _flush_pending_commands(self):
        pending_commands = self._pending_commands
        self._pending_commands = []
        for command, value in pending_commands:
            if command == "enable":
                self._publish_enabled_message(value)
            elif command == "collect" and self._collect_publisher is not None:
                self._collect_publisher.publish(Empty())
            elif command == "reading" and self._reading_publisher is not None:
                self._reading_publisher.publish(Empty())

    def _spin_once(self):
        if self.node is None or rclpy is None:
            return
        try:
            rclpy.spin_once(self.node, timeout_sec=0.0)
            self._check_for_stale_streams()
        except Exception as exc:
            self._report_error(f"ROS 2 communication error: {exc}")

    def _gps_callback(self, message):
        status = getattr(getattr(message, "status", None), "status", 0)
        latitude = finite_or_none(getattr(message, "latitude", None))
        longitude = finite_or_none(getattr(message, "longitude", None))
        if status < 0:
            latitude = None
            longitude = None

        self._mark_seen("gps")
        self.gps_updated.emit(
            {
                "latitude": latitude,
                "longitude": longitude,
                "valid": latitude is not None and longitude is not None,
            }
        )

    def _imu_callback(self, message):
        angular = getattr(message, "angular_velocity", None)
        linear = getattr(message, "linear_acceleration", None)
        values = {
            "gyro": {
                "roll": finite_or_none(getattr(angular, "x", None)),
                "pitch": finite_or_none(getattr(angular, "y", None)),
                "yaw": finite_or_none(getattr(angular, "z", None)),
            },
            "accel": {
                "x": finite_or_none(getattr(linear, "x", None)),
                "y": finite_or_none(getattr(linear, "y", None)),
                "z": finite_or_none(getattr(linear, "z", None)),
            },
        }
        self._mark_seen("imu")
        self.imu_updated.emit(values)

    def _battery_callback(self, message):
        self._mark_seen("battery")
        self.battery_updated.emit(
            {
                "voltage": finite_or_none(getattr(message, "voltage", None)),
                "current": finite_or_none(getattr(message, "current", None)),
                "percentage": finite_or_none(getattr(message, "percentage", None)),
            }
        )

    def _sample_callback(self, message):
        data = list(getattr(message, "data", ()))
        self.sample_updated.emit(
            {
                "pH": finite_or_none(data[0]) if len(data) > 0 else None,
                "Humidity": finite_or_none(data[1]) if len(data) > 1 else None,
                "Temperature": finite_or_none(data[2]) if len(data) > 2 else None,
                "CO2 Level": finite_or_none(data[3]) if len(data) > 3 else None,
            }
        )

    def _enabled_callback(self, message):
        self.enabled_updated.emit(bool(getattr(message, "data", False)))

    def _container_callback(self, message):
        self.container_updated.emit(bool(getattr(message, "data", False)))

    def _mark_seen(self, stream_name):
        self._last_seen[stream_name] = time.monotonic()
        self._stale_streams.discard(stream_name)

    def _check_for_stale_streams(self):
        now = time.monotonic()
        for stream_name, last_seen in self._last_seen.items():
            if last_seen is None or now - last_seen <= SENSOR_TIMEOUT_SECONDS:
                continue
            if stream_name in self._stale_streams:
                continue

            self._stale_streams.add(stream_name)
            if stream_name == "gps":
                self.gps_updated.emit({"latitude": None, "longitude": None, "valid": False})
            elif stream_name == "imu":
                missing = {"x": None, "y": None, "z": None}
                self.imu_updated.emit({"gyro": dict(missing), "accel": dict(missing)})
            elif stream_name == "battery":
                self.battery_updated.emit(
                    {"voltage": None, "current": None, "percentage": None}
                )

    def _report_error(self, message):
        if self._reported_error:
            return
        self._reported_error = True
        self.connection_changed.emit(False, message)
        self.bridge_error.emit(message)

    def _cleanup_ros(self):
        if self.node is not None:
            self.node.destroy_node()
            self.node = None
        if self._initialized_rclpy and rclpy is not None and rclpy.ok():
            rclpy.shutdown()
        self._initialized_rclpy = False
