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
i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA

# address can change based on bme device
# if 0x76 does not work try 0x77 :)
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)

# Connect to the card and mount the filesystem.
spi = busio.SPI(board.GP18, board.GP19, board.GP16)  # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)  # CS pin for SD card
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
    index = int(line.strip()) + 1  # Increment index to start a new file
    print("\nindex =",index)
file_name = "/sd/history"+str(index)+".txt"
print("\nfilename:", file_name)

 # start a new index file from 0
 #comment this out to start a new index file saving the data from previous runs
with open("/sd/indexfile.txt", "w") as writefile:       
    print(str(index), file=writefile)
    writefile.close()



# Open the new history file in append mode ('a')
# We write the header first
with open(file_name, "a") as f:
    f.write("Time(s), Temp(°F), Humidity(%), Pressure(inHg)\n")

print("Logging started. Press Ctrl+C to stop.\n")


total_time = 0
while True:
    try:
        # Flash LED to show activity
        led.value = True
        sleep(ledTime)
        led.value = False

        # Gather data from BME280 
        temp = bme280.temperature* 9 / 5 + 32
        humidity = bme280.relative_humidity
        pressure = bme280.pressure * 0.02953  # Convert hPa to inHg

        # Append data to the SD card file
        with open(file_name, "a") as f:
            data_string = f"{total_time}, {temp:.2f}, {humidity:.2f}, {pressure:.2f}\n"
            f.write(data_string)
            print("Time, Temp(°F), Humidity(%), Pressure(inHg):", data_string.strip())

        # Wait for the next increment
        sleep(timeIncrement - ledTime)
        total_time += timeIncrement

    except OSError as e:
        print("SD card error or sensor unplugged:", e)
        break
