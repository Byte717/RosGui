"""Small ROS 2 companion node for exercising the dashboard.

The dashboard does not depend on this file at runtime.  It is a deterministic
sensor simulator that publishes rover telemetry at ``Constants.UPDATE_INTERVAL``
and responds to the dashboard's enable, collect-sample, and take-reading
commands.
"""

import math
import sys

from Constants import UPDATE_INTERVAL
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
    TAKE_READING_COMMAND_TOPIC,
)

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState, Imu, NavSatFix, NavSatStatus
    from std_msgs.msg import Bool, Empty, Float64MultiArray
except ImportError as exc:
    rclpy = None
    Node = None
    BatteryState = None
    Imu = None
    NavSatFix = None
    NavSatStatus = None
    Bool = None
    Empty = None
    Float64MultiArray = None
    ROS_IMPORT_ERROR = str(exc)
else:
    ROS_IMPORT_ERROR = ""


PUBLISH_PERIOD_SECONDS = UPDATE_INTERVAL / 1000.0
ROS_NODE_BASE = Node if Node is not None else object


class SimulatedRoverPublisher(ROS_NODE_BASE):
    """Publish changing telemetry and respond to GUI operator commands."""

    def __init__(self):
        super().__init__("ros_gui_companion_publisher")

        self.enabled = True
        self.container_collected = False
        self.sample_index = 0
        self.phase = 0.0

        self.gps_publisher = self.create_publisher(NavSatFix, GPS_TOPIC, 10)
        self.imu_publisher = self.create_publisher(Imu, IMU_TOPIC, 10)
        self.battery_publisher = self.create_publisher(BatteryState, BATTERY_TOPIC, 10)
        self.sample_publisher = self.create_publisher(Float64MultiArray, SAMPLE_DATA_TOPIC, 10)
        self.enabled_state_publisher = self.create_publisher(
            Bool,
            ENABLE_STATE_TOPIC,
            COMMAND_QUEUE_DEPTH,
        )
        self.container_state_publisher = self.create_publisher(
            Bool,
            CONTAINER_STATE_TOPIC,
            COMMAND_QUEUE_DEPTH,
        )

        self.create_subscription(
            Bool,
            ENABLE_COMMAND_TOPIC,
            self._enable_callback,
            COMMAND_QUEUE_DEPTH,
        )
        self.create_subscription(
            Empty,
            COLLECT_SAMPLE_COMMAND_TOPIC,
            self._collect_sample_callback,
            COMMAND_QUEUE_DEPTH,
        )
        self.create_subscription(
            Empty,
            TAKE_READING_COMMAND_TOPIC,
            self._take_reading_callback,
            COMMAND_QUEUE_DEPTH,
        )

        # This is the only recurring telemetry timer.  Keeping it tied to the
        # project constant makes the fake node behave like a fixed-rate sensor.
        self.publish_timer = self.create_timer(
            PUBLISH_PERIOD_SECONDS,
            self.publish_telemetry,
        )
        self.publish_state()

    def publish_telemetry(self):
        self.publish_state()
        if not self.enabled:
            return

        self.phase += 0.18
        stamp = self.get_clock().now().to_msg()
        self._publish_gps(stamp)
        self._publish_imu(stamp)
        self._publish_battery(stamp)

    def _publish_gps(self, stamp):
        message = NavSatFix()
        message.header.stamp = stamp
        message.header.frame_id = "gps"
        message.status.status = NavSatStatus.STATUS_FIX
        message.status.service = NavSatStatus.SERVICE_GPS
        message.latitude = 42.3601 + math.sin(self.phase / 5.0) * 0.00035
        message.longitude = -71.0589 + math.cos(self.phase / 5.0) * 0.00035
        message.altitude = 12.0 + math.sin(self.phase) * 0.3
        self.gps_publisher.publish(message)

    def _publish_imu(self, stamp):
        message = Imu()
        message.header.stamp = stamp
        message.header.frame_id = "imu_link"
        message.linear_acceleration.x = 0.15 + math.sin(self.phase) * 0.08
        message.linear_acceleration.y = math.cos(self.phase * 0.8) * 0.06
        message.linear_acceleration.z = 9.81 + math.sin(self.phase * 0.6) * 0.04
        message.angular_velocity.x = math.sin(self.phase * 0.7) * 0.12
        message.angular_velocity.y = math.cos(self.phase * 0.5) * 0.09
        message.angular_velocity.z = 0.04 + math.sin(self.phase * 0.3) * 0.03
        self.imu_publisher.publish(message)

    def _publish_battery(self, stamp):
        message = BatteryState()
        message.header.stamp = stamp
        message.voltage = 12.6 - self.phase * 0.003
        message.current = 1.4 + math.sin(self.phase * 0.9) * 0.25
        message.percentage = max(0.0, 82.0 - self.phase * 0.04)
        self.battery_publisher.publish(message)

    def _enable_callback(self, message):
        self.enabled = bool(message.data)
        self.get_logger().info("Dashboard requested rover %s" % ("enabled" if self.enabled else "disabled"))
        self.publish_state()

    def _collect_sample_callback(self, _message):
        self.container_collected = True
        self.get_logger().info("Sample container collected")
        self.publish_container_state()

    def _take_reading_callback(self, _message):
        if not self.enabled:
            self.get_logger().warning("Reading request ignored while rover is disabled")
            return

        message = Float64MultiArray()
        reading_phase = self.sample_index * 0.73
        message.data = [
            6.8 + math.sin(reading_phase) * 0.18,
            42.0 + math.sin(reading_phase + 0.5) * 4.0,
            21.0 + math.sin(reading_phase + 1.1) * 1.8,
            610.0 + math.sin(reading_phase + 0.2) * 38.0,
        ]
        self.sample_publisher.publish(message)
        self.sample_index += 1
        self.get_logger().info("Published reading %d" % self.sample_index)

    def publish_state(self):
        message = Bool()
        message.data = self.enabled
        self.enabled_state_publisher.publish(message)
        self.publish_container_state()

    def publish_container_state(self):
        message = Bool()
        message.data = self.container_collected
        self.container_state_publisher.publish(message)


def main(argc: int, *argv: str) -> int:
    if rclpy is None:
        print(
            "ROS 2 is unavailable: source a ROS 2 installation before running ROSPublisher.py.",
            file=sys.stderr,
        )
        return 1

    rclpy.init(args=list(argv[1:]))
    node = SimulatedRoverPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    argv = sys.argv
    exit(main(len(argv), *argv))
