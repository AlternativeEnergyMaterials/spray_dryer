from PySide6.QtWidgets import QDialog, QLabel, QWidget, QVBoxLayout, QDialogButtonBox
from PySide6.QtCore import Qt

class WarningDialog(QDialog):
    """A dialog to allow the user to double check before they close the TestSuite."""
    def __init__(self, message:str, title:str, parent:QWidget = None):
        super().__init__(parent=parent)

        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFont(parent.font())
        
        button_box = QDialogButtonBox(self)
        button_box.addButton(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message,self))
        layout.addWidget(button_box, alignment=Qt.AlignHCenter)
        self.setLayout(layout)
        