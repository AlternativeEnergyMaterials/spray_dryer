import os
import yaml
import SM16relind
import lib8mosind

OFF = 0

CONFIG_PATH = os.path.join(os.path.expanduser('~'),'config.yaml')

with open(CONFIG_PATH) as file:
    relay_map:dict[int,str] = yaml.safe_load(file)

for mosfet in relay_map['mosfet_addresses']:
    lib8mosind.set_all(mosfet, OFF)
for relay in relay_map['relay_addresses']:
    SM16relind.SM16relind(relay).set_all(OFF)