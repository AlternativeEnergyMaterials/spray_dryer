from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel
from models import ListModel

class PrefQueueWidget(QScrollArea):
    def __init__(self, queued_prefs:ListModel[dict], active_prefs:ListModel[dict], parent:QWidget = None):
        super().__init__(parent=parent)
        self._queued_prefs = queued_prefs
        self._active_prefs = active_prefs

        self._init_UI()
        self._update_UI()
        self._queued_prefs.data_changed.connect(self._update_UI)
        self._active_prefs.data_changed.connect(self._update_UI)

    def _init_UI(self):
        self._inner_widget = QWidget(self)
        self._layout = QVBoxLayout(self._inner_widget)
        self._inner_widget.setLayout(self._layout)
        self.setWidget(self._inner_widget)
        self.setWidgetResizable(True)

    def _update_UI(self):
        for i in reversed(range(self._layout.count())): 
            widget = self._layout.takeAt(i).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._layout.addWidget(QLabel('Active Sweeps:', self))
        if len(self._active_prefs) > 0:
            for pref in self._active_prefs:
                self._layout.addWidget(QLabel('- ' + pref['filename'], self))
        else:
            self._layout.addWidget(QLabel('- None', self))

        self._layout.addWidget(QLabel('Queued Sweeps:', self))
        if len(self._queued_prefs) > 0:
            for pref in self._queued_prefs:
                self._layout.addWidget(QLabel('- ' + pref['filename'], self))
        else:
            self._layout.addWidget(QLabel('- None', self))

        self._layout.addStretch()