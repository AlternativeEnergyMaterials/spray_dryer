import serial
serPort = serial.Serial('/dev/ttyACM0',19200,timeout = 1)
for i in range(8):
    cmd = 'relay off ' +str(i+1) + '\n\r'
    serPort.write(cmd.encode())
serPort.close()