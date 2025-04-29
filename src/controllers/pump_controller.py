from PySide6.QtCore import QObject, Slot, QTimer, Signal
from models import ListModel, SinglePointModel
from controllers import TemperatureController
from devices import PWMWriter
import time

FILL = "Fill"
OFF = "Off"
DRAINING = "Draining"
DRAINED = "Drained"
LOWERING_TEMPS = "Preparing For Drain (1/2)"
LOWERING_FLOWS = "Preparing For Drain (2/2)"
CONTROL_LOOP_FREQUENCY = 100

class PumpController(QObject):
    shut_off = Signal()

    def __init__(self, temp_controllers:ListModel[TemperatureController], fill_line:int, drain_line:int, voltage_writer:PWMWriter,
                 mfc_targets:dict[int,ListModel[SinglePointModel[float]]], mfc_setpoints:dict[int,ListModel[SinglePointModel[float]]],
                 config:dict, parent:QObject = None):
        super().__init__(parent=parent)
        self._config = config
        self._drain_time = self._config['drain-time']
        self._temp_controllers = temp_controllers
        self._fill_line = fill_line
        self._drain_line = drain_line
        self._voltage_writer = voltage_writer
        self.ON = 100
        self.OFF = 0
        self._mfc_targets = mfc_targets
        self._mfc_setpoints = mfc_setpoints
        self._drain_start = None
        self._saved_targets:dict[int,list[SinglePointModel[float]]] = None

        self._status_model:SinglePointModel[str] = SinglePointModel(OFF)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._control_loop)
        self._timer.start(CONTROL_LOOP_FREQUENCY)

    @property
    def status_model(self) -> SinglePointModel[str]:
        return self._status_model

    @Slot(bool)
    def pump_off_toggled(self, checked:bool):
        if checked:
            self._status_model.data = OFF

            #Bring MFCs to originals targets
            if self._saved_targets is not None:
                for sect in self._mfc_targets:
                    for target_model, saved_target in zip(self._mfc_targets[sect], self._saved_targets[sect]):
                        target_model:SinglePointModel[float]
                        saved_target:float
                        target_model.data = saved_target
                self._saved_targets = None

    @Slot(bool)
    def pump_fill_toggled(self, checked:bool):
        if checked:
            self._status_model.data = FILL
            self._voltage_writer.write(self._fill_line, self.ON)

            #Bring MFCs to originals targets
            if self._saved_targets is not None:
                for sect in self._mfc_targets:
                    for target_model, saved_target in zip(self._mfc_targets[sect], self._saved_targets[sect]):
                        target_model:SinglePointModel[float]
                        saved_target:float
                        target_model.data = saved_target
                self._saved_targets = None
        else:
            self._voltage_writer.write(self._fill_line, self.OFF)

    @Slot(bool)
    def pump_drain_toggled(self, checked:bool):
        if checked:
            self._status_model.data = LOWERING_TEMPS

            #Lower humidifier temps
            for temp_controller in self._temp_controllers:
                temp_controller:TemperatureController
                temp_controller.stop_heating()
        else:
            self._voltage_writer.write(self._drain_line, self.OFF)

    @Slot()
    def _control_loop(self):
        if self._status_model.data == LOWERING_TEMPS and self._humidifiers_cool():
            self._status_model.data = LOWERING_FLOWS

            #Lower flowrates and save targets
            self._saved_targets = {}
            for sect in self._mfc_targets:
                if sect not in self._saved_targets:
                    self._saved_targets[sect] = []
                for target_model in self._mfc_targets[sect]:
                    target_model:SinglePointModel[float]
                    self._saved_targets[sect].append(target_model.data)
                    target_model.data = 0.0


        if self._status_model.data == LOWERING_FLOWS and self._flows_off():
            self._status_model.data = DRAINING

            self._voltage_writer.write(self._drain_line, self.ON)
            self._drain_start = time.time()

        if self._status_model.data == DRAINING and (time.time() - self._drain_start) >= self._drain_time:
            self.shut_off.emit()
            self._status_model.data = DRAINED

    def _humidifiers_cool(self) -> bool:
        cool = True
        for temp_controller in self._temp_controllers:
            temp_controller:TemperatureController
            if temp_controller.control_temp >= 60:
                cool = False
        return cool
    
    def _flows_off(self) -> bool:
        off = True
        for sect in self._mfc_setpoints:
            for sp_model in self._mfc_setpoints[sect]:
                sp_model:SinglePointModel[float]
                if sp_model.data > 5:
                    off = False
        return off

    def close(self):
        print('closing humidifier controller')
        self._timer.stop()