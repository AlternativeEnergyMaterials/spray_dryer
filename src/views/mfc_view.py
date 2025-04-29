from PySide6.QtWidgets import QWidget, QFrame, QGridLayout, QVBoxLayout, QLabel, QLineEdit, QSizePolicy
from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QRegularExpressionValidator, QResizeEvent
from models import ListModel, SinglePointModel
from controllers import MFCController
from devices import ElFlowMFC
from widgets import LiveReadout, PlotWidget
from datetime import datetime

class MFCView(QFrame):
    def __init__(self, time_model:ListModel[datetime], flow_models:dict[int,ListModel[ListModel[float]]],
                 mfcs:dict[int,ListModel[ElFlowMFC]], parent:QWidget = None):
        super().__init__(parent=parent)
        #Create controller and other variables.
        self._controller = MFCController(mfcs,self)
        self._time_model = time_model
        self._flow_models = flow_models
        self._mfcs = mfcs
        self._plots:list[PlotWidget] = []

        #Initialize UI elements.
        self._init_UI()

    def _init_UI(self):
        #Set frame outline.
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(3)
        self.setMidLineWidth(3)

        self._layout = QVBoxLayout(self)
        self.setLayout(self._layout)

        #Create validators for line edits.
        float_regex = QRegularExpression('^[0-9]*[.]?[0-9]*$') #Only allow floats for input.
        float_validator = QRegularExpressionValidator(float_regex, self)

        sects = sorted(self._mfcs.keys())

        for sect in sects:
            inner_layout = QGridLayout()
            fr_label = QLabel('Flow Rate')
            fr_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            inner_layout.addWidget(fr_label,1,1)
            mc_label = QLabel('Max Capacity')
            mc_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            inner_layout.addWidget(mc_label,1,2)
            sp_label = QLabel('Set Point')
            sp_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            inner_layout.addWidget(sp_label,1,3)
            rr_label = QLabel('Ramp Rate (unit/sec)')
            rr_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            inner_layout.addWidget(rr_label,1,5)
            cv_label = QLabel('Conversion Factor')
            cv_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            inner_layout.addWidget(cv_label,1,7)

            row = 2
            for mfc, flow_model, sp_model, rr_model, target_model in zip(self._mfcs[sect],
                                                           self._flow_models[sect],
                                                           self._controller.sp_models[sect],
                                                           self._controller.rr_models[sect],
                                                           self._controller.target_models[sect]):
                mfc:ElFlowMFC
                flow_model:ListModel[float]
                sp_model:SinglePointModel[float]
                target_model:SinglePointModel[float]
                max_cap = str(mfc.max_capacity).split('.')
                max_cap = max_cap[0] + '.' + max_cap[1][:3]
                unit_label = QLabel(mfc.name + '(' + mfc.unit + ')')
                inner_layout.addWidget(unit_label,row,0)
                flow_readout = LiveReadout(flow_model)
                flow_readout.setAlignment(Qt.AlignCenter)
                inner_layout.addWidget(flow_readout,row,1)
                max_cap_label = QLabel(max_cap)
                max_cap_label.setAlignment(Qt.AlignCenter)
                inner_layout.addWidget(max_cap_label,row,2)
                sp_readout = LiveReadout(sp_model)
                sp_readout.setAlignment(Qt.AlignCenter)
                inner_layout.addWidget(sp_readout,row,3)
                sp_edit = QLineEdit()
                sp_edit.returnPressed.connect(self._create_update_func(target_model, sp_edit))
                sp_edit.setValidator(float_validator)
                if mfc._disconnected:
                    sp_edit.setEnabled(False)
                inner_layout.addWidget(sp_edit,row,4)
                rr_readout = LiveReadout(rr_model)
                rr_readout.setAlignment(Qt.AlignCenter)
                inner_layout.addWidget(rr_readout,row,5)
                rr_edit = QLineEdit()
                rr_edit.returnPressed.connect(self._create_update_func(rr_model, rr_edit))
                rr_edit.setValidator(float_validator)
                if mfc._disconnected:
                    rr_edit.setEnabled(False)
                inner_layout.addWidget(rr_edit,row,6)
                cv_label = QLabel(str(mfc.conversion_factor))
                cv_label.setAlignment(Qt.AlignCenter)
                inner_layout.addWidget(cv_label,row,7)
                cv_edit = QLineEdit()
                cv_edit.returnPressed.connect(self._create_cv_func(cv_edit, mfc, flow_model, sp_model, target_model, max_cap_label, cv_label))
                cv_edit.setValidator(float_validator)
                if mfc._disconnected:
                    cv_edit.setEnabled(False)
                mfc.update_display.connect(self._create_display_update_func(mfc, flow_model, sp_model, unit_label, max_cap_label, sp_edit, rr_edit, cv_edit))
                inner_layout.addWidget(cv_edit,row,8)
                row += 1
            
            plot = PlotWidget([self._time_model],
                              self._flow_models[sect],
                              [mfc.name for mfc in self._mfcs[sect]],
                              'Flow Rates ' + str(sect))
            self._plots.append(plot)
            inner_layout.addWidget(plot,0,9,inner_layout.rowCount()+1,1)

            inner_layout.setColumnStretch(0,1)
            inner_layout.setColumnStretch(1,1)
            inner_layout.setColumnStretch(2,1)
            inner_layout.setColumnStretch(3,1)
            inner_layout.setColumnStretch(4,1)
            inner_layout.setColumnStretch(5,1)
            inner_layout.setColumnStretch(6,1)
            inner_layout.setColumnStretch(7,8)
            for row in range(inner_layout.rowCount()):
                inner_layout.setRowStretch(row,1)
            self._layout.addLayout(inner_layout)
            
    def _create_cv_func(self, line_edit:QLineEdit, mfc:ElFlowMFC, flow_model:SinglePointModel,
                        sp_model:SinglePointModel, target_model:SinglePointModel,
                        max_cap_label:QLabel, cv_label:QLabel):
        def cv():
            if line_edit.text() != '':
                old_cv = mfc.conversion_factor
                new_cv = float(line_edit.text())
                cv_label.setText(str(new_cv))
                mfc.conversion_factor = new_cv
                flow_model.data = mfc.flow_rate
                sp_model.data = mfc.setpoint
                target_model.data = (target_model.data*old_cv) / new_cv
                new_max_cap = str(mfc.max_capacity).split('.')
                new_max_cap = new_max_cap[0] + '.' + new_max_cap[1][:3]
                max_cap_label.setText(new_max_cap)
        return cv
    
    def _create_display_update_func(self, mfc:ElFlowMFC, flow_model:SinglePointModel, sp_model:SinglePointModel, unit_label:QLabel,
                                    max_cap_label:QLabel, sp_edit:QLineEdit, rr_edit:QLineEdit, cv_edit:QLineEdit):
        def update_display():
            sp_edit.setDisabled(mfc._disconnected)
            rr_edit.setDisabled(mfc._disconnected)
            cv_edit.setDisabled(mfc._disconnected)
            flow_model.data = mfc.flow_rate
            sp_model.data = mfc.setpoint
            unit_label.setText(mfc.name + '(' + mfc.unit + ')')
            max_cap = str(mfc.max_capacity).split('.')
            max_cap = max_cap[0] + '.' + max_cap[1][:3]
            max_cap_label.setText(max_cap)
        return update_display

    def _create_update_func(self, model:SinglePointModel[float], line_edit:QLineEdit) -> callable:
        def update():
            if line_edit.text() != '':
                model.data = float(line_edit.text())
        return update

    @property
    def controller(self) -> MFCController:
        return self._controller
    
    @property
    def plots(self) -> list[PlotWidget]:
        return self._plots
    
    def resizeEvent(self, event) -> None:
        if len(self._plots) > 1:
            for plot in self._plots:
                plot.setMaximumWidth(16777215) #Set back to default value.

            self._layout.activate()

            min_plot_width = min([plot.width() for plot in self._plots])
            for plot in self._plots:
                plot.setMaximumWidth(min_plot_width)

        super().resizeEvent(event)

    def close(self):
        print('closing mfc view')
        self._controller.close()