from PySide6.QtCore import QObject, Signal, QTimer
from models import ListModel, SinglePointModel
import datetime

CONTROL_LOOP_FREQUENCY = 100
 
class Step():
    ''' Parent class for temperature, flow, pump and other step classes
    Each step class must have the following functions:
    start, is_complete, step_id, chan_id, chan_step_id'''

class ProfileController(QObject):
    queue_empty_sig = Signal()

    def __init__(self, parent:QObject = None):
        super().__init__(parent=parent)

        self._queue:ListModel[Step] = ListModel()
        self._channel_queue:ListModel[Step] = ListModel()
        self._active_steps:ListModel[Step] = ListModel()
        self._paused:SinglePointModel[bool] = SinglePointModel(True)
        self._start_time:datetime.datetime|None = None
        self._skip_pressed:bool = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._control_loop)
        self._timer.start(CONTROL_LOOP_FREQUENCY)

    @property
    def queue(self) -> ListModel[Step]:
        return self._queue
    
    @property
    def channel_queue(self) -> ListModel[Step]:
        return self._channel_queue
    
    @property
    def active_steps(self) -> ListModel[Step]:
        return self._active_steps
    
    @property
    def paused(self) -> SinglePointModel[bool]:
        return self._paused
    
    @property
    def skip_pressed(self) -> bool:
        return self._skip_pressed
    
    @skip_pressed.setter
    def skip_pressed(self, val:bool):
        self._skip_pressed = val

    def remove_completed(self, steps:ListModel[Step]):
        active_chans = []
        for step in steps.copy():
            if self._skip_pressed:
                if step._step_type == 'eis':
                    step.skip()#emit a signal to insturment controller to set the active step instrument stop model to true
                steps.remove(step)
            elif step.is_complete():
                steps.remove(step)
            elif step.chan_id() is not None:
                active_chans.append(step.chan_id())
        if self._skip_pressed:
            self._skip_pressed = False
        return active_chans

    def _start_substeps(self,active_chans):
        self._channel_queue.sort(key=lambda step : step.chan_step_id())
        for substep in self._channel_queue.copy():
            if substep.chan_id() not in active_chans:
                if not substep._step_type == 'eis' or not substep._instrument.active:
                    self._channel_queue.remove(substep)
                    self._active_steps.append(substep)
                    substep.start()
                elif substep._step_type == 'eis' and substep._instrument.active:
                    print('Waiting for octostat/loadbank device to complete previous active test')

    def _control_loop(self):
        '''This function i) checks if it is time to start running, 
        ii) removes from the list of running operations any tasks that have finished, 
        iii) starts new channel subtasks if they are part of the same global task and '''
        if self._start_time is not None and self._start_time <= datetime.datetime.now():
            self._paused.data = False
            self._start_time = None

        if len(self._active_steps)>0:
            #check which sub-steps are complete and remove from the active list
            active_chans = self.remove_completed(self._active_steps)
            #start substeps
            self._start_substeps(active_chans)

        if not self._paused.data and len(self._active_steps)==0 and len(self._queue) > 0:
            #Start or add to channel queue all steps with matching lowest step_id
            min_id = self._queue[0].step_id()
            # min_id = min([step.step_id() for step in self._queue])
            while len(self._queue) > 0 and self._queue[0].step_id() == min_id:
                step = self._queue.pop(0)                
                if step.chan_step_id() == 0:
                    if not step._step_type == 'eis' or not step._instrument.active:
                        self._active_steps.append(step)
                        step.start()
                    elif step._step_type == 'eis' and step._instrument.active:
                        print('Waiting for octostat/loadbank device to complete previous active test')
                else:
                    self._channel_queue.append(step)
            self.queue_empty_sig.emit()

    def close(self):
        print('closing profile controller')
        self._timer.stop()