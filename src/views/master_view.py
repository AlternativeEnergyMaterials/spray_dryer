import os
from PySide6.QtWidgets import QMainWindow, QWidget, QStackedWidget,  QDialog, QGridLayout, QVBoxLayout, QComboBox, QLineEdit, QPushButton
from PySide6.QtGui import QIcon, QFont, QAction
from PySide6.QtCore import Slot, QTimer
from widgets import CloseDialog, MultiPlotWidget, ToggleButton,  TestSelectionDialog
from views import TemperatureView, PressureView, ProfileView, MFCView, EISView, HumidifierView, LOADBANKView, LoadCellView, BPRView
from controllers import MasterController, TemperatureController
from models import ListModel
import yaml
from enum import Enum

class HeaterType(Enum):
    FURNACE = 'furnace'
    HUMIDIFIER = 'humidifier'

class MasterView(QMainWindow):
    def __init__(self, title:str, icon: QIcon, parent:QWidget = None):
        super().__init__(parent)
        self._title = title
        self.setWindowTitle(self._title)
        self._icon = icon
        self.setWindowIcon(self._icon)

        #Load config.
        config_path = os.path.expanduser("~") + "\\AppData\\Local\\AEM TestSuite\\config.yaml"
        with open(config_path) as file:
            self._config = yaml.safe_load(file)

        #Initialize models.
        self._humidifier_views:ListModel[TemperatureView] = ListModel()
        self._humidifier_controllers:ListModel[TemperatureController] = ListModel()
        self._furnace_views:ListModel[TemperatureView] = ListModel()
        self._furnace_controllers:ListModel[TemperatureController] = ListModel()

        #Create controller.
        self._controller = MasterController(self._config, self._furnace_controllers, self._humidifier_controllers, self)
        self._controller._download_data_worker.download_started.connect(self._download_started)
        self._controller._download_data_worker.download_finished.connect(self._download_finished)

        #Initialize UI elements.
        self._init_UI()

        #Add other pages.
        self._pressure_view:PressureView = None
        self._mfc_view:MFCView = None
        self._eis_view:EISView = None
        self._loadbank_view:LOADBANKView = None
        self._main_humidifier_view:HumidifierView = None
        self._main_humidifier_title:str = None
        self._main_furnace_view = None
        self._main_furnace_title:str = None
        self._loadcell_view:LoadCellView = None
        self._plenum_view:BPRView = None
        if self._controller.temperature_reader is not None:
            self._load_heaters(HeaterType.FURNACE)
            self._load_heaters(HeaterType.HUMIDIFIER)
        if self._controller.pressure_reader is not None and len(self._controller.pressure_reader.pressure_models) > 0:
            self._load_pressure()
        if self._controller.mfc_reader is not None and len(self._controller.mfc_reader.mfcs) > 0:
            self._load_mfc()
        
        # if 'plenum-config' in self._config and len(self._config['plenum-config']['plenums']) > 0 and self._mfc_view is not None and self._pressure_view is not None:
        #     self._load_plenums()
        if len(self._controller.octostats) > 0:
            self._load_eis()
        if len(self._controller.loadbanks) > 0:
            self._load_loadbank()
        if self._controller.cells is not None and len(self._controller.cells) > 0 and self._controller.cells[0] is not None:
            self._load_loadcells()

        #Populate home page.
        self._populate_home()

        #snapshot timer
        self.snap_timer = QTimer()
        self.snap_timer.start(60000)

    def _init_UI(self):
        #Set application font.
        self.setFont(QFont('Arial', 14))

        #Create toolbar for page selection.
        self._toolbar = self.addToolBar("Page Selection")
        self._toolbar.setMovable(False)

        #Create view stack and set as central widget. The view stack controls which page is displayed.
        self._view_stack = QStackedWidget(self)
        self.setCentralWidget(self._view_stack)

        #Create home page and add it to the view stack.
        self._home_page = QWidget(self)
        self._add_page(self._home_page, 'Home')

    def _populate_home(self):
        self._layout = QGridLayout()
        self._home_page.setLayout(self._layout)

        #Add furnace power button.
        self._furnace_power_button = ToggleButton(self._controller.furnace_safety_model, 'EMERGENCY STOP', 'Resume Operation', self)
        self._layout.addWidget(self._furnace_power_button,0,0,1,1)

        #Add humidifier power button.
        if self._controller.humidifier_safety_model is not None:
            self._humidifier_power_button = ToggleButton(self._controller.humidifier_safety_model, 'Humidifier Power: ON', 'Humidifier Power: OFF', self)
            self._layout.addWidget(self._humidifier_power_button,0,1,1,1)

        #Disable power buttons if no watchdog.
        if self._controller._watchdog is None and self._controller._control_box_type != 'Pi':
            self._furnace_power_button.setEnabled(False)
            self._humidifier_power_button.setEnabled(False)

        #Add testname input.
        self._testname_input = QLineEdit(self)
        self._testname_input.setPlaceholderText('Test Name')
        self._layout.addWidget(self._testname_input,0,5,1,1)

        #Add measurement select.
        self._measurement_select = QPushButton(self)
        self._measurement_select.setText('Select Existing Test')
        self._measurement_select.clicked.connect(self._update_testname_input)
        self._layout.addWidget(self._measurement_select,0,6,1,1)

        #Add start recording button.
        self._recording_button = QPushButton(self)
        self._recording_button.setText('Start Recording')
        self._recording_button.clicked.connect(self._start_recording)
        self._layout.addWidget(self._recording_button,0,7,1,1)

        #Add download data button.
        self._download_data_button = QPushButton(self)
        self._download_data_button.setText('Download Data')
        self._download_data_button.clicked.connect(self._controller.select_measurement)
        self._layout.addWidget(self._download_data_button,0,8,1,1)

        #Add reload mfc button.
        self._reload_mfc_button = QPushButton(self)
        self._reload_mfc_button.setText('Reload MFCs')
        self._reload_mfc_button.clicked.connect(self._controller.mfc_reader.reload)
        self._layout.addWidget(self._reload_mfc_button,0,9,1,1)

        #Add multiplot view.
        self._multi_plot = MultiPlotWidget(self)
        plots = []
        for view in self._furnace_views + self._humidifier_views:
            plots.append(view.plot)
        if self._mfc_view is not None:
            plots += self._mfc_view.plots
        self._multi_plot.set_plots(plots)
        self._layout.addWidget(self._multi_plot,1,0,1,6)

        #Add profile view.
        temp_views = self._furnace_views + self._humidifier_views
        if len(temp_views) < 1:
            temp_views = None

        if self._mfc_view is not None:
            mfcs = self._controller._mfc_reader.mfcs
            target_models = self._mfc_view.controller.target_models
            sp_models = self._mfc_view.controller.sp_models
            rr_models = self._mfc_view.controller.rr_models
            
        else:
            mfcs = None
            target_models = None
            sp_models = None
            rr_models = None

        if self._eis_view is not None:
            instrument_controller = self._eis_view._controller
        else:
            instrument_controller = None

        self._profile_view = ProfileView(temp_views, mfcs, instrument_controller, target_models, sp_models, rr_models, self._main_humidifier_view, self._config, self)
        self._controller.pause_profile.connect(self._pause_profile)
        self._layout.addWidget(self._profile_view,1,6,1,4)

    @Slot()
    def _start_recording(self):
        self._testname_input.setDisabled(True)
        self._controller.test_name_model.data = 'default-test' if self._testname_input.text() == '' else self._testname_input.text()
        self._controller.is_recording_model.data = True
        self._recording_button.setText('Stop Recording')
        self._recording_button.clicked.disconnect()
        self._recording_button.clicked.connect(self._stop_recording)

    @Slot()
    def _stop_recording(self):
        self._controller.is_recording_model.data = False
        self._testname_input.setEnabled(True)
        self._recording_button.setText('Start Recording')
        self._recording_button.clicked.disconnect()
        self._recording_button.clicked.connect(self._start_recording)

    @Slot()
    def _pause_profile(self):
        self._profile_view._controller.paused.data = True

    def _add_page(self, view:QWidget, name:str):
        """Adds a view to the view stack and makes it a selectable page on the toolbar"""
        index = self._view_stack.addWidget(view)
        print('Main view page index ' + str(index) + ' added')
        action = QAction(name, self)
        action.triggered.connect(lambda:self._view_stack.setCurrentIndex(index))
        self._toolbar.addAction(action)

    def _load_heaters(self, heater_type:HeaterType):
        heater_type:str = heater_type.value
        time_model = eval('self._controller.temperature_reader.' + heater_type + '_tc_time_model')
        all_models = eval('self._controller.temperature_reader.all_' + heater_type + '_models')
        all_names = eval('self._controller.temperature_reader.all_' + heater_type + '_tc_display_names')
        control_map = eval('self._controller.temperature_reader.' + heater_type + '_control_map')
        num_heaters = len(all_names) #Any all_* list can be used here.
        if self._controller._control_box_type == 'NI':
            safety_model = eval('self._controller.' + heater_type + '_safety_model')
        else:
            safety_model = self._controller.furnace_safety_model

        if num_heaters > 0:
            #Create all temperature views
            for i in range(num_heaters):
                name = heater_type.capitalize() + ' ' + str(i+1) if num_heaters > 1 else heater_type.capitalize()
                view = TemperatureView(time_model,
                                       all_models[i],
                                       control_map,
                                       all_names[i],
                                       self._controller.voltage_writer,
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['identifier'],
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['voltage-line'],
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['supervisor-furnace'],
                                       safety_model,
                                       self._config[heater_type + '-config'],
                                       eval('self._' + heater_type + '_controllers'),
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['p'],
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['i'],
                                       self._config[heater_type + '-config'][heater_type + 's'][i]['d'],
                                       name)
                view.controller.under_temp.connect(self._controller._handle_under_temp)
                eval('self._' + heater_type + '_views').append(view)
                eval('self._' + heater_type + '_controllers').append(view.controller)

            #Load heaters in stack if in tuning mode and there are multiple heaters.
            if self._config[heater_type + '-config']['tuning-mode'] and num_heaters > 1:
                page = QWidget(self)
                layout = QVBoxLayout()
                page.setLayout(layout)
                heater_select = QComboBox(page)
                heater_stack = QStackedWidget(page)
                layout.addWidget(heater_select)
                layout.addWidget(heater_stack)
                for i, view in enumerate(eval('self._' + heater_type + '_views')):
                    heater_stack.addWidget(view)
                    heater_select.addItem(heater_type.capitalize() + ' ' + str(i+1))
                heater_select.currentIndexChanged.connect(lambda:heater_stack.setCurrentIndex(heater_select.currentIndex()))
                title = heater_type.capitalize() + 's'

            #Otherwise load all heaters on the same page.
            else:
                page = QWidget(self)
                layout = QVBoxLayout()
                page.setLayout(layout)
                for view in eval('self._' + heater_type + '_views'):
                    layout.addWidget(view)
                title = heater_type.capitalize() + 's' if num_heaters > 1 else heater_type.capitalize()
            
            if heater_type == 'humidifier':
                if self._mfc_view is None:
                    target_models = {}
                    sp_models = {}
                    mfcs = {}
                else:
                    target_models = self._mfc_view.controller.target_models
                    sp_models = self._mfc_view.controller.sp_models
                    mfcs = self._mfc_view.controller._mfcs
                    
                writer = self._controller.voltage_writer
                self._main_humidifier_view = HumidifierView(page,
                                                 self._humidifier_controllers,
                                                 self._config['humidifier-pump-config'],
                                                 writer,
                                                 mfcs,
                                                 target_models,
                                                 sp_models,
                                                 self)
                self._main_humidifier_title = title
                self._add_page(self._main_humidifier_view, title)
            else:
                self._main_furnace_view = page
                self._main_furnace_title = title
                self._add_page(page, title)

    def _load_pressure(self):
        if self._controller.pressure_reader is not None:
            if 'bpr-config' in self._config:
                bpr_view = BPRView(self._controller._bpr,
                                    [self._controller.pressure_reader.channel_model_map[channel] for channel in self._config['bpr-config']['control-transducers']],
                                    self._controller.pressure_reader.time_model,self._config['bpr-config'],self)
            else:
                bpr_view = None
            self._pressure_view = PressureView(bpr_view,self._controller.pressure_reader.time_model,
                                self._controller.pressure_reader.pressure_models,
                                self._controller.pressure_reader.slope_models,
                                self._controller.pressure_reader.intercept_models,
                                self._controller.pressure_reader.pressure_display_names,
                                self._config['pressure-config'],'Pressure',
                                self)
            self._add_page(self._pressure_view, 'Pressure')

    def _load_mfc(self):
        self._mfc_view = MFCView(self._controller.mfc_reader.time_model,
                    self._controller.mfc_reader.flow_models,
                    self._controller.mfc_reader.mfcs,
                    self)
        self._mfc_view.controller._ramp_worker.flow_deviation.connect(self._controller._handle_flow_deviations)
        self._add_page(self._mfc_view, 'Gas Flow')

    # def _load_plenums(self):
    #     plenum_views = []
    #     for i, plenum in enumerate(self._config['plenum-config']['plenums']):
    #         if plenum is not None:
    #             plenum_view = PlenumView(self._controller.pressure_reader.time_model,
    #                                         [self._controller.pressure_reader.channel_model_map[channel] for channel in plenum['control-transducers']],
    #                                         [self._controller.pressure_reader.channel_model_map[channel] for channel in plenum['tracking-transducers']],
    #                                         [self._controller.pressure_reader.channel_name_map[channel] for channel in plenum['control-transducers']],
    #                                         [self._controller.pressure_reader.channel_name_map[channel] for channel in plenum['tracking-transducers']],
    #                                         [self._mfc_view.controller.name_target_model_map[name] for name in plenum['mfcs']],
    #                                         self._config['plenum-config'],
    #                                         plenum['p'], plenum['i'], plenum['d'],
    #                                         'Plenum ' + str(i), self)
    #             plenum_views.append(plenum_view)
    #     self._plenum_view = BPRView(plenum_views,self._controller._bpr,
    #                                 [self._controller.pressure_reader.channel_model_map[channel] for channel in self._config['plenum-config']['control-transducers']],
    #                                 self._controller.pressure_reader.time_model,
    #                                 self._config['plenum-config'],self)
    #     self._plenum_view._controller._duty_cycle_worker.safety_shutoff.connect(self._controller._emit_bpr_alerts)
    #     self._add_page(self._plenum_view, 'Plenum')

    def _load_eis(self):
        self._eis_view = EISView(self._controller._ivium, self._controller.octostats, 'EIS', self)
        self._add_page(self._eis_view, 'EIS')

    def _load_loadbank(self):
        lb_keys = list(self._config['loadbank-config']['loadbanks'].keys())
        self._loadbank_view = LOADBANKView(self._controller.loadbanks, 'Loadbank',self._config['loadbank-config']['loadbanks'][lb_keys[0]], self)
        self._add_page(self._loadbank_view, 'Loadbank')

    def _load_loadcells(self):
        self._loadcell_view = LoadCellView(self._controller.cells, self._controller._ssh_client, self)
        self._add_page(self._loadcell_view, 'Load Cells')

    def _download_started(self):
        self._download_data_button.setDisabled(True)
        self._download_data_button.setText('Download In Progress')

    def _download_finished(self):
        self._download_data_button.setEnabled(True)
        self._download_data_button.setText('Download Data')

    def _update_testname_input(self):
        dialog = TestSelectionDialog(self._controller.measurements)

        if dialog.exec_() == QDialog.Accepted:
            selected_measurement = dialog.selected_measurement
            if selected_measurement:
                self._testname_input.setText(selected_measurement)

    def closeEvent(self, event):
        """Overrides the close event."""
        #Ask the user if they are sure they want to close the application.
        print('in close event of master view')
        dialog = CloseDialog(self._title, self)
        close = dialog.exec()
        if close == QDialog.Rejected:
            event.ignore()
        else: #Handle close event if user accepts.            
            self._profile_view.close()
            for view in self._furnace_views:
                view.close()
            for view in self._humidifier_views:
                view.close()
            if self._pressure_view is not None:
                self._pressure_view.close()
            if self._mfc_view is not None:
                self._mfc_view.close()
            if self._main_humidifier_view is not None:
                self._main_humidifier_view.close()
            if self._loadcell_view is not None:
                self._loadcell_view.close()
            self._controller.close() #Close this last.
