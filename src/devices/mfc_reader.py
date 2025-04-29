from models import ListModel
from devices import ElFlowMFC
from datetime import datetime
from PySide6.QtCore import QObject, QThread, Slot, Signal
from serial.tools.list_ports import comports
from serial.serialutil import PortNotOpenError, SerialException
import propar
import time

class ReloadWorker(QObject):
    def __init__(self, mfc_name_map:dict[str,ElFlowMFC], parent:QObject = None):
        super().__init__(parent=parent)
        self._mfc_name_map = mfc_name_map

    @Slot()
    def reload(self):
        #disconnect all old mfcs
        for key in self._mfc_name_map:
            print('disconnecting',key)
            self._mfc_name_map[key].disconnect()
        for port in comports():
            print(port.name)
            #get propar inst
            try:
                inst = propar.instrument(port.name)
                if inst.readParameter(90) != "DMFC":
                    print(port.name,'not an mfc')
                    inst.master.propar.serial.close()
                else:
                    #find mfc in name map
                    name = inst.readParameter(115)
                    print('found',name,'at',port.name)
                    if name in self._mfc_name_map:
                        mfc = self._mfc_name_map[name]
                        #reconnect mfc with new inst
                        mfc.reconnect(inst)
                    else:
                        print('WARNING: ' + name + ' not in config')
            except (PortNotOpenError, SerialException) as e:
                print('error at',port.name)

class MFCReader(QObject):
    request_reload = Signal()

    def __init__(self, config:dict, parent:QObject = None):
        super().__init__(parent=parent)
        #Create dicts.
        self._config = config
        self._mfcs:dict[int,ListModel[ElFlowMFC]] = {}
        self._mfc_names:dict[int,ListModel[str]] = {}
        self._mfc_metrics:dict[int,ListModel[str]] = {}
        self._flow_models:dict[int,ListModel[ListModel[float]]] = {}
        self._time_model:ListModel[datetime] = ListModel(maxlen=self._config['mfc-config']['max-data'])
        self._mfc_name_map:dict[str,ElFlowMFC] = {}
        loaded_mfcs = []

        #Populate dicts.
        # for port in comports():
        #     try:
        #         mfc = ElFlowMFC(port.name)
        #         sect = self._config['mfc-config'][mfc.name]['section']
        #     except IOError:
        #         pass
        #     except KeyError:
        #         print('WARNING: ' + mfc.name + ' not in config')
        #         mfc.close()
        #     else:
        #         self.append_mfc(mfc.name,sect)      
        #         mfc.conversion_factor = self._config['mfc-config'][mfc.name]['conversion-factor']
        #         self._mfcs[sect].append(mfc)
        #         loaded_mfcs.append(mfc.name)
        #         self._mfc_name_map[mfc.name] = mfc

        #Load disconnected mfcs.
        for mfc_name in self._config['mfc-config'].keys():
            if mfc_name not in loaded_mfcs and mfc_name != 'max-data':
                mfc = ElFlowMFC('N/A', True, mfc_name)                
                sect = self._config['mfc-config'][mfc.name]['section']
                self.append_mfc(mfc.name,sect)        
                mfc.conversion_factor = self._config['mfc-config'][mfc.name]['conversion-factor']
                self._mfcs[sect].append(mfc)
                self._mfc_name_map[mfc.name] = mfc

        #Initialize thread.
        self._reload_worker = ReloadWorker(self._mfc_name_map)
        self._reload_thread = QThread(self)
        self._reload_worker.moveToThread(self._reload_thread)
        self._reload_thread.start()
        self.request_reload.connect(self._reload_worker.reload)

    
    def append_mfc(self,mfc_name,sect):
        if sect not in self._mfcs:
            self._mfcs[sect] = ListModel()
            self._mfc_names[sect] = ListModel()
            self._mfc_metrics[sect] = ListModel()
            self._flow_models[sect] = ListModel()
        self._mfc_names[sect].append(mfc_name)
        self._mfc_metrics[sect].append(self._config['mfc-config'][mfc_name]['metric'])
        self._flow_models[sect].append(ListModel(maxlen=self._config['mfc-config']['max-data']))            

    def reload(self):
        self.request_reload.emit()

    def read(self, time:datetime|None = None) -> dict[int,list[float]]:
        """Reads and stores the temperatures of all connected thermocouples in their relevant models.\n
        time - Read time to add to the time tracker model. If None, time will be calculated upon reading.
        Returns - Dictionary of lists containing flowrates. 
        """
        flow_rates:dict[int,list[float]] = {}

        for sect in self._mfcs:
            for mfc, flow_model in zip(self._mfcs[sect], self._flow_models[sect]):
                mfc:ElFlowMFC
                flow_model:ListModel[float]
                flow_rate = mfc.flow_rate
                if sect not in flow_rates:
                    flow_rates[sect] = []
                flow_rates[sect].append(flow_rate)
                flow_model.append(flow_rate)

        read_time = time if time is not None else datetime.now()
        self._time_model.append(read_time.timestamp())

        return flow_rates

    @property
    def mfcs(self) -> dict[int,ListModel[ElFlowMFC]]:
        return self._mfcs
    
    @property
    def mfc_names(self) -> dict[int,ListModel[str]]:
        return self._mfc_names
    
    @property
    def mfc_metrics(self) -> dict[int,ListModel[str]]:
        return self._mfc_metrics
    
    @property
    def flow_models(self) -> dict[int,ListModel[ListModel[float]]]:
        return self._flow_models
    
    @property
    def time_model(self) -> ListModel[datetime]:
        return self._time_model
    
    @property
    def mfc_name_map(self) -> dict[str,ElFlowMFC]:
        return self._mfc_name_map
    
    def close_mfcs(self):
        for sect in self._mfcs:
            for mfc in self._mfcs[sect]:
                mfc:ElFlowMFC
                mfc.close()

    def close(self):
        self._reload_thread.quit()
        self.close_mfcs