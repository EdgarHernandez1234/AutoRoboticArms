import serial, time
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1.0)
time.sleep(2.0)
payload = 'DRV,90,90,90'
cs = 0
for c in payload: cs ^= ord(c)
ser.write(f'@{payload}*{cs:02X}\n'.encode('ascii'))
print('ACK:', ser.read(1).decode('ascii'))
print('Holding at 90 deg. Keep this running or power on while attaching horns.')
time.sleep(60) # Holds position for 60 seconds
