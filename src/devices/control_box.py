from PySide6.QtCore import QMutex, QTimer, QObject, QThread, Slot, Signal
from devices import SSHClient


PWM_WRITE_FREQUENCY = 1000

class ControlBox:
    '''groups NIcontrolBox and PICOntrolBox. Grouping only needed in temperature reader
    Both types of control boxes need the following functions:
    
    write_voltage(self, line:int, value:bool|int)
    voltage_off(self)
    add_thermocouples(self, thermocouples:list[dict])
    read_all_thermocouples(self) -> list[float]
    close(self)'''

class PWMWorker(QObject):
    restart_sig = Signal()
    unsafe_sig = Signal()

    def __init__(self, pwms:dict[int,int], write_client:SSHClient, parent:QObject = None):
        super().__init__(parent=parent)
        self._pwms = pwms
        self._write_client = write_client
        self._is_running = False
        self._restart_count:int = 0

    @Slot()
    def update_pwms(self):
        self._is_running = True
        if len(self._pwms) > 0:
            channels = str(list(self._pwms.keys())).replace(' ','').strip('[]')
            pwm_vals = str(list(self._pwms.values())).replace(' ','').strip('[]')
            cmd = 'pwm ' + channels + ' ' + pwm_vals
            cmd = 'echo -n "' + cmd + '" | socat - UNIX-CONNECT:/tmp/pwm.sock'
            response = self._write_client.exec_command(cmd)

            if response != 'is_alive':
                print(cmd)
                print(response)
                if self._restart_count < 2:
                    self.restart_sig.emit()
                    self._restart_count += 1
                elif self._restart_count < 3:
                    print('pwm failed 3 times, declaring unsafe')
                    self.unsafe_sig.emit()
                    self._restart_count += 1
            else:
                self._restart_count = 0

        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

class PiControlBox(ControlBox):
    def __init__(self, read_client:SSHClient, write_client:SSHClient, mask_enabled:bool): #TODO: Support write client and read client
        self._mutex = QMutex()
        self._mask_enabled = mask_enabled

        self._read_client = read_client
        self._read_client.exec_command('pkill -f python')
        self._read_client.exec_command('python tcreader.py &')
        self._write_client = write_client
        if write_client != read_client:
            self._write_client.exec_command('pkill -f python')
        self._write_client.exec_command('python pwm.py &')
        self._write_client.exec_command('python pwm_watchdog.py &')

        self._thermocouples:list[tuple[str,str,str,float]] = []

        self._pwms:dict[int,int] = {}
        self._pwm_worker = PWMWorker(self._pwms, self._write_client)
        self._pwm_worker.restart_sig.connect(self._restart_pwm)
        self._voltage_thread = QThread()
        self._pwm_worker.moveToThread(self._voltage_thread)
        self._voltage_thread.finished.connect(self._pwm_worker.deleteLater)
        self._voltage_thread.start()

        self._pressure_transducers:list[dict] = []

        self._timer = QTimer()
        self._timer.timeout.connect(self._pwm_worker.update_pwms)
        self._timer.start(PWM_WRITE_FREQUENCY)

    def write_voltage(self, line: int, value:int):
        """Write a pwm value to a relay channel.\n
        line - Relay channel to write. Range varies.\n
        value - Value to write. Int between 0 and 100 inclusive.\n
        """
        self._pwms[line] = value

    def voltage_off(self):
        """Turn off all voltage outputs."""
        cmd = 'python relay_shutoff.py'
        self._write_client.exec_command(cmd)

    def add_thermocouples(self, thermocouples:list[dict]):
        """Add thermocouples to be read from read_all_thermocouples.\n
        thermocouples - List of dictionaries containing thermocouple information.
        """
        for thermocouple in thermocouples:
            board, channel = thermocouple['channel'].split('-')
            mask = thermocouple['mask'] if 'mask' in thermocouple else None
            offset = thermocouple['offset'] if 'offset' in thermocouple else 0.0
            self._thermocouples.append((board, channel, mask, offset))


    def read_all_thermocouples(self) -> list[float]:
        """Returns a list of temperatures from all loaded thermocouples.\n
        If a thermocouples is disconnected its temperature will read 0.0.
        """
        try:
            if self._mask_enabled:
                ai_temps = self._task_ai.read()
            response:str = self._read_client.exec_command('echo -n "tcreader" | socat - UNIX-CONNECT:/tmp/tcreader.sock')
            temp_dict = eval(response.strip())
            temps = []
            for board, channel, mask, offset in self._thermocouples:
                if self._mask_enabled and mask is not None:
                    temps.append(ai_temps[self._mask_index_map[mask]])
                else:
                    temps.append(temp_dict[int(board)][int(channel)-1] + offset)
            return temps
        except Exception as e:
            print(e)
            return []
        
    @Slot()
    def _restart_pwm(self):
        print('restarting pwm.py')
        self._write_client.exec_command('pkill -f pwm.py')
        self._write_client.exec_command('python pwm.py &')

    def close(self):
        print('closing pi control box')
        self._timer.stop()
        while self._pwm_worker.is_running:
            pass
        self._voltage_thread.quit()
        self._read_client.exec_command('pkill -f python')
        self._write_client.exec_command('pkill -f python')
        self.voltage_off()
