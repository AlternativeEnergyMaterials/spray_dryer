import propar
from PySide6.QtCore import QObject, QMutex, QMutexLocker, Signal

class ElFlowMFC(QObject):
    update_display = Signal()

    def __init__(self, comport:str, disconnected:bool = False, name:str = 'N/A'):
        super().__init__(parent=None)
        self._comport = comport
        self._conversion_factor:float = 1.0
        self._saved_setpoint = 0.0
        self._mutex = QMutex()
        self._disconnected = disconnected
        self._instrument = None

        if not disconnected:
            #Attempt to initialize connection with MFC
            self._instrument = propar.instrument(comport)
            if self._instrument.readParameter(90) != "DMFC":
                    self._instrument.master.stop()
                    raise IOError('Device is not an ElFlow MFC')

            #Set control mode to RS232 and initialize variables.
            self._instrument.writeParameter(12,18)
            self.setpoint = 0

            #Load static variables from MFC
            self._name = self._instrument.readParameter(115)
            self._unit = str(self._instrument.readParameter(129)).strip()
            self._max_capacity = self._instrument.readParameter(21)
        else:
            self._name = name
            self._unit = 'disconnected'
            self._max_capacity = 'N/A'

    @property
    def conversion_factor(self) -> float:
        if not self._disconnected:
            return self._conversion_factor
        else:
            return 0.0
    
    @conversion_factor.setter
    def conversion_factor(self, val:float) -> None:
        self._conversion_factor = val

    @property
    def name(self) -> str:
        """Name of the MFC."""
        return self._name
    
    @property
    def unit(self) -> str:
        """Unit of flowrate"""
        return self._unit
    
    @property
    def max_capacity(self) -> float:
        """Maximum flow rate capacity of the MFC in sccm."""
        try:
            if not self._disconnected:
                return self._max_capacity / self._conversion_factor
            else:
                return 0.0
        except:
            return 0.0
    
    @property
    def flow_rate(self) -> float:
        """Current flow rate of the MFC in sccm."""
        with QMutexLocker(self._mutex):
            try:
                if not self._disconnected:
                    ret = self._instrument.readParameter(205) / self._conversion_factor
                else:
                    ret = 0.0
            except:
                ret = 0.0
        return ret
    
    @property
    def setpoint(self) -> float:
        """Flow rate setpoint of the MFC in sccm."""
        with QMutexLocker(self._mutex):
            try:
                if not self._disconnected:
                    ret = self._instrument.readParameter(206) / self._conversion_factor
                else:
                    ret = 0.0
            except:
                ret = 0.0
        return ret
    
    @setpoint.setter
    def setpoint(self, new_sp:float):
        with QMutexLocker(self._mutex):
            try:
                if not self._disconnected:
                    success = self._instrument.writeParameter(206, new_sp * self._conversion_factor)
                    if not success:
                        raise IOError('Could not change setpoint of MFC')
            except Exception as e:
                print(e)

    def identify(self) -> bool:
        """Makes the MFC blink its LEDs for 5 seconds."""
        with QMutexLocker(self._mutex):
            if not self._disconnected:
                ret = self._instrument.writeParameter(1,5)
            else:
                ret = False
        return ret
    
    def disconnect(self):
        self._saved_setpoint = self.setpoint
        self.setpoint = 0
        if self._instrument is not None:
            self._instrument.master.propar.serial.close()
            self._instrument = None
        self._disconnected = True
        self._unit = 'disconnected'
        self._max_capacity = 'N/A'
        self.update_display.emit()

    def reconnect(self, inst:propar.instrument):
        print('reconnecting',self._name)
        self._instrument = inst
        self._disconnected = False
        self.setpoint = self._saved_setpoint
        self._unit = str(self._instrument.readParameter(129)).strip()
        self._max_capacity = self._instrument.readParameter(21)
        self.update_display.emit()

    def close(self):
        """Close device connection."""
        print('closing mfc ' + self.name)
        if not self._disconnected:
            self.setpoint = 0
            self._instrument.master.propar.serial.close()