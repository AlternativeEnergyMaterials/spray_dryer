import os
import socket
import threading
import time
import serial

SOCKET_PATH = '/tmp/pwm.sock'

ITERATIONS = 100
FREQUENCY = 0.01 #seconds

ON = 1
OFF = 0

lock = threading.Lock()

pwm_map:dict[int,int] = {} #[channel:pwm] where pwm is integer between 0 and 100 (percentage of ontime)

def loop():
    serPort = serial.Serial('/dev/ttyACM0',19200,timeout = 1)
    while True:
        lock.acquire()
        current_pwm_map = pwm_map.copy()
        lock.release()
        
        #Turn on all relays/mosfets before pwm loop
        for channel in pwm_map.keys():
            if current_pwm_map[channel] > 0:
                cmd = 'relay on ' +str(channel) + '\n\r'
                serPort.write(cmd.encode())

        #pwm loop to turn off relays after specified time
        for i in range(ITERATIONS+1): #loop from 0 to iterations (inclusive)
            time_passed = i/ITERATIONS * 100
            for channel in current_pwm_map.keys():
                if time_passed > current_pwm_map[channel]: #If percentage of on time has passed
                    cmd = 'relay off ' +str(channel) + '\n\r'
                    serPort.write(cmd.encode())
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