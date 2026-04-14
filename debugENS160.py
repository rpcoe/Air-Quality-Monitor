""" Debug script for ENS160 sensor - checks if we can get valid readings, and if the sensor is responsive at all.
This is a simplified script that focuses solely on the ENS160 sensor, without any of the other components or logic from the main code.
 It will help us determine if the ENS160 is functioning correctly and providing valid data.
 ENS160 Status/Validity CodesValueMeaningDescription
 0 Normal OperationThe sensor is fully warmed up and providing valid, reliable data.
 1 Warm-up PhaseThe metal oxide heater is active but hasn't reached stable temperature (usually lasts 60 seconds).
 2 Initial Start-upThe sensor is in its "Initial Start-up" sequence (first few minutes of power-on).
 3 Invalid OutputThe sensor is reporting an error or the readings are currently unreliable.
 
 """
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