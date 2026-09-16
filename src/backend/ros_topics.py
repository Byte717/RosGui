"""ROS 2 topic names shared by the dashboard and its companion node."""

GPS_TOPIC = "/rover/gps/fix"
IMU_TOPIC = "/rover/imu/data"
BATTERY_TOPIC = "/rover/battery"
SAMPLE_DATA_TOPIC = "/rover/sample/data"

ENABLE_COMMAND_TOPIC = "/rover/cmd/enable"
ENABLE_STATE_TOPIC = "/rover/state/enabled"
COLLECT_SAMPLE_COMMAND_TOPIC = "/rover/cmd/collect_sample"
CONTAINER_STATE_TOPIC = "/rover/state/container_collected"
TAKE_READING_COMMAND_TOPIC = "/rover/cmd/take_reading"

# Commands are user actions, so keep a deeper queue than the sensor streams.
COMMAND_QUEUE_DEPTH = 100

# A sensor stream that has not produced a message for this long is treated as
# unavailable by the GUI.  The value is deliberately independent of the UI's
# repaint interval.
SENSOR_TIMEOUT_SECONDS = 2.0
