###############  This program will read the index file and print the lastest data run


import os
import board
import busio as io
import digitalio
import storage
import adafruit_sdcard
#import microcontroller
from time import sleep
# Use any pin that is not taken by SPI
SD_CS = board.GP17

# Connect to the card and mount the filesystem.
spi = io.SPI(board.GP18, board.GP19, board.GP16)
cs = digitalio.DigitalInOut(SD_CS)
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)

storage.mount(vfs, "/sd") 


"""with open("/sd/indexfile.txt", "w") as writefile:        # Uncomment this section to start a new index file from 1
    print(str(1), file=writefile)
    writefile.close()
"""

with open("/sd/indexfile.txt", "r") as inputfile:
    for line in inputfile:
        i= line
        #print(i)
    inputfile.close
    index = int(i[0])
    print("\nindex =",index)
file_name = "/sd/history"+str(index)+".txt"
print("\nfilename:", file_name)

#while True:

with open(file_name, "r") as inputfile:      
    for line in inputfile:
        print(line)
    inputfile.close    

print("stopped")