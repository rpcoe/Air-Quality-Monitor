import time
import board
import busio

import adafruit_ens160

#i2c = board.I2C()
i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA

ens = adafruit_ens160.ENS160(i2c)
 
# Reset the sensor mode
print("Setting mode to Standard...")
ens.operation_mode = 2 
time.sleep(1)

while True:
    # Check validity AND the raw status byte if possible
    valid = ens.data_validity
    eco2 = ens.eCO2
    tvoc = ens.TVOC
    
    print(f"Status: {valid} | eCO2: {eco2} | TVOC: {tvoc}")
    
    if eco2 == 0:
        print("Still receiving 0. Attempting mode refresh...")
        ens.operation_mode = 2
        
    time.sleep(2)