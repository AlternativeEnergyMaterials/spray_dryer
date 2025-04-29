from devices import PiControlBox

class PWMWriter:
    """A class to write pwm values to the connected output device."""
    def __init__(self, control_box:PiControlBox):
        """control_box - PiControlBox to write to."""
        self._control_box = control_box

    def write(self, line:int, value:int):
        """Write a pwm value to a relay channel.\n
        line - Relay channel to write. Range varies.\n
        value - Value to write. Int between 0 and 100 inclusive.\n
        """
        self._control_box.write_voltage(line, value)