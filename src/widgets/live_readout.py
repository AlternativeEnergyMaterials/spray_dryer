from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Slot
from models import ListModel, SinglePointModel

class LiveReadout(QLabel):
    """A QLabel that reads a live numerical value from a connected model."""
    def __init__(self, model:ListModel[float|int|str]|SinglePointModel[float|int|str], prefix:str = '', suffix:str = '', parent:QWidget = None):
        """model - ListModel or SinglePointModel to be read out. ListModels will read the tail value.\n
        prefix - String to be displayed before the model value.\n
        suffix - String to be displayed after the model value.
        """
        super().__init__(parent=parent)
        self._model = model
        self._prefix = prefix
        self._suffix = suffix
        self._model.data_changed.connect(self._update_text)
        self._update_text()

    @Slot()
    def _update_text(self):
        if type(self._model) == ListModel:
            value = self._model[-1] if len(self._model) > 0 else None
        else:
            value = self._model.data

        if value is not None and type(value) is not str:
            #Parse value into a string. Limit to 4 decimal places.
            value = str(value).split('.')
            if len(value) == 2:
                value = value[0] + '.' + value[1][:4]
            else:
                value = value[0]
        elif value is None:
            value = ''

        self.setText(self._prefix + value + self._suffix)