import os
import datetime
from PySide6.QtGui import QFont, QRegularExpressionValidator
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QDateEdit, QGridLayout
from PySide6.QtCore import QRegularExpression

class ProfileSaveDialog(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent=parent)

        self.setFont(QFont("Arial", 14))

        self.setWindowTitle("Enter a profile name")
        self.setGeometry(100, 100, 300, 150)

        self.profile_name = None

        layout = QVBoxLayout()

        file_pattern = QRegularExpression("^[^\\\\/:*.?\"<>|]*$")
        file_validator = QRegularExpressionValidator(file_pattern, self)
        label = QLabel("Name:")
        self.line_edit = QLineEdit()
        self.line_edit.setValidator(file_validator)

        ok_button = QPushButton("Ok")
        ok_button.clicked.connect(self.ok_clicked)

        layout.addWidget(label)
        layout.addWidget(self.line_edit)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def ok_clicked(self):
        self.profile_name = self.line_edit.text()
        self.accept()

class ProfileSelectionDialog(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent=parent)

        self.setFont(QFont("Arial", 14))

        self.setWindowTitle("Select a Test")
        self.setGeometry(100, 100, 300, 150)

        layout = QVBoxLayout()

        profiles = [profile.split('.')[0] for profile in os.listdir(os.path.expanduser("~") + "\\AppData\\Local\\AEM TestSuite\\profiles\\")]
        self.selectedProfile = None

        label = QLabel("Select a profile:")
        self.combo_box = QComboBox()
        self.combo_box.addItems(profiles)

        ok_button = QPushButton("Ok")
        ok_button.clicked.connect(self.ok_clicked)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(label)
        layout.addWidget(self.combo_box)
        layout.addWidget(ok_button)
        layout.addWidget(cancel_button)

        self.setLayout(layout)

    def ok_clicked(self):
        self.selectedProfile = self.combo_box.currentText()
        self.accept()

class TimeSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        
        self.setWindowTitle("Select Start Time")
        self.setFont(QFont("Arial",14))
        self.grid = QGridLayout(self)
        self.setLayout(self.grid)
        
        self.date_edit = QDateEdit(datetime.datetime.now(),self)
        self.date_edit.setCalendarPopup(True)

        self.hours = [f"{n:02}" for n in range(24)] #populate list with hours from 0-23 formatted to 2 digits
        self.minutes = [f"{n:02}" for n in range(0,60,5)] #populate list in steps of 5 from 0-55 formatted to 2 digits

        self.hour_selection = QComboBox(self)
        self.hour_selection.addItems(self.hours)
        self.minute_selection = QComboBox(self)
        self.minute_selection.addItems(self.minutes)

        currentHour = f"{(datetime.datetime.now().hour):02}" #get current hour from 0-23 and format to 2 digits
        currentMinute = f"{(int(datetime.datetime.now().minute/5)*5):02}" #get current minute, round it down to nearest 5 and format to 2 digits

        self.hour_selection.setCurrentText(currentHour)
        self.minute_selection.setCurrentText(currentMinute)

        self.date_label = QLabel("Date:", self)
        self.time_label = QLabel("Time:", self)

        self.confirm_button = QPushButton(self)
        self.confirm_button.setText("Confirm")
        self.confirm_button.clicked.connect(self.confirmSelection)

        self.grid.addWidget(self.date_label,0,0)
        self.grid.addWidget(self.date_edit,0,1)
        self.grid.addWidget(self.time_label,1,0)
        self.grid.addWidget(self.hour_selection,1,1)
        self.grid.addWidget(self.minute_selection,1,2)
        self.grid.addWidget(self.confirm_button,2,1)
        
    def confirmSelection(self):
        self.selected_datetime = self.date_edit.date()
        self.selected_datetime = datetime.datetime(self.selected_datetime.year(), self.selected_datetime.month(),
                                                  self.selected_datetime.day(),int(self.hour_selection.currentText()),
                                                  int(self.minute_selection.currentText()))
        self.accept()