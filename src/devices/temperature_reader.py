from devices import ControlBox
from models import ListModel
from datetime import datetime

class TemperatureReader:
    """A class to read and store temperatures from the connected thermocouples"""
    def __init__(self, config:dict, control_box:ControlBox):
        """config - Dictionary representing the full config file.\n
        control_box - ControlBox object for collecting data.
        """
        #Create thermocouple models.
        self._furnace_tc_time_model:ListModel[datetime] = ListModel(maxlen=config['furnace-config']['max-data'])
        self._all_furnace_tcs:list[list[dict]] = []
        self._all_furnace_models:list[list[ListModel[float]]] = []
        self._furnace_control_map:dict[ListModel[float],bool] = {}

        self._humidifier_tc_time_model:ListModel[datetime] = ListModel(maxlen=config['humidifier-config']['max-data'])
        self._all_humidifier_tcs:list[list[dict]] = []
        self._all_humidifier_models:list[list[ListModel[float]]] = []
        self._humidifier_control_map:dict[ListModel[float],bool] = {}

        #Load furnace thermocouples.
        for furnace in config['furnace-config']['furnaces']:
            if furnace is not None:
                tcs,models,control_map = self.load_heaters(furnace,config['furnace-config']['max-data'])
                for model in models:
                    self._furnace_control_map[model] = control_map[model]
                self._all_furnace_tcs.append(tcs)
                self._all_furnace_models.append(models)

        #Load humidifier thermocouples.
        for humidifier in config['humidifier-config']['humidifiers']:
            if humidifier is not None:
                tcs,models,control_map = self.load_heaters(humidifier,config['humidifier-config']['max-data'])
                for model in models:
                    self._humidifier_control_map[model] = control_map[model]
                self._all_humidifier_tcs.append(tcs)
                self._all_humidifier_models.append(models)

        self._control_box = control_box
        self._all_thermocouples:list[dict] = sum(self._all_furnace_tcs, []) + sum(self._all_humidifier_tcs, [])
        self._control_box.add_thermocouples(self._all_thermocouples)

    def load_heaters(self,heater,max_data):
        tcs:list[dict] = []
        models:list[ListModel[float]] = []
        control_map = {} 
        for thermocouple in heater['control-thermocouples']:
            if thermocouple is not None:
                tcs.append(thermocouple)
                model = ListModel(maxlen=max_data)
                models.append(model)
                control_map[model] = True
        for thermocouple in heater['extra-thermocouples']:
            if thermocouple is not None:
                tcs.append(thermocouple)
                model = ListModel(maxlen=max_data)
                models.append(model)
                control_map[model] = False
        return tcs,models,control_map

    def read(self, time:datetime|None = None) -> list[float]:
        """Reads and stores the temperatures of all connected thermocouples in their relevant models.\n
        time - Read time to add to the time tracker model. If None, time will be calculated upon reading.\n
        Returns - Tuple of lists. First list contains furnace temps, second list contains humidifier temps.\n
        NOTE: If a thermocouple is disconnected the tmperature will read 0.0
        """
        try:
            # ntime = thyme.time()
            temperatures = self._control_box.read_all_thermocouples()
            if not all(type(temp) == float for temp in temperatures) or len(temperatures) != len(self._all_thermocouples):
                raise Exception("Temperature read failed: " + str(temperatures))

            # print(thyme.time() - ntime)
            read_time = time if time is not None else datetime.now()

            #Calculate starting indeces of thermocouples.
            furnace_tc_index = 0
            humidifier_tc_index = furnace_tc_index + len(sum(self._all_furnace_tcs, []))

            #Parse furnace temperatures.
            for temperature, model in zip(temperatures[furnace_tc_index:humidifier_tc_index], sum(self._all_furnace_models, [])):
                model.append(temperature)

            #Append read time of temperatures.
            #NOTE: The read time *must* only be updated after all other temperature models are updated.
            self._furnace_tc_time_model.append(read_time.timestamp())
            self._humidifier_tc_time_model.append(read_time.timestamp())

            return temperatures[furnace_tc_index:humidifier_tc_index], temperatures[humidifier_tc_index:]
        except Exception as e:
            print('In TemperatureReader: ' + str(e))

    @property
    def all_furnace_tc_display_names(self) -> list[list[str]]:
        """Returns a list of lists containing display names for each furnace thermocouple."""
        return [[thermocouple['display-name'] for thermocouple in tcs] for tcs in self._all_furnace_tcs]
    
    @property
    def all_furnace_tc_display_names_unordered(self) -> list[str]:
        """Returns a list of display names for each furnace thermoucouple. All control thermocouples preceed all extra thermocouples."""
        return [thermocouple['display-name'] for thermocouple in sum(self._all_furnace_tcs,[])]
    
    @property
    def all_furnace_tc_metrics(self) -> list[list[str]]:
        """Returns a list of lists containing metrics for each furnace thermocouple."""
        return [[thermocouple['metric'] for thermocouple in tcs] for tcs in self._all_furnace_tcs]
    
    @property
    def all_furnace_tc_metrics_unordered(self) -> list[str]:
        """Returns a list of metrics for each furnace thermoucouple. All control thermocouples preceed all extra thermocouples."""
        return [thermocouple['metric'] for thermocouple in sum(self._all_furnace_tcs,[])]
    
    @property
    def all_furnace_tc_max_temps(self) -> list[list[str]]:
        """Returns a list of lists containing max temps for each furnace thermocouple."""
        return [[thermocouple['max-temp'] for thermocouple in tcs] for tcs in self._all_furnace_tcs]
    
    @property
    def all_furnace_tc_max_temps_unordered(self) -> list[str]:
        """Returns a list of max temps for each furnace thermoucouple. All control thermocouples preceed all extra thermocouples."""
        return [thermocouple['max-temp'] for thermocouple in sum(self._all_furnace_tcs,[])]
    
    @property
    def all_furnace_models(self) -> list[list[ListModel[float]]]:
        """Returns a list of lists containing ListModels holding temperatures from furnace control thermocouples."""
        return self._all_furnace_models
    
    @property
    def furnace_tc_time_model(self) -> ListModel[datetime]:
        """Returns a ListModel containing the times each furnace temperature measurement was taken."""
        return self._furnace_tc_time_model
    
    @property
    def furnace_control_map(self) -> dict[ListModel[float],bool]:
        return self._furnace_control_map
