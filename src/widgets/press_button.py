from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Slot
from models import SinglePointModel

class PressButton(QPushButton):
    """A button sets a model to True when pressed and False otherwise."""
    def __init__(self, model:SinglePointModel[bool], label:str = '', parent:QWidget = None):
        """model - SinglePointModel holding a toggleable boolean value.\n
        """
        super().__init__(parent=parent)
        self._model = model
        self._model.data = False
        self.setText(label)
        self.pressed.connect(self._on_model)
        self.released.connect(self._off_model)

    @Slot()
    def _on_model(self):
        self._model.data = True

    @Slot()
    def _off_model(self):
        self._model.data = False