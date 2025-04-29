import os
import yaml
import SM16relind
import lib8mosind
import socket
import time

SOCKET_PATH = '/tmp/pwm.sock'

OFF = 0

CONFIG_PATH = os.path.join(os.path.expanduser('~'),'config.yaml')

with open(CONFIG_PATH) as file:
    relay_map:dict[int,str] = yaml.safe_load(file)

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
        for mosfet in relay_map['mosfet_addresses']:
            lib8mosind.set_all(mosfet, OFF)
        for relay in relay_map['relay_addresses']:
            SM16relind.SM16relind(relay).set_all(OFF)
        time.sleep(1)
