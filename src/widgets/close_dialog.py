from PySide6.QtWidgets import QDialog, QLabel, QWidget, QDialogButtonBox, QVBoxLayout
from PySide6.QtCore import Qt

class CloseDialog(QDialog):
    """A dialog to allow the user to double check before they close the TestSuite."""
    def __init__(self, title:str, parent:QWidget = None):
        """title - Title for the dialog.\n
        parent - Parent widget for the dialog.
        """
        super().__init__(parent=parent)

        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFont(parent.font())

        button_box = QDialogButtonBox(self)
        button_box.addButton(QDialogButtonBox.Yes)
        button_box.addButton(QDialogButtonBox.No)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Are you sure you want to exit AEM TestSuite?",self))
        layout.addWidget(button_box, alignment=Qt.AlignHCenter)
        self.setLayout(layout)
        