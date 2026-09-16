import math

from PyQt5 import QtCore, QtWidgets


class NumberDisplay(QtWidgets.QFrame):
    historyRequested = QtCore.pyqtSignal(str)
    valueChanged = QtCore.pyqtSignal(object)

    def __init__(self, displayText: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.value = None
        self.history = []
        self.displayText = displayText
        self.unit = unit
        self.setMinimumSize(160, 96)
        self.setStyleSheet(
            """
            QFrame {
                background-color: #050505;
                border: 1px solid #262626;
                border-radius: 8px;
            }
            QLabel, QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton {
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

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)

        self.title_label = QtWidgets.QLabel(displayText)
        self.title_label.setStyleSheet("color: #a3a3a3; font-size: 13px; font-weight: 700;")
        self.title_label.setAlignment(QtCore.Qt.AlignLeft)

        self.history_button = QtWidgets.QPushButton("↗")
        self.history_button.setFixedSize(24, 24)
        self.history_button.setToolTip(f"Show {displayText.lower()} history")
        self.history_button.clicked.connect(lambda: self.historyRequested.emit(self.displayText))

        self.value_label = QtWidgets.QLabel()
        self.value_label.setStyleSheet("color: #f5f5f5; font-size: 28px; font-weight: 800;")
        self.value_label.setAlignment(QtCore.Qt.AlignLeft)

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.history_button)

        layout.addLayout(header)
        layout.addStretch()
        layout.addWidget(self.value_label)
        self._sync_text()

    def setValue(self, value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = None

        self.value = numeric_value if numeric_value is not None and math.isfinite(numeric_value) else None
        if self.value is not None:
            self.history.append(self.value)
            if len(self.history) > 600:
                del self.history[:-600]
        self.valueChanged.emit(self.value)
        self._sync_text()

    def get_history(self):
        return list(self.history)

    def _sync_text(self):
        if self.value is None:
            self.value_label.setText("NAN")
        else:
            self.value_label.setText(f"{self.value:.2f} {self.unit}".strip())
