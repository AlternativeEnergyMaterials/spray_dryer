import os
import socket
import threading
import yaml
import time
import SM16relind
import lib8mosind

SOCKET_PATH = '/tmp/pwm.sock'
CONFIG_PATH = os.path.join(os.path.expanduser('~'),'config.yaml')

ITERATIONS = 100
FREQUENCY = 0.01 #seconds

ON = 1
OFF = 0

lock = threading.Lock()

with open(CONFIG_PATH) as file:
    config:dict[int,list[int]] = yaml.safe_load(file)
pwm_map:dict[int,int] = {} #[channel:pwm] where pwm is integer between 0 and 100 (percentage of ontime)

relay_boards:dict[SM16relind.SM16relind] = {}
for addr in config['relay_addresses']:
    relay_boards[addr] = SM16relind.SM16relind(addr)

def loop():
    while True:
        lock.acquire()
        current_pwm_map = pwm_map.copy()
        lock.release()

        #Turn on all relays/mosfets before pwm loop
        for channel in pwm_map.keys():
            if current_pwm_map[channel] > 0:
                if config[channel][0] == 0:
                    lib8mosind.set(config[channel][1],config[channel][2],ON)
                elif config[channel][0] == 1:
                    relay_boards[config[channel][1]].set(config[channel][2],ON)

        #pwm loop to turn off relays after specified time
        for i in range(ITERATIONS+1): #loop from 0 to iterations (inclusive)
            time_passed = i/ITERATIONS * 100
            for channel in current_pwm_map.keys():
                if time_passed > current_pwm_map[channel]: #If percentage of on time has passed
                    if config[channel][0] == 0:
                        lib8mosind.set(config[channel][1],config[channel][2],OFF)
                    elif config[channel][0] == 1:
                        relay_boards[config[channel][1]].set(config[channel][2],OFF)
            time.sleep(FREQUENCY)

def handle_command(cmd:str):
    if 'pwm' in cmd:
        cmd = cmd.split()
        channels = cmd[1].split(',')
        pwm_vals = cmd[2].split(',')

        lock.acquire()
        for channel, pwm_val in zip(channels,pwm_vals):
            pwm_map[int(channel)] = int(pwm_val)
        lock.release()

def run_server():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_socket.bind(SOCKET_PATH)
    server_socket.listen(1)

    while True:
        conn, _ = server_socket.accept()
        try:
            cmd = conn.recv(1024).decode()
            if cmd:
                handle_command(cmd)
                if thread.is_alive():
                    conn.sendall(b'is_alive')
                else:
                    conn.sendall(b'not_alive')
        finally:
            conn.close()

if __name__ == '__main__':
    thread = threading.Thread(target=loop)
    thread.start()
    run_server()