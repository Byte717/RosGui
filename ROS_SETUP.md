# ROS 2 setup

The easiest way to run this project is on Ubuntu 24.04 with ROS 2 Jazzy.
Install ROS 2 by following the [official instructions](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html), then run:

```bash
source /opt/ros/jazzy/setup.bash
sudo apt install python3-pip python3-venv
```

From the project folder, install the GUI packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Open two terminals. In both terminals, source ROS first:

```bash
source /opt/ros/jazzy/setup.bash
```

In the first terminal, start the simulated rover:

```bash
python3 ROSPublisher.py
```

In the second terminal, start the GUI:

```bash
source .venv/bin/activate
python3 main.py
```

The GUI and publisher use the same ROS 2 topics listed in
`ROS_INTERFACE.md`. You can check that they are connected with:

```bash
ros2 topic list
```

On macOS, native ROS 2 installation is more complicated. Running Ubuntu in a
VM or Docker and starting both Python files there is recommended.
