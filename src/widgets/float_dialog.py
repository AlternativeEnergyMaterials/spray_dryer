from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QFormLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, QRegularExpression, Signal
from PySide6.QtGui import QRegularExpressionValidator
from models import SinglePointModel

class FloatDialog(QDialog):
    model_changed_sig = Signal()

    def __init__(self, name:str, model:SinglePointModel, lower_limit:float, upper_limit:float, parent:QWidget = None):
        super().__init__(parent=parent)

        self.setWindowTitle(name)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFont(parent.font())

        layout = QFormLayout(self)
        self.setLayout(layout)

        neg_float_regex = QRegularExpression('^[-]?[0-9]*[.]?[0-9]*$') #Only allow floats for input. Can be negative.
        neg_float_validator = QRegularExpressionValidator(neg_float_regex, self)

        label = QLabel(name + ':', self)
        input = QLineEdit(self)
        input.setValidator(neg_float_validator)
        apply_button = QPushButton(self)
        apply_button.setText('Apply Changes')
        apply_button.clicked.connect(lambda:self._apply_changes(model, float(input.text()), lower_limit, upper_limit))
        layout.addRow(label, input)
        layout.addRow(apply_button)

    def _apply_changes(self, model:SinglePointModel, value:float, lower_limit:float, upper_limit:float):
        if value >= lower_limit and value <= upper_limit:
            model.data = value
            self.model_changed_sig.emit()
            self.close()