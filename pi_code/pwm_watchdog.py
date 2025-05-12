import serial
import socket
import time

SOCKET_PATH = '/tmp/pwm.sock'

while True:
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        cmd = 'ping'
        client.sendall(cmd.encode('utf-8'))
        response = client.recv(1024).decode('utf-8')
        client.close()
    except:
        response = 'not_alive'

    if 'is_alive' not in response:
        print('shutting off all relays')
        serPort = serial.Serial('ttyACM0',19200,timeout = 1)
        for i in range(8):
            serPort.write('relay off ' +str(i) + '\n\r')
        serPort.close()
        time.sleep(1)
