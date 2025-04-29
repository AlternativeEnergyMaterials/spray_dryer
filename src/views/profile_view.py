import os
from PySide6.QtWidgets import QWidget, QComboBox, QLineEdit, QPushButton, QGridLayout, QFormLayout, QStackedWidget, QLabel, QSizePolicy, QScrollArea, QDialog
from PySide6.QtCore import QRegularExpression, Slot
from PySide6.QtGui import QRegularExpressionValidator
from models import ListModel, SinglePointModel
from views import TemperatureView
from controllers import Step, ProfileController
from devices import ElFlowMFC
from widgets import ToggleButton, ProfileSelectionDialog, ProfileSaveDialog, TimeSelectionDialog
import time
import yaml
import serial
PROFILE_PATH = [] #TODO, create a path location in config
class TemperatureStep(Step):
    def __init__(self, 
                 temp_view:TemperatureView, 
                 target:float, 
                 ramp_rate:float,
                 steady_temp_tol:float,
                 step_id:int,
                 chan_id:int,
                 chan_step_id:int):
        self._step_type = 'temperature'
        self._temp_view = temp_view
        self._target = target
        self._rr = ramp_rate
        self._step_id = step_id
        self._chan_id = chan_id #Used for MFC's, Pumps, and Potentiostats/Loadbanks
        self._chan_step_id = chan_step_id #Used for MFC's, Pumps, and Potentiostats/Loadbanks
        self._steady_temp_tol = steady_temp_tol

    def __str__(self):
        return 'S'+str(self._step_id)+'C'+str(self._chan_id)+'CS'+str(self._chan_step_id)+ ' Heating ' + self._temp_view.name + ' to ' + str(self._target) + '℃ at ' + str(self._rr) + '℃/min'

    def start(self):
        self._temp_view.controller.target_model.data = self._target
        self._temp_view.controller.rr_model.data = self._rr
        if not self._temp_view.controller.heating:
            self._temp_view.controller.start_heating()

    def is_complete(self) -> bool: #TODO: Add check for control temp within stt
        if self._temp_view.controller.setpoint_model.data is None:
            return False
        sp_diff = abs(self._temp_view.controller.setpoint_model.data - self._temp_view.controller.target_model.data)
        ct_diff = abs(self._temp_view.controller.control_temp - self._temp_view.controller.target_model.data)
        step_size = self._temp_view.controller.rr_model.data/60.0*1.5
        return sp_diff <= step_size and ct_diff <= self._steady_temp_tol #Return true if setpoint is within 1.5 step sizes of target.
    
    def step_id(self) -> int:
        return self._step_id
    
    def chan_id(self) -> int:
        return self._chan_id
    
    def chan_step_id(self) -> int:
        return self._chan_step_id

class FlowStep(Step):
    def __init__(self,
                 target_model:SinglePointModel[float],
                 rr_model:SinglePointModel[float],
                 sp_model:SinglePointModel[float],
                 mfc:ElFlowMFC,
                 target:float,
                 ramp_rate:float,
                 step_id:int,
                 chan_id:int,
                 chan_step_id:int):
        self._step_type = 'flow'
        self._target_model = target_model
        self._rr_model = rr_model
        self._sp_model = sp_model
        self._mfc = mfc
        self._target = target
        self._ramp_rate = ramp_rate
        self._step_id = step_id
        self._chan_id = chan_id #Used to distinguish individual cells in a stand that can have grouped actions
        self._chan_step_id = chan_step_id #sub-step ID for this channel. EG furnace can hold for 1 hr while cell does 5 different sub-steps

    def __str__(self):
        if self._sp_model.data <= self._target:
            dir = 'Increasing '
        else:
            dir = 'Decreasing '
        return 'S'+str(self._step_id)+'C'+str(self._chan_id)+'CS'+str(self._chan_step_id)+ ' ' + dir + self._mfc.name + ' to ' + str(self._target) + ' ' + self._mfc.unit + ' at ' + str(self._ramp_rate) + ' ' + self._mfc.unit +'/sec'
    
    def start(self):
        self._rr_model.data = self._ramp_rate
        self._target_model.data = self._target

    def is_complete(self) -> bool:
        return self._sp_model.data == self._target_model.data
    
    def step_id(self) -> int:
        return self._step_id
    
    def chan_id(self) -> int:
        return self._chan_id
    
    def chan_step_id(self) -> int:
        return self._chan_step_id
    
class EldexStep(Step):
    def __init__(self, step_id:int, chan_id:int, chan_step_id:int):
        self._step_type = 'eldex'
        self._step_id = step_id
        self._chan_id = chan_id
        self._chan_step_id = chan_step_id
        self._eldex_pump = serial.Serial('COM25', timeout=1) #TODO: add comport

    def __str__(self):
        return 'S'+str(self._step_id)+'C'+str(self._chan_id)+'CS'+str(self._chan_step_id)+ ' Run Eldex Pump'
    
    def start(self):
        self._eldex_pump.write(b'RU')

    def is_complete(self):
        response = self._eldex_pump.read_until(b'/').decode()
        if 'OK' in response:
            return True
        else:
            print(response)
            self._eldex_pump.write(b'Z')
            self._eldex_pump.read_until(b'/')
            self._eldex_pump.write(b'RU')
    
    def step_id(self) -> int:
        return self._step_id
    
    def chan_id(self) -> int:
        return self._chan_id
    
    def chan_step_id(self) -> int:
        return self._chan_step_id

class PumpStep(Step):
    def __init__(self, 
                 pump_mode:str,
                 step_id:int,
                 chan_id:int,
                 chan_step_id:int):
        self._step_type = 'pump'
        self._pump_mode = pump_mode
        self._step_id = step_id
        self._chan_id = chan_id #Used to distinguish individual cells in a stand that can have grouped actions
        self._chan_step_id = chan_step_id #sub-step ID for this channel. EG furnace can hold for 1 hr while cell does 5 different sub-steps

    def __str__(self):
        om = ''
        if self._pump_mode == 'Pump Fill':
            pm = 'fill'
        elif self._pump_mode == 'Pump Drain':
            pm = 'drain'
        elif self._pump_mode == 'Pump Off':
            pm = 'off'
        return 'S'+str(self._step_id)+'C'+str(self._chan_id)+'CS'+str(self._chan_step_id)+ ' Setting pump to ' + self._pump_mode
    
    def start(self):
        pass

    def is_complete(self) -> bool:
        return True #Nothing to check for.
    
    def step_id(self) -> int:
        return self._step_id
    
    def chan_id(self) -> int:
        return self._chan_id
    
    def chan_step_id(self) -> int:
        return self._chan_step_id

class HoldStep(Step):
    def __init__(self, hold_time:float,
                 step_id:int,
                 chan_id:int,
                 chan_step_id:int):
        self._step_type = 'hold'
        self._hold_time = hold_time*60
        self._start_time = None
        self._step_id = step_id
        self._chan_id = chan_id #Used to distinguish individual cells in a stand that can have grouped actions
        self._chan_step_id = chan_step_id #sub-step ID for this channel. EG furnace can hold for 1 hr while cell does 5 different sub-steps

    def __str__(self):
        return 'S'+str(self._step_id)+'C'+str(self._chan_id)+'CS'+str(self._chan_step_id)+ ' Holding for ' + str(self._hold_time/60.0) + ' minutes'

    def start(self):
        self._start_time = time.time()

    def is_complete(self) -> bool:
        return (time.time() - self._start_time) >= self._hold_time
    
    def step_id(self) -> int:
        return self._step_id
    
    def chan_id(self) -> int:
        return self._chan_id
    
    def chan_step_id(self) -> int:
        return self._chan_step_id


class TemperatureParameters(QWidget):
    def __init__(self, temp_views:list[TemperatureView], parent:QWidget = None):
        super().__init__(parent=parent)
        self._temp_views = temp_views

        self._init_UI()

    def _init_UI(self): #TODO: Add stt support
        self._layout = QFormLayout(self)
        self.setLayout(self._layout)

        #Create validators for inputs.
        float_regex = QRegularExpression('^[0-9]*[.]?[0-9]*$') #Only allow floats for input.
        float_validator = QRegularExpressionValidator(float_regex, self)

        self._heater_select = QComboBox(self)
        self._heater_select.addItems([temp_view.name for temp_view in self._temp_views])
        self._layout.addRow('Heater:', self._heater_select)

        self._target_input = QLineEdit(self)
        self._target_input.setValidator(float_validator)
        self._layout.addRow('Target (℃):', self._target_input)

        self._rr_input = QLineEdit(self)
        self._rr_input.setValidator(float_validator)
        self._layout.addRow('Ramp Rate (℃/min):', self._rr_input)

        self._stt_input = QLineEdit(self)
        self._stt_input.setValidator(float_validator)
        self._layout.addRow('Steady Temp Tolerance (℃)', self._stt_input)

    def create_step(self,
                    step_id:int,
                    chan_id:int,
                    chan_step_id:int) -> TemperatureStep:
        try:
            return TemperatureStep(self._temp_views[self._heater_select.currentIndex()], 
                                   float(self._target_input.text()), 
                                   float(self._rr_input.text()),
                                   float(self._stt_input.text()),
                                   step_id,
                                   chan_id,
                                   chan_step_id)
        except:
            print('Could not create temperature step')
            return None
        
class FlowParameters(QWidget):
    def __init__(self, mfcs:dict[int,ListModel[ElFlowMFC]], target_models:dict[int,ListModel[SinglePointModel[float]]],
                 sp_models:dict[int,ListModel[SinglePointModel[float]]], rr_models:dict[int,ListModel[SinglePointModel[float]]],
                 parent:QWidget = None):
        super().__init__(parent=parent)
        self._all_mfcs:list[ElFlowMFC] = []
        self._all_tms:list[SinglePointModel[float]] = []
        self._all_sms:list[SinglePointModel[float]] = []
        self._all_rms:list[SinglePointModel[float]] = []

        #TODO link the MFC section to a channel for queuing operations (channel = cell = section). If not associated with a cell, such as purge flow MFC, set to None
        for sect in mfcs:
            for mfc, tm, sm, rm in zip(mfcs[sect],
                                       target_models[sect],
                                       sp_models[sect],
                                       rr_models[sect]):
                self._all_mfcs.append(mfc)
                self._all_tms.append(tm)
                self._all_sms.append(sm)
                self._all_rms.append(rm)

        self._init_UI()

    def _init_UI(self):
        self._layout = QFormLayout(self)
        self.setLayout(self._layout)

        #Create validators for inputs.
        float_regex = QRegularExpression('^[0-9]*[.]?[0-9]*$') #Only allow floats for input.
        float_validator = QRegularExpressionValidator(float_regex, self)

        self._mfc_select = QComboBox(self)
        self._mfc_select.addItems([mfc.name for mfc in self._all_mfcs])
        self._mfc_select.currentIndexChanged.connect(self._update_text)
        self._layout.addRow('MFC:', self._mfc_select)

        self._target_input = QLineEdit(self)
        self._target_input.setValidator(float_validator)
        self._target_label = QLabel('Target (unit):', self)
        self._layout.addRow(self._target_label, self._target_input)

        self._rr_input = QLineEdit(self)
        self._rr_input.setValidator(float_validator)
        self._rr_label = QLabel('Ramp Rate (unit/sec):')
        self._layout.addRow(self._rr_label, self._rr_input)

        self._update_text()

    def _update_text(self):
        self._target_label.setText('Target (' + self._all_mfcs[self._mfc_select.currentIndex()].unit + '):')
        self._rr_label.setText('Ramp Rate (' + self._all_mfcs[self._mfc_select.currentIndex()].unit + '/sec):')

    def create_step(self,
                    step_id:int,
                    chan_id:int,
                    chan_step_id:int):
        try:
            return FlowStep(self._all_tms[self._mfc_select.currentIndex()],
                            self._all_rms[self._mfc_select.currentIndex()],
                            self._all_sms[self._mfc_select.currentIndex()],
                            self._all_mfcs[self._mfc_select.currentIndex()],
                            float(self._target_input.text()),
                            float(self._rr_input.text()),
                            step_id,
                            chan_id,
                            chan_step_id)
        except:
            print('Could not create flow step')
            return None

class EldexParameters(QWidget):
    def __init__(self, parent:QWidget = None):
        super().__init__(parent)

    def create_step(self,
                    step_id:int,
                    chan_id:int,
                    chan_step_id:int):
        try:
            return EldexStep(step_id, chan_id, chan_step_id)
        except:
            print('Could not create eldex step')
            return None

class PumpParameters(QWidget):
    def __init__(self, parent:QWidget = None):
        super().__init__(parent)

        self._init_UI()

    def _init_UI(self):
        self._layout = QFormLayout(self)
        self.setLayout(self._layout)

        self._mode_select = QComboBox(self)
        self._mode_select.addItems(['Pump Off', 'Pump Fill', 'Pump Drain'])
        self._layout.addRow('Mode:', self._mode_select)

    def create_step(self,
                    step_id:int,
                    chan_id:int,
                    chan_step_id:int):
        try:
            return PumpStep(self._mode_select.currentText(),
                            step_id,
                            chan_id,
                            chan_step_id)
        except:
            print('Could not create pump step')
            return None

class HoldParameters(QWidget):
    def __init__(self, parent:QWidget = None):
        super().__init__(parent=parent)

        self._init_UI()

    def _init_UI(self):
        self._layout = QFormLayout(self)
        self.setLayout(self._layout)

        #Create validators for inputs.
        float_regex = QRegularExpression('^[0-9]*[.]?[0-9]*$') #Only allow floats for input.
        float_validator = QRegularExpressionValidator(float_regex, self)

        self._hold_time_input = QLineEdit(self)
        self._hold_time_input.setValidator(float_validator)
        self._layout.addRow('Hold Time (min):', self._hold_time_input)

        self._hold_channel_select = QComboBox(self)
        self._layout.addRow('Hold Channel:', self._hold_channel_select)

    def create_step(self,
                    step_id:int,
                    chan_id:int,
                    chan_step_id:int) -> HoldStep:
        try:
            return HoldStep(float(self._hold_time_input.text()),
                            step_id,
                            chan_id,
                            chan_step_id)
        except:
            print('Could not create hold step')
            return None

class ProfileView(QWidget):
    def __init__(self, temp_views:list[TemperatureView]|None, mfcs:dict[int,ListModel[ElFlowMFC]]|None,
                 target_models:dict[int,ListModel[SinglePointModel[float]]]|None, sp_models:dict[int,ListModel[SinglePointModel[float]]]|None,
                 rr_models:dict[int,ListModel[SinglePointModel[float]]]|None,  config:dict, parent:QWidget = None):
        super().__init__(parent=parent)
        self._temp_views = temp_views
        self._mfcs = mfcs
        self._channels = list(self._mfcs.keys())
        self._target_models = target_models
        self._sp_models = sp_models
        self._rr_models = rr_models
        self._step_types = []
        self._que_list = []
        self._config = config
        if self._temp_views is not None:
            self._step_types.append('Heater Step')
        if self._mfcs is not None:
            self._step_types.append('MFC Step')
        self._step_types.append('Eldex Step')
        self._step_types.append('Hold Step')

        self._controller = ProfileController(self)
        self._controller.queue.data_changed.connect(self._update_queue)
        self._controller.active_steps.data_changed.connect(self._update_active)
        self._controller.paused.data_changed.connect(self._handle_start)
        self._controller.queue_empty_sig.connect(self._update_que_list)

        self._init_UI()

        self._update_active()
        self._update_queue()

    def _init_UI(self):
        self._layout = QGridLayout(self)
        self.setLayout(self._layout)      

        #Step type selector.
        self._new_step_label = QLabel('New Step Type', self)
        self._layout.addWidget(self._new_step_label,0,0,1,2)
        self._step_type_selector = QComboBox(self)
        self._step_type_selector.addItems(self._step_types)
        self._layout.addWidget(self._step_type_selector,0,2,1,2)

        #Step parameter stack.
        self._parameter_stack = QStackedWidget(self)
        if self._temp_views is not None:
            self._parameter_stack.addWidget(TemperatureParameters(self._temp_views, self))
        if self._mfcs is not None:
            self._parameter_stack.addWidget(FlowParameters(self._mfcs, self._target_models, self._sp_models, self._rr_models, self))
        self._parameter_stack.addWidget(EldexParameters(self))
        self._parameter_stack.addWidget(HoldParameters(self))
        self._parameter_stack.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed))
        self._parameter_stack.currentChanged.connect(self._update_params)
        self._step_type_selector.currentIndexChanged.connect(lambda:self._parameter_stack.setCurrentIndex(self._step_type_selector.currentIndex()))
        self._layout.addWidget(self._parameter_stack,1,0,1,4)
        
        #Add after/to main step
        self._add_step_button = QPushButton(self)
        self._add_step_button.setText('Add After Step')
        self._add_step_button.clicked.connect(self._add_step)
        self._layout.addWidget(self._add_step_button,2,0,1,1)
        self._add_to_step_button = QPushButton(self)
        self._add_to_step_button.setText('Add To Step')
        self._add_to_step_button.clicked.connect(self._add_to_step)
        self._layout.addWidget(self._add_to_step_button,2,1,1,1)
        self._main_step_selector = QComboBox(self)
        self._main_step_selector.addItems(self._que_list)
        self._layout.addWidget(self._main_step_selector,2,2,1,2)        

        # #Add substep after main step button.
        # self._add_substep_button = QPushButton(self)
        # self._add_substep_button.setText('Add After Substep')
        # self._add_substep_button.clicked.connect(self._add_substep)
        # self._layout.addWidget(self._add_substep_button,3,0,1,1)
        # self._add_substep_button.hide()

        #Add to end
        self._add_end_button = QPushButton(self)
        self._add_end_button.setText('Add After Last Step')
        self._add_end_button.clicked.connect(self._add_end)
        self._layout.addWidget(self._add_end_button,3,0,1,1)

        #Add before step
        self._add_before_button = QPushButton(self)
        self._add_before_button.setText('Add Before Step')
        self._add_before_button.clicked.connect(self._add_before)
        self._layout.addWidget(self._add_before_button,3,1,1,1)

        #Edit step button.
        self._edit_step_button = QPushButton(self)
        self._edit_step_button.setText('Edit Step')
        self._edit_step_button.clicked.connect(self._edit_step)
        self._layout.addWidget(self._edit_step_button,3,2,1,1)

        #delete step
        self._delete_button = QPushButton(self)
        self._delete_button.setText('Delete Step')
        self._delete_button.clicked.connect(self._delete)
        self._layout.addWidget(self._delete_button,3,3,1,1)

        #Current step label.
        self._current_step_label = QLabel('Current Step: None', self)
        self._layout.addWidget(self._current_step_label,5,0,1,3)

        #Skip step button.
        self._skip_step_button = QPushButton(self)
        self._skip_step_button.setText('Skip Step')
        self._skip_step_button.clicked.connect(self._skip_step)
        self._layout.addWidget(self._skip_step_button,5,3,1,1)

        #Step queue.
        self._step_queue = QScrollArea(self)
        self._step_queue.setStyleSheet('border:none;')
        inner_widget = QWidget(self._step_queue)
        self._queue_layout = QFormLayout(self._step_queue)
        inner_widget.setLayout(self._queue_layout)
        self._step_queue.setWidget(inner_widget)
        self._step_queue.setWidgetResizable(True)
        self._layout.addWidget(self._step_queue,6,0,1,4)

        #Load profile button.
        self._load_profile_button = QPushButton(self)
        self._load_profile_button.setText('Load Profile')
        self._load_profile_button.clicked.connect(self._load_profile)
        self._layout.addWidget(self._load_profile_button,7,0,1,1)

        #Save profile button.
        self._save_profile_button = QPushButton(self)
        self._save_profile_button.setText('Save Profile')
        self._save_profile_button.clicked.connect(self._save_profile)
        self._layout.addWidget(self._save_profile_button,7,1,1,1)

        #Set start time button.
        self._set_start_time_button = QPushButton(self)
        self._set_start_time_button.setText('Set Start Time')
        self._set_start_time_button.clicked.connect(self._set_start)
        self._layout.addWidget(self._set_start_time_button,7,2,1,1)

        #Start/Pause profile button.
        self._start_profile_button = ToggleButton(self._controller.paused,'Start Profile', 'Pause Profile',self)
        self._start_profile_button.setText('Start Profile')
        self._layout.addWidget(self._start_profile_button,7,3,1,1)

    def _update_params(self):
        if type(self._parameter_stack.currentWidget()) == HoldParameters:
                widget = self._parameter_stack.currentWidget()
                if len(self._channels)>1:
                    widget._hold_channel_select.clear()
                    widget._hold_channel_select.addItems([str(chan) for chan in self._channels])
                    widget._hold_channel_select.show()
                else:
                    widget._hold_channel_select.hide()


    def _update_active(self):

        if len(self._controller.active_steps)>0:
            self._current_step_label.setText('Current Step/s: ' + str(self._controller.active_steps[0]))
            # if len(self._controller.active_steps)>1:
            #     list_of_strings = []
            #     for i in range(len(self._controller.active_steps)):
            #         list_of_strings.append(str(self._controller.active_steps[i]))            
            #     self._current_step_label.setText('Current Step/s: ' + " ".join(list_of_strings) )
        else:
            self._current_step_label.setText('Current Step: None')

    def _update_queue(self):
        for i in reversed(range(self._queue_layout.count())):
            widget = self._queue_layout.takeAt(i).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        
        self._queue_layout.addWidget(QLabel('Queued Steps:', self))
        for step in self._controller.queue:
            self._queue_layout.addWidget(QLabel(str(step), self))

    def get_chan_id(self):
        ''' Get channel ID from the MFC, Pump, Potentiostat/Loadbank selected in the GUI'''
        chan_id = 0 #0 corresponds to no channel (full test stand parameter like temperature and pressure)
        current_widget = self._parameter_stack.currentWidget()
        if type(current_widget) == FlowParameters:
            mfc = current_widget._all_mfcs[current_widget._mfc_select.currentIndex()]
            chan_id = self._config['mfc-config'][mfc.name]['section']
        elif type(current_widget) == HoldParameters:
            if len(self._channels)>1:
                chan_id = int(self._channels[current_widget._hold_channel_select.currentIndex()])
        #TODO add Temperature step here for a gas inlet furnace specific to a channel
        return chan_id

    def check_basic(self): #returns step_id, chan_step_id, and n for selected existing step, returns chan_id based on selected step type (parameter widget)
        chan_step_id = None
        n = self._main_step_selector.currentIndex()        
        chan_id = self.get_chan_id()
        if len(self._controller.queue) == 0:
            step_id = 0 #start a new que
            chan_step_id = 0
        else:
            step_id = self._controller.queue[n].step_id()  #use same ID as selected step
        return step_id, chan_id, chan_step_id, n

    def _add_substep(self):
        ''' Adds a new action step to complete when the prior is done'''
        step_id, chan_id, chan_step_id, n = self.check_basic()
        if chan_step_id is None:
            if self._controller.queue[n].chan_id() !=0: #user selected to add after a channel specific device
                chan_step_id = self.check_substeps(n,step_id,chan_id)+1
            else:
                step_id = step_id + 1 #ID is one more than last step in que
                chan_step_id = 0
                #increment upward all subsequent steps for items already queued
                for i in range(n+1,len(self._controller.queue)):
                    self._controller.queue[i]._step_id +=1
        step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)
        self._update_que_list(step,n+1)

    def check_substeps(self,n,step_id,chan_id):
        #identify any other substeps on same channel and same main step earlier in the queue
        pre_sub_step = -1
        i = 0
        while i<=n:
            if self._controller.queue[i].step_id() == step_id:
                if self._controller.queue[i].chan_id() == chan_id:
                    pre_sub_step = max(pre_sub_step,self._controller.queue[i].chan_step_id())
            i+=1
        #increment other sub-steps on same channel and main step
        while i<len(self._controller.queue) and self._controller.queue[i].step_id() == step_id:
            if self._controller.queue[i].chan_id() == chan_id and self._controller.queue[i].chan_step_id()>pre_sub_step:
                self._controller.queue[i]._chan_step_id +=1
            i+=1
        return pre_sub_step
    
    def _find_last_in_step(self,n,step_id):
        if len(self._controller.queue) == 0:
            n = -1
        else:
            while n<len(self._controller.queue)-1 and step_id == self._controller.queue[n+1].step_id():
                n +=1
        return n

    def _add_step(self):
        ''' Adds a new action step to complete when the prior is done'''
        step_id, chan_id, chan_step_id, n = self.check_basic() #returns step_id, chan_step_id, and n for selected existing step, returns chan_id based on selected step type (parameter widget)
        n = self._find_last_in_step(n,step_id)
        if chan_step_id is None:
            step_id = step_id + 1 #ID is one more than last step in que
            chan_step_id = 0
            #increment upward all subsequent steps for items already queued
            for step in self._controller.queue: #TODO: Fix this, sometimes increments the wrong steps (n is innacurate if selected step is not last in batch)
                if step._step_id >= step_id:
                    step._step_id +=1
        step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)        
        self._update_que_list(step,n+1)

    def _add_end(self):
        ''' Adds a new action step to complete when the prior is done'''
        if len(self._controller.queue) == 0:
            step_id = 0
        else:
            step_id = self._controller.queue[-1].step_id() +1
        chan_id = self.get_chan_id()
        chan_step_id = 0        
        step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)
        self._update_que_list(step,len(self._controller.queue))

    def _add_before(self):
        ''' Adds a new action step prior to the selected step'''
        step_id, chan_id, chan_step_id, n = self.check_basic() #returns step_id, chan_step_id, and n for selected existing step, returns chan_id based on selected step type (parameter widget)
        #increment upward all subsequent steps for items already queued
        for step in self._controller.queue: #TODO: Fix this, sometimes increments the wrong steps (n is innacurate if selected step is not last in batch)
            if step._step_id >= step_id:
                step._step_id +=1
        chan_step_id = 0        
        step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)
        self._update_que_list(step,n)

    def _delete(self):
        ''' Adds a new action step to complete when the prior is done'''
        n = self._main_step_selector.currentIndex()                           
        del_step = self._controller.queue.pop(n)
        step_id = del_step.step_id()  #use same ID as selected step
        concurrent_step = False
        for step in self._controller.queue: 
            if step._step_id == step_id:
                concurrent_step = True
        if not concurrent_step:
            for step in self._controller.queue: 
                if step._step_id > step_id:
                    step._step_id -=1
        self._update_que_list()

    def _add_to_step(self):
        ''' Adds a new action to start concurrently with an existing step or sub-step in the que'''
        step_id, chan_id, chan_step_id, n = self.check_basic()
        if chan_step_id is None:
            if chan_id == self._controller.queue[n].chan_id():
                chan_step_id = self._controller.queue[n].chan_step_id() #use same step_id if on the same channel
            else:
                chan_step_id = 0
        step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)
        self._update_que_list(step,n+1)

    def _update_que_list(self,step=None,n=None):
        if step is not None and n is not None:
            self._controller.queue.insert(n,step)
        self._que_list.clear()
        self._que_list += [str(stp) for stp in self._controller.queue]
        #Rebuild steps in the list      
        self._main_step_selector.clear()
        self._main_step_selector.addItems(self._que_list)

    def _edit_step(self):
        n = self._main_step_selector.currentIndex()
        
        if self._edit_step_button.text() == 'Edit Step':
            step = self._controller.queue[n]  
            if type(step) == TemperatureStep:
                self._step_type_selector.setCurrentText('Heater Step')
            elif type(step) == HoldStep:
                self._step_type_selector.setCurrentText('Hold Step')
            elif type(step) == FlowStep:
                self._step_type_selector.setCurrentText('MFC Step')
            elif type(step) == PumpStep:
                self._step_type_selector.setCurrentText('Pump Step')
            current_widget = self._parameter_stack.currentWidget()    
            if type(current_widget) == FlowParameters:
                mfc_list = current_widget._mfc_select.currentData()
                new_index = mfc_list.index(step._mfc.name)
                current_widget._mfc_select.setCurrentIndex(new_index)
                current_widget._target_input.setText(str(step._target))
                current_widget._rr_input.setText(str(step._ramp_rate))
            elif type(current_widget) == HoldParameters:
                current_widget._hold_time_input.setText(str(step._hold_time/60))
            elif type(current_widget) == PumpParameters:
                new_index = ['Pump Off', 'Pump Fill', 'Pump Drain'].index(step._pump_mode)
                current_widget._mode_select.setCurrentIndex(new_index)
            elif type(current_widget) == TemperatureParameters:
                current_widget._target_input.setText(str(step._target))
                current_widget._rr_input.setText(str(step._rr))
            self._edit_step_button.setText('Update Step')
        elif self._edit_step_button.text() == 'Update Step':
            current_widget = self._parameter_stack.currentWidget()
            old_step = self._controller.queue[n]
            step_id = old_step.step_id()
            if type(current_widget) == FlowParameters:
                chan_id = self.get_chan_id()
                if chan_id == old_step.chan_id():
                    chan_step_id = old_step.chan_step_id()
                else:
                    i=0
                    chan_step_id = 0
                    while i<n:
                        if self._controller.queue[i].step_id() == step_id:
                            if self._controller.queue[i].chan_id() == chan_id:
                                chan_step_id = self._controller.queue[i].chan_step_id() #make the chan step id same as the last of the same channel and step. Don't need to increment future ones
            else:
                chan_id = old_step.chan_id()
                chan_step_id = old_step.chan_step_id()
            step = self._parameter_stack.currentWidget().create_step(step_id,chan_id,chan_step_id)
            self._controller.queue[n] = step
            self._que_list[n] = str(step)
            #Rebuild steps in the list      
            self._main_step_selector.clear()
            self._main_step_selector.addItems(self._que_list)
            self._edit_step_button.setText('Edit Step')


    def _skip_step(self):
        #TODO, make sure this ends what is happening. Need to send stopfunction to EIS
        self._controller.skip_pressed = True

    @Slot()
    def _save_profile(self):
        #TODO update with channel ID and sub-steps
        dialog = ProfileSaveDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            profile_name = dialog.profile_name + '.yaml'

            steps = {}
            stepCount = 0
            for step in self._controller.queue:
                if type(step) == TemperatureStep:
                    steps[str(stepCount) + '_Temp'] = {}
                    steps[str(stepCount) + '_Temp']['furnace-name'] = str(step._temp_view.name)
                    steps[str(stepCount) + '_Temp']['ramp-rate'] = step._rr
                    steps[str(stepCount) + '_Temp']['target'] = step._target
                    steps[str(stepCount) + '_Temp']['steady-temp-tol'] = step._steady_temp_tol
                    steps[str(stepCount) + '_Temp']['step-id'] = step._step_id
                    steps[str(stepCount) + '_Temp']['chan-id'] = step._chan_id
                    steps[str(stepCount) + '_Temp']['chan-step-id'] = step._chan_step_id

                elif type(step) == FlowStep:
                    steps[str(stepCount) + '_Flow'] = {}
                    steps[str(stepCount) + '_Flow']['mfc-name'] = str(step._mfc.name)
                    steps[str(stepCount) + '_Flow']['ramp-rate'] = step._ramp_rate
                    steps[str(stepCount) + '_Flow']['target'] = step._target
                    steps[str(stepCount) + '_Flow']['step-id'] = step._step_id
                    steps[str(stepCount) + '_Flow']['chan-id'] = step._chan_id
                    steps[str(stepCount) + '_Flow']['chan-step-id'] = step._chan_step_id

                elif type(step) == HoldStep:
                    steps[str(stepCount) + '_Hold'] = {}
                    steps[str(stepCount) + '_Hold']['time'] = step._hold_time/60.0
                    steps[str(stepCount) + '_Hold']['step-id'] = step._step_id
                    steps[str(stepCount) + '_Hold']['chan-id'] = step._chan_id
                    steps[str(stepCount) + '_Hold']['chan-step-id'] = step._chan_step_id

                elif type(step) == EldexStep:
                    steps[str(stepCount) + '_Eldex'] = {}
                    steps[str(stepCount) + '_Eldex']['step-id'] = step._step_id
                    steps[str(stepCount) + '_Eldex']['chan-id'] = step._chan_id
                    steps[str(stepCount) + '_Eldex']['chan-step-id'] = step._chan_step_id
                
                stepCount += 1

            with open(PROFILE_PATH + profile_name,'w') as file:
                yaml.dump(steps,file,sort_keys=False)

    @Slot()
    def _load_profile(self):
        #TODO, if appending the profile to other steps in que, need to update the step numbers accordingly
        #TODO add loading pump steps and hold steps
        dialog = ProfileSelectionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            profileName = dialog.selectedProfile + '.yaml'

            self._controller.queue.clear()
            with open(PROFILE_PATH + profileName) as file:
                steps = yaml.safe_load(file)
            for step in steps:
                if 'Temp' in step:
                    temp_view = None
                    for view in self._temp_views:
                        if view.name == steps[step]['furnace-name']:
                            temp_view = view
                    ramp_rate = steps[step]['ramp-rate']
                    target = steps[step]['target']
                    steady_temp_tol = steps[step]['steady-temp-tol']
                    step_id = steps[step]['step-id']
                    chan_id = steps[step]['chan-id']
                    chan_step_id = steps[step]['chan-step-id']

                    if  temp_view is not None:
                        self._controller.queue.append(TemperatureStep(temp_view, 
                                                                      target, 
                                                                      ramp_rate,
                                                                      steady_temp_tol,
                                                                      step_id,
                                                                      chan_id,
                                                                      chan_step_id
                                                                      ))


                elif 'Flow' in step:
                    mfc_name = steps[step]['mfc-name']
                    ramp_rate = steps[step]['ramp-rate']
                    target = steps[step]['target']
                    step_id = steps[step]['step-id']
                    chan_id = steps[step]['chan-id']
                    chan_step_id = steps[step]['chan-step-id']
                    brk = False
                    for sect in self._mfcs:
                        for mfc, target_model, sp_model, rr_model in zip(self._mfcs[sect],
                                                                         self._target_models[sect],
                                                                         self._sp_models[sect],
                                                                         self._rr_models[sect]):
                            mfc:ElFlowMFC
                            if mfc.name == mfc_name:
                                self._controller.queue.append(FlowStep(target_model,
                                                                       rr_model, 
                                                                       sp_model, 
                                                                       mfc, 
                                                                       target, 
                                                                       ramp_rate,
                                                                       step_id,
                                                                       chan_id,
                                                                       chan_step_id
                                                                       ))
                                brk = True
                                break
                        if brk:
                            break

                elif 'Hold' in step:
                    holdTime = steps[step]['time']
                    step_id = steps[step]['step-id']
                    chan_id = steps[step]['chan-id']
                    chan_step_id = steps[step]['chan-step-id']

                    self._controller.queue.append(HoldStep(holdTime, step_id, chan_id, chan_step_id))

                elif 'Eldex' in step:
                    step_id = steps[step]['step-id']
                    chan_id = steps[step]['chan-id']
                    chan_step_id = steps[step]['chan-step-id']

                    self._controller.queue.append(EldexStep(step_id, chan_id, chan_step_id))

    @Slot()
    def _set_start(self):
        dialog = TimeSelectionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self._controller._start_time = dialog.selected_datetime
            self._set_start_time_button.setText('Starting at ' + str(self._controller._start_time))

    @Slot()
    def _handle_start(self):
        if not self._controller.paused.data:
            self._controller._start_time = None
            self._set_start_time_button.setText('Set Start Time')

    def close(self):
        print('closing profile view')
        self._controller.close()