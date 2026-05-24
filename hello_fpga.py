import serial
import time

s = serial.Serial('/dev/tty.usbserial-0001', 115200, timeout=1)

# Send a message
s.write(b'Hello FPGA\r\n')

# Read the echo back
response = s.read(12)
print("Received:", response)

s.close()