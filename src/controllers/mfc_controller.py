from PySide6.QtCore import QObject, QThread, QTimer, Slot, Signal
from devices import ElFlowMFC
from models import ListModel, SinglePointModel
import time

CONTROL_LOOP_FREQUENCY = 100
DEFAULT_RAMP_RATE = 5.0
DEFAULT_TARGET = 0.0

class RampWorker(QObject):
    flow_deviation = Signal(str)

    def __init__(self, mfcs:dict[int,ListModel[ElFlowMFC]], target_models:dict[int,ListModel[SinglePointModel[float]]], sp_models:dict[int,ListModel[SinglePointModel[float]]],
                 rr_models:dict[int,ListModel[SinglePointModel[float]]], parent:QObject = None):
        super().__init__(parent=parent)
        self._mfcs = mfcs
        self._target_models = target_models
        self._sp_models = sp_models
        self._rr_models = rr_models #Ramp rate in sccm/sec
        self._last_time = None

    @Slot()
    def ramp_mfcs(self):
        now = time.time()
        dt = now - self._last_time if self._last_time else 1.0 #Use 1 second for initial dt
        self._last_time = now

        for sect in self._target_models:
            for mfc, target_model, sp_model, rr_model in zip(self._mfcs[sect],
                                                             self._target_models[sect],
                                                             self._sp_models[sect],
                                                             self._rr_models[sect]):
                mfc:ElFlowMFC
                target_model:SinglePointModel[float]
                sp_model:SinglePointModel[float]
                rr_model:SinglePointModel[float]

                #Catch the set point and set it to the target if it gets within .125 step sizes of the target.
                if sp_model.data != target_model.data and abs(target_model.data-sp_model.data) <= rr_model.data*0.125:
                    sp_model.data = target_model.data

                #Increment the set point if it's below the target.
                elif sp_model.data < target_model.data:
                    sp_model.data = sp_model.data + (rr_model.data * dt)

                #Decrement the set point if it's above the target.
                elif sp_model.data > target_model.data:
                    sp_model.data = sp_model.data - (rr_model.data * dt)

                # if sp_model.data!=0.0 and abs(mfc.flow_rate - sp_model.data)/sp_model.data  >= 0.1: #if deviation is >= 10% #TODO: Reimplement, only raise error if happening for 10s
                #     self.flow_deviation.emit(mfc.name)


class MFCController(QObject):
    request_ramp = Signal()
    def __init__(self, mfcs:dict[int,ListModel[ElFlowMFC]], parent:QObject = None):
        super().__init__(parent=parent)
        self._mfcs = mfcs
        self._sp_models:dict[int,ListModel[SinglePointModel[float]]] = {}
        self._rr_models:dict[int,ListModel[SinglePointModel[float]]] = {}
        self._target_models:dict[int,ListModel[SinglePointModel[float]]] = {}
        self._name_target_model_map:dict[str,SinglePointModel[float]] = {}

        for sect in self._mfcs:
            if sect not in self._sp_models:
                self._sp_models[sect] = ListModel()
                self._rr_models[sect] = ListModel()
                self._target_models[sect] = ListModel()
            for mfc in self._mfcs[sect]:
                mfc:ElFlowMFC
                sp_model = SinglePointModel(mfc.setpoint)
                sp_model.data_changed.connect(self._create_sp_update_func(mfc, sp_model))
                self._sp_models[sect].append(sp_model)
                self._rr_models[sect].append(SinglePointModel(DEFAULT_RAMP_RATE))
                target_model = SinglePointModel(DEFAULT_TARGET)
                self._target_models[sect].append(target_model)
                self._name_target_model_map[mfc.name] = target_model

        #Initialzie ramp thread.
        self._ramp_worker = RampWorker(self._mfcs, self._target_models, self._sp_models, self._rr_models)
        self.request_ramp.connect(self._ramp_worker.ramp_mfcs)
        self._ramp_thread = QThread(self)
        self._ramp_worker.moveToThread(self._ramp_thread)
        self._ramp_thread.start()

        #Initialize control loop.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._control_loop)
        self._timer.start(CONTROL_LOOP_FREQUENCY)

    def _create_sp_update_func(self, mfc:ElFlowMFC, sp_model:SinglePointModel[float]) -> callable:
        def update_sp():
            mfc.setpoint = sp_model.data
        return update_sp
    
    @property
    def sp_models(self) -> dict[int,ListModel[SinglePointModel[float]]]:
        return self._sp_models
    
    @property
    def rr_models(self) -> dict[int,ListModel[SinglePointModel[float]]]:
        return self._rr_models
    
    @property
    def target_models(self) -> dict[int,ListModel[SinglePointModel[float]]]:
        return self._target_models

    @property
    def name_target_model_map(self):
        return self._name_target_model_map

    def _control_loop(self):
        self.request_ramp.emit()

    def close(self):
        print('closing mfc controller')
        self._timer.stop()
        self._ramp_thread.quit()