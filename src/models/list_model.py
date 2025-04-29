import sys
from PySide6.QtCore import QRecursiveMutex, Signal, QObject, QMutexLocker
from typing import Generic, TypeVar

T = TypeVar('T')

class ListModel(QObject, Generic[T]): #TODO: Have list model support max length
    """A threadsafe list that emits a signal when the internal data is changed."""
    data_changed = Signal()

    def __init__(self, list:list = None, maxlen:int|None = None):
        """list - Data to be initialized with the ListModel. Will initialize with [] if None.\n
        maxlen - Maximum length of the list. If None, no max length is set.
        """
        super().__init__()
        self._list = list if list is not None else []
        self._maxlen = maxlen
        self._mutex = QRecursiveMutex()
        self.data_changed.connect(self._handle_overflow)

    def _handle_overflow(self):
        if self._maxlen is not None and len(self._list) > self._maxlen:
            with QMutexLocker(self._mutex):
                self._list.pop(0)

    def append(self, value: T):
        with QMutexLocker(self._mutex):
            try:
                self._list.append(value)
                self.data_changed.emit()
            except Exception as error:
                raise error

    def sort(self, key, reverse:bool = False):
        with QMutexLocker(self._mutex):
            try:
                self._list.sort(key=key,reverse=reverse)
                self.data_changed.emit()
            except Exception as error:
                raise error
            else:
                return self
        
    def clear(self):
        with QMutexLocker(self._mutex):
            try:
                self._list.clear()
                self.data_changed.emit()
            except Exception as error:
                raise error

    def copy(self):
        with QMutexLocker(self._mutex):
            try:
                copy = self._list.copy()
            except Exception as error:
                raise error
            else:
                return copy
        
    def count(self, value:T):
        with QMutexLocker(self._mutex):
            try:
                count = self._list.count(value)
            except Exception as error:
                raise error
            else:
                return count
        
    def extend(self, iterable):
        with QMutexLocker(self._mutex):
            try:
                self._list.extend(iterable)
                self.data_changed.emit()
            except Exception as error:
                raise error

    def index(self, value:T, start=0, stop=sys.maxsize):
        with QMutexLocker(self._mutex):
            try:
                index = self._list.index(value, start, stop)
            except Exception as error:
                raise error
            else:
                return index
        
    def insert(self, index, object:T):
        with QMutexLocker(self._mutex):
            try:
                self._list.insert(index, object)
                self.data_changed.emit()
            except Exception as error:
                raise error

    def pop(self, index=-1) -> T:
        with QMutexLocker(self._mutex):
            try:
                item = self._list.pop(index)
                self.data_changed.emit()
            except Exception as error:
                raise error
            else:
                return item
        
    def remove(self, value:T):
        with QMutexLocker(self._mutex):
            try:
                self._list.remove(value)
                self.data_changed.emit()
            except Exception as error:
                raise error

    def reverse(self):
        with QMutexLocker(self._mutex):
            try:
                self._list.reverse()
                self.data_changed.emit()
            except Exception as error:
                raise error

    def __len__(self):
        with QMutexLocker(self._mutex):
            try:
                length = len(self._list)
            except Exception as error:
                raise error
            else:
                return length
        
    def __iter__(self) -> T:
        for item in self._list:
            yield item

    def __contains__(self, item:T):
        with QMutexLocker(self._mutex):
            try:
                ret = item in self._list
            except Exception as error:
                raise error
            else:
                return ret

    def __getitem__(self, index:int) -> T:
        with QMutexLocker(self._mutex):
            try:
                item = self._list[index]
            except Exception as error:
                raise error
            else:    
                return item
        
    def __setitem__(self, index:int, value:T):
        with QMutexLocker(self._mutex):
            try:
                self._list[index] = value
                self.data_changed.emit()
            except Exception as error:
                raise error
    
    def __add__(self, right):
        with QMutexLocker(self._mutex):
            try:
                with QMutexLocker(right._mutex):
                    try:
                        newList = ListModel(self._list + right._list)
                    except Exception as error:
                        raise error
            except Exception as error:
                raise error
            else:
                return newList