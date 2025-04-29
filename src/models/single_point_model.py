from PySide6.QtCore import QRecursiveMutex, Signal, QObject, QMutexLocker
from typing import Generic, TypeVar

T = TypeVar('T')

class SinglePointModel(QObject, Generic[T]):
    """A threadsafe model that holds a single piece of data and emits a signal if the data is changed."""
    data_changed = Signal()

    def __init__(self, data = None):
        """data - Data to be initialized with the SinglePointModel. Defaults to None."""
        super().__init__()
        self._mutex = QRecursiveMutex()
        self._data = data

    @property
    def data(self):
        """Returns the model's data using threadsafe operations."""
        with QMutexLocker(self._mutex):
            ret = self._data
        return ret
    
    @data.setter
    def data(self, new_data):
        """Sets the model's data using threadsafe operations."""
        with QMutexLocker(self._mutex):
            self._data = new_data
        self.data_changed.emit()