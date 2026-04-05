from time import sleep
import os
import busio
import digitalio
import board
import storage
import adafruit_sdcard

from adafruit_bme280 import basic as adafruit_bme280


timeIncrement = 10  # Set the time increment in seconds
ledTime = .01       # time that the led is flashing each cycle

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Create sensor object, using the board's default I2C bus.
#i2c = busio.I2C(board.GP1, board.GP0)  # SCL, SDA
i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA

# address can change based on bme device
# if 0x76 does not work try 0x77 :)
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)

SD_CS = board.GP17
# Connect to the card and mount the filesystem.
spi = busio.SPI(board.GP18, board.GP19, board.GP16)
cs = digitalio.DigitalInOut(SD_CS)
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)
storage.mount(vfs, "/sd")



#  uncomment this section out to start a new index file each run
with open("/sd/indexfile.txt", "w") as writefile:   
    print( 0, file=writefile)
    writefile.close()

with open("/sd/indexfile.txt", "r") as inputfile:
    for line in inputfile:
        i= line
        #print(i)
    inputfile.close
    index = int(i[0]) +1   # Increment index to start a new file
    print("\nindex =",index)
file_name = "/sd/history"+str(index)+".txt"
print("\nfilename:", file_name)

 # start a new index file from 0
 #comment this out to start a new index file saving the data from previous runs
with open("/sd/indexfile.txt", "w") as writefile:       
    print(str(index), file=writefile)
    writefile.close()




with open(file_name, "a") as appendfile:        
    print("                                       NEW DATA", file=appendfile)
    #print("Initial Pressure:  %0.1f hPa" % bme280.pressure, file=appendfile)
    print("TIME ,,   TEMP. ,,  Humidity,,   Pressure,", file=appendfile)
    appendfile.close

time = 0
while True:
    tempF = bme280.temperature * 9 / 5 + 32
    print("\nTemperature: %0.1f F" % tempF)
    print("Humidity: %0.1f %%" % bme280.relative_humidity)
    print("Pressure: %0.1f hPa" % bme280.pressure)

    with open(file_name, "a") as appendfile:        
        print("%4.0f,"% time,"Sec,", "%0.1f,"% tempF, "F,"," %0.1f ," % bme280.relative_humidity, 
              "%,", "%0.1f," % bme280.pressure, "hPa,", file=appendfile)
    appendfile.close

    led.value = True
    sleep(ledTime)
    led.value = False
    
    sleep(timeIncrement-ledTime)
    time += timeIncrement