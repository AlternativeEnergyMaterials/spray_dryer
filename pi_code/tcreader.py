import os
import socket
import threading
import sm_tc
import yaml
import time

SOCKET_PATH = '/tmp/tcreader.sock'

CONFIG_PATH = os.path.join(os.path.expanduser('~'),'config.yaml')
with open(CONFIG_PATH) as file:
    config:dict[int,list[int]] = yaml.safe_load(file)

ITERATIONS = 100
FREQUENCY = 0.01 #seconds

smtcs:dict[int,sm_tc.SMtc] = {}
temps:dict[int,list[float]] = {}
for addr in config['smtc_addresses']:
    smtcs[addr] = sm_tc.SMtc(addr)
    temps[addr] = []

lock = threading.Lock()

def loop():
    global temps
    while True:
        buffer_temps = {}
        for addr in config['smtc_addresses']:
            buffer_temps[addr] = []
            for i in range(8):
                buffer_temps[addr].append(smtcs[addr].get_temp(i+1))
        lock.acquire()
        temps = buffer_temps
        lock.release()

def handle_command(cmd:str):
    if 'tcreader' in cmd:
        lock.acquire()
        ret = str(temps)
        lock.release()
        return ret + '\n'
    else:
        return 'Unknown command\n'

def run_server():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_socket.bind(SOCKET_PATH)
    server_socket.listen(1)

    while True:
        conn, _ = server_socket.accept()
        try:
            cmd = conn.recv(1024).decode('utf-8')
            if cmd:
                response = handle_command(cmd)
                conn.sendall(response.encode('utf-8'))
        finally:
            conn.close()

if __name__ == '__main__':
    thread = threading.Thread(target=loop)
    thread.start()
    run_server()