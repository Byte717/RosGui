import math
import os

import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets

from src.backend.ros_bridge import RosBridge, finite_or_none
from src.gui.components.NumberDisplay import NumberDisplay
from src.gui.components.graphs import MultiAxisGraphWidget
from src.gui.components.maps import MapWidget


APP_BACKGROUND = "#050505"
PANEL_BACKGROUND = "#0a0a0a"
TEXT = "#f5f5f5"
MUTED_TEXT = "#a3a3a3"
ACCENT = "#f5c542"


class StatusIndicator(QtWidgets.QFrame):
    statusRequested = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_ready = None
        self.setStyleSheet(
            """
            QFrame {
                background-color: #050505;
                border: 1px solid #262626;
                border-radius: 8px;
            }
            QLabel, QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton {
                background-color: #171717;
                border: 1px solid #404040;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #262626;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Status")
        title.setStyleSheet("color: #a3a3a3; font-size: 13px; font-weight: 700;")

        state_row = QtWidgets.QHBoxLayout()
        state_row.setSpacing(8)

        self.indicator = QtWidgets.QFrame()
        self.indicator.setFixedSize(14, 14)

        self.state_label = QtWidgets.QLabel()
        self.state_label.setStyleSheet("color: #f5f5f5; font-size: 14px; font-weight: 800;")

        state_row.addWidget(self.indicator)
        state_row.addWidget(self.state_label)
        state_row.addStretch()

        self.toggle_button = QtWidgets.QPushButton()
        self.toggle_button.clicked.connect(self.toggle_status)

        layout.addWidget(title)
        layout.addLayout(state_row)
        layout.addWidget(self.toggle_button)
        self._sync_state()

    def set_status(self, ready: bool):
        self.is_ready = ready
        self._sync_state()

    def toggle_status(self):
        desired_state = True if self.is_ready is None else not self.is_ready
        self.statusRequested.emit(desired_state)

    def _sync_state(self):
        if self.is_ready is True:
            color = "#22c55e"
            state = "READY"
            action = "Deactivate"
            button_color = "#ef4444"
        elif self.is_ready is False:
            color = "#ef4444"
            state = "DISABLED"
            action = "Activate"
            button_color = "#22c55e"
        else:
            color = "#f5c542"
            state = "NO DATA"
            action = "Enable"
            button_color = "#f5c542"

        self.indicator.setStyleSheet(
            f"background-color: {color}; border: none; border-radius: 7px;"
        )
        self.state_label.setText(state)
        self.toggle_button.setText(action)
        self.toggle_button.setStyleSheet(
            f"""
            background-color: #171717;
            border: 1px solid #404040;
            border-radius: 6px;
            color: {button_color};
            font-size: 13px;
            font-weight: 700;
            padding: 8px;
            """
        )


class Sidebar(QtWidgets.QFrame):
    expandedChanged = QtCore.pyqtSignal(bool)
    pageSelected = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.collapsed_width = 64
        self.expanded_width = 220
        self.is_expanded = False
        self.animation = QtCore.QPropertyAnimation(self, b"geometry", self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self.animation.finished.connect(self._animation_finished)
        self.setMinimumWidth(self.collapsed_width)
        self.setMaximumWidth(self.expanded_width)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {PANEL_BACKGROUND};
                border-right: 1px solid #262626;
            }}
            QPushButton {{
                border: none;
                background: transparent;
                color: {TEXT};
            }}
            QPushButton#menuButton {{
                color: {ACCENT};
                font-size: 28px;
                font-weight: 800;
                padding: 8px 0;
            }}
            QPushButton#pageButton {{
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 10px 12px;
                text-align: left;
            }}
            QPushButton#pageButton:hover {{
                background-color: #171717;
            }}
            QPushButton#activePage {{
                background-color: #171717;
                border-left: 3px solid {ACCENT};
                border-radius: 6px;
                color: {ACCENT};
                font-size: 13px;
                font-weight: 800;
                padding: 10px 12px;
                text-align: left;
            }}
            """
        )

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 14, 10, 14)
        self.layout.setSpacing(12)

        self.menu_button = QtWidgets.QPushButton("☰")
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.menu_button.clicked.connect(self.toggle_expanded)
        self.layout.addWidget(self.menu_button, alignment=QtCore.Qt.AlignTop)

        self.page_buttons = {}
        for page_name in ("General dashboard", "Data page"):
            button = QtWidgets.QPushButton(page_name)
            button.setObjectName("activePage" if page_name == "General dashboard" else "pageButton")
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.setVisible(False)
            button.clicked.connect(lambda checked=False, selected=page_name: self.select_page(selected))
            self.page_buttons[page_name] = button
            self.layout.addWidget(button)

        self.layout.addStretch()

    def toggle_expanded(self):
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded: bool):
        if self.is_expanded == expanded:
            return

        self.is_expanded = expanded
        target_width = self.expanded_width if self.is_expanded else self.collapsed_width

        if expanded:
            for button in self.page_buttons.values():
                button.setVisible(True)
            self.raise_()

        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QtCore.QRect(0, 0, target_width, self.parentWidget().height()))
        self.animation.start()
        self.expandedChanged.emit(self.is_expanded)

    def collapse(self):
        self.set_expanded(False)

    def _animation_finished(self):
        for button in self.page_buttons.values():
            button.setVisible(self.is_expanded)

    def select_page(self, page_name: str):
        self.set_active_page(page_name)
        self.pageSelected.emit(page_name)

    def set_active_page(self, page_name: str):
        for name, button in self.page_buttons.items():
            button.setObjectName("activePage" if name == page_name else "pageButton")
            button.style().unpolish(button)
            button.style().polish(button)


class HistoryOverlay(QtWidgets.QFrame):
    closed = QtCore.pyqtSignal()

    def __init__(self, title: str, unit: str, values=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.setObjectName("overlay")
        self.setStyleSheet(
            """
            QFrame#overlay {
                background-color: rgba(0, 0, 0, 150);
            }
            QFrame#card {
                background-color: #050505;
                border: 1px solid #f5c542;
                border-radius: 10px;
            }
            QLabel {
                background: transparent;
                border: none;
                color: #f5f5f5;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #f5c542;
                font-size: 20px;
                font-weight: 800;
            }
            QPushButton:hover {
                color: #ffe08a;
            }
            """
        )

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(80, 70, 80, 70)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        outer.addWidget(card)

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel(f"{title} History")
        close_button = QtWidgets.QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.closed.emit)

        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(close_button)
        layout.addLayout(header)

        self.plot = pg.PlotWidget(background="#050505")
        self.plot.showGrid(x=True, y=True, alpha=0.24)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=True, y=True)

        plot_item = self.plot.getPlotItem()
        plot_item.hideButtons()
        plot_item.setLabel("left", unit, color="#a3a3a3")
        plot_item.setLabel("bottom", "t", color="#a3a3a3")
        plot_item.getAxis("left").setTextPen("#a3a3a3")
        plot_item.getAxis("bottom").setTextPen("#a3a3a3")
        plot_item.getAxis("left").setPen("#404040")
        plot_item.getAxis("bottom").setPen("#404040")

        plot_container = QtWidgets.QWidget()
        plot_stack = QtWidgets.QStackedLayout(plot_container)
        plot_stack.setContentsMargins(0, 0, 0, 0)
        plot_stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        plot_stack.addWidget(self.plot)

        empty_label = QtWidgets.QLabel("X")
        empty_label.setAlignment(QtCore.Qt.AlignCenter)
        empty_label.setStyleSheet(
            "color: #737373; font-size: 34px; font-weight: 800; background: transparent;"
        )
        empty_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        plot_stack.addWidget(empty_label)
        self.empty_label = empty_label
        self.plot_curve = self.plot.plot(pen=pg.mkPen(ACCENT, width=2))
        self.set_values(values or [])
        layout.addWidget(plot_container, stretch=1)

    def set_values(self, values):
        valid_values = [finite_or_none(value) for value in values]
        plot_values = [value if value is not None else math.nan for value in valid_values]
        has_data = any(value is not None for value in valid_values)

        self.plot_curve.setData(
            list(range(len(plot_values))),
            plot_values,
            connect="finite",
        )
        self.empty_label.setVisible(not has_data)
        if not has_data:
            return

        finite_values = [value for value in valid_values if value is not None]
        low = min(finite_values)
        high = max(finite_values)
        if low == high:
            low -= 1
            high += 1
        self.plot.setXRange(0, max(1, len(plot_values) - 1), padding=0.05)
        self.plot.setYRange(low, high, padding=0.2)


class DataPage(QtWidgets.QWidget):
    sampleRequested = QtCore.pyqtSignal()
    readingRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.readings = {}
        self.current_reading = None
        self.current_metric = "pH"
        self.container_collected = None
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {APP_BACKGROUND};
                color: {TEXT};
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
            QFrame#panel {{
                background-color: #050505;
                border: 1px solid #262626;
                border-radius: 8px;
            }}
            QLabel#title {{
                color: {ACCENT};
                font-size: 24px;
                font-weight: 800;
            }}
            QLabel#panelTitle {{
                color: #f5f5f5;
                font-size: 15px;
                font-weight: 800;
            }}
            QLabel#muted {{
                color: #a3a3a3;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#reading {{
                color: #f5f5f5;
                font-size: 16px;
                font-weight: 800;
            }}
            QFrame#readingCard {{
                background-color: #0a0a0a;
                border: 1px solid #262626;
                border-radius: 6px;
            }}
            QLabel#readingName {{
                color: #a3a3a3;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#readingValue {{
                color: #f5f5f5;
                font-size: 18px;
                font-weight: 800;
            }}
            QListWidget, QComboBox, QTableWidget {{
                background-color: #050505;
                border: 1px solid #404040;
                border-radius: 6px;
                color: #f5f5f5;
                font-size: 13px;
                padding: 6px;
            }}
            QHeaderView::section {{
                background-color: #171717;
                border: none;
                border-right: 1px solid #404040;
                color: {ACCENT};
                font-size: 12px;
                font-weight: 800;
                padding: 8px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid #171717;
                padding: 6px;
            }}
            QTableWidget::item:selected {{
                background-color: #171717;
                color: {ACCENT};
            }}
            QListWidget::item {{
                border-radius: 4px;
                padding: 8px;
            }}
            QListWidget::item:selected {{
                background-color: #171717;
                color: {ACCENT};
            }}
            QPushButton {{
                background-color: #171717;
                border: 1px solid #404040;
                border-radius: 6px;
                color: {ACCENT};
                font-size: 13px;
                font-weight: 800;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: #262626;
                color: #ffe08a;
            }}
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("Data page")
        title.setObjectName("title")
        layout.addWidget(title)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(18)
        layout.addLayout(body, stretch=1)

        body.addWidget(self._build_reading_history_panel(), stretch=20)
        body.addWidget(self._build_graph_panel(), stretch=58)
        body.addWidget(self._build_right_column(), stretch=22)

        self._sync_current_reading()
        self._sync_container_status()
        self._sync_graph()
        self._sync_table()

    def _build_reading_history_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Reading history")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.reading_list = QtWidgets.QListWidget()
        for reading_name in self.readings:
            self.reading_list.addItem(reading_name)
        self.reading_list.setCurrentRow(0)
        self.reading_list.currentTextChanged.connect(self._reading_changed)
        layout.addWidget(self.reading_list, stretch=1)
        return panel

    def _build_graph_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Sample graph")
        title.setObjectName("panelTitle")
        self.metric_selector = QtWidgets.QComboBox()
        self.metric_selector.addItems(("pH", "Humidity", "Temperature", "CO2 Level"))
        self.metric_selector.currentTextChanged.connect(self._metric_changed)
        self.view_selector = QtWidgets.QComboBox()
        self.view_selector.addItems(("Graph", "Spreadsheet"))
        self.view_selector.currentTextChanged.connect(self._view_changed)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.view_selector)
        header.addWidget(self.metric_selector)
        layout.addLayout(header)

        self.data_view_stack = QtWidgets.QStackedWidget()

        graph_container = QtWidgets.QWidget()
        graph_stack = QtWidgets.QStackedLayout(graph_container)
        graph_stack.setContentsMargins(0, 0, 0, 0)
        graph_stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)

        self.data_plot = pg.PlotWidget(background="#050505")
        self.data_plot.showGrid(x=True, y=True, alpha=0.24)
        self.data_plot.setMenuEnabled(False)
        self.data_plot.setMouseEnabled(x=True, y=True)

        plot_item = self.data_plot.getPlotItem()
        plot_item.hideButtons()
        plot_item.setLabel("bottom", "reading", color="#a3a3a3")
        plot_item.getAxis("left").setTextPen("#a3a3a3")
        plot_item.getAxis("bottom").setTextPen("#a3a3a3")
        plot_item.getAxis("left").setPen("#404040")
        plot_item.getAxis("bottom").setPen("#404040")
        self.data_curve = self.data_plot.plot(pen=pg.mkPen(ACCENT, width=2))
        graph_stack.addWidget(self.data_plot)

        self.data_empty_label = QtWidgets.QLabel("X")
        self.data_empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.data_empty_label.setStyleSheet(
            "color: #737373; font-size: 34px; font-weight: 800; background: transparent;"
        )
        self.data_empty_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        graph_stack.addWidget(self.data_empty_label)

        self.data_table = QtWidgets.QTableWidget()
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(
            ("Reading", "pH", "Humidity", "Temperature", "CO2 Level")
        )
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.data_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.data_table.setAlternatingRowColors(False)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        self.data_view_stack.addWidget(graph_container)
        self.data_view_stack.addWidget(self.data_table)
        layout.addWidget(self.data_view_stack, stretch=1)
        return panel

    def _build_right_column(self):
        column = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_current_reading_panel(), stretch=4)
        layout.addWidget(self._build_container_status_panel(), stretch=2)
        layout.addWidget(self._build_action_panel(), stretch=3)
        layout.addStretch()
        return column

    def _build_current_reading_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Current reading data")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.reading_labels = {}
        for metric in ("pH", "Humidity", "Temperature", "CO2 Level"):
            card = QtWidgets.QFrame()
            card.setObjectName("readingCard")
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)

            name = QtWidgets.QLabel(metric)
            name.setObjectName("readingName")

            value = QtWidgets.QLabel()
            value.setObjectName("readingValue")

            card_layout.addWidget(name)
            card_layout.addWidget(value)
            self.reading_labels[metric] = value
            layout.addWidget(card)
        layout.addStretch()
        return panel

    def _build_container_status_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.container_light = QtWidgets.QFrame()
        self.container_light.setFixedSize(16, 16)
        self.container_light.setStyleSheet("background-color: #f5c542; border-radius: 8px;")

        title = QtWidgets.QLabel("Container status")
        title.setObjectName("panelTitle")
        self.container_status_label = QtWidgets.QLabel()
        self.container_status_label.setObjectName("muted")

        layout.addWidget(self.container_light)
        layout.addWidget(title)
        layout.addWidget(self.container_status_label)
        layout.addStretch()
        return panel

    def _build_action_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Sample controls")
        title.setObjectName("panelTitle")
        self.collect_button = QtWidgets.QPushButton("Collect sample")
        self.collect_button.clicked.connect(self.collect_sample)
        self.reading_button = QtWidgets.QPushButton("Take reading")
        self.reading_button.clicked.connect(self.take_reading)

        layout.addWidget(title)
        layout.addWidget(self.collect_button)
        layout.addWidget(self.reading_button)
        layout.addStretch()
        return panel

    def collect_sample(self):
        self.sampleRequested.emit()

    def take_reading(self):
        self.readingRequested.emit()

    def add_remote_reading(self, reading):
        reading_name = f"Reading {len(self.readings) + 1}"
        self.readings[reading_name] = {
            metric: finite_or_none(reading.get(metric))
            for metric in ("pH", "Humidity", "Temperature", "CO2 Level")
        }
        self.reading_list.addItem(reading_name)
        self.reading_list.setCurrentRow(self.reading_list.count() - 1)
        self._sync_current_reading()
        self._sync_graph()
        self._sync_table()

    def set_container_status(self, collected):
        self.container_collected = None if collected is None else bool(collected)
        self._sync_container_status()

    def _reading_changed(self, reading_name):
        if reading_name:
            self.current_reading = reading_name
            self._sync_current_reading()
            self._sync_graph()

    def _metric_changed(self, metric_name):
        self.current_metric = metric_name
        self._sync_graph()

    def _view_changed(self, view_name):
        self.data_view_stack.setCurrentIndex(1 if view_name == "Spreadsheet" else 0)

    def _sync_current_reading(self):
        reading = self.readings.get(self.current_reading, {})
        units = {
            "pH": "",
            "Humidity": "%",
            "Temperature": "°C",
            "CO2 Level": "ppm",
        }
        for metric, label in self.reading_labels.items():
            value = reading.get(metric)
            unit = units[metric]
            if value is None:
                label.setText("NAN")
            else:
                label.setText(f"{value:.1f}{unit}" if unit else f"{value:.2f}")

    def _sync_container_status(self):
        if self.container_collected is True:
            color = "#22c55e"
            text = "Collected"
        elif self.container_collected is False:
            color = ACCENT
            text = "Ready"
        else:
            color = ACCENT
            text = "NAN"
        self.container_light.setStyleSheet(f"background-color: {color}; border-radius: 8px;")
        self.container_status_label.setText(text)

    def _sync_table(self):
        self.data_table.setRowCount(len(self.readings))
        for row, (reading_name, reading) in enumerate(self.readings.items()):
            row_values = [
                reading_name,
                self._format_metric(reading.get("pH"), ""),
                self._format_metric(reading.get("Humidity"), "%"),
                self._format_metric(reading.get("Temperature"), "°C"),
                self._format_metric(reading.get("CO2 Level"), "ppm"),
            ]
            for column, value in enumerate(row_values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.data_table.setItem(row, column, item)

    def _sync_graph(self):
        reading_names = list(self.readings.keys())
        values = [
            self.readings[reading_name].get(self.current_metric)
            for reading_name in reading_names
        ]
        x_values = list(range(1, len(values) + 1))
        plot_values = [value if value is not None else math.nan for value in values]
        self.data_curve.setData(
            x_values,
            plot_values,
            connect="finite",
            symbol="o",
            symbolSize=8,
            symbolBrush=ACCENT,
        )
        has_data = any(value is not None for value in values)
        self.data_empty_label.setVisible(not has_data)
        plot_item = self.data_plot.getPlotItem()
        plot_item.setLabel("left", self.current_metric, color="#a3a3a3")
        plot_item.getAxis("bottom").setTicks(
            [[(index + 1, reading_name) for index, reading_name in enumerate(reading_names)]]
        )
        if has_data:
            finite_values = [value for value in values if value is not None]
            low = min(finite_values)
            high = max(finite_values)
            if low == high:
                low -= 1
                high += 1
            self.data_plot.setXRange(0.75, len(values) + 0.25, padding=0)
            self.data_plot.setYRange(low, high, padding=0.2)

    def _format_metric(self, value, unit):
        if value is None:
            return "NAN"
        if unit == "":
            return f"{value:.2f}"
        return f"{value:.1f}{unit}"


class RosDashboard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ROS GUI")
        self.resize(1500, 900)
        self.setMinimumSize(1000, 650)

        root = QtWidgets.QWidget()
        root.setStyleSheet(f"background-color: {APP_BACKGROUND};")
        self.setCentralWidget(root)
        self.root = root
        self.history_overlay = None
        self.sidebar_open = False

        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.app_body = QtWidgets.QWidget()
        root_layout.addWidget(self.app_body)

        self.stack = QtWidgets.QStackedWidget()
        self.pages = {}
        content = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(self.app_body)
        body_layout.setContentsMargins(64, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.stack)
        self.stack.addWidget(content)
        self.pages["General dashboard"] = content

        self.sidebar = Sidebar(root)
        self.sidebar.expandedChanged.connect(self._sidebar_expanded_changed)
        self.sidebar.pageSelected.connect(self.show_page)
        self.sidebar.setGeometry(0, 0, self.sidebar.collapsed_width, root.height())
        self.sidebar.raise_()

        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        page_title = QtWidgets.QLabel("General dashboard")
        page_title.setStyleSheet(f"color: {ACCENT}; font-size: 24px; font-weight: 800;")
        header.addWidget(page_title)
        header.addStretch()
        self.ros_status_label = QtWidgets.QLabel("ROS 2: STARTING")
        self.ros_status_label.setStyleSheet(
            "color: #f5c542; font-size: 12px; font-weight: 800;"
        )
        header.addWidget(self.ros_status_label)
        content_layout.addLayout(header)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(18)
        content_layout.addLayout(top_row, stretch=58)

        self.map_widget = MapWidget()
        top_row.addWidget(self.map_widget, stretch=48)

        self.accelerometer_graph = MultiAxisGraphWidget(
            "Accelerometer",
            axis_labels=("x", "y", "z"),
        )
        top_row.addWidget(self.accelerometer_graph, stretch=36)

        metrics = QtWidgets.QVBoxLayout()
        metrics.setSpacing(14)
        top_row.addLayout(metrics, stretch=16)

        self.voltage_display = NumberDisplay("Voltage", "V")
        self.voltage_display.historyRequested.connect(
            lambda _label: self.show_history_overlay("Voltage", "V")
        )
        self.voltage_display.valueChanged.connect(
            lambda _value: self._update_history_overlay("Voltage")
        )

        self.current_display = NumberDisplay("Current Draw", "A")
        self.current_display.historyRequested.connect(
            lambda _label: self.show_history_overlay("Current Draw", "A")
        )
        self.current_display.valueChanged.connect(
            lambda _value: self._update_history_overlay("Current Draw")
        )

        self.status_indicator = StatusIndicator()

        metrics.addWidget(self.voltage_display)
        metrics.addWidget(self.current_display)
        metrics.addWidget(self.status_indicator)
        metrics.addStretch()

        self.gyroscope_graph = MultiAxisGraphWidget(
            "Gyroscope",
            axis_labels=("roll", "pitch", "yaw"),
        )
        content_layout.addWidget(self.gyroscope_graph, stretch=42)

        self.data_page = DataPage()
        self.stack.addWidget(self.data_page)
        self.pages["Data page"] = self.data_page

        self.ros_thread = QtCore.QThread(self)
        self.ros_bridge = RosBridge()
        self.ros_bridge.moveToThread(self.ros_thread)
        self.ros_thread.started.connect(self.ros_bridge.start)

        self.status_indicator.statusRequested.connect(self.ros_bridge.publish_enabled)
        self.data_page.sampleRequested.connect(self.ros_bridge.publish_collect_sample)
        self.data_page.readingRequested.connect(self.ros_bridge.publish_take_reading)

        self.ros_bridge.gps_updated.connect(self._on_gps_updated)
        self.ros_bridge.imu_updated.connect(self._on_imu_updated)
        self.ros_bridge.battery_updated.connect(self._on_battery_updated)
        self.ros_bridge.sample_updated.connect(self._on_sample_updated)
        self.ros_bridge.enabled_updated.connect(self.status_indicator.set_status)
        self.ros_bridge.container_updated.connect(self.data_page.set_container_status)
        self.ros_bridge.connection_changed.connect(self._on_ros_connection_changed)
        self.ros_bridge.bridge_error.connect(self._on_ros_error)
        self.ros_thread.start()

    def _on_gps_updated(self, location):
        if not location.get("valid"):
            self.map_widget.clear_location()
            return

        latitude = location.get("latitude")
        longitude = location.get("longitude")
        self.map_widget.set_location(latitude, longitude, "Rover")
        self.map_widget.add_path_point(latitude, longitude)

    def _on_imu_updated(self, values):
        accel = values.get("accel", {})
        gyro = values.get("gyro", {})
        accel_values = (accel.get("x"), accel.get("y"), accel.get("z"))
        gyro_values = (gyro.get("roll"), gyro.get("pitch"), gyro.get("yaw"))

        if any(value is not None for value in accel_values):
            self.accelerometer_graph.add_sample(*accel_values)
            self.accelerometer_graph.set_live_available(True)
        else:
            self.accelerometer_graph.set_live_available(False)

        if any(value is not None for value in gyro_values):
            self.gyroscope_graph.add_sample(*gyro_values)
            self.gyroscope_graph.set_live_available(True)
        else:
            self.gyroscope_graph.set_live_available(False)

    def _on_battery_updated(self, values):
        self.voltage_display.setValue(values.get("voltage"))
        self.current_display.setValue(values.get("current"))

    def _update_history_overlay(self, title):
        if self.history_overlay is None or self.history_overlay.title != title:
            return

        display = {
            "Voltage": self.voltage_display,
            "Current Draw": self.current_display,
        }.get(title)
        if display is not None:
            self.history_overlay.set_values(display.get_history())

    def _on_sample_updated(self, reading):
        self.data_page.add_remote_reading(reading)

    def _on_ros_connection_changed(self, connected, message):
        color = "#22c55e" if connected else "#f5c542"
        self.ros_status_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 800;"
        )
        self.ros_status_label.setText(f"ROS 2: {message}")
        self.ros_status_label.setToolTip(message)

    def _on_ros_error(self, message):
        self.ros_status_label.setToolTip(message)

    def show_page(self, page_name: str):
        page = self.pages.get(page_name)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active_page(page_name)
        self.sidebar.collapse()

    def show_history_overlay(self, title: str, unit: str):
        if self.history_overlay is not None:
            self.hide_history_overlay()

        display = {
            "Voltage": self.voltage_display,
            "Current Draw": self.current_display,
        }.get(title)
        values = display.get_history() if display is not None else []
        self.history_overlay = HistoryOverlay(title, unit, values, self.root)
        self.history_overlay.closed.connect(self.hide_history_overlay)
        self.history_overlay.setGeometry(self.root.rect())
        self.history_overlay.show()
        self.history_overlay.raise_()
        self._sync_page_blur()

    def hide_history_overlay(self):
        if self.history_overlay is not None:
            self.history_overlay.deleteLater()
            self.history_overlay = None
        self._sync_page_blur()

    def _sidebar_expanded_changed(self, expanded: bool):
        self.sidebar_open = expanded
        self._sync_page_blur()

    def _sync_page_blur(self):
        if self.history_overlay is not None:
            radius = 8
        elif self.sidebar_open:
            radius = 3
        else:
            radius = 0

        if radius:
            blur = QtWidgets.QGraphicsBlurEffect()
            blur.setBlurRadius(radius)
            self.app_body.setGraphicsEffect(blur)
        else:
            self.app_body.setGraphicsEffect(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            width = self.sidebar.expanded_width if self.sidebar.is_expanded else self.sidebar.collapsed_width
            self.sidebar.setGeometry(0, 0, width, self.root.height())
        if self.history_overlay is not None:
            self.history_overlay.setGeometry(self.root.rect())

    def closeEvent(self, event):
        if hasattr(self, "ros_thread") and self.ros_thread.isRunning():
            QtCore.QMetaObject.invokeMethod(
                self.ros_bridge,
                "shutdown",
                QtCore.Qt.QueuedConnection,
            )
            self.ros_thread.wait(2000)
            if self.ros_thread.isRunning():
                self.ros_thread.quit()
                self.ros_thread.wait(1000)
        super().closeEvent(event)


def main(argc: int, *argv: str) -> int:
    # QtWebEngine can fail to create its GPU process under WSLg even when the
    # widget itself is installed.  Keep the fallback limited to WSL and allow
    # an explicit user value to take precedence.
    if os.environ.get("WSL_DISTRO_NAME"):
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

    app = QtWidgets.QApplication(list(argv))
    app.setFont(QtGui.QFont("Arial"))
    window = RosDashboard()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    argv = __import__("sys").argv
    exit(main(len(argv), *argv))
