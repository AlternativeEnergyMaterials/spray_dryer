from PySide6.QtCore import QMutex, QMutexLocker
import fabric
from invoke.exceptions import CommandTimedOut

MAX_TRIES = 10

class SSHClient():
    def __init__(self, hostname: str, username: str, password: str, port: int):
        self._mutex = QMutex()
        self._config = fabric.Config(overrides={'connect_timeout': 60})
        self._conn = fabric.Connection(host=hostname, user=username, port=port, connect_kwargs={'password':password}, config=self._config)

    def exec_command(self, cmd:str):
        with QMutexLocker(self._mutex):
            tries = 0
            success = False
            while not success and tries < MAX_TRIES:
                try:
                    result = self._conn.run(cmd, warn=True, hide='both', timeout=1)
                except OSError as e:
                    self._conn.close()
                    self._conn.open()
                    print('Connection reestablished.')
                except CommandTimedOut as e:
                    print('SSH run timeout, retrying')
                else:
                    success = True
                finally:
                    tries += 1
        if result.stderr != '':
            print(result.stderr)
        return result.stdout

    def close(self):
        with QMutexLocker(self._mutex):
            self._conn.close()