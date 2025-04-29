from PySide6.QtWidgets import QWidget, QFrame, QPushButton, QGridLayout, QLineEdit, QCheckBox, QLabel, QSizePolicy, QDialog
from PySide6.QtCore import QRegularExpression, Slot
from PySide6.QtGui import QRegularExpressionValidator
from models import ListModel, SinglePointModel
from controllers import TemperatureController
from widgets import PlotWidget, LiveReadout, ToggleButton, OverrideDialog
from devices import PWMWriter
from datetime import datetime

def clamp(value:float|int, min:float|int, max:float|int) -> float|int:
    """Returns a value within the specified bounds if the input value exceeds those bounds.\n
    value - Value to be clamped.\n
    min - Inclusive lower bound.\n
    max - Inclusive upper bound.
    """
    if value < min:
        return min
    elif value > max:
        return max
    else:
        return value
    

class TemperatureView(QFrame):
    """A view that displays a live plot of thermocouple temperature's and sends user input to the temperature controller."""
    def __init__(self, time_model:ListModel[datetime], models:list[ListModel[float]], control_map:dict[ListModel[float],bool],
                 thermocouple_names:list[str], voltage_writer:PWMWriter, identifier:int, voltage_line:int, supervisor_furnace:int, safety_model:SinglePointModel[bool], 
                 config:dict, all_temp_controllers:ListModel[TemperatureController],
                 p:float, i:float, d:float, name:str = '', parent:QWidget = None):
        """
        time_model - A list of timestamps corresponding to each temperature measurement.\n
        models - A list of ListModels where each model holds the temperature readouts from thermocouples.\n
        control_map - A mapping of temp models to bools to show which models should be used to control the PID.\n
        thermocouple_names - Display names of the thermocouples that are plotted. Should correspond to the control and temperature models.\n
        voltage_writer - VoltageWriter device used in the duty cycle.\n
        voltage_line - Voltage output line to be controlled with the duty cycle.\n
        config - Dictionary holding data in furnace-config or humidifier-config.\n
        all_temp_controllers - ListModel of all temperature controllers of the same type (Furnace or Humidifier).\n
        p, i, d - Respective PID values for the duty cycle.\n
        name - Furnace display name.
        """
        super().__init__(parent=parent)
        self._time_model = time_model
        self._time_model.data_changed.connect(self._update_setpoint_history) #Ensure that setpoints update at the same time as temperatures.
        self._models = models
        self._control_map = control_map
        self._thermocouple_names = thermocouple_names
        self._voltage_writer = voltage_writer
        self._identifier = identifier
        self._voltage_line = voltage_line
        self._supervisor_furnace = supervisor_furnace
        self._safety_model = safety_model
        self._config = config
        self._all_temp_controllers = all_temp_controllers
        self._name = name
        self._tuning = config['tuning-mode']
        self._temp_cap = config['temperature-cap']
        self._setpoint_history_model:ListModel[float] = ListModel(maxlen=self._config['max-data']) #Track old setpoins for the plot.

        #Create controller.
        self._controller = TemperatureController(self._models,
                                                 self._control_map,
                                                 self._voltage_writer,
                                                 self._identifier,
                                                 self._voltage_line,
                                                 self._supervisor_furnace,
                                                 self._safety_model,
                                                 self._config,
                                                 self._all_temp_controllers,
                                                 self._name,
                                                 p,
                                                 i,
                                                 d,
                                                 self)
        self._controller.heating_started.connect(self._heating_started)
        self._controller.heating_stopped.connect(self._heating_stopped)

        #Initialize UI elements.
        self._init_UI()

    def _init_UI(self):
        #Set frame outline.
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(3)
        self.setMidLineWidth(3)

        #Create layout and initialize row trackers.
        self._layout = QGridLayout(self)
        self.setLayout(self._layout)
        row = 0

        #Create validators for line edits.
        float_regex = QRegularExpression('^[0-9]*[.]?[0-9]*$') #Only allow floats for input.
        float_validator = QRegularExpressionValidator(float_regex, self)
        neg_float_regex = QRegularExpression('^[-]?[0-9]*[.]?[0-9]*$') #Only allow floats for input. Can be negative.
        neg_float_validator = QRegularExpressionValidator(neg_float_regex, self)
        int_regex = QRegularExpression('^[0-9]*$') #Only allow ints for input.
        int_validator = QRegularExpressionValidator(int_regex, self)

        #Create heating button.
        self._heating_button = QPushButton(self) #NOTE: Not using ToggleButton because of safety logic in temperature controller.
        self._heating_button.setText('Start Heating')
        self._heating_button.clicked.connect(self.controller.start_heating)
        self._layout.addWidget(self._heating_button,row,0,1,3)
        row += 1

        #Create user inputs.
        if self._tuning:
            #Proportional constant.
            self._p_label = LiveReadout(self.controller.p_model, 'Proportional Constant: ', parent=self)
            self._p_input = QLineEdit(self)
            self._p_input.setValidator(float_validator)
            self._layout.addWidget(self._p_label,row,0,1,1)
            self._layout.addWidget(self._p_input,row,1,1,2)
            row += 1

            #Integral constant.
            self._i_label = LiveReadout(self.controller.i_model, 'Integral Constant: ', parent=self)
            self._i_input = QLineEdit(self)
            self._i_input.setValidator(float_validator)
            self._layout.addWidget(self._i_label,row,0,1,1)
            self._layout.addWidget(self._i_input,row,1,1,2)
            row += 1

            #Derivative constant.
            self._d_label = LiveReadout(self.controller.d_model, 'Derivative Constant: ', parent=self)
            self._d_input = QLineEdit(self)
            self._d_input.setValidator(float_validator)
            self._layout.addWidget(self._d_label,row,0,1,1)
            self._layout.addWidget(self._d_input,row,1,1,2)
            row += 1

            #Maximum output.
            self._maxout_label = LiveReadout(self.controller.max_output_model, 'Maximum Output: ', '%', self)
            self._maxout_input = QLineEdit(self)
            self._maxout_input.setValidator(int_validator)
            self._layout.addWidget(self._maxout_label,row,0,1,1)
            self._layout.addWidget(self._maxout_input,row,1,1,2)
            row += 1

            #Integral maximum.
            self._integral_max_label = LiveReadout(self.controller.integral_max_model, 'Integral Maximum: ', parent=self)
            self._integral_max_input = QLineEdit(self)
            self._integral_max_input.setValidator(float_validator)
            self._layout.addWidget(self._integral_max_label,row,0,1,1)
            self._layout.addWidget(self._integral_max_input,row,1,1,2)
            row += 1

            #Integral minimum.
            self._integral_min_label = LiveReadout(self.controller.integral_min_model, 'Integral Minimum: ', parent=self)
            self._integral_min_input = QLineEdit(self)
            self._integral_min_input.setValidator(neg_float_validator)
            self._layout.addWidget(self._integral_min_label,row,0,1,1)
            self._layout.addWidget(self._integral_min_input,row,1,1,2)
            row += 1

            #Output bias.
            self._output_bias_label = LiveReadout(self.controller.output_bias_model, 'Output Bias: ', '%', self)
            self._output_bias_input = QLineEdit(self)
            self._output_bias_input.setValidator(neg_float_validator)
            self._layout.addWidget(self._output_bias_label,row,0,1,1)
            self._layout.addWidget(self._output_bias_input,row,1,1,2)
            row += 1

            if self._supervisor_furnace != -1:
                self._duty_max_label = LiveReadout(self.controller.duty_clamp_max_model, 'Duty Max Modifier: ', parent=self)
                self._duty_max_input = QLineEdit(self)
                self._duty_max_input.setValidator(neg_float_validator)
                self._layout.addWidget(self._duty_max_label,row,0,1,1)
                self._layout.addWidget(self._duty_max_input,row,1,1,2)
                row += 1
                
                self._duty_min_label = LiveReadout(self.controller.duty_clamp_min_model, 'Duty Min Modifier: ', parent=self)
                self._duty_min_input = QLineEdit(self)
                self._duty_min_input.setValidator(neg_float_validator)
                self._layout.addWidget(self._duty_min_label,row,0,1,1)
                self._layout.addWidget(self._duty_min_input,row,1,1,2)
                row += 1

            #Integral crossover.
            self._integral_crossover_button = ToggleButton(self.controller.integral_crossover_model,
                                                           'Zero Integral On Crossover: Enabled',
                                                           'Zero Integral On Crossover: Disabled',
                                                           self)
            self._layout.addWidget(self._integral_crossover_button,row,0,1,3)
            row += 1

            #Override.
            self._output_override_label = LiveReadout(self.controller.output_override_model, 'Output Override: ', '%', self)
            self._output_override_input = QLineEdit(self)
            self._output_override_input.setValidator(float_validator)
            self._layout.addWidget(self._output_override_label,row,0,1,1)
            self._layout.addWidget(self._output_override_input,row,1,1,2)
            row += 1

            self._apply_override_button = QPushButton('Enable Output Override', self)
            self._apply_override_button.clicked.connect(self._enable_override)
            self._layout.addWidget(self._apply_override_button,row,0,1,3)
            row += 1

        #Target
        self._target_label = LiveReadout(self.controller.target_model, 'Target: ', '℃', self)
        self._target_input = QLineEdit(self)
        self._target_input.setValidator(float_validator)
        self._layout.addWidget(self._target_label,row,0,1,1)
        self._layout.addWidget(self._target_input,row,1,1,2)
        row += 1

        #Ramp rate
        self._rr_label = LiveReadout(self.controller.rr_model, 'Ramp Rate: ', '℃/min', self)
        self._rr_input = QLineEdit(self)
        self._rr_input.setValidator(float_validator)
        self._layout.addWidget(self._rr_label,row,0,1,1)
        self._layout.addWidget(self._rr_input,row,1,1,2)
        row += 1

        #Create apply button.
        self._apply_button = QPushButton(self)
        self._apply_button.setText('Apply Parameters')
        self._apply_button.clicked.connect(self._update_parameters)
        self._layout.addWidget(self._apply_button,row,0,1,3)
        row += 1

        #Create readout labels.
        col = 0
        cstretch = 2
        row_b = 0
        if self._tuning:
            #Create control label
            self._control_label = QLabel('Control   ', self)
            self._control_label.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
            self._layout.addWidget(self._control_label,row,2,1,1)

            #Create row_b tracker for tuning labels.
            row_b = row

            #PID output.
            self._pid_output = LiveReadout(self.controller.pid_output_model, 'PID Output: ', '%', self)
            self._layout.addWidget(self._pid_output,row_b,0,1,1)
            row_b += 1

            #P output.
            self._p_output = LiveReadout(self.controller.p_output_model, 'P Value: ', parent=self)
            self._layout.addWidget(self._p_output,row_b,0,1,1)
            row_b += 1

            #I output.
            self._i_output = LiveReadout(self.controller.i_output_model, 'I Value: ', parent=self)
            self._layout.addWidget(self._i_output,row_b,0,1,1)
            row_b += 1

            #D output.
            self._d_output = LiveReadout(self.controller.d_output_model, 'D Value: ', parent=self)
            self._layout.addWidget(self._d_output,row_b,0,1,1)
            row_b += 1

            #Modify col trackers so temps are on right side if tuning.
            col += 1
            cstretch = 1

        #Set point value.
        self._setpoint_value = LiveReadout(self.controller.setpoint_model, 'Set Point: ', '℃', self)
        self._layout.addWidget(self._setpoint_value,row,col,1,cstretch)
        if not self._tuning:
            if col == 0:
                col = 1
            else:
                col = 0
                row += 1
        else:
            row += 1

        #Create temperature readouts.
        for temp_model, tc_name in zip(self._models, self._thermocouple_names):
            temp_label = LiveReadout(temp_model, tc_name+': ', '℃', self)
            self._layout.addWidget(temp_label,row,col,1,cstretch)
            if not self._tuning:
                if col == 0:
                    col = 1
                else:
                    col = 0
                    row += 1
            else:
                control_check = QCheckBox(self)
                control_check.setSizePolicy(temp_label.sizePolicy())
                if self._control_map[temp_model]:
                    control_check.setChecked(True)
                control_check.stateChanged.connect(self._create_update_func(temp_model,control_check))
                self._layout.addWidget(control_check,row,2,1,1)
                row += 1

        #Ensure row and col are at correct positions.
        if col == 1:
            row += 1
        else:
            col = 0

        #Create plot widget.
        self._plot = PlotWidget([self._time_model],
                                [self._setpoint_history_model]+self._models,
                                ['Set Point']+self._thermocouple_names,
                                self._name, self)
        self._plot.set_x_label("Time")
        self._plot.set_y_label("Temp (℃)")
        self._plot.add_hline('#ffa300', self.controller.target_model)
        self._plot.add_legend_item('#ffa300', 'Target')
        self._layout.addWidget(self._plot,0,3,max(row,row_b),1)

        #Specify column stretch.
        self._layout.setColumnStretch(0,1) #1/9 of screen.
        self._layout.setColumnStretch(1,1) #1/9 of screen.
        if self._tuning:
            self._layout.setColumnStretch(2,1) #1/9 of screen.
        else:
            self._layout.setColumnStretch(2,0) #1/9 of screen.
        self._layout.setColumnStretch(3,6) #6/9 of screen.

    @property
    def controller(self) -> TemperatureController:
        return self._controller
    
    @property
    def plot(self) -> PlotWidget:
        return self._plot
    
    @property
    def name(self) -> str:
        return self._name
    
    @Slot()
    def _update_parameters(self):
        if self._tuning:
            #Update proportional constant.
            try:
                p = float(self._p_input.text())
                self.controller.p_model.data = p
            except:
                pass

            #Update integral constant.
            try:
                i = float(self._i_input.text())
                self.controller.i_model.data = i
            except:
                pass

            #Update derivative constant.
            try:
                d = float(self._d_input.text())
                self.controller.d_model.data = d
            except:
                pass

            #Update maximum output.
            try:
                max_out = clamp(int(self._maxout_input.text()), 0, 100)
                self.controller.max_output_model.data = max_out
            except:
                pass

            #Update output bias.
            try:
                bias = float(self._output_bias_input.text())
                self.controller.output_bias_model.data = bias
            except:
                pass

            #Update output override.
            try:
                override = float(self._output_override_input.text())
                self.controller.output_override_model.data = override
            except:
                pass

            #Update integral max.
            try:
                integral_max = float(self._integral_max_input.text())
                self.controller.integral_max_model.data = integral_max
            except:
                pass

            #Update integral min.
            try:
                integral_min = float(self._integral_min_input.text())
                self.controller.integral_min_model.data = integral_min
            except:
                pass

            if self._supervisor_furnace != -1:
                #Update duty cycle max.
                try:
                    duty_max = float(self._duty_max_input.text())
                    self.controller.duty_clamp_max_model.data = duty_max
                except:
                    pass

                #Update duty cycle min.
                try:
                    duty_min = float(self._duty_min_input.text())
                    self.controller.duty_clamp_min_model.data = duty_min
                except:
                    pass

        #Update target.
        try:
            target = clamp(float(self._target_input.text()), 0.0, self._temp_cap)
            self.controller.target_model.data = target
        except:
            pass

        #Update ramp rate.
        try:
            rr = float(self._rr_input.text())
            self.controller.rr_model.data = rr
        except:
            pass

    @Slot()
    def _heating_started(self):
        """Changes the heating button functionality when heating starts."""
        if self.controller.heating: #Allow controller logic to apply before changing the button.
            self._heating_button.setText("Stop Heating")
            self._heating_button.clicked.disconnect()
            self._heating_button.clicked.connect(self.controller.stop_heating)

    @Slot()
    def _heating_stopped(self):
        """Changes the heating button functionality when heating stops."""
        if not self.controller.heating: #Allow controller logic to apply before changing the button.
            self._heating_button.setText("Start Heating")
            self._heating_button.clicked.disconnect()
            self._heating_button.clicked.connect(self.controller.start_heating)

    @Slot()
    def _update_setpoint_history(self):
        if self.controller is not None and self.controller.setpoint_model.data is not None:
            self._setpoint_history_model.append(self.controller.setpoint_model.data)
        else:
            self._setpoint_history_model.append(0.0)

    def _create_update_func(self, model:ListModel[float], control_check:QCheckBox) -> callable:
        def update():
            if control_check.isChecked():
                self._control_map[model] = True
            else:
                self._control_map[model] = False
        return update

    def update_all_temp_views(self,views):
        self._all_temp_views = views
        self.controller.update_all_temp_controllers(ListModel([view.controller for view in self._all_temp_views]))

    def _enable_override(self):
        dialog = OverrideDialog('Enable Override', "Are you sure you want to enable PID Output Override?", self)
        close = dialog.exec()
        if close == QDialog.Accepted:
            self.controller.apply_override_model.data = True
            print("enabled output override")
            self._apply_override_button.clicked.disconnect()
            self._apply_override_button.clicked.connect(self._disable_override)
            self._apply_override_button.setText('Disable Output Override')

    def _disable_override(self):
        dialog = OverrideDialog('Disable Override', "Are you sure you want to disable PID Output Override?", self)
        close = dialog.exec()
        if close == QDialog.Accepted:
            self.controller.apply_override_model.data = False
            print("disabled output override") 
            self._apply_override_button.clicked.disconnect()
            self._apply_override_button.clicked.connect(self._enable_override)
            self._apply_override_button.setText('Enable Output Override')


    def close(self):
        """Closes the controller."""
        print('closing temperature view for furnace ' + str(self._identifier))
        self.controller.close()