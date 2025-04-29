import os
from PySide6.QtWidgets import QDialog, QWidget, QGridLayout, QLabel, QComboBox, QDateEdit, QPushButton, QFrame, QVBoxLayout, QLineEdit
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from datetime import datetime
import yaml

class ScheduleDialog(QDialog):
    def __init__(self, folder_path:str, pstat_names:list[str],parent:QWidget = None):
        super().__init__(parent=parent)

        self._pstat_names= pstat_names

        self.setWindowTitle(parent.windowTitle())
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFont(parent.font())

        self._prefs:list[dict] = []
        for filename in os.listdir(folder_path):
            with open(folder_path + filename) as file:
                self._prefs.append(yaml.safe_load(file))

        self._init_UI()

        self._update_sweep_preview()

    def _init_UI(self):
        self._layout = QGridLayout(self)
        self.setLayout(self._layout)

        self._filename_regex = QRegularExpression('^[^*"/\\\<>:|?]*$')
        self._filename_validator = QRegularExpressionValidator(self._filename_regex, self)

        self._sweep_label = QLabel('Profile:', self)
        self._sweep_select = QComboBox(self)
        self._sweep_select.addItems([pref['profile-name'] for pref in self._prefs])
        self._sweep_select.currentTextChanged.connect(self._update_sweep_preview)
        self._layout.addWidget(self._sweep_label,0,0,1,1)
        self._layout.addWidget(self._sweep_select,0,1,1,2)

        self._start_date_label = QLabel('Start Date:', self)
        self._date_select = QDateEdit(datetime.now(), self)
        self._date_select.setCalendarPopup(True)
        self._layout.addWidget(self._start_date_label,1,0,1,1)
        self._layout.addWidget(self._date_select,1,1,1,2)

        self._start_time_label = QLabel('Start Time:', self)
        self._hour_select = QComboBox(self)
        self._hour_select.addItems([f'{i:02}' for i in range(24)])
        self._hour_select.setCurrentText(f"{(datetime.now().hour):02}")
        self._minute_select = QComboBox(self)
        self._minute_select.addItems([f'{i:02}' for i in range(0,60,5)])
        self._minute_select.setCurrentText(f"{(int(datetime.now().minute/5)*5):02}")
        self._layout.addWidget(self._start_time_label,2,0,1,1)
        self._layout.addWidget(self._hour_select,2,1,1,1)
        self._layout.addWidget(self._minute_select,2,2,1,1)

        #Device selector.
        #Load pstats.
        self._device_selector = QComboBox(self)
        self._device_selector.addItems(self._pstat_names)
        self._layout.addWidget(self._device_selector,3,0,1,2)

        self._name_label = QLabel('Sweep Name:', self)
        self._name_input = QLineEdit(self)
        self._name_input.setValidator(self._filename_validator)
        self._layout.addWidget(self._name_label,4,0,1,1)
        self._layout.addWidget(self._name_input,4,1,1,2)

        self._sweep_preview_widget = QFrame(self)
        self._sweep_preview_widget.setFrameStyle(QFrame.Box)
        self._sweep_preview_widget.setLineWidth(1)
        self._sweep_preview_layout = QVBoxLayout(self._sweep_preview_widget)
        self._sweep_preview_widget.setLayout(self._sweep_preview_layout)
        self._layout.addWidget(self._sweep_preview_widget,0,4,5,1)

        self._schedule_button = QPushButton(self)
        self._schedule_button.setText('Schedule Sweep')
        self._schedule_button.clicked.connect(self._confirm_selection)
        self._layout.addWidget(self._schedule_button,5,0,1,3)

    def _update_sweep_preview(self):
        for i in reversed(range(self._sweep_preview_layout.count())): 
            widget = self._sweep_preview_layout.takeAt(i).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        pref = self._prefs[self._sweep_select.currentIndex()]
        for key in pref:
            self._sweep_preview_layout.addWidget(QLabel(key + ': ' + str(pref[key]), self))

    def _confirm_selection(self):
        self.selected_dt = datetime(self._date_select.date().year(), self._date_select.date().month(),
                                    self._date_select.date().day(),int(self._hour_select.currentText()),
                                    int(self._minute_select.currentText()))
        
        self.selected_sweep = self._prefs[self._sweep_select.currentIndex()]
        self.selected_name = self._name_input.text()
        if self.selected_name == '':
            self.selected_name = str(self.selected_dt).replace(':','-')
        self._prefs[self._sweep_select.currentIndex()]['filename'] = self.selected_name + '.csv'
        self._prefs[self._sweep_select.currentIndex()]['device-name'] = self._device_selector.currentText()
        self.accept()