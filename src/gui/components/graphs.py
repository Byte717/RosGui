import math

import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets


class MultiAxisGraphWidget(QtWidgets.QFrame):
    def __init__(self, title: str, axis_labels=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.axis_labels = axis_labels or ("X", "Y", "Z")
        self.series = {
            axis: [] for axis in self.axis_labels
        }
        self.times = {
            axis: list(range(len(values)))
            for axis, values in self.series.items()
        }
        self.curves = {}
        self.plots = {}
        self.hover_lines = {}
        self.hover_points = {}
        self.hover_labels = {}
        self.hover_proxies = []
        self.reset_buttons = {}
        self.empty_labels = {}
        self.sample_index = 0
        self.live_available = False

        self.setMinimumSize(360, 230)
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
                color: #f5f5f5;
                font-size: 14px;
                font-weight: 700;
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

        pg.setConfigOptions(antialias=True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        title_label = QtWidgets.QLabel(title)
        layout.addWidget(title_label)

        self._build_plots(layout)

    def set_series(self, axis: str, values, times=None):
        if axis not in self.series:
            raise ValueError(f"Unknown axis: {axis}")
        self.series[axis] = [self._normalize_value(value) for value in values]
        self.times[axis] = self._normalize_times(self.series[axis], times)
        if any(value is not None for value in self.series[axis]):
            self.live_available = True
        self._redraw_axis(axis)

    def set_all_series(self, x_values, y_values, z_values, times=None):
        for axis, values in zip(self.axis_labels, (x_values, y_values, z_values)):
            self.series[axis] = [self._normalize_value(value) for value in values]
            self.times[axis] = self._normalize_times(self.series[axis], times)
        self.live_available = any(
            value is not None
            for axis in self.axis_labels
            for value in self.series[axis]
        )
        self._redraw_all()

    def set_live_available(self, available: bool):
        self.live_available = bool(available)
        for axis in self.axis_labels:
            self._sync_axis_availability(axis)

    def add_sample(
        self,
        x_value: float,
        y_value: float,
        z_value: float,
        max_points: int = 120,
        t=None,
    ):
        time_value = self.sample_index if t is None else t
        for axis, value in zip(self.axis_labels, (x_value, y_value, z_value)):
            values = self.series[axis]
            values.append(self._normalize_value(value))
            if len(values) > max_points:
                del values[0 : len(values) - max_points]

            times = self.times[axis]
            times.append(time_value)
            if len(times) > max_points:
                del times[0 : len(times) - max_points]

        self.sample_index += 1
        self.live_available = any(
            value is not None for value in (x_value, y_value, z_value)
        )
        self._redraw_all()

    def _build_plots(self, layout):
        pens = {
            self.axis_labels[0]: pg.mkPen("#ff5252", width=2),
            self.axis_labels[1]: pg.mkPen("#40c463", width=2),
            self.axis_labels[2]: pg.mkPen("#4f8cff", width=2),
        }

        linked_plot = None
        for index, axis in enumerate(self.axis_labels):
            axis_panel = QtWidgets.QWidget()
            axis_layout = QtWidgets.QVBoxLayout(axis_panel)
            axis_layout.setContentsMargins(0, 0, 0, 0)
            axis_layout.setSpacing(2)

            axis_header = QtWidgets.QHBoxLayout()
            axis_header.setContentsMargins(0, 0, 0, 0)
            axis_header.setSpacing(8)

            axis_label = QtWidgets.QLabel(axis)
            reset_button = QtWidgets.QPushButton("⟲")
            reset_button.setFixedSize(24, 22)
            reset_button.setToolTip(f"Reset {axis} graph view")
            reset_button.clicked.connect(lambda checked=False, selected_axis=axis: self._reset_axis_view(selected_axis))

            axis_header.addWidget(axis_label)
            axis_header.addStretch()
            axis_header.addWidget(reset_button)
            axis_layout.addLayout(axis_header)

            plot_container = QtWidgets.QWidget()
            plot_stack = QtWidgets.QStackedLayout(plot_container)
            plot_stack.setContentsMargins(0, 0, 0, 0)
            plot_stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)

            plot = pg.PlotWidget(background="#050505")
            plot.showGrid(x=True, y=True, alpha=0.24)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=True, y=True)
            plot.viewport().installEventFilter(self)

            plot_item = plot.getPlotItem()
            plot_item.hideButtons()
            plot_item.setLabel("left", axis, color="#a3a3a3")
            plot_item.getAxis("left").setTextPen("#a3a3a3")
            plot_item.getAxis("bottom").setTextPen("#a3a3a3")
            plot_item.getAxis("left").setPen("#404040")
            plot_item.getAxis("bottom").setPen("#404040")

            if index == len(self.axis_labels) - 1:
                plot_item.setLabel("bottom", "t", color="#a3a3a3")
            else:
                plot_item.hideAxis("bottom")

            if linked_plot is None:
                linked_plot = plot
            else:
                plot.setXLink(linked_plot)

            self.plots[axis] = plot
            self.curves[axis] = plot.plot(
                self.times[axis],
                self.series[axis],
                pen=pens[axis],
            )
            self.reset_buttons[axis] = reset_button
            self._add_hover_items(axis, plot, pens[axis])
            proxy = pg.SignalProxy(
                plot.scene().sigMouseMoved,
                rateLimit=60,
                slot=lambda event, source_axis=axis: self._handle_mouse_move(source_axis, event),
            )
            self.hover_proxies.append(proxy)
            empty_label = QtWidgets.QLabel("X")
            empty_label.setAlignment(QtCore.Qt.AlignCenter)
            empty_label.setStyleSheet(
                "color: #737373; font-size: 34px; font-weight: 800; background: transparent;"
            )
            empty_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self.empty_labels[axis] = empty_label
            plot_stack.addWidget(plot)
            plot_stack.addWidget(empty_label)
            axis_layout.addWidget(plot_container, stretch=1)
            layout.addWidget(axis_panel, stretch=1)

        self._reset_all_views()

    def _redraw_axis(self, axis):
        self.curves[axis].setData(
            self.times[axis],
            self._plot_values(self.series[axis]),
            connect="finite",
        )
        self._sync_axis_availability(axis)

    def _redraw_all(self):
        for axis in self.axis_labels:
            self._redraw_axis(axis)

    def _normalize_times(self, values, times):
        if times is None:
            return list(range(len(values)))

        normalized = [float(value) for value in times]
        if len(normalized) != len(values):
            raise ValueError("times must have the same length as values")
        return normalized

    def _normalize_value(self, value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None
        return numeric_value if math.isfinite(numeric_value) else None

    def _plot_values(self, values):
        return [value if value is not None else math.nan for value in values]

    def _sync_axis_availability(self, axis):
        has_data = any(value is not None for value in self.series[axis])
        self.empty_labels[axis].setVisible(not has_data or not self.live_available)

    def _add_hover_items(self, axis, plot, pen):
        cursor_pen = pg.mkPen("#f5c542", width=1, style=QtCore.Qt.DashLine)
        line = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
        line.setVisible(False)
        plot.addItem(line, ignoreBounds=True)

        point = pg.ScatterPlotItem(
            size=8,
            brush=pg.mkBrush(pen.color()),
            pen=pg.mkPen("#f5f5f5", width=1),
        )
        point.setVisible(False)
        plot.addItem(point)

        label = pg.TextItem(
            color="#f5f5f5",
            anchor=(0, 1),
            fill=pg.mkBrush(23, 23, 23, 230),
            border=pg.mkPen("#525252"),
        )
        label.setVisible(False)
        plot.addItem(label, ignoreBounds=True)

        self.hover_lines[axis] = line
        self.hover_points[axis] = point
        self.hover_labels[axis] = label

    def _handle_mouse_move(self, source_axis, event):
        position = event[0]
        plot_item = self.plots[source_axis].getPlotItem()
        if not plot_item.sceneBoundingRect().contains(position):
            return

        mouse_point = plot_item.vb.mapSceneToView(position)
        nearest = self._nearest_point(source_axis, mouse_point.x())
        if nearest is None:
            return

        nearest_time, _ = nearest
        self._show_hover_at(nearest_time)

    def _show_hover_at(self, time_value):
        for axis in self.axis_labels:
            nearest = self._nearest_point(axis, time_value)
            if nearest is None:
                continue

            x_value, y_value = nearest
            self.hover_lines[axis].setValue(x_value)
            self.hover_lines[axis].setVisible(True)

            self.hover_points[axis].setData([x_value], [y_value])
            self.hover_points[axis].setVisible(True)

            self.hover_labels[axis].setText(f"t={x_value:g}  {axis}={y_value:.3f}")
            self.hover_labels[axis].setPos(x_value, y_value)
            self.hover_labels[axis].setVisible(True)

    def _hide_hover(self):
        for axis in self.axis_labels:
            self.hover_lines[axis].setVisible(False)
            self.hover_points[axis].setVisible(False)
            self.hover_labels[axis].setVisible(False)

    def _nearest_point(self, axis, time_value):
        times = self.times[axis]
        values = self.series[axis]
        valid_indices = [index for index, value in enumerate(values) if value is not None]
        if not times or not valid_indices:
            return None

        nearest_index = min(
            valid_indices,
            key=lambda index: abs(times[index] - time_value),
        )

        return times[nearest_index], values[nearest_index]

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Leave:
            self._hide_hover()
        return super().eventFilter(watched, event)

    def _reset_axis_view(self, axis):
        x_range = self._x_data_range()
        y_range = self._y_data_range(axis)
        if x_range is not None:
            self.plots[axis].setXRange(*x_range, padding=0.02)
        if y_range is not None:
            self.plots[axis].setYRange(*y_range, padding=0.12)

    def _reset_all_views(self):
        for axis in self.axis_labels:
            self._reset_axis_view(axis)

    def _x_data_range(self):
        all_times = [time for axis in self.axis_labels for time in self.times[axis]]
        if not all_times:
            return None
        start = min(all_times)
        end = max(all_times)
        if start == end:
            return start - 1, end + 1
        return start, end

    def _y_data_range(self, axis):
        values = [value for value in self.series[axis] if value is not None]
        if not values:
            return None
        bottom = min(values)
        top = max(values)
        if bottom == top:
            return bottom - 1, top + 1
        return bottom, top
