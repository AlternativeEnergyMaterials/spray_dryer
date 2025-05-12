import serial
serPort = serial.Serial('ttyACM0',19200,timeout = 1)
for i in range(8):
    serPort.write('relay off ' +str(i) + '\n\r')
serPort.close()