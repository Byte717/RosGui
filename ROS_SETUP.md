# ROS 2 setup

The easiest way to run this project is on Ubuntu 22.04 with ROS 2 Humble.
Install ROS 2 by following the [official instructions](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html), then run:

```bash
source /opt/ros/humble/setup.bash
sudo apt install python3-pip
```

From the project folder, install the GUI packages:

```bash
python3 -m pip install --user -r requirements.txt
```

Open two terminals. In both terminals, source ROS first:

```bash
source /opt/ros/humble/setup.bash
```

In the first terminal, start the simulated rover:

```bash
python3 ROSPublisher.py
```

In the second terminal, start the GUI:

```bash
python3 main.py
```

The route map is drawn directly by PyQt5, so PyQtWebEngine is not required.
It loads the visible OpenStreetMap tiles over HTTPS and caches them locally.
The GPS route continues to render if the tile service is temporarily unreachable.
For a private or self-hosted tile service, set a compatible URL template before
starting the GUI:

```bash
export ROSGUI_TILE_URL="https://maps.example.com/{z}/{x}/{y}.png"
python3 main.py
```

The GUI and publisher use the same ROS 2 topics listed in
`ROS_INTERFACE.md`. You can check that they are connected with:

```bash
ros2 topic list
```

On macOS, native ROS 2 installation is more complicated. Running Ubuntu in a
VM or Docker and starting both Python files there is recommended.
