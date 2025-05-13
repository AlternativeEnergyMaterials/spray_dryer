import sys
from io import StringIO, TextIOWrapper
import os
from datetime import datetime
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from views import MasterView
import multiprocessing
import faulthandler
faulthandler.enable()

OG_STDERR = sys.stderr #Save the original stderr output for when sys.stderr gets overridden.
OG_STDOUT = sys.stdout #Save the original stdout output for when sys.stdout gets overridden.

__icon_path__ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AEMlogo.ico') #Icon path is for pyinstaller file structure.
__version__ = '1.0.0'


class IOCap(StringIO):
    def __init__(self, og_output):
        super().__init__()
        self._output_path = os.path.expanduser('~') + '\\AppData\\Local\\AEM SprayDryer\\logs\\'
        self._og_output:TextIOWrapper = og_output

    def write(self, text:str):
        if not os.path.exists(self._output_path):
            os.makedirs(self._output_path)
        now = datetime.now().replace(second=0, microsecond=0).astimezone()
        with open(self._output_path + str(now).replace(':', '.') + '.txt', 'a') as file:
            file.write(text)
        self._og_output.write(text)

if __name__ == '__main__':
    #Enable multiprocessing in single file application.
    multiprocessing.freeze_support()

    #Save messages in logs folder.
    sys.stderr = IOCap(OG_STDERR)
    sys.stdout = IOCap(OG_STDOUT)

    #Change icon path if running from .py instead of .exe.
    if not getattr(sys, 'frozen', False):
        __icon_path__ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..\\..\\res\\AEMlogo.ico'))

    app = QApplication(sys.argv)
    window = MasterView('AEM Spray Dryer v' + str(__version__), QIcon(__icon_path__))
    window.showMaximized()
    try:
        app.exec()
    except Exception as e:
        print(e)