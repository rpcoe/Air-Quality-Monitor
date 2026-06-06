import time
import busio

import board

i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA

while not i2c.try_lock():
    pass

print("Press Ctrl-C to exit program")

try:
    while True:
        print(
            "I2C addresses found:",
            [hex(device_address) for device_address in i2c.scan()],
        )
        time.sleep(5)
except KeyboardInterrupt:
    pass

finally:
    i2c.unlock()
