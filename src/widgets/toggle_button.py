from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Slot
from models import SinglePointModel
from enum import Enum

class ControlMode(Enum):
    VOLTAGE = True
    CURRENT = False

class MonitorMode(Enum):
    ON = True
    OFF = False

class VoltageRelative(Enum):
    OCV = True
    ZERO_V = False


class ToggleButton(QPushButton):
    """A button that changes the value of a boolean SinglePointModel"""
    def __init__(self, model:SinglePointModel[bool], true_label:str = 'True', false_label:str = 'False', parent:QWidget = None):
        """model - SinglePointModel holding a toggleable boolean value.\n
        true_label - Text to be shown on button when model is True.\n
        false_label - Text to be shown on  button when model is False.
        """
        super().__init__(parent=parent)
        self._model = model
        self._true_label = true_label
        self._false_label = false_label
        self._model.data_changed.connect(self._update_display)
        self.clicked.connect(self._toggle_model)
        self._update_display()

    @Slot()
    def _toggle_model(self):
        if type(self._model.data) == MonitorMode:
            if self._model.data.value:
                 self._model.data = MonitorMode.OFF
            else:
                self._model.data = MonitorMode.ON
        elif type(self._model.data) == ControlMode:
            if self._model.data.value:
                 self._model.data = ControlMode.CURRENT
            else:
                self._model.data = ControlMode.VOLTAGE
        elif type(self._model.data) == VoltageRelative:
            if self._model.data.value:
                 self._model.data = VoltageRelative.ZERO_V
            else:
                self._model.data = VoltageRelative.OCV
        elif type(self._model.data) == bool:
            self._model.data = not self._model.data

    @Slot()
    def _update_display(self):
        if type(self._model.data) != bool:
            if self._model.data.value:
                self.setText(self._true_label)
            else:
                self.setText(self._false_label)
        else:
            if self._model.data:
                self.setText(self._true_label)
            else:
                self.setText(self._false_label)