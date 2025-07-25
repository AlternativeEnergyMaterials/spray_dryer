import os
import psutil
from PySide6.QtCore import QObject, QThread, Slot, Signal, QTimer
from PySide6.QtWidgets import QDialog
from devices import PiControlBox,TemperatureReader, SSHClient,  MFCReader
from devices import PWMWriter
from models import SinglePointModel, ListModel
from controllers import TemperatureController
from widgets import TestSelectionDialog, WarningDialog
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WriteApi
from influxdb_client.client.write_api import SYNCHRONOUS
import serial
import time
from multiprocessing import Process
import pandas as pd
from smtp2go.core import Smtp2goClient

CONTROL_LOOP_FREQUENCY = 1000 #Milliseconds between control loop calls.

BUCKET = 'TESTS' #Write bucket for influx data.
INFLUX_FILE = os.path.expanduser('~') + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\startInflux.vbs'
TESTS_PATH = os.path.expanduser('~') + '\\AppData\\Local\\AEM SprayDyer\\Tests\\'

SECOND_RELAY_SIG = bytearray([0x04, 0x07, 0x03, 0x08, 0x02]) #signal to reset watchdog timer for second relay (furnace)
PI_RELAY_SIG = b'reset\n'
PI_ESTOP_SIG = b'check_estop\n'

def download_data(url:str, token:str, org:str, measurement:str):
        print('Data download started')
        try:
            if measurement is not None:
                client = InfluxDBClient(url=url,
                                        token=token,
                                        org=org)

                query = 'from(bucket: "TESTS") |> range(start: 0) |> filter(fn: (r) => r["_measurement"] == "' + measurement + '")'

                result = client.query_api().query(query)

                data = []
                for table in result:
                    for record in table.records:
                        data.append(record.values)

                df = pd.DataFrame(data)
                df = df[["_time","_value","DeviceName","_field"]].sort_values('_time') # remove insignificant data and sort by time

                df["_time"] = df["_time"].dt.tz_convert(datetime.now().astimezone().tzinfo).dt.tz_localize(None) # ensure timezones are local when downloaded, also makes them look nicer

                df = df.pivot(index="_time",columns=["DeviceName","_field"],values="_value") # pivot dataframe so identifier columns are combined
                df.columns = ['_'.join(col) if col[0] != '_time' else col[0] for col in df.columns] # squish headers together into one row

                #organize columns
                cellCols = [col for col in df.columns if "Cell" in col] # get Cell devices
                cellCols.sort()

                stepCols = [col for col in df.columns if "Step" in col] # get Step devices
                stepCols.sort()

                furnaceCols = [col for col in df.columns if "Furnace" in col] # get Furnace devices
                furnaceCols.sort()

                nameCols = [col for col in cellCols if "Name" in col] # split Cell_Name cols
                cellCols = [col for col in cellCols if col not in nameCols] # remove Cell_Name cols from regular Cell cols

                otherCols = [col for col in df.columns if "Cell" not in col and "Step" not in col and "Furnace" not in col and "Name" not in col]
                otherCols.sort()

                df = df[furnaceCols + cellCols + stepCols + nameCols + otherCols] # repopulate dataframe in correct order

                df.to_csv(TESTS_PATH + measurement + ".csv") # save as csv
        except Exception as e:
            print('Data download failed:',e)
        else:
            print('Data download completed')

class DownloadDataWorker(QObject):
    download_started = Signal()
    download_finished = Signal()

    """A worker object for managing the download data process"""
    def __init__(self, parent:QObject = None):
        super().__init__(parent=parent)
        self._is_running = False

    @Slot(str,str,str,str)
    def download_data(self, url:str, token:str, org:str, measurement:str):
        self.download_started.emit()
        proc = Process(target=download_data, args=(url, token, org, measurement,)) 
        proc.start()
        proc.join()
        self.download_finished.emit()

class CheckInfluxWorker(QObject):
    """A worker object to ensure InfluxDB is running."""
    def __init__(self, parent:QObject = None):
        super().__init__(parent=parent)
        self._is_running = False

    @Slot()
    def check_influx(self):
        self._is_running = True
        try:
            p_list = [process.name() for process in psutil.process_iter()]
            if 'influxd.exe' in p_list:
                influx_running = True
            else:
                influx_running = False
            if not influx_running:
                print('influx not running, restarting')
                os.startfile(INFLUX_FILE)
        except:
            print('Error when checking if influxd is running')
        self._is_running = False

    @property
    def is_running(self):
        return self._is_running

class WatchdogWorker(QObject):
    """A worker object to send watchdog signals."""
    def __init__(self, watchdog:serial.Serial, furnace_safety_model:SinglePointModel[bool], parent:QObject = None):
        super().__init__(parent=parent)
        self._watchdog = watchdog
        self._furnace_safety_model = furnace_safety_model
    @Slot()
    def signal_watchdog(self):
        if self._furnace_safety_model.data:
            self._write_watchdog(SECOND_RELAY_SIG)

    def _write_watchdog(self, signal:bytearray):
        self._watchdog.write(signal)
        time.sleep(0.2)

class TempCollectionWorker(QObject):
    temp_restart_sig = Signal()

    """A worker object to handle temperature data collection."""
    def __init__(self, temp_reader:TemperatureReader, test_name_model:SinglePointModel[str], is_recording_model:SinglePointModel[bool],
                 write_api:WriteApi, furnace_safety_model:SinglePointModel[bool], furnace_controllers:ListModel[TemperatureController],  parent:QObject = None):
        super().__init__(parent=parent)
        self._temp_reader = temp_reader
        self._is_running = False
        self._test_name_model = test_name_model
        self._is_recording_model = is_recording_model
        self._write_api = write_api
        self._furnace_safety_model = furnace_safety_model
        self._furnace_controllers = furnace_controllers
        self._bad_temp_reads:int = 0
        self._temp_restart_count:int = 0

    @property
    def is_running(self) -> bool:
        return self._is_running

    @Slot(datetime)
    def collect_data(self, read_time:datetime):
        self._is_running = True

        #Collect temperature data.
        try:
            furnace_temps = self._temp_reader.read(read_time)

            #Check if any temps are too hot.
            if self._furnace_safety_model.data:
                for max_temp, name, temp in zip(self._temp_reader.all_furnace_tc_max_temps_unordered, self._temp_reader.all_furnace_tc_display_names_unordered, furnace_temps):
                    if temp > max_temp:
                        self._furnace_safety_model.data = False
                        print('Shutting off power due to ' + name + ' overheating at ' + str(temp) + 'C.')
                        break

            #Record temp data.
            if self._is_recording_model.data:
                labels = self._temp_reader.all_furnace_tc_display_names_unordered 
                metrics = self._temp_reader.all_furnace_tc_metrics_unordered
                for label, metric, temp in zip(labels, metrics, furnace_temps):
                    self._push_influx(label, metric, temp, read_time)

                #Record controller data.
                for controller in self._furnace_controllers:
                    controller:TemperatureController
                    if controller.setpoint_model.data is not None:
                        self._push_influx(controller.name, 'Setpoint', controller.setpoint_model.data, read_time)
                    if controller.pid_output_model.data is not None:
                        self._push_influx(controller.name, 'PID Output', controller.pid_output_model.data, read_time)
        except Exception as e:
            print('Exception during temperature collection:',e)
            self._bad_temp_reads += 1
        else:
            self._bad_temp_reads = 0
            self._temp_restart_count = 0

        if self._bad_temp_reads >= 10:
            if self._temp_restart_count < 2:
                self.temp_restart_sig.emit()
                self._temp_restart_count += 1
            elif self._temp_restart_count < 3:
                self._furnace_safety_model.data = False
                self._temp_restart_count += 1

        self._is_running = False

    def _push_influx(self, label:str, metric:str, value:float, time:datetime):
        try:
            point = Point(self._test_name_model.data).tag('DeviceName',label).field(metric,value).time(time.astimezone())
            self._write_api.write(BUCKET, record=point)
        except:
            pass


class FlowCollectionWorker(QObject):
    """A worker object to handle flow data collection."""
    def __init__(self, mfc_reader:MFCReader, test_name_model:SinglePointModel[str], is_recording_model:SinglePointModel[bool],
                 write_api:WriteApi, parent:QObject = None):
        super().__init__(parent=parent)
        self._mfc_reader = mfc_reader
        self._is_running = False
        self._test_name_model = test_name_model
        self._is_recording_model = is_recording_model
        self._write_api = write_api

    @property
    def is_running(self) -> bool:
        return self._is_running

    @Slot(datetime)
    def collect_data(self, read_time:datetime):
        self._is_running = True

        #Collect flow data.
        try:
            flowrates_dict = self._mfc_reader.read(read_time)
            if flowrates_dict is None:
                flowrates_dict = self._mfc_reader.read(read_time)
            if flowrates_dict is None:
                print('Tried and failed reading MFC twice, skipping time step')
            else:
                if self._is_recording_model.data:
                    for sect in self._mfc_reader.mfcs:
                        labels = self._mfc_reader.mfc_names[sect]
                        metrics = self._mfc_reader.mfc_metrics[sect]
                        flowrates = flowrates_dict[sect]
                        for label, metric, flowrate in zip(labels, metrics, flowrates):
                            self._push_influx(label, metric, flowrate, read_time)
        except Exception as e:
            print('Exception during flowrate collection:',e)

        self._is_running = False

    def _push_influx(self, label:str, metric:str, value:float, time:datetime):
        try:
            point = Point(self._test_name_model.data).tag('DeviceName',label).field(metric,value).time(time.astimezone())
            self._write_api.write(BUCKET, record=point)
        except:
            pass

class MasterController(QObject):
    """A class that controls the device management and data collection of the TestSuite."""
    request_temp_data = Signal(datetime)
    request_pressure_data = Signal(datetime)
    request_flow_data = Signal(datetime)
    request_download = Signal(str,str,str,str)
    check_influx = Signal()
    pause_profile = Signal()
    purge_finished = Signal()

    def __init__(self, config:dict, furnace_controllers:ListModel[TemperatureController], parent:QObject = None):
        """config - Dictionary representing the full config file."""
        super().__init__(parent=parent)
        self._config = config
        self._furnace_controllers = furnace_controllers
        self._control_box_type = self._config['control-box-config']['box-type']
        self._control_box = None
        self._read_client = None
        self._write_client = None
        self._temperature_reader = None
        self._voltage_writer = None
        self._mfc_reader = None
        self._tc_restart_counter:int = 0
        self._fc_restart_counter:int = 0
        self._alert_emails = self._config['watchdog-config']['alert-emails']
        self._smpt_client = Smtp2goClient(api_key=self._config['watchdog-config']['alert-api-key'])
        self._t_solid_on:float = None
        self._t_purge_on:float = None
        self._pumps_active:SinglePointModel[bool] = SinglePointModel(False)
        self._purge_active:SinglePointModel[bool] = SinglePointModel(False)
        self._pump_flow:SinglePointModel[float] = SinglePointModel(0.0)
        self._purge_freq:SinglePointModel[float] = SinglePointModel(0.0)
        self._purge_duration:SinglePointModel[float] = SinglePointModel(0.0)
        self._reverse_purge_duration:SinglePointModel[float] = SinglePointModel(0.0)
        self._solid_line = []
        self._purge_line = []

        self._init_pumps(self._config)


        #Create control box and all readers/writers.
        try:
            if self._control_box_type == 'Pi':
                ssh_port = self._config['control-box-config']['ssh-port']
                if 'hostname' in self._config['control-box-config']:
                    hostname = self._config['control-box-config']['hostname']
                    username = self._config['control-box-config']['username']
                    password = self._config['control-box-config']['password']
                    self._read_client = SSHClient(hostname=hostname, username=username, password=password, port=ssh_port)
                    self._write_client = self._read_client
                else:
                    hostname = self._config['control-box-config']['write-hostname']
                    username = self._config['control-box-config']['write-username']
                    password = self._config['control-box-config']['write-password']
                    self._write_client = SSHClient(hostname=hostname, username=username, password=password, port=ssh_port)
                    hostname = self._config['control-box-config']['read-hostname']
                    username = self._config['control-box-config']['read-username']
                    password = self._config['control-box-config']['read-password']
                    self._read_client = SSHClient(hostname=hostname, username=username, password=password, port=ssh_port)
                self._control_box = PiControlBox(self._read_client, self._write_client, self._config['control-box-config']['mask-enabled'])
                self._control_box._pwm_worker.unsafe_sig.connect(self._turn_off_heaters)
                self._voltage_writer = PWMWriter(self._control_box)
                
            else:
                raise IOError('Control box type not specified')
            self._temperature_reader = TemperatureReader(self._config, self._control_box)
        except Exception as e:
            print('WARNING: Control box could not be loaded')
            print(e)
            if self._read_client is not None:
                self._read_client = None
            if self._write_client is not None:
                self._write_client = None

        #This loads always since it is not dependent on control box
        self._mfc_reader = MFCReader(self._config, self)

        #Initialize models.
        self._furnace_safety_model:SinglePointModel[bool] = SinglePointModel(True)
        self._furnace_safety_model.data_changed.connect(self._handle_estop_press)
        self._is_recording_model:SinglePointModel[bool] = SinglePointModel(False)
        self._test_name_model:SinglePointModel[str] = SinglePointModel('default-test')

        #Initialize database client.
        self._influx_client = InfluxDBClient(url=self._config['database-config']['url'],
                                             token=self._config['database-config']['token'],
                                             org=self._config['database-config']['org-id'])
        self._write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)

        #Initialize threads.
        self._initialize_data_collection()

        self._influx_check_thread = QThread(self)
        self._influx_check_worker = CheckInfluxWorker()
        self._influx_check_worker.moveToThread(self._influx_check_thread)
        self._influx_check_thread.finished.connect(self._influx_check_worker.deleteLater)
        self.check_influx.connect(self._influx_check_worker.check_influx)
        self._influx_check_thread.start()

        self._download_data_thread = QThread(self)
        self._download_data_worker = DownloadDataWorker()
        self._download_data_worker.moveToThread(self._download_data_thread)
        self.request_download.connect(self._download_data_worker.download_data)
        self._download_data_thread.start()

        #Initialize control loop.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._control_loop)
        self._timer.start(CONTROL_LOOP_FREQUENCY)

        #reload mfcs after startup
        QTimer.singleShot(2000,self._mfc_reader.reload)

    @property
    def temperature_reader(self) -> TemperatureReader:
        return self._temperature_reader

    @property
    def mfc_reader(self) -> MFCReader:
        return self._mfc_reader

    @property
    def furnace_safety_model(self) -> SinglePointModel[bool]:
        return self._furnace_safety_model

    @property
    def is_recording_model(self) -> SinglePointModel[bool]:
        return self._is_recording_model
    
    @property
    def test_name_model(self) -> SinglePointModel[str]:
        return self._test_name_model

    @property
    def measurements(self) -> list[str]:
        """All measurements in the TESTS bucket in InfluxDB."""
        query = f"""
        import \"influxdata/influxdb/schema\"

        schema.measurements(bucket: \"TESTS\")
        """

        query_api = self._influx_client.query_api()
        tables = query_api.query(query=query)

        # Flatten output tables into list of measurements
        measurements = [row.values["_value"] for table in tables for row in table]
        return measurements

    @Slot()
    def select_measurement(self):
        dialog = TestSelectionDialog(self.measurements)

        if dialog.exec_() == QDialog.Accepted:
            selected_measurement = dialog.selected_measurement
            if selected_measurement:
                self.request_download.emit(self._config['database-config']['url'], 
                                           self._config['database-config']['token'], 
                                           self._config['database-config']['org-id'], 
                                           selected_measurement)

    @Slot()
    def _control_loop(self):
        """This loop gets called at a specified frequency to manage data collection."""
        #Request data from data collection workers.
        read_time = datetime.now()
        if self.temperature_reader is not None:
            if not self._temp_collection_thread.isRunning() and self._tc_restart_counter < 3:
                if self._tc_restart_counter < 2:
                    print('restarting temp collection thread')
                    self._temp_collection_thread.deleteLater()
                    self._initialize_temp_collection()
                else:
                    print('temp collection thread failed 3 times, declaring unsafe')
                    self._furnace_safety_model.data = False
                self._tc_restart_counter += 1
            
            if self._temp_collection_thread.isRunning():
                if not self._temp_collection_worker.is_running:
                    self.request_temp_data.emit(read_time)
                else:
                    print('temp collection worker currently running, skipping request')
            else:
                print('restarting temp collection thread')
                self._temp_collection_thread.start()

        if self.mfc_reader is not None:
            if not self._flow_collection_thread.isRunning() and self._fc_restart_counter < 3:
                if self._fc_restart_counter < 2:
                    print('restarting flow collection thread')
                    self._flow_collection_thread.deleteLater()
                    self._initialize_flow_collection()
                else:
                    print('flow collection thread failed 3 times, declaring unsafe')
                self._fc_restart_counter += 1
            
            if self._flow_collection_thread.isRunning():
                if not self._flow_collection_worker.is_running:
                    self.request_flow_data.emit(read_time)
                else:
                    print('flow collection worker currently running, skipping request')
            else:
                print('restarting flow collection thread')
                self._flow_collection_thread.start()

        self._pump_cycle(read_time)

        #Ensure influx is running.
        if not self._influx_check_worker.is_running:
            self.check_influx.emit()

    def _initialize_data_collection(self):
        if self._temperature_reader is not None:
            self._initialize_temp_collection()

        if self._mfc_reader is not None:
            self._initialize_flow_collection()

    def _initialize_temp_collection(self):
        self._temp_collection_thread = QThread(self)
        self._temp_collection_worker = TempCollectionWorker(self.temperature_reader, self.test_name_model, self.is_recording_model,
                                                            self._write_api, self.furnace_safety_model,
                                                            self._furnace_controllers)
        self._temp_collection_worker.moveToThread(self._temp_collection_thread)
        self._temp_collection_worker.temp_restart_sig.connect(self.restart_tcreader)
        self._temp_collection_thread.finished.connect(self._temp_collection_worker.deleteLater)
        self.request_temp_data.connect(self._temp_collection_worker.collect_data)
        self._temp_collection_thread.start()

    def _initialize_flow_collection(self):
        self._flow_collection_thread = QThread(self)
        self._flow_collection_worker = FlowCollectionWorker(self.mfc_reader, self.test_name_model, self.is_recording_model, self._write_api)
        self._flow_collection_worker.moveToThread(self._flow_collection_thread)
        self._flow_collection_thread.finished.connect(self._flow_collection_worker.deleteLater)
        self.request_flow_data.connect(self._flow_collection_worker.collect_data)
        self._flow_collection_thread.start()

    def _pump_cycle(self, tn:datetime):
        if self._pumps_active.data:
            if self._t_solid_on is None: #Just starting the pump, begin with reverse purge, then start main solids pump
                val = min(100,max(0,self._pump_flow.data*self._pump_conversion))# convert to duty cycle
                if self._t_purge_on is None and self._reverse_purge_duration.data>0:
                    self._t_purge_on = tn.timestamp()
                    for l in self._purge_line:
                        self._voltage_writer.write(l,int(val)) #write relay channel and % on 
                elif self._reverse_purge_duration.data<=0 or (tn.timestamp()-self._t_purge_on)> self._reverse_purge_duration.data.data:
                    self._t_solid_on = tn.timestamp()
                    for l in self._solid_line:
                        self._voltage_writer.write(l,int(val)) #write relay channel and % on
                    for l in self._purge_line:
                        self._voltage_writer.write(l,0) #write relay channel and % on 
            if (tn.timestamp()-self._t_solid_on) > self._purge_freq.data:
                self._t_purge_on = tn.timestamp()
                self._t_solid_on = tn.timestamp()+self._purge_duration.data
                val = min(100,max(0,self._pump_flow.data*self._purge_conversion))# convert to duty cycle
                for l in self._purge_line:
                    self._voltage_writer.write(l,int(val)) #write relay channel and % on 
            if (tn.timestamp()-self._t_purge_on)> self._purge_duration.data:
                self._t_solid_on = tn.timestamp()
                self._t_purge_on = tn.timestamp() + self._purge_freq.data
                for l in self._purge_line:
                    self._voltage_writer.write(l,0) #write relay channel and % on 
        elif self._purge_active.data:
            if self._t_solid_on is None:
                val = min(100,max(0,self._pump_flow.data*self._purge_conversion))# convert to duty cycle
                if self._t_purge_on is None:
                    self._t_purge_on = tn.timestamp()
                    for l in self._purge_line:
                        self._voltage_writer.write(l,int(val)) #write relay channel and % on 
                if (tn.timestamp()-self._t_purge_on)>= self._reverse_purge_duration.data:
                    self._t_solid_on = tn.timestamp()
                    try:
                        for l in self._solid_line:
                            self._voltage_writer.write(l,int(val)) #write relay channel and % on 
                    except Exception as e:
                        print('Cant write voltage because voltage writer not loaded')
                        print(e)
            elif (tn.timestamp()-self._t_solid_on) > self._purge_duration.data:
                self.purge_finished.emit()

    def _init_pumps(self,config):
        for pump in config['pump-config']['pumps']:
            if 'solids' in pump['display-name']:
                self._pump_conversion = 100/pump['full-flow']
                self._solid_line.append(pump['voltage-line'])
            elif 'purge' in pump['display-name']:
                self._purge_conversion = 100/pump['full-flow']
                self._purge_line.append(pump['voltage-line'])

    @Slot()
    def restart_tcreader(self):
        print('restarting tcreader')
        self._read_client.exec_command('pkill -f tcreader.py')
        self._read_client.exec_command('python tcreader.py &')

    @Slot()
    def restart_readvoltage(self):
        print('restarting readvoltage')
        self._read_client.exec_command('pkill -f readadc.py')
        self._read_client.exec_command('python readadc.py &')

    @Slot()
    def _turn_off_heaters(self):
        self._furnace_safety_model.data = False

    def send_message(self, subject:str, text:str):
        if len(self._alert_emails) > 0:
            try:
                payload = {
                    'sender':self._config['watchdog-config']['alert-sender'],
                    'recipients':self._alert_emails,
                    'subject':subject,
                    'text':text,
                    'html':'<html><body><h1>' + text + '</h1></body><html>'
                }
                self._smpt_client.send(**payload)
            except Exception as e:
                print(e)

    def _handle_estop_press(self):
        if self._furnace_safety_model.data == False: #If estop is pressed
            self.send_message('Test Stand E-Stop Alert', 'WARNING: Emergency Stop has been activated')
            self.pause_profile.emit()
            #TODO: initiate configured safe state
            WarningDialog('WARNING: E-Stop has been activated', self.parent()._title, self.parent()).show()

    @Slot(str)
    def _handle_under_temp(self, furnace_name:str):
        self.send_message('Test Stand Temperature Alert', 'WARNING: ' + furnace_name + ' stopped heating due to low temperature detected')
        self.pause_profile.emit()
        #TODO: initiate configured safe state
        WarningDialog('WARNING: ' + furnace_name + ' stopped heating due to low temperature detected', self.parent()._title, self.parent()).show()

    @Slot(str)
    def _handle_flow_deviations(self, mfc_name:str):
        self.send_message('Test Stand Flow Rate Alert', 'WARNING: ' + mfc_name + ' deviation from setpoint detected')
        self.pause_profile.emit()
        #TODO: initiate configured safe state
        WarningDialog('WARNING: ' + mfc_name + ' deviation from setpoint detected', self.parent()._title, self.parent()).show()

    def _emit_bpr_alerts(self):
        self.send_message('Test Stand Warning', 'WARNING: BPR Control has Shutoff')

    def close(self):
        """Stops the control loop and quits all threads. Should only be called upon exiting TestSuite."""
        print('closing master controller')
        self._timer.stop()
        print('waiting for workers to stop')
        while self._influx_check_worker.is_running or\
            (self.temperature_reader is not None and self._temp_collection_worker.is_running) or\
            (self.mfc_reader is not None and self._flow_collection_worker.is_running): #Wait for workers to stop.
            pass
        print('quitting temp collection thread')
        if self.temperature_reader is not None and self._temp_collection_thread.isRunning():
            self._temp_collection_thread.quit()
            self._temp_collection_thread.wait()
        print('quitting flow collection thread')
        if self.mfc_reader is not None and self._flow_collection_thread.isRunning():
            self._flow_collection_thread.quit()
            self._flow_collection_thread.wait()
        print('quitting influx check thread')
        self._influx_check_thread.quit()
        self._influx_check_thread.wait()
        if self._mfc_reader is not None:
            self._mfc_reader.close_mfcs()
        if self._control_box is not None:
            self._control_box.close()
        if self._read_client is not None:
            self._read_client.close()
        if self._write_client is not None:
            self._write_client.close()
