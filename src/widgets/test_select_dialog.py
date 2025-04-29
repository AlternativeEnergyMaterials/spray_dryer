from PySide6.QtGui import QFont
from PySide6.QtWidgets import QVBoxLayout, QLabel, QComboBox, QPushButton, QDialog, QWidget

class TestSelectionDialog(QDialog):
    def __init__(self, measurements, parent:QWidget = None):
        super().__init__(parent=parent)

        self.setFont(QFont("Arial", 14))

        self.measurements = measurements
        self.selected_measurement = None

        self.setWindowTitle("Select a Test")
        self.setGeometry(100, 100, 300, 150)

        layout = QVBoxLayout()

        label = QLabel("Select a test:")
        self.combo_box = QComboBox()
        self.combo_box.addItems(self.measurements)

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
        self.selected_measurement = self.combo_box.currentText()
        self.accept()