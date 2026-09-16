"""Small ROS 2 companion node for exercising the dashboard.

The dashboard does not depend on this file at runtime.  It is a deterministic
sensor simulator that publishes rover telemetry at ``Constants.UPDATE_INTERVAL``
and responds to the dashboard's enable, collect-sample, and take-reading
commands.
"""

import math
import random
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
        self.elapsed_seconds = 0.0
        self.random = random.Random(2026)

        # Motion is a bounded random walk instead of a repeated waveform.
        self.origin_latitude = 42.3601
        self.origin_longitude = -71.0589
        self.north_meters = 0.0
        self.east_meters = 0.0
        self.heading = 0.0
        self.speed_mps = 0.25

        # These values drift slowly and get measurement noise on every update.
        self.acceleration_drift = [0.0, 0.0, 0.0]
        self.gyro_drift = [0.0, 0.0, 0.0]
        self.battery_soc = 0.86
        self.battery_current = 1.4
        self.sample_values = [6.8, 45.0, 21.5, 650.0]

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

        self.elapsed_seconds += PUBLISH_PERIOD_SECONDS
        self._update_motion()
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
        message.latitude = self.origin_latitude + (
            self.north_meters + self.random.gauss(0.0, 1.2)
        ) / 111111.0
        message.longitude = self.origin_longitude + (
            self.east_meters + self.random.gauss(0.0, 1.2)
        ) / 111111.0
        message.altitude = 12.0 + self.random.gauss(0.0, 0.15)
        self.gps_publisher.publish(message)

    def _publish_imu(self, stamp):
        message = Imu()
        message.header.stamp = stamp
        message.header.frame_id = "imu_link"
        for index in range(3):
            self.acceleration_drift[index] = self._bounded_walk(
                self.acceleration_drift[index],
                0.025,
                -0.35,
                0.35,
            )
            self.gyro_drift[index] = self._bounded_walk(
                self.gyro_drift[index],
                0.012,
                -0.16,
                0.16,
            )

        message.linear_acceleration.x = self.acceleration_drift[0] + self.random.gauss(0.0, 0.035)
        message.linear_acceleration.y = self.acceleration_drift[1] + self.random.gauss(0.0, 0.035)
        message.linear_acceleration.z = 9.81 + self.acceleration_drift[2] + self.random.gauss(0.0, 0.025)
        message.angular_velocity.x = self.gyro_drift[0] + self.random.gauss(0.0, 0.012)
        message.angular_velocity.y = self.gyro_drift[1] + self.random.gauss(0.0, 0.012)
        message.angular_velocity.z = self.gyro_drift[2] + self.random.gauss(0.0, 0.012)
        self.imu_publisher.publish(message)

    def _publish_battery(self, stamp):
        message = BatteryState()
        message.header.stamp = stamp
        self.battery_current = self._bounded_walk(
            self.battery_current,
            0.08,
            0.8,
            2.4,
        )
        self.battery_soc = max(
            0.0,
            self.battery_soc
            - self.battery_current * PUBLISH_PERIOD_SECONDS / (10.0 * 3600.0),
        )

        # Open-circuit voltage follows a curved state-of-charge response. The
        # current-dependent sag and sensor noise keep it from being linear.
        open_circuit_voltage = 10.55 + 2.25 * (self.battery_soc ** 0.55)
        voltage_sag = self.battery_current * 0.11
        message.voltage = max(
            10.2,
            open_circuit_voltage - voltage_sag + self.random.gauss(0.0, 0.025),
        )
        message.current = self.battery_current + self.random.gauss(0.0, 0.035)
        message.percentage = self.battery_soc * 100.0
        self.battery_publisher.publish(message)

    def _update_motion(self):
        self.speed_mps = self._bounded_walk(self.speed_mps, 0.035, 0.05, 0.6)
        self.heading += self.random.gauss(0.0, 0.10)
        distance = self.speed_mps * PUBLISH_PERIOD_SECONDS
        self.north_meters += math.cos(self.heading) * distance + self.random.gauss(0.0, 0.02)
        self.east_meters += math.sin(self.heading) * distance + self.random.gauss(0.0, 0.02)

    def _bounded_walk(self, value, step, minimum, maximum):
        return min(maximum, max(minimum, value + self.random.gauss(0.0, step)))

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
        sample_limits = (
            (6.3, 7.4, 0.025, 0.015),
            (20.0, 85.0, 0.8, 0.35),
            (5.0, 38.0, 0.35, 0.15),
            (350.0, 1800.0, 25.0, 12.0),
        )
        for index, (minimum, maximum, walk_step, noise) in enumerate(sample_limits):
            self.sample_values[index] = self._bounded_walk(
                self.sample_values[index],
                walk_step,
                minimum,
                maximum,
            )
        message.data = [
            value + self.random.gauss(0.0, noise)
            for value, (_minimum, _maximum, _walk_step, noise) in zip(
                self.sample_values,
                sample_limits,
            )
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
