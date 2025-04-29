from PySide6.QtCore import QObject, Slot, Signal, QThread
from models import SinglePointModel, ListModel
from devices import PWMWriter
import time
import statistics

CYCLE_ITERATION_TIME = 1 #Time for each duty cycle iteration in seconds.
ITERATIONS_PER_CYCLE = 1 #How many iterations run per duty cycle.
MAX_SAFETY_FLAGS = 5 #Maximum safety flags before declaring unsafe.

def clamp(value:float|int, min:float|int, max:float|int) -> float|int:
    """Returns a value within the specified bounds if the input value exceeds those bounds.\n
    value - Value to be clamped.\n
    min - Inclusive lower bound.\n
    max - Inclusive upper bound.
    """
    if value < min:
        return min
    elif value > max:
        return max
    else:
        return value

class DutyCycleWorker(QObject):
    """A worker object to handle the PID duty cycle. Can be supervisor (senority 0), independant (senority 1), supervisee (senority 2). 
    Supervisors receive and average multiple temperatures and determine a global duty cycle for multiple supervisee's. Does not send commands to a heating wire
    Independant take in one temperature and operate one heating control wire
    Supervisee's receive a single temperature and compute an error from the supervisors average then compute a duty cycle deviation from the global duty cycle. 
    (Note: Do the sum of supervisee's deviations should always be zero which means proportional and integral values must be identical and derivative must be zero? Or just ensure supervisees are slower response PID's)"""
    cycle_complete = Signal()
    emergency_stop = Signal()
    under_temp = Signal()

    def __init__(self, setpoint_model:SinglePointModel[float], target_model:SinglePointModel[float],
                 models:list[ListModel[float]], control_map:dict[ListModel[float],bool], safety_model:SinglePointModel[bool],
                 safety_range:float, cooling_range:float, rr_model:SinglePointModel[float],
                 p_constant_model:SinglePointModel[float], i_constant_model:SinglePointModel[float],
                 d_constant_model:SinglePointModel[float], max_output_model:SinglePointModel[int],
                 integral_max_model:SinglePointModel[float], integral_min_model:SinglePointModel[float],
                 output_bias_model:SinglePointModel[float], output_override_model:SinglePointModel[float], apply_override_model:SinglePointModel[float],
                 integral_crossover_model:SinglePointModel[float], pid_output_model:SinglePointModel[float], unclamped_pid_output_model:SinglePointModel[float],
                 p_output_model:SinglePointModel[float], i_output_model:SinglePointModel[float],
                 d_output_model:SinglePointModel[float], duty_clamp_max_model:SinglePointModel[float],
                 duty_clamp_min_model:SinglePointModel[float], voltage_writer:PWMWriter, identifier:int,
                 voltage_output_line:int, supervisor_furnace: int, all_temp_controllers:ListModel['TemperatureController'],
                 parent:QObject = None):
        """setpoint_model - Model used for the PID controller to utilize the current temperature setpoint.\n
        target_model - Model used for the PID controller to detect crossover when the target is reached.\n
        models - List of ListModels each holding temperatures from thermocouples.\n
        control_map - Dictionary mapping temp models to bools to show if they should be used for control.\n
        safety_model - Model used to check if it is safe to heat or not.\n
        safety_range - Range used to detect if temperatures are out of safety bounds.\n
        cooling_range - Range used to detect if the setpoint needs to wait for the control temperature to cool.\n
        rr_model - Model used for the PID controller to utilize the specified ramp rate.\n
        p_constant_model - Model used for the PID controller to utilize the specified p constant value.\n
        i_constant_model - Model used for the PID controller to utilize the specified i constant value.\n
        d_constant_model - Model used for the PID controller to utilize the specified d constant value.\n
        max_output_model - Model used for the PID controller to limit the output to the specified percentage.\n
        integral_max_model - Model used to limit the integral value to the specified upper bound.\n
        integral_min_model - Model used to limit the integral value to the specified lower bound.\n
        output_bias_model - Model used to add bias to PID output.\n
        output_override_model - Model used to ignore the PID controller and set the output.\n
        apply_override_model - Model used to toggle if override is applied.\n
        integral_crossover_model - Model used for the PID controller to zero the integral value upon setpoint crossover.\n
        pid_output_model - Model used for the view to display the most recent PID output value.\n
        unclamped_pid_output_model - Model used to store an unclamped PID output.\n
        p_output_model - Model used for the view to display the most recent P value.\n
        i_output_model - Model used for the view to display the most recent I value.\n
        d_output_model - Model used for the view to display the most recent D value.\n
        voltage_output_line - Output line to write voltage to.\n
        supervisor_furnace - Index of supervisor furnace. -1 if no supervisor. NOTE: Indexing in this case starts at 1, please convert accordingly when needed.\n
        all_temp_controllers - ListModel of all temperature controllers of the same type (Furnace or Humidifier).
        """
        super().__init__(parent=parent)
        self._setpoint_model = setpoint_model
        self._target_model = target_model
        self._models = models
        self._control_map = control_map
        self._safety_model = safety_model
        self._safety_range = safety_range
        self._cooling_range = cooling_range
        self._rr_model = rr_model
        self._p_constant_model = p_constant_model
        self._i_constant_model = i_constant_model
        self._d_constant_model = d_constant_model
        self._max_output_model = max_output_model
        self._integral_max_model = integral_max_model
        self._integral_min_model = integral_min_model
        self._output_bias_model = output_bias_model
        self._output_override_model = output_override_model
        self._apply_override_model = apply_override_model
        self._integral_crossover_model = integral_crossover_model
        self._pid_output_model = pid_output_model
        self._unclamped_pid_output_model = unclamped_pid_output_model
        self._p_output_model = p_output_model
        self._i_output_model = i_output_model
        self._d_output_model = d_output_model
        self._duty_clamp_max_model = duty_clamp_max_model
        self._duty_clamp_min_model = duty_clamp_min_model
        self._voltage_writer = voltage_writer
        self._identifier = identifier
        self._voltage_output_line = voltage_output_line
        self._supervisor_furnace = supervisor_furnace
        self._all_temp_controllers = all_temp_controllers
        self._is_running = False
        self._high_temp_error_count = 0
        self._low_temp_error_count = 0
        self._last_ramp_time = None
        
        #Define values used in PID
        self._proportional = 0
        self._integral = 0
        self._derivative = 0

        self._last_time = None
        self._last_output = None
        self._last_error = None
        self._last_input = None
        self._last_target = None

    @Slot()
    def prepare_duty_cycle(self):
        #TODO consider combining all furnaces into a single thread that has all the thermocouples and furnace objects, determines the duty cycle of each, then writes the PWM value.
        #then it could run at a fixed frequency and not use the sleep function to set the wait time.
        #One function would loop through all the duty cycle workers.
        self._is_running = True

        #Calculate control temperature (average of thermocouple measurements).
        control_temp = self._get_control_temp()

        #Create initial setpoint.
        if self._setpoint_model.data is None:
            self._setpoint_model.data = control_temp

        #Retrieve supervisor temperature cycle, None if no supervisor
        supervisor_temp = self.get_supervisor_temp()

        if supervisor_temp is not None:
            self._setpoint_model.data = supervisor_temp

        #Run safety checks.
        safe = self._check_safety(control_temp)

        #Retrieve supervisor duty cycle, None if no supervisor
        supervisor_duty = self.get_supervisor_duty()

        if safe:
            #Ramp setpoint (not if heater is only tracking a supervisor)
            if supervisor_temp is None:
                self._ramp_setpoint(control_temp)
            # else:
            #     print('Supervisor duty is ' + str(supervisor_duty) + ' and temperature error is ' + str(supervisor_temp-control_temp))

            #Call duty cycle.
            self._run_duty_cycle(control_temp,supervisor_duty)

        #Reset tracker values so heating restarts properly.
        else:
            self._high_temp_error_count = 0
            self._low_temp_error_count = 0
            self._last_ramp_time = None
            self._proportional = 0
            self._integral = 0
            self._derivative = 0
            self._last_time = None
            self._last_output = None
            self._last_error = None
            self._last_input = None
            self._last_target = None
        
        self._is_running = False
        self.cycle_complete.emit()

    def get_supervisor_temp(self) -> float:
        if self._supervisor_furnace == -1:
            supervisor_temp = None
        else:
            #Retrieve measured average temperature of supervisor furnace.
            supervisor_index = self._supervisor_furnace - 1 #Converting indexing from config stye to python style.
            supervisor:TemperatureController = self._all_temp_controllers[supervisor_index]
            supervisor_temp = supervisor._duty_cycle_worker._get_control_temp()
        return supervisor_temp

    def get_supervisor_duty(self) -> float:
        if self._supervisor_furnace == -1:
            supervisor_duty = -1
        else:
            #Retrieve _pid_output_model.data of supervisor furnace.
            supervisor_index = self._supervisor_furnace - 1 #Converting indexing from config stye to python style.
            supervisor:TemperatureController = self._all_temp_controllers[supervisor_index]
            supervisor_duty = supervisor.unclamped_pid_output_model.data
            if supervisor_duty is None:
                supervisor_duty = 0
        return supervisor_duty

    def _get_control_temp(self) -> float:
        #Collect recent temps and remove invalid temps.
        recent_temps = [model[-1] for model in self._models if self._control_map[model]]
        if len(recent_temps) > 0:
            recent_temps = [temp for temp in filter(lambda temp:temp!=0.0, recent_temps)] #Remove temps at 0.0 Celsius (disconnected).

            # #Remove temps 20 below other temps.
            # for temp in recent_temps.copy(): 
            #     too_cold = False
            #     for other_temp in recent_temps:
            #         if other_temp - temp >= 20:
            #             too_cold = True
            #     if too_cold:
            #         recent_temps.remove(temp)

            #Find average of valid temps.
            control_temp = statistics.mean(recent_temps) if len(recent_temps) > 0 else None
            return control_temp
        
        else:
            print(0.0)
            return 0.0
    
    def _check_safety(self, control_temp:float | None) -> bool: #TODO: make error count configurable
        #Check for no valid control temp.
        if control_temp is None:
            self.emergency_stop.emit()
            self._safety_model.data = False #Shut off power due to unsafe conditions.
            print('Shutting off power due to invalid control temperature reading.')
            return False

        #If too hot, turn off heating and declare unsafe.
        if control_temp - self._setpoint_model.data > self._safety_range:
            self._high_temp_error_count += 1
            if self._high_temp_error_count >= MAX_SAFETY_FLAGS:
                self.emergency_stop.emit()
                self._safety_model.data = False #Shut off power due to unsafe conditions.
                print('Shutting off power due to overheating.')
                self._high_temp_error_count = 0
                return False
        else:
            self._high_temp_error_count = 0

        #If too cold, turn off heating.
        if self._setpoint_model.data - control_temp > self._safety_range:
            self._low_temp_error_count += 1
            if self._low_temp_error_count >= MAX_SAFETY_FLAGS:
                self.emergency_stop.emit()
                self.under_temp.emit()
                print('Stopping heating due to underheating.')
                self._low_temp_error_count = 0
                return False
        else:
            self._low_temp_error_count = 0
            
        #Check if safety is off.
        if self._safety_model.data is False:
            self.emergency_stop.emit()
            return False
        
        return True #Safe to continue duty cycle.

    def _ramp_setpoint(self, control_temp:float):
        if self._last_ramp_time is not None: #Ramp the setpoint.
            #Get ramprate in C/sec.
            ramp_rate = self._rr_model.data/60.0

            #Catch the set point and set it to the target if it gets within 1.5 step sizes of the target.
            if self._setpoint_model.data != self._target_model.data and abs(self._target_model.data-self._setpoint_model.data) <= ramp_rate*1.5:
                self._setpoint_model.data = self._target_model.data

            #Increment the set point if it's below the target.
            elif self._setpoint_model.data < self._target_model.data:
                self._setpoint_model.data = self._setpoint_model.data + ramp_rate * (time.time() - self._last_ramp_time)

            #Decrement the set point if it's above the target.
            elif self._setpoint_model.data > self._target_model.data:
                #Check that actual temperature is within cooling range before lowering setpoint.
                if control_temp - self._setpoint_model.data <= self._cooling_range:
                    self._setpoint_model.data = self._setpoint_model.data - ramp_rate * (time.time() - self._last_ramp_time)

        self._last_ramp_time = time.time()

    def _run_duty_cycle(self, control_temp:float, supervisor_duty:float):
        """Runs the PID duty cycle.\n
        control_temp - Float value to control the PID cycle.
        supervisor_duty - Float value with duty cycle from supervisor furnace
        """
        try:
            d_cycle = self._pid(control_temp)
            if supervisor_duty != -1:
                d_cycle = d_cycle + supervisor_duty
                d_cycle = clamp(d_cycle,supervisor_duty*self._duty_clamp_min_model.data,supervisor_duty*self._duty_clamp_max_model.data)
            #add bias here
            d_cycle += self._output_bias_model.data
            #save unclamped pid here
            unclamped_d_cycle = d_cycle
            #add clamp here
            d_cycle = clamp(d_cycle, 0.0, self._max_output_model.data) #clamp will be moved outside of this function
            #apply override here
            if self._apply_override_model.data:
                d_cycle = self._output_override_model.data
                unclamped_d_cycle = self._output_override_model.data
            self._pid_output_model.data = d_cycle
            self._unclamped_pid_output_model.data = unclamped_d_cycle
            self._p_output_model.data = self._proportional
            self._i_output_model.data = self._integral
            self._d_output_model.data = self._derivative
            if self._voltage_output_line != -1:
                self._voltage_writer.write(self._voltage_output_line, clamp(int(d_cycle),0,100))
                time.sleep(CYCLE_ITERATION_TIME*ITERATIONS_PER_CYCLE)
        except Exception as e:
            print("Error in DutyCycleWorker for furnace ", self._identifier, ": ",e,sep='')            

    def _cycle_heater(self,d_cycle):
        if self._voltage_output_line != -1:
            if d_cycle > 0 and d_cycle < 100:
                on_time = d_cycle * CYCLE_ITERATION_TIME / 100.0
                off_time = CYCLE_ITERATION_TIME - on_time

                for _ in range(ITERATIONS_PER_CYCLE):
                    self._voltage_writer.write(self._voltage_output_line, True)
                    time.sleep(on_time)

                    self._voltage_writer.write(self._voltage_output_line, False)
                    time.sleep(off_time)

            elif d_cycle >= 100:
                for _ in range(ITERATIONS_PER_CYCLE):
                    self._voltage_writer.write(self._voltage_output_line, True)
                    time.sleep(CYCLE_ITERATION_TIME)

            else:
                for _ in range(ITERATIONS_PER_CYCLE):
                    time.sleep(CYCLE_ITERATION_TIME)
            self._voltage_writer.write(self._voltage_output_line, False) #Always turn off voltage when iteration ends for safety.


    def _pid(self, input:float) -> float:
        #Compute time values.
        now = time.time()
        dt = now - self._last_time if self._last_time is not None else 1e-16
        # print(dt)

        #Compute error and input values.
        error = self._setpoint_model.data - input
        d_error = error - (self._last_error if self._last_error is not None else error)

        #Compute proportional value.
        if self._p_constant_model.data > 0:
            self._proportional = self._p_constant_model.data * error
        else:
            self._proportional = 0.0

        #Compute integral value.
        if (self._i_constant_model.data > 0 and self._last_input is not None)\
                and (not self._integral_crossover_model.data or (input > self._target_model.data) == (self._last_input > self._last_target)): #Check for crossover.
            self._integral += self._i_constant_model.data * error * dt
            self._integral = clamp(self._integral, self._integral_min_model.data, self._integral_max_model.data) #Avoid integral windup.
        else:
            self._integral = 0.0

        #Compute derivative value.
        if self._d_constant_model.data > 0:
            try:
                self._derivative = self._d_constant_model.data * d_error / dt
            except:
                self._derivative = 0.0
        else:
            self._derivative = 0.0

        #Keep track of state
        self._last_input = input
        self._last_error = error
        self._last_time = now
        self._last_target = self._target_model.data

        #Compute final output.
        output = self._proportional + self._integral + self._derivative

        return output
    
    @property
    def is_running(self) -> bool:
        return self._is_running

class TemperatureController(QObject):
    """A controller that handles PID control and other operations from TemperatureView."""
    heating_started = Signal()
    heating_stopped = Signal()
    request_duty_cycle = Signal()
    under_temp = Signal(str)

    def __init__(self, models:list[ListModel[float]], control_map:dict[ListModel[float],bool], voltage_writer:PWMWriter, identifier:int,
                 voltage_line:int, supervisor_furnace:int, safety_model:SinglePointModel[bool],
                 config:dict, all_temp_controllers:ListModel['TemperatureController'], name:str,
                 p:float, i:float, d:float, parent:QObject = None):
        """models - A list of ListModels holding temperature values that will control the PID controller.\n
        control_map - A mapping of temp models that show which ones will control the PID controller.\n
        voltage_line - Voltage output line to be controlled with the duty cycle.\n
        safety_model - SinglePointModel used to determine if heating is safe to start.\n
        config - Dictionary holding data in furnace-config or humidifier-config.\m
        all_temp_controllers - ListModel of all loaded temperature controllers of the same type.\n
        p, i, d - respective PID constants for the duty cycle.
        """
        super().__init__(parent=parent)
        self._models = models
        self._control_map = control_map
        self._voltage_writer = voltage_writer
        self._identifier = identifier
        self._voltage_output_line = voltage_line
        self._supervisor_furnace = supervisor_furnace
        self._safety_model = safety_model
        self._config = config
        self._all_temp_controllers = all_temp_controllers
        self._name = name

        #Initialize models for PID control.
        self._p_model:SinglePointModel[float] = SinglePointModel(p)
        self._i_model:SinglePointModel[float] = SinglePointModel(i)
        self._d_model:SinglePointModel[float] = SinglePointModel(d)
        self._rr_model:SinglePointModel[float] = SinglePointModel(config['ramp-rate'])
        self._max_output_model:SinglePointModel[int] = SinglePointModel(config['max-output'])
        self._integral_max_model:SinglePointModel[float] = SinglePointModel(config['integral-max'])
        self._integral_min_model:SinglePointModel[float] = SinglePointModel(config['integral-min'])
        self._output_bias_model:SinglePointModel[float] = SinglePointModel(config['output-bias'])
        self._output_override_model:SinglePointModel[float] = SinglePointModel(0.0)
        self._apply_override_model:SinglePointModel[bool] = SinglePointModel(False)
        self._integral_crossover_model:SinglePointModel[bool] = SinglePointModel(config['zero-integral-on-crossover'])
        self._duty_clamp_max_model:SinglePointModel[float] = SinglePointModel(1.01)
        self._duty_clamp_min_model:SinglePointModel[float] = SinglePointModel(0.99)
        
        self._target_model:SinglePointModel[float] = SinglePointModel()
        self._setpoint_model:SinglePointModel[float] = SinglePointModel()
        self._pid_output_model:SinglePointModel[float] = SinglePointModel()
        self._unclamped_pid_output_model:SinglePointModel[float] = SinglePointModel()
        self._p_output_model:SinglePointModel[float] = SinglePointModel()
        self._i_output_model:SinglePointModel[float] = SinglePointModel()
        self._d_output_model:SinglePointModel[float] = SinglePointModel()

        #Initialize other variables
        self._heating = False
        self._safety_range = config['temp-safety-range']
        self._cooling_range = config['cooling-wait-range']

        #Initialize threads
        self._duty_cycle_thread = QThread(self)
        self._duty_cycle_worker = DutyCycleWorker(self.setpoint_model, self.target_model,
                                                  self._models, self._control_map, self._safety_model,
                                                  self._safety_range, self._cooling_range,
                                                  self._rr_model,
                                                  self.p_model, self.i_model,
                                                  self.d_model, self.max_output_model,
                                                  self.integral_max_model, self.integral_min_model,
                                                  self.output_bias_model, self.output_override_model, self.apply_override_model,
                                                  self.integral_crossover_model, self.pid_output_model, self.unclamped_pid_output_model,
                                                  self.p_output_model, self.i_output_model,
                                                  self.d_output_model, self._duty_clamp_max_model,
                                                  self._duty_clamp_min_model, self._voltage_writer,
                                                  self._identifier,
                                                  self._voltage_output_line,
                                                  self._supervisor_furnace,
                                                  self._all_temp_controllers)
        self._duty_cycle_worker.moveToThread(self._duty_cycle_thread)
        self._duty_cycle_thread.finished.connect(self._duty_cycle_worker.deleteLater)
        self._duty_cycle_thread.start()

        #Connect signals
        self.heating_started.connect(self._duty_cycle_manager)
        self.request_duty_cycle.connect(self._duty_cycle_worker.prepare_duty_cycle)
        self._duty_cycle_worker.cycle_complete.connect(self._duty_cycle_manager)
        self._duty_cycle_worker.emergency_stop.connect(self.stop_heating)
        self._duty_cycle_worker.under_temp.connect(lambda:self.under_temp.emit(self.name))

    @property
    def p_model(self) -> SinglePointModel[float]:
        return self._p_model
    
    @property
    def i_model(self) -> SinglePointModel[float]:
        return self._i_model
    
    @property
    def d_model(self) -> SinglePointModel[float]:
        return self._d_model
    
    @property
    def rr_model(self) -> SinglePointModel[float]:
        return self._rr_model
    
    @property
    def max_output_model(self) -> SinglePointModel[int]:
        return self._max_output_model
    
    @property
    def integral_max_model(self) -> SinglePointModel[float]:
        return self._integral_max_model
    
    @property
    def integral_min_model(self) -> SinglePointModel[float]:
        return self._integral_min_model
    
    @property
    def output_bias_model(self) -> SinglePointModel[float]:
        return self._output_bias_model
    
    @property
    def output_override_model(self) -> SinglePointModel[float]:
        return self._output_override_model
    
    @property
    def apply_override_model(self) -> SinglePointModel[bool]:
        return self._apply_override_model
    
    @property
    def integral_crossover_model(self) -> SinglePointModel[bool]:
        return self._integral_crossover_model
    
    @property
    def target_model(self) -> SinglePointModel[float]:
        return self._target_model
    
    @property
    def setpoint_model(self) -> SinglePointModel[float]:
        return self._setpoint_model
    
    @property
    def pid_output_model(self) -> SinglePointModel[float]:
        return self._pid_output_model
    
    @property
    def unclamped_pid_output_model(self) -> SinglePointModel[float]:
        return self._unclamped_pid_output_model
    
    @property
    def p_output_model(self) -> SinglePointModel[float]:
        return self._p_output_model
    
    @property
    def i_output_model(self) -> SinglePointModel[float]:
        return self._i_output_model
    
    @property
    def d_output_model(self) -> SinglePointModel[float]:
        return self._d_output_model
    
    @property
    def duty_clamp_max_model(self) -> SinglePointModel[float]:
        return self._duty_clamp_max_model
    
    @property
    def duty_clamp_min_model(self) -> SinglePointModel[float]:
        return self._duty_clamp_min_model
    
    @property
    def heating(self) -> bool:
        return self._heating
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def control_temp(self) -> float:
        #Collect recent temps and remove invalid temps.
        recent_temps = [model[-1] for model in self._models if self._control_map[model]]
        if len(recent_temps) > 0:
            recent_temps = [temp for temp in filter(lambda temp:temp!=0.0, recent_temps)] #Remove temps at 0.0 Celsius (disconnected).

            #Find average of valid temps.
            control_temp = statistics.mean(recent_temps) if len(recent_temps) > 0 else None
            return control_temp
        
        else:
            print(0.0)
            return 0.0
    
    @Slot()
    def start_heating(self):
        """Starts heating the Test Stand to the specified target."""
        if self.target_model.data is not None and self._safety_model.data:
            print('Starting heating on furnace identifier ' + str(self._identifier))
            self._heating = True
            self._setpoint_model.data = None
            self._duty_cycle_worker._last_ramp_time = None
            self.heating_started.emit()            
            if self._supervisor_furnace == -1:
                #if supervisor start any supervisee heaters
                print('there are ' + str(len(self._all_temp_controllers)) + ' furnaces')
                for h in range(len(self._all_temp_controllers)):
                    supervisee:TemperatureController = self._all_temp_controllers[h]
                    print('Furnace identifier ' + str(supervisee._identifier) + ' has a supervisor with identifier ' + str(supervisee._supervisor_furnace))
                    if self._identifier == supervisee._supervisor_furnace:
                        supervisee.target_model.data = self.target_model.data
                        supervisee.start_heating()
                        print('Starting supervisee furnace ' +str(h+1))

    @Slot()
    def stop_heating(self):
        """Stops heating the Test Stand."""
        if type(self._voltage_writer) == PWMWriter and self._voltage_output_line != -1:
            self._voltage_writer.write(self._voltage_output_line, 0)
        self._heating = False
        self._setpoint_model.data = None
        self._duty_cycle_worker._last_ramp_time = None
        self._pid_output_model.data = None
        self._p_output_model.data = None
        self._i_output_model.data = None
        self._d_output_model.data = None
        self.heating_stopped.emit()
        if self._supervisor_furnace == -1:
            #if supervisor stop any supervisee heaters
            for h in range(len(self._all_temp_controllers)):
                supervisee:TemperatureController = self._all_temp_controllers[h]
                if self._identifier == supervisee._supervisor_furnace:
                    supervisee.stop_heating()
                    print('Stoping supervisee furnace ' +str(h+1))
        

    @Slot()
    def _duty_cycle_manager(self):
        if self._heating:
            self.request_duty_cycle.emit()

    def update_all_temp_controllers(self,controllers):
        self._all_temp_controllers = controllers

    def close(self):
        """Quits all threads. Should only be called upon exiting TestSuite."""
        print('closing temperature controller for furnace ' + str(self._identifier))
        self.stop_heating()
        while self._duty_cycle_worker.is_running: #Wait for last duty cycle to finish.
            pass
        self._duty_cycle_thread.quit()
        self._duty_cycle_thread.wait()
        