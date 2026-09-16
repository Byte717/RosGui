
## Sensor data

- `/rover/gps/fix` (`sensor_msgs/msg/NavSatFix`) — GPS position
- `/rover/imu/data` (`sensor_msgs/msg/Imu`) — acceleration and gyro
- `/rover/battery` (`sensor_msgs/msg/BatteryState`) — voltage and current
- `/rover/sample/data` (`std_msgs/msg/Float64MultiArray`) — pH, humidity, temperature, and CO₂

- `/rover/cmd/enable` (`std_msgs/msg/Bool`) — enable or disable the rover
- `/rover/state/enabled` (`std_msgs/msg/Bool`) — enabled-state feedback
- `/rover/cmd/collect_sample` (`std_msgs/msg/Empty`) — collect a sample
- `/rover/state/container_collected` (`std_msgs/msg/Bool`) — sample container status
- `/rover/cmd/take_reading` (`std_msgs/msg/Empty`) — take a reading


When sensor data is missing, the GUI shows `NAN`. Empty graphs show `X`.
